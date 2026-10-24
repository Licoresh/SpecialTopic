"""Small authenticated JSON store for the shared Streamlit workspace.

The app uses a Supabase publishable key plus each researcher's Auth access
token. No elevated database key is sent to this module or exposed to users.
"""

from __future__ import annotations

import os
import time
import copy
import base64
import gzip
import io
import json
from pathlib import Path
from functools import wraps
from contextlib import contextmanager
from contextvars import ContextVar

import requests
import streamlit as st
from .config import ROOT

_worker_state = ContextVar("research_worker_state", default=None)


def session_state():
    """Workers own their auth and caches; only the UI reads Streamlit state."""
    state = _worker_state.get()
    return state if state is not None else st.session_state


def worker_credentials():
    token = get_token()
    if configured() and not token:
        raise SupabaseError("Sign in before starting processing.")
    return {"_configuration": configuration(), "supabase_access_token": token,
            "supabase_expires_at": session_state().get("supabase_expires_at", 0)}


@contextmanager
def worker_session(credentials):
    state = dict(credentials)
    reset = _worker_state.set(state)
    try:
        yield
    finally:
        connection = state.get("_supabase_http")
        if connection:
            connection[1].close()
        state.clear()
        _worker_state.reset(reset)


class SupabaseError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def clear_read_cache(*, frames=False):
    session_state().pop("supabase_reads", None)
    # Shared saves and explicit refreshes should invalidate per-user derived views too.
    for key in ("_fow_source_cache", "_fow_analysis_cache", "_fow_signature_cache", "_manual_review_queue"):
        session_state().pop(key, None)
    # Decoded generations remain valid after annotation saves. Every frame read
    # still checks its manifest/file revision; logout removes the entire session.
    if frames:
        session_state().pop("_fow_frame_cache", None)


def _http_session():
    """Reuse this user's HTTPS connections without putting credentials in defaults."""
    url = configuration()[0]
    saved = session_state().get("_supabase_http")
    if saved is None or saved[0] != url:
        if saved is not None:
            saved[1].close()
        saved = (url, requests.Session())
        session_state()["_supabase_http"] = saved
    return saved[1]


def session_cached(function):
    """Short, per-session cache: never share an authenticated response globally."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        key = (configuration()[0], function.__name__, repr(args), repr(kwargs))
        cache = session_state().setdefault("supabase_reads", {})
        entry = cache.get(key)
        if entry and time.monotonic() - entry[0] < 15:
            return copy.deepcopy(entry[1])
        result = function(*args, **kwargs)
        if len(cache) >= 64:
            cache.clear()
        cache[key] = (time.monotonic(), copy.deepcopy(result))
        return result
    return wrapped


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE entries without overriding process environment."""
    values = {}
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key.strip()] = value
    return values


def _setting(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value.strip()
    value = _read_dotenv(ROOT / ".env").get(name, "")
    if value:
        return value.strip()
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value).strip()


def configuration() -> tuple[str, str]:
    worker = _worker_state.get()
    if worker is not None:
        return worker["_configuration"]
    return _setting("SUPABASE_URL").rstrip("/"), _setting("SUPABASE_PUBLISHABLE_KEY")


def configured() -> bool:
    url, key = configuration()
    # Partial configuration must never silently expose local files without login.
    return bool(url or key)


