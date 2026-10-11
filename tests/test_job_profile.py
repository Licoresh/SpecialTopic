"""SYNTHETIC DATA — NOT RESEARCH DATA; tests job-ad profile summaries."""

import pandas as pd

from src.job_profile import job_profile_tables
from src.reporting import export_research_report


def test_profile_counts_unique_ads_and_keeps_source_family():
    jobs = pd.DataFrame([
        {"source_id": "SYNTHETIC-1", "job_title": "Data Analyst", "job_family": "Analytics",
         "education_requirement": "Bachelor's degree", "experience_requirement": "2 years"},
        {"source_id": "SYNTHETIC-1", "job_title": "Data Analyst", "job_family": "Analytics",
         "education_requirement": "Bachelor's degree", "experience_requirement": "2 years"},
        {"source_id": "SYNTHETIC-2", "job_title": "Data Analyst", "job_family": "Analytics",
         "education_requirement": "", "experience_requirement": ""},
    ])
    tables = job_profile_tables(jobs)
    title = tables["job_title_counts"].iloc[0]
    assert title.job_title == "Data Analyst" and title.job_ads == 2 and title.job_ads_pct == 100
    family = tables["job_family_counts"].iloc[0]
    assert family.job_family == "Analytics" and family.job_ads == 2 and family.job_ads_pct == 100
    requirements = tables["education_requirement_counts"].set_index("requirement")
    assert requirements.loc["Bachelor's degree", "job_ads"] == 1
    assert requirements.loc["Bachelor's degree", "job_ads_pct"] == 50
    assert requirements.loc["Not stated", "job_ads"] == 1


def test_text_matches_are_candidate_evidence_and_not_inferred_into_explicit_counts():
    jobs = pd.DataFrame([{
        "source_id": "SYNTHETIC-3", "job_title": "Synthetic Analyst", "job_family": "",
        "education_requirement": "", "experience_requirement": "",
        "qualifications": "Bachelor's degree required; 3 years of relevant experience required.",
        "job_description": "Synthetic posting.", "url": "https://example.invalid/synthetic-3",
    }])
    tables = job_profile_tables(jobs)
    assert tables["education_requirement_counts"].iloc[0].requirement == "Not stated"
    evidence = tables["requirement_evidence"]
    assert set(evidence.requirement_type) == {"Education", "Experience"}
    assert evidence.evidence_status.eq("Text mention candidate; researcher should verify context").all()
    assert evidence.source_id.eq("SYNTHETIC-3").all()
    assert evidence.url.eq("https://example.invalid/synthetic-3").all()


def test_written_report_is_scoped_and_flags_researcher_review():
    report = export_research_report(
        {"job_title_counts": pd.DataFrame([{"job_title": "Synthetic Analyst", "job_ads": 1}])},
        {"dataset_counts": {"jobs": 1, "psf_competencies": 2}, "timestamp": "test-time",
         "limitations": "Synthetic test limitations."},
    ).decode("utf-8")
    assert "TESDA PSF-AAI" in report
    assert "does not analyze curricula" in report
    assert "Researcher review is required" in report
    assert "Synthetic Analyst" in report
    assert "Synthetic test limitations." in report
