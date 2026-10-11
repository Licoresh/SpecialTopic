"""Build a clearly separate draft classifier from unambiguous labeled rows.

This path never writes the production research model or its evaluation outputs.
Conflicting phrase groups are omitted as a whole until a researcher resolves them.
"""
import json
from pathlib import Path

from . import storage
from .classification import save_model, train_model, VECTORIZER_CONFIG
from .training_data import load_labeled_data, validate_labeled_data, labeled_file_hash
from .training_sources import resolve_training_file
from .cleaning import normalize_text
from .utils import timestamp


def train_provisional_model(root=None):
    """Fit an internal-only classifier; return metadata without research metrics."""
    root = Path(root or storage.ROOT)
    training_file = resolve_training_file(root)
    labels = load_labeled_data(training_file)
    _, initial = validate_labeled_data(labels, .2, False, require_provenance=True)

    conflict_keys = {
        normalize_text(item["phrase"])
        for item in initial["conflicting_labels"]
        if item.get("phrase")
    }
    if conflict_keys:
        phrase_keys = labels["normalized_phrase"].fillna("").astype(str).map(
            lambda value: normalize_text(value) if value.strip() else ""
        )
        phrase_keys = phrase_keys.where(phrase_keys.ne(""), labels["phrase"].fillna("").astype(str).map(normalize_text))
        labels = labels.loc[~phrase_keys.isin(conflict_keys)].copy()

    data, validation = validate_labeled_data(labels, .2, False, require_provenance=True)
    if validation["errors"]:
        raise ValueError("Provisional training is not ready: " + " ".join(validation["errors"]))

    model = train_model(data.text, data.label, "Logistic Regression", VECTORIZER_CONFIG)
    model_dir = root / "models" / "provisional"
    model_path = model_dir / "competency_classifier.joblib"
    save_model(model, model_path)

    metadata = {
        "model_name": "Balanced Logistic Regression",
        "created_at": timestamp(),
        "training_file": str(training_file.resolve()),
        "training_file_hash": labeled_file_hash(training_file),
        "rows_used": int(validation["rows_used"]),
        "number_of_classes": int(validation["number_of_classes"]),
        "class_distribution": validation["class_distribution"],
        "conflict_groups_excluded": sorted(conflict_keys),
        "vectorizer_config": VECTORIZER_CONFIG,
        "is_research_model": False,
        "label_review_status": "Unverified. Reviewer IDs and timestamps in the source CSV do not establish whether each label was independently reviewed.",
        "evaluation_metrics": None,
        "intended_use": "Weak-supervision experiment for internal draft suggestions only. Not an evaluated or reportable research model.",
    }
    storage.atomic_bytes(
        model_dir / "model_metadata.json",
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
    )
    return model_path, metadata