def _request(method: str, endpoint: str, *, token: str, payload=None, params=None, prefer=None, retry_safe=False):
    url, key = configuration()
    if not url or not key:
        raise SupabaseError("Supabase is not configured. Add SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY to Streamlit secrets.")
    headers = {"apikey": key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    attempts = 3 if method == "GET" or retry_safe else 1
    from .background_tasks import checkpoint, report
    for attempt in range(attempts):
        checkpoint()
        try:
            response = _http_session().request(method, f"{url}{endpoint}", headers=headers,
                                               json=payload, params=params, timeout=(10, 30))
        except requests.exceptions.SSLError as exc:
            raise SupabaseError("Could not verify the secure Supabase connection. Check this computer's certificates and network.") from exc
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as exc:
            if attempt + 1 == attempts:
                raise SupabaseError(f"Supabase connection interrupted after {attempts} attempt(s). Check the internet connection and retry. This operation could not be confirmed.") from exc
        except requests.RequestException as exc:
            raise SupabaseError("Could not reach Supabase. Check the internet connection and retry.") from exc
        else:
            if response.status_code not in {502, 503, 504} or attempt + 1 == attempts:
                break
            response.close()
        saved = session_state().pop("_supabase_http", None)
        if saved is not None:
            saved[1].close()
        report(f"Connection interrupted · retrying Supabase ({attempt + 2}/{attempts})…")
        time.sleep(.5 * (attempt + 1))
    if not response.ok:
        try:
            detail = response.json().get("message") or response.json().get("msg") or response.text
        except (ValueError, AttributeError):
            detail = response.text
        if response.status_code == 404 and "schema cache" in str(detail):
            raise SupabaseError(
                "The shared database setup is incomplete. Ask the project owner to apply the Supabase migrations, then retry.",
                status_code=response.status_code,
            )
        if response.status_code == 401:
            raise SupabaseError(
                "Your session has expired. Sign in again, then retry.",
                status_code=response.status_code,
            )
        if response.status_code == 403:
            raise SupabaseError(
                "Supabase denied this operation. Your sign-in may be valid; ask the project owner to check your team role and database permissions.",
                status_code=response.status_code,
            )
        raise SupabaseError(f"Supabase returned HTTP {response.status_code}: {detail}", status_code=response.status_code)
    if not response.content:
        if method == "GET":
            raise SupabaseError("Supabase returned an empty response body. Retry the read; no empty dataset has been assumed.")
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise SupabaseError("Supabase returned an unreadable response. Retry the operation; no empty dataset has been assumed.") from exc


def sign_in(email: str, password: str) -> dict:
    url, key = configuration()
    if not url or not key:
        raise SupabaseError("Supabase is not configured. Add SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY to Streamlit secrets.")
    try:
        response = requests.post(
            f"{url}/auth/v1/token?grant_type=password",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"email": email.strip(), "password": password}, timeout=30,
        )
    except requests.RequestException as exc:
        raise SupabaseError(f"Could not reach Supabase Auth: {exc}") from exc
    if not response.ok:
        try:
            detail = response.json().get("msg") or response.json().get("message") or "Check the email and password."
        except ValueError:
            detail = "Check the email and password."
        raise SupabaseError(f"Sign-in failed: {detail}")
    result = response.json()
    if not result.get("access_token") or not result.get("user", {}).get("id"):
        raise SupabaseError("Supabase Auth did not return a valid user session.")
    return result


@session_cached
def state_version(name: str, token: str):
    rows = _request("GET", "/rest/v1/app_state", token=token,
                    params={"name": f"eq.{name}", "select": "updated_at", "limit": "1"})
    return rows[0]["updated_at"] if rows else None


@session_cached
def read_state(name: str, token: str):
    result = _request("GET", "/rest/v1/app_state", token=token,
                      params={"name": f"eq.{name}", "select": "payload", "limit": "1"})
    return unpack_state(result[0]["payload"]) if result else None


def read_states(names: list[str], token: str) -> dict:
    """Read several chunk rows per request without retaining a second large cache."""
    found = {}
    for start in range(0, len(names), 25):
        batch = names[start:start + 25]
        values = ",".join('"' + name.replace('"', '\\"') + '"' for name in batch)
        rows = _request("GET", "/rest/v1/app_state", token=token,
                        params={"name": f"in.({values})", "select": "name,payload"}) or []
        found.update({row["name"]: unpack_state(row["payload"]) for row in rows})
    return found


