import json
import os
from pathlib import Path
import time
import uuid
import pandas as pd
from .config import ROOT, DEFAULTS
from .utils import digest, timestamp


MODEL_TABLES = {"model_metrics", "training_snapshot"}
MODEL_JSON = {"selected_model", "training_details"}


def _shared_key(kind, name, writing=False):
    """Publish evaluation bundles by switching metadata only after all writes succeed."""
    from . import supabase_store as backend
    if not (name in MODEL_TABLES or name.startswith("evaluation_") or name in MODEL_JSON):
        return f"{kind}:{name}"
    run_id = backend.st.session_state.get("training_run_id") if writing else None
    if not writing:
        metadata = backend.read_state("json:model_metadata", backend.get_token()) or {}
        run_id = metadata.get("shared_run_id")
    return f"{kind}:modelrun:{run_id}:{name}" if run_id else f"{kind}:{name}"


def _remote_payload(kind, name):
    from .supabase_store import configured, get_token, read_state, SupabaseError
    if not configured():
        return None
    token = get_token()
    if not token:
        raise SupabaseError("Sign in to read the shared research workspace.")
    return read_state(_shared_key(kind, name), token)


def _remote_write(kind, name, payload):
    from .supabase_store import configured, get_token, write_state
    if not configured():
        return
    token = get_token()
    if not token:
        raise RuntimeError("Sign in to the shared Supabase workspace before saving research data.")
    write_state(_shared_key(kind, name, writing=True), payload, token)

def initialize():
    for name in ("data/raw", "data/processed", "data/feedback", "data/templates", "models", "outputs/charts", "outputs/tables", "outputs/reports"):
        (ROOT / name).mkdir(parents=True, exist_ok=True)

def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A unique sibling avoids collisions when Streamlit reruns overlap and keeps
    # the final replace on the same volume. OneDrive/antivirus can briefly hold
    # the destination on Windows, so retry transient replace failures.
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_bytes(content)
    delays = (0.1, 0.2, 0.4, 0.8, 1.6)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(temporary, path)
            return
        except PermissionError as exc:
            if attempt == len(delays):
                # Preserve the complete staged file so a later retry or manual
                # recovery can recover the result rather than silently losing it.
                raise PermissionError(
                    f"Windows could not replace {path.name}; it may be temporarily locked by OneDrive, Excel, or antivirus. "
                    f"Close anything using the file and retry. The complete new result is preserved at {temporary}."
                ) from exc
            time.sleep(delays[attempt])
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

def save_frame(name, frame):
    # Keep the local CSV as a recoverable backup while the authenticated
    # Supabase row becomes the shared source of truth for the deployed team.
    clean = frame.fillna("").astype(str)
    if name == "team_training_candidates":
        from .supabase_store import configured, get_token, upsert_candidates
        if configured():
            token = get_token()
            if not token:
                raise RuntimeError("Sign in to the shared Supabase workspace before saving candidate data.")
            upsert_candidates(clean.to_dict(orient="records"), token)
        atomic_bytes(ROOT / "data/processed" / f"{name}.csv", clean.to_csv(index=False).encode("utf-8-sig"))
        return
    if name == "labeled_competencies":
        from .supabase_store import configured, get_token, upsert_annotations
        if configured():
            token = get_token()
            if not token:
                raise RuntimeError("Sign in to the shared Supabase workspace before saving research data.")
            upsert_annotations(clean.to_dict(orient="records"), token)
    else:
        _remote_write("frame", name, {"columns": list(clean.columns), "records": clean.to_dict(orient="records")})
    if name == "labeled_competencies":
        from .training_sources import resolve_training_file
        path = resolve_training_file(ROOT)
        if path.suffix.lower() != ".csv":
            raise ValueError("The editable training dataset must be a CSV file in ./train.")
        atomic_bytes(path, clean.to_csv(index=False).encode("utf-8-sig"))
        return
    atomic_bytes(ROOT / "data/processed" / f"{name}.csv", clean.to_csv(index=False).encode("utf-8-sig"))

def read_frame(name):
    from .supabase_store import configured, get_token, SupabaseError
    if configured() and not get_token():
        raise SupabaseError("Sign in to read the shared research workspace.")
    if name == "psf_mapping_reviews" and configured():
        from .supabase_store import read_mapping_reviews
        from .psf_reviews import REVIEW_COLUMNS
        return pd.DataFrame(read_mapping_reviews(get_token()), columns=REVIEW_COLUMNS, dtype=str).fillna("")
    if name == "team_training_candidates":
        from .supabase_store import configured, get_token, read_candidates
        if configured() and get_token():
            return pd.DataFrame(read_candidates(get_token()), dtype=str).fillna("")
    if name == "labeled_competencies":
        from .supabase_store import configured, get_token, read_annotations
        if configured() and get_token():
            from .training_sources import ANNOTATION_COLUMNS
            return pd.DataFrame(read_annotations(get_token()), columns=ANNOTATION_COLUMNS + ["version"], dtype=str).fillna("")
    payload = _remote_payload("frame", name)
    if payload is not None:
        return pd.DataFrame(payload.get("records", []), columns=payload.get("columns", []), dtype=str).fillna("")
    if configured():
        return pd.DataFrame()
    if name == "labeled_competencies":
        from .training_sources import read_annotations
        return read_annotations(ROOT)
    path = ROOT / "data/processed" / f"{name}.csv"
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

