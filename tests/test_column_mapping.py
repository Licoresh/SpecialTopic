import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src.column_mapping import suggest_column_mapping
from src.config import FIELDS
from src import storage

@pytest.mark.parametrize("kind", list(FIELDS))
def test_standard_columns_and_formatting(kind):
    columns = [field.replace("_", " ").title() for field in FIELDS[kind]]
    mapping, _ = suggest_column_mapping(columns, kind)
    assert list(mapping.values()) == columns

def test_job_pack_aliases_and_ambiguity():
    columns = ["job_id", "job_title", "company", "posted_date", "source_url", "skills_summary", "education_requirements_summary", "education_level", "experience_summary"]
    mapping, evidence = suggest_column_mapping(columns, "jobs")
    assert mapping["posting_date"] == "posted_date"
    assert mapping["url"] == "source_url"
    assert mapping["required_skills"] == "skills_summary"
    assert mapping["experience_requirement"] == "experience_summary"
    assert mapping["education_requirement"] == ""
    assert any(row["field"] == "education_requirement" and row["status"].startswith("Ambiguous") for row in evidence)
    assert len([v for v in mapping.values() if v]) == len(set(v for v in mapping.values() if v))

def test_philjobnet_headers_keep_research_metadata():
    columns = ["job_id", "job_title", "company", "salary", "location", "education_level",
               "employment_type", "posting_date", "job_description", "qualifications", "industry",
               "employment_size", "source_url", "search_term", "collected_at_utc"]
    mapping, _ = suggest_column_mapping(columns, "jobs")
    assert mapping["job_title"] == "job_title"
    assert mapping["job_description"] == "job_description"
    assert mapping["education_requirement"] == "education_level"
    assert mapping["url"] == "source_url"
    assert mapping["salary"] == "salary"
    assert mapping["employment_size"] == "employment_size"
    assert mapping["search_term"] == "search_term"
    assert mapping["collected_at_utc"] == "collected_at_utc"

def test_fuzzy_unknown_and_saved_overrides():
    mapping, evidence = suggest_column_mapping(["Job Descriptino", "Position", "Mystery", "Role"], "jobs")
    assert mapping["job_description"] == "Job Descriptino"
    assert mapping["job_title"] == ""
    assert "Mystery" not in mapping.values()
    saved, _ = suggest_column_mapping(["Position", "Role"], "jobs", {"job_title": "Role", "location": "Old missing column"})
    assert saved["job_title"] == "Role" and saved["location"] == ""

def test_ui_prefills_saves_and_redetects(workspace):
    raw = b"Position,Details,Skills,Posted Date,Source URL\nAnalyst,Uses SQL,Python,2026-10-01,https://example.test"
    storage.archive_raw(raw, "jobs.csv", "jobs")
    app = AppTest.from_string("from src.ui import column_mapping\ncolumn_mapping()").run(timeout=60)
    assert not app.exception and not app.error
    boxes = {box.label:box for box in app.selectbox}
    assert boxes["Job Title"].value == "Position"
    assert boxes["Job Description"].value == "Details"
    assert boxes["Posting Date"].value == "Posted Date"
    boxes["Job Description"].select("")
    next(button for button in app.button if button.label == "Save mapping").click().run(timeout=60)
    assert storage.read_json("mapping_jobs")["job_description"] == ""
    assert storage.read_json("mapping_audit_jobs")["dataset_hash"]
    next(button for button in app.button if button.label == "Re-detect columns").click().run(timeout=60)
    assert next(box for box in app.selectbox if box.label == "Job Description").value == "Details"
    assert storage.read_json("mapping_jobs")["job_description"] == ""

def test_ui_applies_automatic_mapping(workspace):
    raw = b"job_title,job_description,location,source_url,salary,employment_size\nAnalyst,Uses SQL,Manila,https://example.test,PHP 50000,10-99"
    storage.archive_raw(raw, "philjobnet_jobs.csv", "jobs")
    app = AppTest.from_string("from src.ui import column_mapping\ncolumn_mapping()").run(timeout=60)
    assert not app.exception and not app.error
    next(button for button in app.button if button.label == "Apply automatic mapping").click().run(timeout=60)
    assert not app.exception and not app.error
    assert storage.read_json("mapping_jobs")["url"] == "source_url"
    mapped = storage.read_frame("mapped_jobs")
    assert mapped.loc[0, "salary"] == "PHP 50000"
    assert mapped.loc[0, "employment_size"] == "10-99"
