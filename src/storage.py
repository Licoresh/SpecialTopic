import gzip
import json
import os
from pathlib import Path
import shutil
import time
import uuid
import pandas as pd
from .config import ROOT, DEFAULTS
from .utils import digest, timestamp


MODEL_TABLES = {"model_metrics", "training_snapshot"}
MODEL_JSON = {"selected_model", "training_details"}
REMOTE_FRAME_CHUNK_BYTES = 4 * 1024 * 1024
EXTRACTION_REVIEW_COLUMNS = "extraction_id original_phrase normalized_phrase source_type source_id competency_category human_label model_prediction accepted psf_competency matching_method confidence_score".split()


def _cached_frame(key, revision, loader, columns=None, source_ids=None):
    """Keep decoded frames within this session; callers receive independent cells."""
    from .supabase_store import session_state
    cache = session_state().setdefault("_fow_frame_cache", {})
    entry = cache.get(key)
    if entry is None or entry[0] != revision:
        frame = loader()
        cache.pop(key, None)
        cache[key] = (revision, frame)
        while len(cache) > 4:
            cache.pop(next(iter(cache)))
    else:
        frame = entry[1]
    if source_ids is not None and not frame.empty:
        frame = frame[frame.source_id.isin(source_ids)]
    if columns is not None:
        frame = frame.loc[:, [column for column in columns if column in frame]]
    return frame.copy(deep=True)


def frame_revision(name):
    """Cheap version check, including extraction reruns with identical inputs."""
    from . import supabase_store as backend
    if backend.configured():
        token = backend.get_token()
        if not token:
            raise backend.SupabaseError("Sign in to read the shared research workspace.")
        return backend.state_version(_shared_key("frame", name), token)
    path = ROOT / "data/processed" / f"{name}.csv"
    if not path.is_file():
        return None
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def _shared_key(kind, name, writing=False):
    """Publish evaluation bundles by switching metadata only after all writes succeed."""
    from . import supabase_store as backend
    if not (name in MODEL_TABLES or name.startswith("evaluation_") or name in MODEL_JSON):
        return f"{kind}:{name}"
    run_id = backend.session_state().get("training_run_id") if writing else None
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


def _remote_payloads(kind, names):
    from .supabase_store import configured, get_token, read_states
    if not configured():
        return {}
    token = get_token()
    if not token:
        raise RuntimeError("Sign in to read the shared research workspace.")
    keys = {name: _shared_key(kind, name) for name in names}
    values = read_states(list(keys.values()), token)
    return {name: values[key] for name, key in keys.items() if key in values}


def _remote_write(kind, name, payload):
    from .supabase_store import configured, get_token, write_state
    if not configured():
        return
    token = get_token()
    if not token:
        raise RuntimeError("Sign in to the shared Supabase workspace before saving research data.")
    write_state(_shared_key(kind, name, writing=True), payload, token)


