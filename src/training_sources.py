"""Discover the researcher's training pack without assuming input filenames."""
from functools import lru_cache
from pathlib import Path
import csv
import json
import pandas as pd
from .loaders import load_data
from .cleaning import normalize_text
from .utils import digest

ANNOTATION_COLUMNS = ["phrase", "normalized_phrase", "label", "psf_competency", "source_type", "source_id", "reviewer", "timestamp"]

@lru_cache(maxsize=64)
def _table_summary(path, modified, size):
    """Count records without retaining large posting descriptions in memory."""
    if Path(path).suffix.lower() != ".csv":
        frame = read_source_table(path)
        count = int((frame.label.str.strip().ne("") & frame.phrase.str.strip().ne("")).sum()) if {"phrase", "label"}.issubset(frame) else 0
        return list(frame), len(frame), count
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        columns = [c.strip() for c in next(reader, [])]
        if not columns or any(not c for c in columns) or len(set(columns)) != len(columns):
            raise ValueError("CSV headers must be nonempty and unique.")
        positions = (columns.index("phrase"), columns.index("label")) if {"phrase", "label"}.issubset(columns) else None
        rows, labeled = 0, 0
        for ordinal, row in enumerate(reader, 2):
            if not row:
                continue
            if len(row) != len(columns):
                raise ValueError(f"CSV record {ordinal} has {len(row)} fields; expected {len(columns)}.")
            rows += 1
            if positions and row[positions[0]].strip() and row[positions[1]].strip():
                labeled += 1
    return columns, rows, labeled


@lru_cache(maxsize=32)
def _read_table(path, modified, size):
    file = Path(path)
    try:
        return load_data(file.read_bytes(), file.name)
    except ValueError as exc:
        if "no data rows" not in str(exc):
            raise
        return pd.read_csv(file, dtype=str, keep_default_na=False) if file.suffix.lower() == ".csv" else pd.read_excel(file, dtype=str, keep_default_na=False)

def read_source_table(path):
    path = Path(path)
    stat = path.stat()
    return _read_table(str(path.resolve()), stat.st_mtime_ns, stat.st_size).copy()

def inspect_training_folder(root):
    folder = Path(root) / "train"
    records = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or any(part.startswith(".") or part == "__pycache__" for part in path.relative_to(folder).parts):
            continue
        record = {"filename": str(path.relative_to(folder)), "purpose": "documentation / supporting source", "rows": None,
                  "columns": [], "labeled_rows": 0, "training_use": "not a labeled training table", "error": ""}
        if path.suffix.lower() in (".csv", ".xlsx"):
            try:
                stat = path.stat()
                names, rows, count = _table_summary(str(path.resolve()), stat.st_mtime_ns, stat.st_size)
                columns = set(names)
                record.update(rows=rows, columns=names)
                if {"phrase", "label"}.issubset(columns):
                    record.update(labeled_rows=count, purpose="labeled phrases" if count else "candidate phrases" if rows else "empty label schema",
                                  training_use="reviewed-label validation required" if count else "not trainable: no assigned labels")
                elif "phrase" in columns or "normalized_phrase" in columns:
                    record["purpose"] = "candidate phrases"
                    record["training_use"] = "not trainable: researcher labeling required"
                elif "competency_name" in columns:
                    record["purpose"] = "PSF-AAI data" if rows else "PSF-AAI template"
                elif columns.intersection({"job_title", "title"}) and columns.intersection({"skills_summary", "job_description", "description", "required_skills", "location"}):
                    record["purpose"] = "job-ad source data"
                elif "source_url" in columns:
                    record["purpose"] = "source catalog"
            except (ValueError, OSError, csv.Error) as exc:
                record.update(purpose="unreadable table", error=str(exc), training_use="not trainable: invalid file")
        elif path.suffix.lower() == ".py":
            record["purpose"] = "source helper script (not executed)"
        records.append(record)
    return records

def resolve_training_file(root, create=True):
    root = Path(root)
    folder = root / "train"
    canonical = folder / "labeled_competencies.csv"
    selection = root / "data/processed/training_source.json"
    if selection.exists():
        relative = json.loads(selection.read_text(encoding="utf-8"))["file"]
        selected = (folder / relative).resolve()
        if not selected.is_relative_to(folder.resolve()) or not selected.is_file():
            raise ValueError("The selected training file is missing or outside ./train. Select an existing labeled file on ML Training.")
        return selected
    inventory = inspect_training_folder(root)
    populated = [folder / item["filename"] for item in inventory if item["purpose"] == "labeled phrases"]
    if len(populated) > 1:
        raise ValueError("Multiple populated labeled files were detected in ./train. Select the intended training file on ML Training.")
    if populated:
        return populated[0]
    if create and not canonical.exists():
        folder.mkdir(parents=True, exist_ok=True)
        canonical.write_text(",".join(ANNOTATION_COLUMNS)+"\n", encoding="utf-8")
    return canonical

