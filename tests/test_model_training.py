"""SYNTHETIC DATA — NOT RESEARCH DATA. Fitted test artifacts use temporary directories only."""
import json
from unittest.mock import patch
import pandas as pd
import pytest
from src.classification import (compare_models, select_best_model, cached_load_model,
                                predict_competency_category, MODEL_FILES, VECTORIZER_CONFIG)
from src.model_training import train_and_save_models, training_data_changed
from src.labeling import save_annotations
from src.training_data import load_labeled_data, labeled_file_hash

def test_pipeline_configuration_and_three_cv_metrics(labeled):
    results = compare_models(labeled)
    for name, result in results.items():
        model = result["model"]
        params = model.named_steps["tfidf"].get_params()
        assert all(params[key] == value for key,value in VECTORIZER_CONFIG.items())
        assert 2 <= result["metrics"]["cv_folds"] <= 5
        for metric in ("macro_f1", "weighted_f1", "accuracy"):
            assert 0 <= result["metrics"][f"cv_{metric}_mean"] <= 1
            assert result["metrics"][f"cv_{metric}_std"] >= 0
        if name == "Logistic Regression":
            assert model.named_steps["classifier"].class_weight == "balanced"
            assert model.named_steps["classifier"].max_iter == 1000

def test_selection_prioritizes_macro_f1_not_accuracy():
    per_class = pd.DataFrame({"f1-score":[.4,.6]})
    results = {
        "higher accuracy": {"metrics":{"accuracy":.99,"macro_f1":.5,"weighted_f1":.95},"per_class":per_class},
        "higher macro": {"metrics":{"accuracy":.7,"macro_f1":.7,"weighted_f1":.7},"per_class":per_class},
    }
    assert select_best_model(results) == "higher macro"
    results["higher accuracy"]["metrics"]["macro_f1"] = .7
    assert select_best_model(results) == "higher accuracy"

def test_labeled_csv_train_save_load_predict(workspace, labeled):
    save_annotations(labeled, "SYNTHETIC TEST REVIEWER")
    path = workspace / "train/labeled_competencies.csv"
    original = path.read_bytes()
    assert len(load_labeled_data(path)) == 30
    progress = []
    metadata, comparison = train_and_save_models(progress=lambda value,message: progress.append(value))
    assert progress == [0., .5, 1.]
    assert comparison.selected.sum() == 1
    assert metadata["macro_f1"] == comparison.macro_f1.max()
    assert metadata["dataset_rows_used"] == 30 and metadata["train_size"] == 24 and metadata["test_size"] == 6
    assert metadata["training_data_hash"] == labeled_file_hash(path)
    assert metadata["software_versions"]["scikit-learn"]
    for filename in MODEL_FILES.values():
        assert (workspace/"models"/filename).exists()
    for filename in ("model_metrics.csv", "classification_report.csv", "confusion_matrix.csv", "model_comparison.csv", "test_predictions.csv"):
        assert not pd.read_csv(workspace/"outputs/tables"/filename).empty
    disk_metadata = json.loads((workspace/"models/model_metadata.json").read_text())
    assert disk_metadata["model_name"] == metadata["model_name"]
    assert metadata["training_file"] == str(path.resolve())
    assert metadata["training_file_hash"] == labeled_file_hash(path)
    prediction = predict_competency_category("Python programming", root=workspace)
    assert prediction["predicted_label"] in metadata["class_names"]
    assert 0 <= prediction["confidence_score"] <= 1
    assert prediction["model_name"] == metadata["model_name"]
    assert path.read_bytes() == original
    assert not training_data_changed()
    path.write_bytes(original + b"\n")
    assert training_data_changed()

def test_invalid_data_does_not_create_research_models(workspace):
    with pytest.raises(ValueError, match="30"):
        train_and_save_models()
    assert not list((workspace/"models").glob("*.joblib"))
    assert not list((workspace/"outputs/tables").glob("*.csv"))
    assert not (workspace/"models/model_metadata.json").exists()

def test_cached_prediction_loads_once(workspace, labeled):
    from src import classification
    save_annotations(labeled, "SYNTHETIC TEST REVIEWER")
    train_and_save_models()
    classification._cached_load_model.clear()
    original = classification.load_model
    with patch.object(classification, "load_model", wraps=original) as loader:
        predict_competency_category("Python", root=workspace)
        predict_competency_category("SQL", root=workspace)
        assert loader.call_count == 1
    with pytest.raises(ValueError, match="nonempty"):
        predict_competency_category(" ", root=workspace)

def test_changed_annotations_during_training_are_not_published(workspace, labeled):
    save_annotations(labeled, "SYNTHETIC TEST REVIEWER")
    path = workspace/"train/labeled_competencies.csv"
    def progress(value, message):
        if value == 1.:
            path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed during training"):
        train_and_save_models(progress=progress)
    assert not list((workspace/"models").glob("*.joblib"))
