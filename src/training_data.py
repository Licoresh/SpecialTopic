"""Validate human annotations before any model is fitted."""
import math
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from .cleaning import normalize_text
from .utils import digest
from .training_sources import ANNOTATION_COLUMNS, read_source_table

LABEL_COLUMNS = ANNOTATION_COLUMNS
MIN_ROWS = 30
MIN_PER_CLASS = 5

def source_disjoint_split(data, test_size=.2, seed=42):
    """Split by source posting when provenance is available; never split phrases from one ad across partitions."""
    labels = set(data.label)
    groups = data.get("source_id", pd.Series(dtype=str)).fillna("").astype(str)
    if groups.empty or groups.str.strip().eq("").any() or groups.nunique() < 2:
        train, test = train_test_split(data, test_size=test_size, random_state=seed, stratify=data.label)
        return train, test, "stratified phrase-level holdout (source IDs unavailable)"
    candidates = []
    splitter = GroupShuffleSplit(n_splits=256, test_size=test_size, random_state=seed)
    for train_idx, test_idx in splitter.split(data, data.label, groups):
        train, test = data.iloc[train_idx], data.iloc[test_idx]
        if set(train.label) == labels and set(test.label) == labels:
            size_error = abs(len(test) / len(data) - test_size)
            # Prefer a representative label mix while keeping the requested holdout size.
            full_share = data.label.value_counts(normalize=True).sort_index()
            test_share = test.label.value_counts(normalize=True).reindex(full_share.index, fill_value=0)
            candidates.append((size_error + float((full_share - test_share).abs().mean()), train, test))
    if not candidates:
        raise ValueError("No source-disjoint holdout can represent every category in both partitions. Label more distinct job ads across all categories before training; a phrase-level split would leak ad-specific wording into evaluation.")
    _, train, test = min(candidates, key=lambda item: item[0])
    return train, test, "source-disjoint holdout by job-ad source_id"

def labeled_file_hash(path):
    path = Path(path)
    return digest(path.read_bytes()) if path.exists() else None

def load_labeled_data(path):
    path = Path(path)
    if not path.exists():
        raise ValueError("No labeled competency file exists. Save researcher-reviewed phrases on Manual Labeling first.")
    frame = read_source_table(path)
    missing = {"phrase", "label"} - set(frame.columns)
    if missing:
        raise ValueError("Labeled data is missing columns: " + ", ".join(sorted(missing)))
    for column in LABEL_COLUMNS:
        if column not in frame:
            frame[column] = ""
    return frame

