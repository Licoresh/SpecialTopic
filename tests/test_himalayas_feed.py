import json

from src.himalayas_feed import fetch_philippines_jobs


def test_himalayas_import_fetches_one_page_filters_and_appends_idempotently(tmp_path):
    calls = []
    payload = {
        "totalCount": 99,
        "jobs": [
            {"guid": "https://himalayas.app/job/1", "title": "PH data analyst", "companyName": "A",
             "locationRestrictions": ["Philippines"], "description": "Analyze data", "pubDate": "today"},
            {"guid": "https://himalayas.app/job/2", "title": "Worldwide engineer", "companyName": "B",
             "locationRestrictions": [], "description": "Build software"},
            {"guid": "https://himalayas.app/job/3", "title": "US-only engineer", "companyName": "C",
             "locationRestrictions": ["United States"], "description": "Build software"},
        ],
    }

    def request_get(url, timeout):
        calls.append((url, timeout))
        return json.dumps(payload).encode()

    first = fetch_philippines_jobs(tmp_path, request_get=request_get)
    second = fetch_philippines_jobs(tmp_path, request_get=request_get)

    assert len(calls) == 2
    assert all("country=PH" in url and "page=1" in url for url, _ in calls)
    assert first["response_rows"] == 3
    assert first["explicit_philippines_eligible_rows"] == 1
    assert first["new_rows_added"] == 1
    assert second["new_rows_added"] == 0
    assert second["total_saved_rows"] == 1
    assert second["training_labels_created"] == second["models_trained"] == 0

    import pandas as pd
    frame = pd.read_csv(tmp_path / "train/remote_feeds/himalayas_ph_jobs.csv", dtype=str, keep_default_na=False)
    assert len(frame) == 1
    assert frame.iloc[0].location == "Remote; Philippines"
    assert frame.iloc[0].url == "https://himalayas.app/job/1"


def test_himalayas_import_rejects_invalid_page(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="positive integer"):
        fetch_philippines_jobs(tmp_path, page=0, request_get=lambda *_args, **_kwargs: b"{}")