def pack_state(payload):
    """Compress repeated source text in larger tables to reduce network transfer."""
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(encoded) < 128 * 1024:
        return payload
    return {"_codec": "gzip-json-v1", "data": base64.b64encode(gzip.compress(encoded, compresslevel=6)).decode("ascii")}


def unpack_state(payload):
    if isinstance(payload, dict) and payload.get("_codec") == "gzip-json-v1":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(payload["data"], validate=True))) as source:
                content = source.read(256 * 1024 * 1024 + 1)
            if len(content) > 256 * 1024 * 1024:
                raise ValueError("This older shared snapshot exceeds the decoded-size limit. Update the app, then rerun Competency Extraction to replace it with the compact chunked format.")
            return json.loads(content)
        except (ValueError, KeyError, OSError) as exc:
            raise SupabaseError(f"Could not read this shared table: {exc}") from exc
    return payload


@session_cached
def read_annotations(token: str) -> list[dict]:
    return _request("POST", "/rest/v1/rpc/annotation_snapshot", token=token, payload={}) or []


def save_reviewed_annotations(records, token, expected_versions, resolutions=None):
    result = _request("POST", "/rest/v1/rpc/save_reviewed_annotations", token=token,
                      payload={"rows": records, "expected_versions": expected_versions, "resolutions": resolutions or {}})
    clear_read_cache()
    return result


@session_cached
def read_mapping_reviews(token):
    rows, offset = [], 0
    while True:
        page = _request("GET", "/rest/v1/psf_mapping_reviews", token=token,
                        params={"select": "records,version", "order": "extraction_id.asc",
                                "limit": "1000", "offset": str(offset)}) or []
        for decision in page:
            rows.extend(row | {"version": str(decision["version"])} for row in decision["records"])
        if len(page) < 1000:
            return rows
        offset += 1000


def save_mapping_review(records, expected_version, token):
    result = _request("POST", "/rest/v1/rpc/save_psf_mapping_review", token=token,
                      payload={"rows": records, "expected_version": expected_version})
    clear_read_cache()
    return result


def upsert_annotations(records: list[dict], token: str, *, preserve_existing: bool = False):
    raise SupabaseError("Use the review table to save annotations. Bulk uploads cannot become verified research labels automatically.")


@session_cached
def read_candidates(token: str, *, include_source_text=True) -> list[dict]:
    rows = []
    offset = 0
    fields = "phrase,normalized_phrase,source_type,source_id,job_title,company,source_url,candidate_file"
    if include_source_text:
        fields += ",original_text"
    while True:
        page = _request("GET", "/rest/v1/research_candidates", token=token,
                        params={"select": fields,
                                "order": "normalized_phrase.asc,source_type.asc,source_id.asc",
                                "limit": "1000", "offset": str(offset)})
        rows.extend(page or [])
        if not page or len(page) < 1000:
            return rows
        offset += 1000


@session_cached
def candidate_contexts(token, keys):
    """Fetch exact occurrence evidence only for the small displayed review batch."""
    found = {}
    fields = ("normalized_phrase", "source_type", "source_id")
    for start in range(0, len(keys), 10):
        batch = keys[start:start + 10]
        filters = [
            "and(" + ",".join(f"{field}.eq.{json.dumps(str(value), ensure_ascii=False)}"
                             for field, value in zip(fields, key)) + ")"
            for key in batch
        ]
        rows = _request("GET", "/rest/v1/research_candidates", token=token, params={
            "select": ",".join(fields) + ",original_text",
            "or": "(" + ",".join(filters) + ")", "limit": str(len(batch)),
        }) or []
        for row in rows:
            found[tuple(row[field] for field in fields)] = row.get("original_text", "")
    return found


@session_cached
def read_annotation_history(token: str) -> list[dict]:
    rows, offset = [], 0
    while True:
        page = _request("GET", "/rest/v1/annotation_audit", token=token,
                        params={"select": "old_row,new_row", "order": "id.asc", "limit": "1000", "offset": str(offset)}) or []
        for event in page:
            rows.extend(row for row in (event.get("old_row"), event.get("new_row")) if row)
        if len(page) < 1000:
            return rows
        offset += 1000


