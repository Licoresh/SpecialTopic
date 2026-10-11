import pandas as pd
import pytest
from src.cleaning import clean_text, normalize_text, normalize_url, clean_dataset, duplicate_ids
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
    assert clean.job_description_clean.iloc[0] == "Python"
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
