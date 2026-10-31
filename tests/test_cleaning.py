import pandas as pd
import pytest
from src.cleaning import clean_text, normalize_text, normalize_url, clean_dataset, duplicate_ids, analysis_jobs, analysis_job_values
from src.loaders import map_columns

def test_meaningful_characters():
    assert clean_text("<p>C++ &amp; C# .NET R SQL Power BI</p>\n") == "C++ & C# .NET R SQL Power BI"
    assert normalize_text("  PYTHON\t SQL ") == "python sql"
    assert normalize_url("HTTPS://Example.COM/a?q=1#fragment") == "https://example.com/a?q=1"

def test_duplicates_missing_dates_and_preservation():
    raw = pd.DataFrame({"job_description": ["<b>Python</b>", "<b>Python</b>", ""], "posting_date": ["bad", "bad", "2025-01-01"]})
    mapped = map_columns(raw, {c:c for c in raw}, "jobs", "abc")
    duplicates = duplicate_ids(mapped)
    assert len(duplicates) == 1
    clean, report = clean_dataset(mapped, "jobs", duplicates)
    assert len(clean) == 2 and len(mapped) == 3
    assert clean.job_description.iloc[0] == "<b>Python</b>"
    assert clean.job_description_clean.iloc[0] == "python"
    assert clean.posting_date_parsed.iloc[0] == ""
    assert clean.empty_job_description.sum() == 1
    assert report.set_index("check").loc["invalid_posting_dates", "count"] == 1
    with pytest.raises(ValueError):
        clean_dataset(mapped, "jobs", [mapped.source_id.iloc[0]])

def test_education_experience_extraction():
    raw = pd.DataFrame({"job_description": ["Bachelor’s degree. At least 3-5 years of relevant work experience."]})
    mapped = map_columns(raw, {"job_description":"job_description"}, "jobs", "test")
    clean, _ = clean_dataset(mapped, "jobs")
    assert "bachelor" in clean.education_detected.iloc[0]
    assert clean.experience_detected.iloc[0] == "3-5 years of relevant work experience"


def test_job_cleaning_lowercases_analysis_but_preserves_source_identity():
    raw = pd.DataFrame({"job_id": ["JOB-AbC"], "job_title": ["DATA Analyst"],
                        "company": ["ACME PH"], "location": ["Cebu, Philippines"],
                        "job_description": ["C++ C# .NET R SQL Power BI"],
                        "posting_date": ["2026-10-30"],
                        "url": ["https://Example.test/Jobs/AbC?Token=XyZ"],
                        "collected_at_utc": ["2026-10-30T01:00:00Z"]})
    mapped = map_columns(raw, {field: field for field in raw}, "jobs", "MixedHASH")
    before = mapped.copy(deep=True)
    cleaned, _ = clean_dataset(mapped, "jobs")
    for field in ("job_title", "company", "location", "job_description"):
        assert cleaned[field + "_clean"].iloc[0] == normalize_text(mapped[field].iloc[0])
    assert cleaned.job_description_clean.iloc[0] == "c++ c# .net r sql power bi"
    assert cleaned.job_id_clean.iloc[0] == "JOB-AbC"
    assert cleaned.url_clean.iloc[0] == "https://example.test/Jobs/AbC?Token=XyZ"
    assert cleaned.collected_at_utc_clean.iloc[0] == "2026-10-30T01:00:00Z"
    assert cleaned.source_id.tolist() == mapped.source_id.tolist()
    assert "DATA Analyst" in cleaned.original_text.iloc[0]
    pd.testing.assert_frame_equal(mapped, before)
    pd.testing.assert_frame_equal(cleaned[mapped.columns], mapped)
    recleaned, _ = clean_dataset(cleaned, "jobs")
    assert set(recleaned.columns) == set(cleaned.columns)
    assert not any(field.endswith("_clean_clean") for field in recleaned)
    pd.testing.assert_frame_equal(recleaned, cleaned)


def test_existing_job_analysis_fields_refresh_without_reupload_or_raw_mutation():
    jobs = pd.DataFrame({"source_id": ["Jobs:MixedCase:2"], "job_title": ["DATA ANALYST"],
                         "job_title_clean": ["DATA ANALYST"], "job_description": ["SQL & Python"],
                         "original_text": ["EXACT RAW EVIDENCE"], "source_hash": ["MixedHash"],
                         "url": ["https://example.test/Jobs/AbC"], "posting_date": ["2026-10-30"]})
    before = jobs.copy(deep=True)
    refreshed = analysis_jobs(jobs)
    assert refreshed.job_title_clean.iloc[0] == "data analyst"
    assert refreshed.job_description_clean.iloc[0] == "sql & python"
    assert refreshed.cleaned_text.iloc[0] == "data analyst\nsql & python"
    for field in ("source_id", "job_title", "job_description", "original_text", "source_hash", "url", "posting_date"):
        pd.testing.assert_series_equal(refreshed[field], jobs[field])
    pd.testing.assert_frame_equal(jobs, before)


def test_psf_cleaning_keeps_official_source_case_and_codes():
    raw = pd.DataFrame({"competency_id": ["FSC-ABC"], "competency_name": ["Data Design"],
                        "competency_description": ["Design SQL Data Models"]})
    mapped = map_columns(raw, {field: field for field in raw}, "psf_aai", "TestHash")
    cleaned, _ = clean_dataset(mapped, "psf_aai")
    assert cleaned.competency_id_clean.iloc[0] == "FSC-ABC"
    assert cleaned.competency_name_clean.iloc[0] == "Data Design"
    pd.testing.assert_frame_equal(cleaned[mapped.columns], mapped)


def test_normalized_job_values_export_only_schema_and_preserve_machine_identity():
    from src.config import FIELDS
    jobs = pd.DataFrame({"source_id": ["Jobs:MixedCase:2"], "job_id": ["Job-AbC"],
                         "job_id_clean": ["wrong-old-derived-id"],
                         "job_title": ["DATA ANALYST"], "job_description": ["SQL & Python"],
                         "original_text": ["EXACT RAW EVIDENCE"], "source_hash": ["MixedHash"],
                         "url": ["https://Example.test/Jobs/AbC?ID=XyZ"],
                         "url_clean": ["https://example.test/Jobs/AbC?ID=XyZ"],
                         "posting_date": ["2026-10-30"], "collected_at_utc": ["2026-10-30T01:00:00Z"]})
    before = jobs.copy(deep=True)
    values = analysis_job_values(jobs)
    assert values.columns.tolist() == ["source_id", *FIELDS["jobs"]]
    assert values.job_title.iloc[0] == "data analyst"
    assert values.job_description.iloc[0] == "sql & python"
    assert values.url.iloc[0] == "https://example.test/Jobs/AbC?ID=XyZ"
    assert values.job_id.iloc[0] == "Job-AbC"
    for field in ("source_id", "posting_date", "collected_at_utc"):
        pd.testing.assert_series_equal(values[field], jobs[field])
    pd.testing.assert_frame_equal(jobs, before)