def validate_labeled_data(labeled, test_size=.2, include_irrelevant=False, require_provenance=False):
    report = {"total_rows": len(labeled), "rows_used": 0, "number_of_classes": 0,
              "class_distribution": {}, "missing_values": {}, "duplicate_phrases": 0,
              "duplicate_phrase_label_pairs": 0, "duplicate_normalized_phrases": 0,
              "conflicting_labels": [], "excluded_rows": [], "warnings": [], "errors": [],
              "include_irrelevant": include_irrelevant, "minimum_rows": MIN_ROWS, "minimum_per_class": MIN_PER_CLASS, "valid": False}
    if not {"phrase", "label"}.issubset(labeled):
        report["errors"].append("Labeled data needs phrase and label columns.")
        return pd.DataFrame(columns=["phrase", "label", "text", "source_row"]), report
    frame = labeled.copy().reset_index(drop=True)
    for column in LABEL_COLUMNS:
        if column not in frame:
            frame[column] = ""
        report["missing_values"][column] = int(frame[column].isna().sum() + frame[column].map(lambda v: isinstance(v, str) and not v.strip()).sum())
    kept = []
    for index, row in frame.iterrows():
        reason = ""
        phrase, label, normalized = row.phrase, row.label, row.normalized_phrase
        if not isinstance(phrase, str) or not isinstance(label, str):
            reason = "missing or non-text phrase/label"
        elif not phrase.strip() or not label.strip():
            reason = "empty phrase/label"
        elif label.strip().casefold() in ("unclassified", "unlabeled", "nan", "null", "none"):
            reason = "unassigned label"
        elif not isinstance(normalized, str) and not pd.api.types.is_scalar(normalized):
            reason = "malformed normalized phrase"
        elif not isinstance(normalized, str) and not pd.isna(normalized):
            reason = "non-text normalized phrase"
        elif require_provenance and any(not isinstance(row[field], str) or not row[field].strip() for field in ("source_type", "source_id", "reviewer", "timestamp")):
            reason = "missing source or reviewer provenance"
        elif require_provenance and row.source_type.strip().casefold() not in ("jobs", "philippine job advertisement"):
            reason = "outside Philippine job-ad training scope"
        if reason:
            report["excluded_rows"].append({"source_row": index+2, "reason": reason})
            continue
        label = label.strip()
        if label.casefold() == "irrelevant":
            label = "IRRELEVANT"
        text = normalize_text(normalized) if isinstance(normalized, str) and normalized.strip() else normalize_text(phrase)
        if not text or not any(ch.isalnum() for ch in text):
            report["excluded_rows"].append({"source_row": index+2, "reason": "no usable text features"})
            continue
        kept.append({"phrase": phrase.strip(), "surface": normalize_text(phrase), "label": label, "text": text,
                     "source_row": index+2, "source_id": str(row.source_id).strip() if isinstance(row.source_id, str) else ""})
    data = pd.DataFrame(kept, columns=["phrase", "surface", "label", "text", "source_row", "source_id"])
    report["valid_labeled_rows"] = len(data)
    report["duplicate_phrases"] = int(data.duplicated("surface").sum())
    report["duplicate_phrase_label_pairs"] = int(data.duplicated(["text", "label"]).sum())
    report["duplicate_normalized_phrases"] = int(data.duplicated("text").sum())
    # Check before excluding IRRELEVANT: conflicting human decisions must not be hidden.
    for key in ("surface", "text"):
        for phrase, group in data.groupby(key):
            if group.label.nunique() > 1:
                report["conflicting_labels"].append({"key": key, "phrase": phrase, "labels": sorted(group.label.unique()), "source_rows": group.source_row.tolist()})
    if report["conflicting_labels"]:
        report["errors"].append("Conflicting labels exist for the same normalized or original phrase. Resolve the annotations before training.")
    if not include_irrelevant:
        for row in data[data.label.eq("IRRELEVANT")].itertuples():
            report["excluded_rows"].append({"source_row": row.source_row, "reason": "IRRELEVANT excluded by configuration"})
        data = data[data.label.ne("IRRELEVANT")]
    duplicates = data.duplicated("surface") | data.duplicated("text")
    for row in data[duplicates].itertuples():
        report["excluded_rows"].append({"source_row": row.source_row, "reason": "duplicate training phrase"})
    data = data.loc[~duplicates].reset_index(drop=True)
    counts = data.label.value_counts().sort_index()
    report.update(rows_used=len(data), number_of_classes=len(counts), class_distribution={str(k): int(v) for k,v in counts.items()})
    report["smallest_class_size"] = int(counts.min()) if len(counts) else 0
    report["imbalance_ratio"] = float(counts.max()/counts.min()) if len(counts) else None
    report["additional_distinct_labels_needed"] = max(0, MIN_ROWS-len(data))
    report["additional_classes_needed"] = max(0, 2-len(counts))
    report["per_class_shortfall"] = {str(name): max(0, MIN_PER_CLASS-int(count)) for name,count in counts.items()}
    if report["excluded_rows"]:
        report["warnings"].append(f"Excluded {len(report['excluded_rows'])} empty, malformed, irrelevant or duplicate rows. See validation details.")
    if len(data) < MIN_ROWS:
        message = f"Fewer than {MIN_ROWS} distinct usable labeled phrases ({len(data)} available). Add researcher-reviewed labels."
        report["warnings"].append(message)
        report["errors"].append(message)
    if len(counts) < 2:
        report["errors"].append("At least two competency classes are required; zero or one class cannot train this classifier.")
        report["warnings"].append("Only one or no class is present.")
    low = counts[counts < MIN_PER_CLASS]
    if not low.empty:
        message = "Classes with fewer than 5 distinct samples: " + ", ".join(f"{name} ({count})" for name,count in low.items())
        report["warnings"].append(message)
        report["errors"].append(message)
    if len(counts) > 1 and counts.max() / counts.min() >= 5:
        report["warnings"].append("Highly imbalanced classes: the largest class has at least five times as many phrases as the smallest.")
    if not isinstance(test_size, (int, float)) or not 0 < test_size < 1:
        report["errors"].append("Holdout fraction must be between 0 and 1.")
    elif len(counts) >= 2 and counts.min() >= 2:
        test_n = math.ceil(len(data)*test_size)
        if min(test_n, len(data)-test_n) < len(counts):
            report["errors"].append("Both train and test partitions must have room for every class. Add labels or adjust the holdout fraction.")
        else:
            try:
                train, test, strategy = source_disjoint_split(data, test_size)
                report["validation_split"] = strategy
                report["source_count"] = int(data.source_id.nunique()) if data.source_id.astype(str).str.strip().ne("").all() else None
            except ValueError as exc:
                report["errors"].append(str(exc))
                train = test = pd.DataFrame()
            if set(train.label) != set(counts.index) or set(test.label) != set(counts.index):
                if not any("No source-disjoint holdout" in error for error in report["errors"]):
                    report["errors"].append("The holdout would omit a class from a partition. Add minority-class labels or adjust the holdout fraction.")
    report["valid"] = not report["errors"]
    return data, report