def save_json(name, value):
    shared_value = value
    if name == "uploads":
        # Local paths are machine-specific and can disclose usernames. The
        # filename/hash pair is sufficient to resolve each file on a host.
        shared_value = {
            kind: {key: item for key, item in entry.items() if key != "path"}
            for kind, entry in value.items()
        }
    _remote_write("json", name, shared_value)
    atomic_bytes(ROOT / "data/processed" / f"{name}.json", json.dumps(value, indent=2, default=str).encode())

def read_json(name, default=None):
    payload = _remote_payload("json", name)
    if payload is not None:
        return payload
    from .supabase_store import configured
    if configured():
        return default
    path = ROOT / "data/processed" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def seed_shared_workspace():
    """Copy local processed tables into empty shared slots; never overwrite cloud data."""
    from .supabase_store import configured, get_token, read_state, write_state
    if not configured() or not get_token():
        raise RuntimeError("Sign in to a configured Supabase workspace before copying local data.")
    seeded, skipped = [], []
    folder = ROOT / "data/processed"
    for path in sorted(folder.glob("*.csv")):
        name = path.stem
        if name in {"psf_mapping_reviews", "labeled_competencies", "shared_labeled_competencies", "training_snapshot", "team_training_candidates", "model_metrics", "pretrained_label_suggestions"} or name.startswith("evaluation_"):
            continue
        key = f"frame:{name}"
        if read_state(key, get_token()) is not None:
            skipped.append(name)
            continue
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False)
        except pd.errors.EmptyDataError:
            frame = pd.DataFrame()
        frame = frame.fillna("").astype(str)
        write_state(key, {"columns": list(frame.columns), "records": frame.to_dict(orient="records")}, get_token(), preserve_existing=True)
        seeded.append(name)
    for path in sorted(folder.glob("*.json")):
        name = path.stem
        if name in {"selected_model", "model_metadata", "training_details", "training_source"}:
            continue
        key = f"json:{name}"
        if read_state(key, get_token()) is not None:
            skipped.append(name)
            continue
        write_state(key, json.loads(path.read_text(encoding="utf-8")), get_token(), preserve_existing=True)
        seeded.append(name)
    # The canonical manual-label file may live under ./train instead.
    # Legacy CSV labels need deliberate review in the signed-in team workspace.
    # Copying source data must never attest that the copying user reviewed them.
    skipped.append("local annotations (review them in the shared review table)")
    from .supabase_store import read_candidates, upsert_candidates
    if not read_candidates(get_token()):
        try:
            from .training_sources import training_candidates
            candidates = training_candidates(ROOT)
            if not candidates.empty:
                upsert_candidates(candidates.fillna("").astype(str).to_dict(orient="records"), get_token(), preserve_existing=True)
                seeded.append("team_training_candidates")
        except (OSError, ValueError):
            pass
    return seeded, skipped

def settings():
    return DEFAULTS | read_json("settings", {})

def archive_raw(content, filename, kind):
    file_hash = digest(content)
    path = ROOT / "data/raw" / f"{kind}_{file_hash}{Path(filename).suffix.lower()}"
    if not path.exists():
        atomic_bytes(path, content)
    manifest = read_json("uploads", {})
    manifest[kind] = {"hash": file_hash, "filename": Path(filename).name, "path": str(path), "timestamp": timestamp()}
    save_json("uploads", manifest)
    return file_hash


def raw_upload_path(entry, kind):
    """Resolve portable uploads without trusting database-provided absolute paths."""
    folder = (ROOT / "data/raw").resolve()
    source_hash = str(entry.get("hash", ""))
    if not source_hash or any(char not in "0123456789abcdef" for char in source_hash.lower()):
        raise ValueError("The upload source hash is invalid. Upload the original source again.")
    if kind not in {"jobs", "psf_aai", "stakeholder"}:
        raise ValueError("Unknown upload type.")
    path = (folder / f"{kind}_{source_hash}{Path(entry.get('filename', '')).suffix.lower()}").resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        raise ValueError("This host does not have the original upload. Restore the data/raw folder on this server or upload the original file again. Shared processed data is still available.")
    return path