def select_training_file(root, relative):
    root = Path(root)
    candidate = (root / "train" / relative).resolve()
    if not candidate.is_relative_to((root / "train").resolve()) or not candidate.is_file():
        raise ValueError("Select an existing labeled table within ./train.")
    frame = read_source_table(candidate)
    if not {"phrase", "label"}.issubset(frame):
        raise ValueError("This table does not contain phrase and label columns.")
    if candidate.suffix.lower() != ".csv":
        raise ValueError("Save reviewed annotations as CSV before selecting the editable training file.")
    if not frame.empty and not frame.label.str.strip().ne("").any():
        raise ValueError("This is an unreviewed candidate table. Review it on Manual Labeling; keep its source bytes unchanged.")
    target = root / "data/processed/training_source.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"file": str(candidate.relative_to((root / "train").resolve()))}), encoding="utf-8")
    return candidate

def read_annotations(root):
    path = resolve_training_file(root)
    frame = read_source_table(path)
    for column in ANNOTATION_COLUMNS:
        if column not in frame:
            frame[column] = ""
    return frame

def training_candidates(root):
    root = Path(root)
    inventory = inspect_training_folder(root)
    frames, jobs = [], []
    # Keep original candidate evidence ahead of thinner saved annotation rows.
    for item in sorted(inventory, key=lambda item: item["purpose"] != "candidate phrases"):
        if item["purpose"] in ("candidate phrases", "labeled phrases") and item["rows"]:
            frame = read_source_table(root / "train" / item["filename"])
            if "phrase" not in frame:
                frame["phrase"] = frame.normalized_phrase
            if "normalized_phrase" not in frame:
                frame["normalized_phrase"] = frame.phrase.map(normalize_text)
            for column in ("source_type", "source_id", "job_title", "company", "source_url", "original_text"):
                if column not in frame:
                    frame[column] = ""
            frame["candidate_file"] = item["filename"]
            frame["candidate_row"] = range(2, len(frame)+2)
            # Labels in source packs are not copied into human annotations on page load.
            frames.append(frame)
        # Large raw postings are processed explicitly by posting_import. Their
        # derived candidates carry full evidence; do not load the raw corpus on
        # every labeling-page rerun just to enrich the small starter pack.
        if item["purpose"] == "job-ad source data":
            path = root / "train" / item["filename"]
            if path.stat().st_size <= 20_000_000:
                jobs.append(read_source_table(path))
    if not frames:
        return pd.DataFrame(columns=["phrase", "normalized_phrase", "source_type", "source_id", "job_title", "company", "source_url", "original_text"])
    candidates = pd.concat(frames, ignore_index=True).fillna("")
    if jobs:
        source = pd.concat(jobs, ignore_index=True).fillna("")
        if "job_id" in source:
            references = source.drop_duplicates("job_id").set_index("job_id")
            for column in ("source_url", "job_title", "company"):
                if column in references:
                    candidates[column] = candidates[column].where(candidates[column].ne(""), candidates.source_id.map(references[column]).fillna(""))
            fields = [c for c in ("job_description", "skills_summary", "education_requirements_summary", "experience_summary", "location") if c in source]
            if fields:
                source["context"] = source[fields].agg(" | ".join, axis=1)
                context = source.drop_duplicates("job_id").set_index("job_id").context
                candidates["original_text"] = candidates.original_text.where(candidates.original_text.ne(""), candidates.source_id.map(context).fillna(""))
    candidates = candidates[candidates.source_type.str.strip().str.casefold().isin({"jobs", "philippine job advertisement"})].copy()
    candidates["candidate_id"] = [digest([row.candidate_file, row.candidate_row])[:24] for row in candidates.itertuples()]
    return candidates.drop_duplicates(["normalized_phrase", "source_type", "source_id"], keep="first")

def training_taxonomy(root):
    root = Path(root)
    cleaned = root / "data/processed/cleaned_psf_aai.csv"
    if cleaned.exists():
        frame = read_source_table(cleaned)
        if not frame.empty:
            return frame
    detected = [row for row in inspect_training_folder(root) if row["purpose"] == "PSF-AAI data"]
    if len(detected) > 1:
        raise ValueError("Multiple PSF-AAI tables detected. Upload/map the intended taxonomy on Data Upload first.")
    if detected:
        frame = read_source_table(root / "train" / detected[0]["filename"])
        if "source_page" not in frame or "source_url" not in frame:
            raise ValueError("The PSF-AAI reference needs source_page and source_url fields. Add provenance before mapping.")
        return frame
    return pd.DataFrame()
