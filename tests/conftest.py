"""SYNTHETIC DATA — NOT RESEARCH DATA. All fixtures are confined to tests."""
import pandas as pd
import pytest
from src.loaders import map_columns
from src.cleaning import clean_dataset

@pytest.fixture(autouse=True)
def keep_tests_off_real_supabase(monkeypatch):
    """Tests use synthetic fixtures only and must never touch the live project."""
    from src import supabase_store
    monkeypatch.setattr(supabase_store, "configured", lambda: False)

def prepared(rows, kind, suffix="synthetic"):
    raw = pd.DataFrame(rows).fillna("")
    mapped = map_columns(raw, {c:c for c in raw}, kind, suffix)
    return clean_dataset(mapped, kind)[0]

@pytest.fixture
def jobs():
    return prepared([
        {"job_title": "Synthetic analyst", "job_description": "Python, SQL, machine learning and communication skills.", "company": "SYNTHETIC DATA — NOT RESEARCH DATA", "posting_date": "2025-01-05"},
        {"job_title": "Synthetic developer", "job_description": "Python and C++ with data visualization.", "posting_date": "invalid"},
        {"job_title": "Synthetic analyst", "job_description": "SQL; critical thinking; data analysis.", "posting_date": "2025-02-01"},
    ], "jobs")

@pytest.fixture
def taxonomy():
    # This testing taxonomy is deliberately fictional; not an official PSF-AAI source.
    return prepared([
        {"competency_id": "TEST-1", "competency_name": "Python", "competency_category": "Technical / Digital", "aliases": "Python programming", "job_role": "Synthetic analyst", "proficiency_level": "Test level"},
        {"competency_id": "TEST-2", "competency_name": "SQL", "competency_category": "Data / Analytics"},
        {"competency_id": "TEST-3", "competency_name": "machine learning", "competency_category": "AI / Machine Learning", "aliases": "ML"},
        {"competency_id": "TEST-4", "competency_name": "communication skills", "competency_category": "Soft / Enabling"},
        {"competency_id": "TEST-5", "competency_name": "data analysis", "competency_category": "Data / Analytics"},
    ], "psf_aai")

@pytest.fixture
def labeled():
    terms = {"Technical": ["python programming", "java programming", "sql querying", "docker deployment", "linux systems", "python scripts", "java software", "sql databases", "cloud deployment", "linux administration"],
             "Soft": ["team communication", "critical thinking", "problem solving", "team collaboration", "public speaking", "clear communication", "analytical thinking", "creative solving", "cross team collaboration", "public presentation"]}
    terms["Technical"] += ["database indexing", "software testing", "container orchestration", "version control", "network configuration"]
    terms["Soft"] += ["active listening", "conflict resolution", "time management", "team negotiation", "decision making"]
    result = pd.DataFrame([{"phrase": phrase, "label": label} for label, phrases in terms.items() for phrase in phrases])
    result["source_type"] = "Philippine job advertisement"
    result["source_id"] = [f"SYNTHETIC-TEST-{index}" for index in range(len(result))]
    return result

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from src import storage, workflow, labeling
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(workflow, "ROOT", tmp_path)
    monkeypatch.setattr(labeling, "ROOT", tmp_path)
    storage.initialize()
    yield tmp_path
    # Background work must finish before temporary roots and network guards reset.
    import threading
    for thread in threading.enumerate():
        if thread.name == "research-processing":
            thread.join(timeout=60)
            assert not thread.is_alive(), "Test worker did not stop inside its isolated workspace"
