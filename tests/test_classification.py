import pandas as pd
import pytest
from src.classification import compare_models, save_model, load_model, predict_category
from src.training_data import source_disjoint_split

def test_models_reproducible_persistence(labeled, tmp_path):
    first = compare_models(labeled)
    second = compare_models(labeled)
    assert len(first) == 2
    for name, result in first.items():
        assert result["metrics"] == second[name]["metrics"]
        assert set(result["split"]["train_phrases"]).isdisjoint(result["split"]["test_phrases"])
        assert set(result["split"]["train_source_ids"]).isdisjoint(result["split"]["test_source_ids"])
        assert result["metrics"]["cv_folds"] >= 3
        path = tmp_path / "model.joblib"
        save_model(result["model"], path)
        reloaded = load_model(path)
        pred = predict_category(reloaded, ["python software", "team communication"])
        assert pred.predicted_category.tolist() == result["model"].predict(pred.phrase).tolist()
        assert pred.probability.between(0,1).all()

def test_source_holdout_fails_when_categories_cannot_be_represented_in_both_partitions():
    data = pd.DataFrame({"text": ["a1", "a2", "b1", "b2"],
                         "label": ["A", "A", "B", "B"],
                         "source_id": ["ad-a", "ad-a", "ad-b", "ad-b"]})
    with pytest.raises(ValueError, match="No source-disjoint holdout"):
        source_disjoint_split(data, .25)

@pytest.mark.parametrize("rows", [[("a","one")], [("a","one"),("b","two")], [("same","one"),("SAME","two")]])
def test_invalid_training(rows):
    with pytest.raises(ValueError):
        compare_models(pd.DataFrame(rows, columns=["phrase", "label"]))

def test_invalid_model(tmp_path):
    path = tmp_path / "bad.joblib"
    path.write_text("invalid")
    with pytest.raises(ValueError):
        load_model(path)
