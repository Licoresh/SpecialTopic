"""SYNTHETIC DATA — NOT RESEARCH DATA; all outputs stay in tmp_path."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src import training_sources, storage
from src.posting_import import prepare_posting_candidates, file_sha256
from src.training_sources import inspect_training_folder, training_candidates, resolve_training_file


def postings(root, locations=("Manila, AR", "Philippines", "New York, NY", "Makati, Philippines", "", "Manila")):
    folder = root / "train/postings.csv"
    folder.mkdir(parents=True)
    path = folder / "postings.csv"
    pd.DataFrame([{"job_id": f"SYNTHETIC-{i}", "title": "Synthetic analyst", "company_name": "SYNTHETIC DATA",
                   "description": "Python and SQL.\nCommunication skills and data analysis.", "location": location,
                   "skills_desc": "SQL", "formatted_work_type": "Full-time", "formatted_experience_level": "Entry level",
                   "job_posting_url": f"https://example.test/{i}"} for i, location in enumerate(locations)]).to_csv(path, index=False)
    return path


def test_chunked_import_preserves_provenance_and_never_labels(workspace):
    path = postings(workspace)
    original = path.read_bytes()
    label_path = resolve_training_file(workspace)
    original_labels = label_path.read_bytes()
    report = prepare_posting_candidates(workspace, "postings.csv/postings.csv", chunksize=1)
    assert report["total_postings"] == 6 and report["explicit_philippine_postings"] == 2
    assert report["excluded_without_explicit_philippine_location"] == 4
    assert report["source_sha256"] == file_sha256(path)
    assert report["reviewed_labels_created"] == 0 and not report["model_trained"]
    assert report["mapping"]["url"] == "job_posting_url"
    assert report["mapping"]["required_skills"] == "skills_desc"
    assert report["mapping"]["employment_type"] == "formatted_work_type"
    assert report["mapping"]["experience_requirement"] == "formatted_experience_level"
    candidates = training_candidates(workspace)
    assert candidates.source_id.nunique() == 2 and len(candidates) > 0
    assert set(candidates.source_record) == {"3", "5"}  # Original CSV records, not subset offsets.
    assert set(candidates.source_url) == {"https://example.test/1", "https://example.test/3"}
    assert candidates.original_text.str.contains("Python").all()
    assert candidates[["label", "reviewer", "timestamp", "psf_competency"]].eq("").all().all()
    candidate_path = workspace / "train" / report["candidate_file"]
    candidate_bytes = candidate_path.read_bytes()
    prepare_posting_candidates(workspace, "postings.csv/postings.csv", chunksize=3)
    assert candidate_path.read_bytes() == candidate_bytes
    assert len(training_candidates(workspace)) == len(candidates)
    assert path.read_bytes() == original and label_path.read_bytes() == original_labels
    assert not list((workspace / "models").glob("*.joblib"))


def test_inventory_does_not_load_posting_table(workspace, monkeypatch):
    postings(workspace)
    def forbidden(*args):
        raise AssertionError("Inventory must stream CSVs, not load entire tables")
    monkeypatch.setattr(training_sources, "read_source_table", forbidden)
    item = inspect_training_folder(workspace)[0]
    assert item["rows"] == 6 and item["purpose"] == "job-ad source data"
    assert not item["error"]


def test_no_explicit_ph_locations_creates_no_candidates(workspace):
    postings(workspace, ("Manila, AR", "", "Manila"))
    report = prepare_posting_candidates(workspace, "postings.csv/postings.csv")
    assert report["explicit_philippine_postings"] == report["candidate_occurrences"] == 0
    assert training_candidates(workspace).empty
    assert storage.read_frame("labeled_competencies").empty


def test_himalayas_source_id_is_stable_when_feed_file_grows(workspace):
    path = workspace / "train/remote_feeds/himalayas_ph_jobs.csv"
    path.parent.mkdir(parents=True)
    row = {"job_id": "https://himalayas.app/jobs/example", "job_title": "Data Analyst", "company": "Example",
           "location": "Remote; Philippines", "job_description": "SQL and data analysis", "url": "https://himalayas.app/jobs/example",
           "source": "Himalayas (public remote jobs API)", "posting_date": "2026-10-10"}
    pd.DataFrame([row]).to_csv(path, index=False)
    first = prepare_posting_candidates(workspace, "remote_feeds/himalayas_ph_jobs.csv")
    first_candidates = pd.read_csv(workspace / "train" / first["candidate_file"], dtype=str, keep_default_na=False)
    first_id = first_candidates.iloc[0].source_id

    row["job_description"] += "; communication skills"
    pd.DataFrame([row]).to_csv(path, index=False)
    second = prepare_posting_candidates(workspace, "remote_feeds/himalayas_ph_jobs.csv")
    second_candidates = pd.read_csv(workspace / "train" / second["candidate_file"], dtype=str, keep_default_na=False)
    assert first_id == "jobs:himalayas:https://himalayas.app/jobs/example"
    assert set(second_candidates.source_id) == {first_id}


def test_missing_mapping_and_outside_source_rejected(workspace):
    path = postings(workspace)
    pd.DataFrame([{"title": "SYNTHETIC", "description": "SQL"}]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="location"):
        prepare_posting_candidates(workspace, "postings.csv/postings.csv")
    with pytest.raises(ValueError, match="within"):
        prepare_posting_candidates(workspace, "../../outside.csv")


def test_manual_labeling_import_action_and_training_gate(workspace):
    postings(workspace)
    # AppTest does not round-trip expander state when a child button is clicked.
    app = AppTest.from_string(
        "import streamlit as st\nst.session_state['review_source_tools'] = True\n"
        "from src.ui import render\nrender('Manual Labeling')"
    ).run(timeout=60)
    next(button for button in app.button if button.label == "Prepare Philippine posting candidates").click().run(timeout=60)
    assert not app.exception and not app.error
    assert any("Labels remain blank" in message.value for message in app.success)
    assert any("derived" in str(widget.options) for widget in app.multiselect)
    assert storage.read_frame("labeled_competencies").empty
    training = AppTest.from_string("from src.ui import render\nrender('ML Training')").run(timeout=60)
    assert not training.exception and not training.error
    assert next(button for button in training.button if button.label == "Train / Retrain Models").disabled
    assert not list((workspace / "models").glob("*.joblib"))


def test_malformed_csv_is_reported(workspace):
    path = postings(workspace)
    path.write_text("title,description,location\nSynthetic,SQL,Philippines,unexpected\n", encoding="utf-8")
    item = inspect_training_folder(workspace)[0]
    assert item["purpose"] == "unreadable table" and "fields" in item["error"]
    with pytest.raises(ValueError, match="fields"):
        prepare_posting_candidates(workspace, "postings.csv/postings.csv")
