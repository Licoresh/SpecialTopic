"""Resumable local candidate preparation and AI-suggestion runner.

This workflow only creates editable suggestion drafts. It never saves human
labels, trains a classifier, or reports research performance metrics.
"""
from pathlib import Path
import json
import pandas as pd

from .cleaning import normalize_text
from .config import ROOT
from .pretrained_suggestions import (
    load_ai_suggestions,
    save_ai_suggestions,
    suggest_labels,
    suggestion_key,
)
from .preprocessing import EXTRACTION_VERSION
from .posting_import import file_sha256, prepare_posting_candidates
from .training_sources import inspect_training_folder, read_annotations, read_source_table, training_taxonomy


def _source_posting_files(root, inventory=None):
    """Find raw posting CSVs in ./train; never re-import generated derived files."""
    folder = Path(root) / "train"
    files = []
    for item in (inventory if inventory is not None else inspect_training_folder(root)):
        relative = Path(item["filename"])
        if (item["purpose"] == "job-ad source data" and relative.suffix.lower() == ".csv"
                and "derived" not in relative.parts):
            files.append(relative)
    return [folder / item for item in files]


def _candidate_files(root, inventory=None):
    folder = Path(root) / "train"
    return [
        folder / item["filename"]
        for item in (inventory if inventory is not None else inspect_training_folder(root))
        if item["purpose"] in ("candidate phrases", "labeled phrases")
        and Path(item["filename"]).suffix.lower() in (".csv", ".xlsx")
        and item["rows"]
    ]


def _iter_rows(path, chunksize):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        for frame in pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", chunksize=chunksize):
            yield frame
    else:
        yield read_source_table(path)


def _usable_candidate_rows(frame):
    if "phrase" not in frame and "normalized_phrase" in frame:
        frame = frame.copy()
        frame["phrase"] = frame.normalized_phrase
    if "phrase" not in frame or "source_type" not in frame:
        return frame.iloc[0:0]
    phrase = frame.phrase.astype(str).str.strip()
    source_type = frame.source_type.astype(str).str.strip().str.casefold()
    return frame.loc[
        phrase.ne("") & source_type.isin({"jobs", "philippine job advertisement"})
    ]


def run_local_suggestions(root=ROOT, progress=None, chunksize=5000, batch_size=25, max_drafts=None):
    """Prepare local job CSVs, then save BGE-M3 suggestions in resumable batches."""
    if batch_size < 1 or (max_drafts is not None and max_drafts < 1):
        raise ValueError("Batch size and draft limit must be positive.")
    root = Path(root)
    progress = progress or (lambda fraction, message: None)
    progress(0.0, "Scanning local job CSVs in ./train")

    initial_inventory = inspect_training_folder(root)
    raw_postings = _source_posting_files(root, initial_inventory)
    prepared = []
    preparation_errors = []
    preparation_skips = []
    for index, path in enumerate(raw_postings):
        relative = str(path.relative_to(root / "train"))
        try:
            source_hash = file_sha256(path)
            destination = root / "train" / "derived" / f"postings_{source_hash[:16]}"
            report_path = destination / "import_report.json"
            candidate_path = destination / "candidate_phrases.csv"
            if report_path.exists() and candidate_path.exists():
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if (report.get("source_sha256") == source_hash
                        and report.get("extraction_version") == EXTRACTION_VERSION):
                    prepared.append({"source": relative, "status": "already prepared"})
                    progress(0.03 + 0.17 * (index + 1) / max(len(raw_postings), 1), f"Using prepared candidates from {relative}")
                    continue
            report = prepare_posting_candidates(root, relative)
            prepared.append({"source": relative, "status": "prepared", "candidate_occurrences": report["candidate_occurrences"]})
        except Exception as exc:
            message = str(exc)
            if "No unambiguous column for: job_description" in message:
                preparation_skips.append(
                    f"{relative}: no full job-description column; its existing candidate rows remain available for review."
                )
            else:
                preparation_errors.append(f"{relative}: {message}")
        progress(0.03 + 0.17 * (index + 1) / max(len(raw_postings), 1), f"Prepared {index + 1} of {len(raw_postings)} local posting files")

    taxonomy = training_taxonomy(root)
    if taxonomy.empty:
        raise ValueError("No active PSF-AAI taxonomy is available. Review and activate the framework before generating suggestions.")

    labels = read_annotations(root)
    reviewed = set()
    if not labels.empty and {"phrase", "label"}.issubset(labels.columns):
        for row in labels[labels.label.astype(str).str.strip().ne("")].to_dict("records"):
            reviewed.add(suggestion_key(row))
    existing = load_ai_suggestions(root)
    completed = set(existing)

    inventory = inspect_training_folder(root)
    files = _candidate_files(root, inventory)
    row_counts = {item["filename"]: item["rows"] or 0 for item in inventory}
    total_rows = sum(row_counts.get(str(path.relative_to(root / "train")), 0) for path in files)
    scanned = already_reviewed = already_suggested = missing_source_id = generated = 0
    seen = set()
    pending = []

    def flush_batch():
        nonlocal generated, pending
        if not pending:
            return
        progress(0.20 + 0.79 * min(scanned / max(total_rows, 1), 1.0),
                 f"Generating {len(pending)} drafts; {generated} saved. First use may download/load BGE-M3 (about 2.3 GB).")
        predictions = suggest_labels(pending, taxonomy)
        save_ai_suggestions(root, pending, predictions)
        generated += len(pending)
        pending = []

    for path in files:
        for frame in _iter_rows(path, chunksize):
            for row in _usable_candidate_rows(frame).to_dict("records"):
                scanned += 1
                phrase = str(row.get("phrase", "") or row.get("normalized_phrase", "")).strip()
                source_type = str(row.get("source_type", "")).strip()
                if not row.get("normalized_phrase"):
                    row["normalized_phrase"] = normalize_text(phrase)
                row["phrase"] = phrase
                row["source_type"] = source_type
                row["source_id"] = str(row.get("source_id", "") or "")
                if not row["source_id"]:
                    missing_source_id += 1
                    continue
                key = suggestion_key(row)
                if not key or key in seen:
                    continue
                seen.add(key)
                if key in reviewed:
                    already_reviewed += 1
                    continue
                if key in completed:
                    already_suggested += 1
                    continue
                if max_drafts is not None and generated + len(pending) >= max_drafts:
                    continue
                pending.append(row)
                if len(pending) >= batch_size:
                    flush_batch()
                denominator = max(total_rows, 1)
                fraction = 0.20 + 0.79 * min(scanned / denominator, 1.0)
                if scanned % 100 == 0 or not pending:
                    progress(fraction, f"Scanned {scanned:,} candidate rows; saved {generated:,} suggestion drafts")
    flush_batch()
    progress(1.0, f"Done: generated {generated:,} new suggestion drafts")
    return {
        "posting_sources": len(raw_postings),
        "prepared_sources": prepared,
        "candidate_files": len(files),
        "candidate_rows_scanned": scanned,
        "already_reviewed": already_reviewed,
        "already_suggested": already_suggested,
        "missing_source_id": missing_source_id,
        "suggestions_generated": generated,
        "preparation_skips": preparation_skips,
        "preparation_errors": preparation_errors,
    }
