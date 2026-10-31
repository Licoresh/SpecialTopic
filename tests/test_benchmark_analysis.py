"""Synthetic benchmark verification; not research timing or model evaluation."""
import pandas as pd
import pytest
from scripts.benchmark_analysis import benchmark


def test_benchmark_reports_real_sizes_and_preserves_input(jobs, taxonomy):
    original = jobs.copy(deep=True)
    reference = taxonomy.copy(deep=True)
    report = benchmark(jobs, taxonomy, sizes=[2, 20, 100], max_candidates=20)
    assert [row["input_rows"] for row in report["observations"]] == [2, 3]
    for row in report["observations"]:
        assert row["retained_unique_ads"] == row["input_rows"]
        assert row["figure_json_bytes"] > 0
        assert all(seconds >= 0 for seconds in row["stage_seconds"].values())
        assert "no classifier supplied" in row["classifier"]
        assert "classifier_inference_only" not in row["stage_seconds"]
    pd.testing.assert_frame_equal(jobs, original)
    pd.testing.assert_frame_equal(taxonomy, reference)
    assert any("browser" in item for item in report["conditions"])


def test_benchmark_identifies_duplicates_without_removing_input_rows(jobs):
    duplicate = jobs.iloc[[0]].copy()
    duplicate["source_id"] = "SYNTHETIC-DUPLICATE"
    repeated = pd.concat([jobs, duplicate], ignore_index=True)
    original = repeated.copy(deep=True)
    row = benchmark(repeated, pd.DataFrame(), sizes=[4], max_candidates=5)["observations"][0]
    assert row["duplicate_candidates"] == 1
    assert row["retained_unique_ads"] == 4
    assert row["input_rows"] == 4
    pd.testing.assert_frame_equal(repeated, original)
    assert row["reference"] == "unavailable"


@pytest.mark.parametrize("sizes", [[0], [-1], [1.5]])
def test_benchmark_rejects_invalid_sizes(jobs, sizes):
    with pytest.raises(ValueError, match="positive whole"):
        benchmark(jobs, pd.DataFrame(), sizes=sizes)
