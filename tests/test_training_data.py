"""SYNTHETIC DATA — NOT RESEARCH DATA. Never persisted into the application workspace."""
import pandas as pd
import pytest
from src.training_data import load_labeled_data, validate_labeled_data, labeled_file_hash, LABEL_COLUMNS

def complete(frame):
    return frame.reindex(columns=LABEL_COLUMNS, fill_value="")

def test_header_only_and_missing_file(tmp_path):
    path = tmp_path / "labeled_competencies.csv"
    with pytest.raises(ValueError, match="No labeled"):
        load_labeled_data(path)
    pd.DataFrame(columns=LABEL_COLUMNS).to_csv(path, index=False)
    loaded = load_labeled_data(path)
    assert loaded.empty and list(loaded) == LABEL_COLUMNS
    data, report = validate_labeled_data(loaded)
    assert data.empty and not report["valid"] and report["rows_used"] == 0
    assert any("30" in warning for warning in report["warnings"])

def test_load_rejects_missing_columns_and_malformed_csv(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("phrase\nSQL\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_labeled_data(path)
    path.write_text(",".join(LABEL_COLUMNS) + "\nSQL,Technical,too,few\n")
    with pytest.raises(ValueError, match="fields"):
        load_labeled_data(path)

def test_preferred_text_fallback_and_row_exclusions(labeled):
    frame = complete(labeled)
    frame.loc[0, "normalized_phrase"] = "  preferred normalized phrase "
    invalid = pd.DataFrame([
        {"phrase":"", "label":"Technical"}, {"phrase":"blank label", "label":" "},
        {"phrase":"rejected example", "label":"IRRELEVANT"}, {"phrase":123, "label":"Technical"},
        {"phrase":"malformed", "normalized_phrase":["a"], "label":"Technical"},
        {"phrase":"candidate", "label":"UNCLASSIFIED"},
    ])
    data, report = validate_labeled_data(pd.concat([frame, invalid], ignore_index=True))
    assert report["valid"] and report["rows_used"] == 30
    assert len(report["excluded_rows"]) == 6
    assert data.text.iloc[0] == "preferred normalized phrase"
    assert data.text.iloc[1] == labeled.phrase.iloc[1]
    assert "IRRELEVANT" not in data.label.unique()

def test_duplicate_conflicts_and_irrelevant_not_hidden(labeled):
    frame = complete(labeled)
    duplicate = frame.iloc[[0]].copy()
    data, report = validate_labeled_data(pd.concat([frame, duplicate], ignore_index=True))
    assert len(data) == 30 and report["duplicate_phrases"] == 1 and report["duplicate_phrase_label_pairs"] == 1
    duplicate["label"] = "IRRELEVANT"
    _, report = validate_labeled_data(pd.concat([frame, duplicate], ignore_index=True))
    assert not report["valid"] and report["conflicting_labels"]

def test_minimum_samples_and_explicit_irrelevant_class(labeled):
    frame = complete(labeled)
    _, report = validate_labeled_data(frame.iloc[:20])
    assert not report["valid"]
    frame.loc[frame.label.eq("Soft"), "label"] = "IRRELEVANT"
    _, excluded = validate_labeled_data(frame)
    _, included = validate_labeled_data(frame, include_irrelevant=True)
    assert not excluded["valid"] and included["valid"]
    assert included["class_distribution"]["IRRELEVANT"] == 15

def test_imbalance_warning_and_stratification_gate(labeled):
    frame = labeled.copy()
    frame["label"] = ["A"]*25 + ["B"]*5
    _, report = validate_labeled_data(frame)
    assert report["valid"] and any("imbalanced" in w for w in report["warnings"])
    frame["label"] = [f"Class {i//5}" for i in range(30)]
    _, report = validate_labeled_data(frame, test_size=.1)
    assert not report["valid"] and any("partitions" in error for error in report["errors"])

def test_file_hash_tracks_exact_bytes(tmp_path, labeled):
    path = tmp_path / "labels.csv"
    complete(labeled).to_csv(path, index=False)
    first = labeled_file_hash(path)
    assert labeled_file_hash(path) == first
    path.write_bytes(path.read_bytes() + b"\n")
    assert labeled_file_hash(path) != first