def upsert_candidates(records: list[dict], token: str, *, preserve_existing: bool = False):
    if not records:
        return
    fields = ("phrase", "normalized_phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text", "candidate_file")
    clean = [{field: str(record.get(field, "") or "") for field in fields} for record in records]
    prefer = "resolution=ignore-duplicates,return=minimal" if preserve_existing else "resolution=merge-duplicates,return=minimal"
    for start in range(0, len(clean), 250):
        _request("POST", "/rest/v1/research_candidates", token=token,
                 payload=clean[start:start + 250],
                 params={"on_conflict": "normalized_phrase,source_type,source_id"},
                 prefer=prefer)
    clear_read_cache()


@session_cached
def check_connection(token: str):
    role = _request("POST", "/rest/v1/rpc/workspace_role", token=token, payload={})
    if role not in {"admin", "reviewer"}:
        raise SupabaseError("Your account has no active research-team membership. Ask the project owner to add it to research_members.")
    _request("GET", "/rest/v1/app_state", token=token,
             params={"select": "name", "limit": "1"})
    return role


def is_admin():
    return not configured() or (bool(get_token()) and check_connection(get_token()) == "admin")


def write_state(name: str, payload, token: str, *, preserve_existing=False):
    result = _request("POST", "/rest/v1/app_state", token=token,
                    payload={"name": name, "payload": pack_state(payload)},
                    prefer=f"resolution={'ignore' if preserve_existing else 'merge'}-duplicates,return=minimal",
                    retry_safe=True)
    clear_read_cache()
    return result


def clear_generated_extractions(token: str):
    """Clear only generated extraction snapshots through the admin-checked RPC."""
    try:
        _request("POST", "/rest/v1/rpc/clear_generated_extractions", token=token, payload={})
    except SupabaseError as exc:
        if exc.status_code == 404:
            raise SupabaseError(
                "The shared database is missing the extraction-cleanup migration. Apply "
                "supabase/migrations/20261020143000_admin_clear_generated_extractions.sql in Supabase SQL Editor, then retry."
            ) from exc
        raise
    clear_read_cache()


def get_token() -> str:
    token = str(session_state().get("supabase_access_token", ""))
    if not token:
        return ""
    if time.time() < float(session_state().get("supabase_expires_at", 0)):
        return token
    if _worker_state.get() is not None:
        raise SupabaseError("Processing paused because its sign-in expired. Sign in again and retry; saved drafts are retained.")
    refresh = str(session_state().get("supabase_refresh_token", ""))
    url, key = configuration()
    if not refresh or not url or not key:
        sign_out()
        return ""
    try:
        response = requests.post(
            f"{url}/auth/v1/token?grant_type=refresh_token",
            headers={"apikey": key, "Content-Type": "application/json"},
            json={"refresh_token": refresh}, timeout=30,
        )
        response.raise_for_status()
        session = response.json()
        if not session.get("access_token") or not session.get("refresh_token"):
            raise ValueError("Invalid refresh response")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (400, 401, 403):
            sign_out()
            return ""
        raise SupabaseError("Session refresh is temporarily unavailable. Retry; unsaved work is retained.") from exc
    except (requests.RequestException, ValueError) as exc:
        raise SupabaseError("Could not refresh the session. Retry the connection; unsaved work is retained.") from exc
    session_state()["supabase_access_token"] = session["access_token"]
    session_state()["supabase_refresh_token"] = session["refresh_token"]
    session_state()["supabase_expires_at"] = time.time() + int(session.get("expires_in", 3600)) - 60
    return str(session["access_token"])


def sign_out():
    job = session_state().get("_background_job")
    if job is not None:
        job.cancel()
    connection = session_state().get("_supabase_http")
    if connection:
        connection[1].close()
    # Also remove review drafts and cached research data before another login.
    for key in list(session_state()):
        del session_state()[key]
