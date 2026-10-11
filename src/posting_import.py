"""Prepare real posting CSVs for review; never infer or save training labels."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from .cleaning import clean_dataset
from .column_mapping import suggest_column_mapping
from .loaders import map_columns
from .skill_extraction import extract_skills
from .preprocessing import EXTRACTION_VERSION
from .storage import atomic_bytes
from .training_sources import ANNOTATION_COLUMNS, _table_summary
from .utils import timestamp

SOURCE_TYPE = "Philippine job advertisement"
COUNTRY_RULE = "Location is Philippines or ends with ', Philippines' or '; Philippines' (case insensitive). Other locations require separate provenance review."


def file_sha256(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def prepare_posting_candidates(root, relative, chunksize=2000, max_candidates=300):
    """Stream a source within train; retain explicit PH locations for review.

    Derived files are deterministic per source content. Re-running never changes
    the raw input or saved researcher annotations. Row IDs refer to CSV records,
    including quoted multiline descriptions, rather than physical line numbers.
    """
    root = Path(root)
    folder = (root / "train").resolve()
    path = (folder / relative).resolve()
    if not path.is_relative_to(folder) or not path.is_file() or path.suffix.lower() != ".csv":
        raise ValueError("Select an existing posting CSV within ./train.")
    before = path.stat()
    # Validate complete CSV records before a projected pandas read can hide
    # malformed fields, while keeping the full corpus out of memory.
    _table_summary(str(path), before.st_mtime_ns, before.st_size)
    source_hash = file_sha256(path)
    columns = pd.read_csv(path, nrows=0, encoding="utf-8-sig").columns.tolist()
    mapping, evidence = suggest_column_mapping(columns, "jobs")
    required = [field for field in ("job_title", "job_description", "location") if not mapping[field]]
    if required:
        raise ValueError("No unambiguous column for: " + ", ".join(required) + ". Rename these source headers in a separate copy before importing.")
    retained, total = [], 0
    usecols = list(dict.fromkeys(column for column in mapping.values() if column))
    with pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", usecols=usecols, chunksize=chunksize) as reader:
        for chunk in reader:
            total += len(chunk)
            locations = chunk[mapping["location"]].str.strip()
            explicit_ph = locations.str.contains(r"(?:^|[,;])\s*philippines\s*$", case=False, regex=True)
            selected = chunk.loc[explicit_ph].copy()
            if not selected.empty:
                mapped = map_columns(selected, mapping, "jobs", source_hash)
                mapped["_raw_row"] = selected.index + 2
                mapped["source_id"] = [f"jobs:{source_hash[:16]}:{row}" for row in mapped._raw_row]
                # Public Himalayas listing GUIDs are stable across daily feed
                # snapshots, so the same posting does not become a new sample
                # every time the feed file grows.
                if "source" in mapped and "job_id" in mapped:
                    himalayas = mapped.source.astype(str).str.casefold().str.contains("himalayas", regex=False)
                    has_id = mapped.job_id.astype(str).str.strip().ne("")
                    stable = himalayas & has_id
                    mapped.loc[stable, "source_id"] = mapped.loc[stable, "job_id"].map(lambda value: f"jobs:himalayas:{value}")
                retained.append(mapped)
    mapped = pd.concat(retained, ignore_index=True) if retained else None
    extra = ["job_title", "company", "source_url", "original_text", "location", "source_file", "source_hash", "source_record"]
    candidates = pd.DataFrame(columns=ANNOTATION_COLUMNS + extra)
    cleaned, diagnostics = pd.DataFrame(), pd.DataFrame()
    if mapped is not None:
        cleaned, _ = clean_dataset(mapped, "jobs")
        extracted, diagnostics = extract_skills(cleaned, SOURCE_TYPE, max_candidates=max_candidates)
        references = cleaned.set_index("source_id")
        candidates = extracted.rename(columns={"original_phrase": "phrase"})[["phrase", "normalized_phrase", "source_type", "source_id", "original_text"]].copy()
        # Discovery categories, vocabulary matches and model predictions are NOT
        # reviewed labels. Only the manual-labeling workflow may populate these.
        for column in ("label", "psf_competency", "reviewer", "timestamp"):
            candidates[column] = ""
        for column, field in (("job_title", "job_title"), ("company", "company"), ("source_url", "url"), ("location", "location"), ("source_record", "_raw_row")):
            candidates[column] = candidates.source_id.map(references[field])
        candidates["source_file"] = str(path.relative_to(folder))
        candidates["source_hash"] = source_hash
        candidates = candidates[ANNOTATION_COLUMNS + extra]
    after = path.stat()
    if (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        raise ValueError("Posting CSV changed during import. Retry with the completed file.")
    target = folder / "derived" / f"postings_{source_hash[:16]}"
    report = {
        "created_at": timestamp(), "source_file": str(path.relative_to(folder)), "source_sha256": source_hash,
        "source_bytes": before.st_size, "total_postings": total,
        "explicit_philippine_postings": 0 if mapped is None else len(mapped),
        "excluded_without_explicit_philippine_location": total - (0 if mapped is None else len(mapped)),
        "location_rule": COUNTRY_RULE, "mapping": mapping, "mapping_evidence": evidence,
        "candidate_occurrences": len(candidates), "distinct_phrases": candidates.normalized_phrase.nunique(),
        "candidate_limit_per_posting": max_candidates,
        "extraction_version": EXTRACTION_VERSION,
        "postings_reaching_candidate_limit": int(diagnostics.candidate_limit_reached.sum()) if not diagnostics.empty else 0,
        "candidate_file": str((target / "candidate_phrases.csv").relative_to(folder)),
        "reviewed_labels_created": 0, "model_trained": False,
        "review_required": "Verify Philippine provenance and AI/analytics relevance against original URLs. Geography alone does not establish research relevance. Review all phrases, including IRRELEVANT extractions, before training.",
    }
    if not cleaned.empty:
        atomic_bytes(target / "philippine_jobs.csv", cleaned.to_csv(index=False).encode("utf-8-sig"))
    atomic_bytes(target / "candidate_phrases.csv", candidates.to_csv(index=False).encode("utf-8-sig"))
    atomic_bytes(target / "import_report.json", json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
    return report


if __name__ == "__main__":
    import argparse
    from .config import ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="CSV path relative to ./train")
    args = parser.parse_args()
    report = prepare_posting_candidates(ROOT, args.source)
    print(json.dumps({key: report[key] for key in ("total_postings", "explicit_philippine_postings", "candidate_occurrences", "candidate_file", "reviewed_labels_created", "model_trained")}, indent=2))
