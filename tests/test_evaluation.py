import numpy as np
import pytest
from src.evaluation import evaluate_model

def test_metrics_use_predictions():
    class Model:
        classes_ = np.array(["A", "B"])
        def predict(self, values):
            return np.array(["A", "A", "B", "B"])
    result = evaluate_model(Model(), ["1","2","3","4"], ["A","B","B","B"])
    assert result["metrics"]["accuracy"] == .75
    assert result["metrics"]["macro_precision"] == .75
    assert result["metrics"]["macro_recall"] == pytest.approx(5/6)
    assert result["metrics"]["macro_f1"] == pytest.approx((2/3 + .8)/2)
    assert result["confusion"].values.tolist() == [[1,0],[1,2]]
