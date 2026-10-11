import json
import os
from pathlib import Path
import time
import uuid
import pandas as pd
from .config import ROOT, DEFAULTS
from .utils import digest, timestamp

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
    if name == "labeled_competencies":
        from .training_sources import resolve_training_file
        path = resolve_training_file(ROOT)
        if path.suffix.lower() != ".csv":
            raise ValueError("The editable training dataset must be a CSV file in ./train.")
        atomic_bytes(path, frame.to_csv(index=False).encode("utf-8-sig"))
        return
    atomic_bytes(ROOT / "data/processed" / f"{name}.csv", frame.to_csv(index=False).encode("utf-8-sig"))

def read_frame(name):
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
    atomic_bytes(ROOT / "data/processed" / f"{name}.json", json.dumps(value, indent=2, default=str).encode())

def read_json(name, default=None):
    path = ROOT / "data/processed" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default

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
