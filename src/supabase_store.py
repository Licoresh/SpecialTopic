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

import requests
import streamlit as st
from .config import ROOT


class SupabaseError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def clear_read_cache():
    st.session_state.pop("supabase_reads", None)
    # Shared saves and explicit refreshes should invalidate per-user derived views too.
    for key in ("_fow_source_cache", "_fow_analysis_cache", "_fow_signature_cache"):
        st.session_state.pop(key, None)


def session_cached(function):
    """Short, per-session cache: never share an authenticated response globally."""
    @wraps(function)
    def wrapped(*args, **kwargs):
        key = (configuration()[0], function.__name__, repr(args), repr(kwargs))
        cache = st.session_state.setdefault("supabase_reads", {})
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
    return _setting("SUPABASE_URL").rstrip("/"), _setting("SUPABASE_PUBLISHABLE_KEY")


def configured() -> bool:
    url, key = configuration()
    # Partial configuration must never silently expose local files without login.
    return bool(url or key)


def _request(method: str, endpoint: str, *, token: str, payload=None, params=None, prefer=None):
    url, key = configuration()
    if not url or not key:
        raise SupabaseError("Supabase is not configured. Add SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY to Streamlit secrets.")
    headers = {"apikey": key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(method, f"{url}{endpoint}", headers=headers, json=payload, params=params, timeout=30)
    except requests.RequestException as exc:
        raise SupabaseError(f"Could not reach Supabase: {exc}") from exc
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
        return None
    try:
        return response.json()
    except ValueError:
        return None


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
    return {"_codec": "gzip-json-v1", "data": base64.b64encode(gzip.compress(encoded)).decode("ascii")}


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
def read_candidates(token: str) -> list[dict]:
    rows = []
    offset = 0
    while True:
        page = _request("GET", "/rest/v1/research_candidates", token=token,
                        params={"select": "phrase,normalized_phrase,source_type,source_id,job_title,company,source_url,original_text,candidate_file",
                                "order": "normalized_phrase.asc,source_type.asc,source_id.asc",
                                "limit": "1000", "offset": str(offset)})
        rows.extend(page or [])
        if not page or len(page) < 1000:
            return rows
        offset += 1000


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
                    prefer=f"resolution={'ignore' if preserve_existing else 'merge'}-duplicates,return=minimal")
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
    token = str(st.session_state.get("supabase_access_token", ""))
    if not token:
        return ""
    if time.time() < float(st.session_state.get("supabase_expires_at", 0)):
        return token
    refresh = str(st.session_state.get("supabase_refresh_token", ""))
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
    st.session_state["supabase_access_token"] = session["access_token"]
    st.session_state["supabase_refresh_token"] = session["refresh_token"]
    st.session_state["supabase_expires_at"] = time.time() + int(session.get("expires_in", 3600)) - 60
    return str(session["access_token"])


def sign_out():
    # Also remove review drafts and cached research data before another login.
    for key in list(st.session_state):
        del st.session_state[key]
