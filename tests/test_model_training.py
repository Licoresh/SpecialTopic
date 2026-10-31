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

def test_selection_uses_training_cv_and_ignores_all_holdout_scores():
    results = {
        "better holdout": {"metrics": {"cv_folds": 5, "cv_macro_f1_mean": .5,
            "cv_weighted_f1_mean": .95, "cv_macro_f1_std": .01,
            "accuracy": .99, "macro_f1": .99, "weighted_f1": .99}},
        "better CV": {"metrics": {"cv_folds": 5, "cv_macro_f1_mean": .7,
            "cv_weighted_f1_mean": .7, "cv_macro_f1_std": .02,
            "accuracy": .4, "macro_f1": .4, "weighted_f1": .4}},
    }
    assert select_best_model(results) == "better CV"
    for result in results.values():
        for key in ("accuracy", "macro_f1", "weighted_f1"):
            result["metrics"].pop(key)
    assert select_best_model(results) == "better CV"
    results["better holdout"]["metrics"]["cv_macro_f1_mean"] = .7
    assert select_best_model(results) == "better holdout"  # weighted CV breaks the tie
    results["better holdout"]["metrics"]["cv_weighted_f1_mean"] = .7
    assert select_best_model(results) == "better holdout"  # lower CV variation
    results["better holdout"]["metrics"]["cv_macro_f1_std"] = .02
    assert select_best_model(results) == "better holdout"  # stable original order


@pytest.mark.parametrize("key,value", [
    ("cv_macro_f1_mean", None), ("cv_macro_f1_mean", float("nan")),
    ("cv_weighted_f1_mean", float("inf")), ("cv_macro_f1_std", None),
    ("cv_folds", 1),
])
def test_selection_cannot_fall_back_to_holdout(key, value):
    metrics = {"cv_folds": 5, "cv_macro_f1_mean": .7,
               "cv_weighted_f1_mean": .7, "cv_macro_f1_std": .02,
               "macro_f1": 1., "weighted_f1": 1.}
    metrics[key] = value
    with pytest.raises(ValueError, match="Training-only cross-validation is unavailable"):
        select_best_model({"candidate": {"metrics": metrics}})


def test_selection_is_fixed_before_holdout_is_scored(labeled, monkeypatch):
    from src import classification
    original_select = classification.select_best_model
    original_evaluate = classification.evaluate_model
    selected = []
    tested = []
    def select(results):
        assert not tested
        assert all("macro_f1" not in result["metrics"] for result in results.values())
        winner = original_select(results)
        selected.append(winner)
        return winner
    def evaluate(model, text, labels):
        assert selected
        tested.append(model.research_model_name_)
        result = original_evaluate(model, text, labels)
        result["metrics"]["macro_f1"] = 0. if model.research_model_name_ == selected[0] else 1.
        return result
    monkeypatch.setattr(classification, "select_best_model", select)
    monkeypatch.setattr(classification, "evaluate_model", evaluate)
    results = compare_models(labeled)
    assert len(tested) == 2 and len(selected) == 1
    assert [name for name, result in results.items() if result["selected"]] == selected
    assert original_select(results) == selected[0]
    assert results[selected[0]]["metrics"]["macro_f1"] == 0.


def test_labeled_csv_train_save_load_predict(workspace, labeled):
    save_annotations(labeled, "SYNTHETIC TEST REVIEWER")
    path = workspace / "train/labeled_competencies.csv"
    original = path.read_bytes()
    assert len(load_labeled_data(path)) == 30
    progress = []
    metadata, comparison = train_and_save_models(progress=lambda value,message: progress.append(value))
    assert progress == [0., .5, 1.]
    assert comparison.selected.sum() == 1
    winner = comparison.loc[comparison.selected].iloc[0]
    assert metadata["macro_f1"] == winner.macro_f1
    assert metadata["model_name"] == winner.model
    assert metadata["selection_basis"] == "training_cross_validation"
    assert metadata["refit_on_holdout"] is False
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


def test_unavailable_cv_preserves_saved_models_and_never_scores_holdout(workspace, labeled, monkeypatch):
    from src import classification
    import numpy as np
    save_annotations(labeled, "SYNTHETIC TEST REVIEWER")
    train_and_save_models()
    paths = list((workspace / "models").glob("*")) + list((workspace / "outputs/tables").glob("*"))
    original = {path: path.read_bytes() for path in paths if path.is_file()}
    monkeypatch.setattr(classification, "cross_validate", lambda *args, **kwargs: {
        "test_" + metric: np.array([float("nan")])
        for metric in ("macro_f1", "weighted_f1", "accuracy")
    })
    with patch.object(classification, "evaluate_model") as evaluate:
        with pytest.raises(ValueError, match="Holdout scores cannot select a model"):
            train_and_save_models()
        evaluate.assert_not_called()
    assert all(path.read_bytes() == contents for path, contents in original.items())
