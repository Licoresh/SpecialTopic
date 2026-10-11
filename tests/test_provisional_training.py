"""Synthetic fixtures only; verify the draft model stays separate from research artifacts."""
import pandas as pd

from src.labeling import save_annotations
from src.provisional_training import train_provisional_model
from src.training_data import load_labeled_data
from src.training_sources import resolve_training_file


def test_provisional_model_excludes_conflicts_and_does_not_publish_research_artifacts(workspace, labeled):
    extra = pd.DataFrame([
        {"phrase": "PowerShell automation", "label": "Technical", "source_type": "Philippine job advertisement", "source_id": "SYNTHETIC-31"},
        {"phrase": "user research design", "label": "Soft", "source_type": "Philippine job advertisement", "source_id": "SYNTHETIC-32"},
    ])
    save_annotations(pd.concat([labeled, extra], ignore_index=True), "SYNTHETIC TEST REVIEWER")
    path = resolve_training_file(workspace)
    rows = load_labeled_data(path)
    conflict = rows.iloc[[0]].copy()
    conflict.loc[:, "label"] = "Conflicting synthetic category"
    conflict.loc[:, "source_id"] = "SYNTHETIC-CONFLICT"
    rows = pd.concat([rows, conflict], ignore_index=True)
    rows.to_csv(path, index=False)

    model_path, metadata = train_provisional_model(workspace)

    assert model_path.exists()
    assert metadata["is_research_model"] is False
    assert metadata["evaluation_metrics"] is None
    assert metadata["label_review_status"].startswith("Unverified")
    assert metadata["rows_used"] == 31
    assert "python programming" in metadata["conflict_groups_excluded"]
    assert not (workspace / "models/competency_classifier.joblib").exists()
    assert not (workspace / "outputs/tables/model_metrics.csv").exists()