def _frame_chunks(columns, records, max_bytes=None):
    """Split records by encoded size so no app_state payload needs huge decoding."""
    max_bytes = max_bytes or REMOTE_FRAME_CHUNK_BYTES
    chunks, current, size = [], [], 32
    for record in records:
        record_size = len(json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1
        if record_size + 32 > max_bytes:
            raise ValueError("A single shared row exceeds the storage chunk size; shorten its text or split the source record.")
        if current and size + record_size > max_bytes:
            chunks.append(current)
            current, size = [], 32
        current.append(record)
        size += record_size
    if current:
        chunks.append(current)
    return chunks


def _save_remote_frame(name, frame):
    from .supabase_store import configured
    from .background_tasks import report
    if not configured():
        return
    shared = frame
    elided = []
    if name == "extractions_original" and "original_text" in frame:
        # Job text is already stored once per source in cleaned_jobs. Keeping it
        # on every extracted phrase multiplies the largest payload needlessly.
        shared = frame.copy()
        shared["original_text"] = ""
        elided = ["original_text"]
    columns = list(shared.columns)
    records = shared.to_dict(orient="records")
    payload = {"columns": columns, "records": records, "_elided_columns": elided}
    encoded_size = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if encoded_size <= REMOTE_FRAME_CHUNK_BYTES:
        _remote_write("frame", name, payload)
        return
    generation = uuid.uuid4().hex
    chunks = _frame_chunks(columns, records)
    for index, chunk in enumerate(chunks):
        report(f"Saving {name} · batch {index + 1} of {len(chunks)}")
        _remote_write("frame", f"{name}:chunk:{generation}:{index}", {"records": chunk})
    review_projection = None
    if name == "extractions_original":
        review = shared.loc[:, [column for column in EXTRACTION_REVIEW_COLUMNS if column in shared]]
        review_chunks = _frame_chunks(list(review.columns), review.to_dict(orient="records"))
        for index, chunk in enumerate(review_chunks):
            report(f"Saving review index · batch {index + 1} of {len(review_chunks)}")
            _remote_write("frame", f"{name}:chunk:review:{generation}:{index}", {"records": chunk})
        review_projection = {"_storage_codec": "frame-chunks-v1", "generation": generation,
                             "chunk_count": len(review_chunks), "record_count": len(review),
                             "columns": list(review.columns), "chunk_prefix": f"{name}:chunk:review"}
    # Publish only after every chunk is durable; interrupted writes leave the
    # previous snapshot readable.
    report(f"Publishing completed {name} snapshot…")
    _remote_write("frame", name, {"_storage_codec": "frame-chunks-v1", "generation": generation,
                                  "chunk_count": len(chunks), "record_count": len(records),
                                  "columns": columns, "elided_columns": elided,
                                  "review_projection": review_projection,
                                  "chunk_sources": [sorted({str(row.get("source_id", "")) for row in chunk}) for chunk in chunks]
                                      if name == "extractions_original" else None,
                                  "source_counts": shared.source_id.astype(str).value_counts().to_dict()
                                      if name == "extractions_original" and "source_id" in shared else None})


def _read_remote_frame(name, payload, source_ids=None):
    if not isinstance(payload, dict) or payload.get("_storage_codec") != "frame-chunks-v1":
        return payload
    generation = payload.get("generation", "")
    count = int(payload.get("chunk_count", 0))
    indices = list(range(count))
    source_counts = payload.get("source_counts")
    partitions = payload.get("chunk_sources")
    if source_ids is not None and source_counts is not None and partitions is not None and len(partitions) == count:
        indices = [index for index in indices if set(partitions[index]).intersection(source_ids)]
    prefix = payload.get("chunk_prefix", f"{name}:chunk")
    names = [f"{prefix}:{generation}:{index}" for index in indices]
    chunks = _remote_payloads("frame", names)
    records = []
    for index, chunk_name in enumerate(names):
        chunk = chunks.get(chunk_name)
        if not isinstance(chunk, dict) or not isinstance(chunk.get("records"), list):
            raise ValueError(f"Shared table {name} is missing chunk {index + 1} of {count}; ask an admin to retry the last save.")
        records.extend(chunk["records"])
    if len(indices) == count and len(records) != int(payload.get("record_count", -1)):
        raise ValueError(f"Shared table {name} is incomplete; ask an admin to retry the last save.")
    if source_ids is not None:
        records = [row for row in records if str(row.get("source_id", "")) in source_ids]
        if source_counts is not None and len(records) != sum(source_counts.get(source, 0) for source in source_ids):
            raise ValueError(f"Shared table {name} has incomplete source evidence; retry the last save.")
    return {"columns": payload.get("columns", []), "records": records,
            "_elided_columns": payload.get("elided_columns", [])}


def _bundled_psf_default():
    path = ROOT / "data/reference/psf_aai_default.csv"
    if not path.is_file():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.attrs["reference_source"] = "bundled_default"
    return frame


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
        _save_remote_frame(name, clean)
    if name == "labeled_competencies":
        from .training_sources import resolve_training_file
        path = resolve_training_file(ROOT)
        if path.suffix.lower() != ".csv":
            raise ValueError("The editable training dataset must be a CSV file in ./train.")
        atomic_bytes(path, clean.to_csv(index=False).encode("utf-8-sig"))
        return
    atomic_bytes(ROOT / "data/processed" / f"{name}.csv", clean.to_csv(index=False).encode("utf-8-sig"))


def clear_extraction_data():
    """Archive and clear generated extraction outputs, preserving source/review data."""
    from . import supabase_store
    token = supabase_store.get_token() if supabase_store.configured() else ""
    if supabase_store.configured() and (not token or not supabase_store.is_admin()):
        raise RuntimeError("Only a signed-in workspace admin can clear shared extraction results.")

    folder = ROOT / "data/processed"
    archive = ROOT / "outputs/archive" / ("extractions_" + timestamp().replace(":", "").replace("-", "").replace(".", ""))
    backed_up = []
    for filename in ("extractions_original.csv", "nlp_processed.csv", "extraction_metadata.json"):
        source = folder / filename
        if not source.is_file():
            continue
        target = archive / (filename + ".gz")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        with source.open("rb") as incoming, gzip.open(temporary, "wb", compresslevel=6) as compressed:
            shutil.copyfileobj(incoming, compressed, length=1024 * 1024)
        os.replace(temporary, target)
        backed_up.append(target)

    if supabase_store.configured():
        supabase_store.clear_generated_extractions(token)

    for filename in ("extractions_original.csv", "nlp_processed.csv", "extraction_metadata.json"):
        (folder / filename).unlink(missing_ok=True)
    for temporary in folder.glob("extractions_original.csv*.tmp"):
        temporary.unlink(missing_ok=True)
    for key in ("_fow_source_cache", "_fow_analysis_cache", "_fow_signature_cache", "_page_ai_suggestions"):
        supabase_store.session_state().pop(key, None)
    return archive if backed_up else None

def read_frame(name, *, include_source_text=True, columns=None, source_ids=None):
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
            return pd.DataFrame(read_candidates(get_token(), include_source_text=include_source_text), dtype=str).fillna("")
    if name == "labeled_competencies":
        from .supabase_store import configured, get_token, read_annotations
        if configured() and get_token():
            from .training_sources import ANNOTATION_COLUMNS
            return pd.DataFrame(read_annotations(get_token()), columns=ANNOTATION_COLUMNS + ["version"], dtype=str).fillna("")
    payload = _remote_payload("frame", name)
    source_ids = tuple(sorted(set(str(source) for source in source_ids))) if source_ids is not None else None
    if payload is not None:
        if payload.get("_storage_codec") == "frame-chunks-v1":
            from .supabase_store import configuration
            read_name = name
            projection = payload.get("review_projection")
            if projection and columns is not None and set(columns).issubset(projection["columns"]):
                payload = projection
                read_name = name + ":review"
            # A published generation is immutable. Check its small manifest on
            # the usual auth-cache schedule, but download/decode its chunks once.
            key = ("shared", configuration()[0], digest(get_token()), read_name)
            if source_ids is not None:
                key += (source_ids,)
            def decode():
                decoded = _read_remote_frame(read_name, payload, source_ids)
                return pd.DataFrame(decoded["records"], columns=decoded["columns"], dtype=str).fillna("")
            frame = _cached_frame(key, digest(payload), decode, columns)
            elided = payload.get("elided_columns", [])
        else:
            frame = pd.DataFrame(payload.get("records", []), columns=payload.get("columns", []), dtype=str).fillna("")
            if source_ids is not None and not frame.empty:
                frame = frame[frame.source_id.isin(source_ids)]
            if columns is not None:
                frame = frame.loc[:, [column for column in columns if column in frame]]
            elided = payload.get("_elided_columns", [])
        if include_source_text and (columns is None or "original_text" in columns) and "original_text" in elided and not frame.empty:
            jobs = read_frame("cleaned_jobs")
            if {"source_id", "original_text"}.issubset(jobs.columns):
                source_text = jobs.drop_duplicates("source_id").set_index("source_id").original_text
                frame["original_text"] = frame.source_id.map(source_text).fillna("")
        if name == "cleaned_psf_aai" and frame.empty:
            frame = _bundled_psf_default()
        return frame if include_source_text else frame.drop(columns=["original_text"], errors="ignore")
    if configured():
        if name == "cleaned_psf_aai":
            return _bundled_psf_default()
        return pd.DataFrame()
    if name == "labeled_competencies":
        from .training_sources import read_annotations
        return read_annotations(ROOT)
    path = ROOT / "data/processed" / f"{name}.csv"
    if not path.exists():
        if name == "cleaned_psf_aai":
            return _bundled_psf_default()
        return pd.DataFrame()
    try:
        stat = path.stat()
        key = ("local", str(path.resolve()))
        revision = (stat.st_mtime_ns, stat.st_size)
        from .supabase_store import session_state
        full = session_state().get("_fow_frame_cache", {}).get(key)
        requested = tuple(columns) if columns is not None else None
        usecols = None
        if not full or full[0] != revision:
            if requested is not None or not include_source_text:
                # Skip constructing long context/taxonomy strings when a screen
                # needs only metadata. A full cached frame can still be reused.
                key += (requested, include_source_text)
                usecols = lambda column: (requested is None or column in requested or (source_ids is not None and column == "source_id")) and (include_source_text or column != "original_text")
            if source_ids is not None:
                key += (source_ids,)
        def read_local():
            if source_ids is not None and stat.st_size > 32 * 1024 * 1024:
                selected = []
                with pd.read_csv(path, dtype=str, keep_default_na=False, usecols=usecols, chunksize=2000) as chunks:
                    for chunk in chunks:
                        selected.append(chunk[chunk.source_id.isin(source_ids)])
                return pd.concat(selected, ignore_index=True)
            return pd.read_csv(path, dtype=str, keep_default_na=False, usecols=usecols)
        frame = _cached_frame(
            key, revision,
            read_local, columns, source_ids,
        )
        if name == "cleaned_psf_aai" and frame.empty:
            return _bundled_psf_default()
        return frame if include_source_text else frame.drop(columns=["original_text"], errors="ignore")
    except pd.errors.EmptyDataError:
        if name == "cleaned_psf_aai":
            return _bundled_psf_default()
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


def remove_misfiled_psf_range_upload():
    """Remove only the accidental jobs upload when its PSF source copy exists."""
    manifest = read_json("uploads", {})
    job_entry = manifest.get("jobs", {})
    psf_entry = manifest.get("psf_aai", {})
    expected = "psf_aai_range_review_draft.csv"
    if (job_entry.get("filename") != expected or psf_entry.get("filename") != expected
            or not job_entry.get("hash") or job_entry.get("hash") != psf_entry.get("hash")):
        raise ValueError("The mistaken jobs upload or its matching PSF-AAI source copy was not found; no files were removed.")
    source_hash = str(job_entry["hash"]).lower()
    if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
        raise ValueError("The mistaken upload hash is invalid; no files were removed.")
    folder = (ROOT / "data/raw").resolve()
    path = (folder / f"jobs_{source_hash}.csv").resolve()
    if path.parent != folder:
        raise ValueError("The mistaken upload path is invalid; no files were removed.")
    manifest.pop("jobs")
    save_json("uploads", manifest)
    path.unlink(missing_ok=True)
    from .supabase_store import clear_read_cache
    clear_read_cache()
    return path


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
