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
    assert title.job_title == "data analyst" and title.job_ads == 2 and title.job_ads_pct == 100
    family = tables["job_family_counts"].iloc[0]
    assert family.job_family == "analytics" and family.job_ads == 2 and family.job_ads_pct == 100
    requirements = tables["education_requirement_counts"].set_index("requirement")
    assert requirements.loc["bachelor's degree", "job_ads"] == 1
    assert requirements.loc["bachelor's degree", "job_ads_pct"] == 50
    assert requirements.loc["not stated", "job_ads"] == 1


def test_text_matches_are_candidate_evidence_and_not_inferred_into_explicit_counts():
    jobs = pd.DataFrame([{
        "source_id": "SYNTHETIC-3", "job_title": "Synthetic Analyst", "job_family": "",
        "education_requirement": "", "experience_requirement": "",
        "qualifications": "Bachelor's degree required; 3 years of relevant experience required.",
        "job_description": "Synthetic posting.", "url": "https://example.invalid/synthetic-3",
    }])
    tables = job_profile_tables(jobs)
    assert tables["education_requirement_counts"].iloc[0].requirement == "not stated"
    evidence = tables["requirement_evidence"]
    assert set(evidence.requirement_type) == {"Education", "Experience"}
    assert set(evidence.evidence_status) == {
        "Text mention candidate; researcher should verify context",
        "Text evidence; researcher should verify context",
    }
    assert evidence.source_id.eq("SYNTHETIC-3").all()
    assert evidence.url.eq("https://example.invalid/synthetic-3").all()


def test_written_report_is_scoped_and_flags_researcher_review():
    report = export_research_report(
        {"job_title_counts": pd.DataFrame([{"job_title": "Synthetic Analyst", "job_ads": 1}]),
         "common_job_title_counts": pd.DataFrame([{"common_job_title": "business analyst", "job_ads": 1}])},
        {"dataset_counts": {"jobs": 1, "psf_competencies": 2}, "timestamp": "test-time",
         "limitations": "Synthetic test limitations."},
    ).decode("utf-8")
    assert "TESDA PSF-AAI" in report
    assert "## Context" in report and "## Approach" in report and "## Results" in report
    assert "does not analyze curricula" in report
    assert "Researcher review is required" in report
    assert "Synthetic Analyst" in report
    assert "business analyst" in report and "Most common normalized job titles" in report
    assert "Synthetic test limitations." in report


def test_presentation_variants_group_without_mutating_source_or_merging_roles():
    jobs = pd.DataFrame([
        {"source_id": "A", "job_title": "Data Analyst", "job_family": "Analytics", "education_requirement": "Bachelor's degree"},
        {"source_id": "B", "job_title": "  data\u00a0analyst  ", "job_family": "analytics", "education_requirement": "bachelor's degree"},
        {"source_id": "C", "job_title": "Data Engineer", "job_family": "Engineering", "education_requirement": "N/A"},
    ])
    original = jobs.copy(deep=True)
    tables = job_profile_tables(jobs)
    title = tables["job_title_counts"].set_index("job_title")
    assert title.loc["data analyst", "job_ads"] == 2
    assert title.loc["data engineer", "job_ads"] == 1
    assert tables["job_family_counts"].iloc[0].job_ads == 2
    assert tables["education_requirement_counts"].set_index("requirement").loc["bachelor's degree", "job_ads"] == 2
    coverage = tables["requirement_field_coverage"].set_index("source_field")
    assert coverage.loc["education_requirement", "stated_job_ads"] == 2
    assert coverage.loc["education_requirement", "not_stated_job_ads"] == 1
    assert coverage.loc["experience_requirement", "not_stated_job_ads"] == 3
    pd.testing.assert_frame_equal(jobs, original)


def test_experience_years_only_from_explicit_field_and_preserves_originals():
    requirements = ["2 years", "3+ years", "2–4 years of experience", "At least 5 years", "Up to 2 years", "No experience required", "", "not stated"]
    jobs = pd.DataFrame([{"source_id": str(index), "experience_requirement": value,
                          "job_description": "10 years of relevant experience required."}
                         for index, value in enumerate(requirements)])
    tables = job_profile_tables(jobs)
    evidence = tables["experience_year_evidence"]
    assert evidence.original_requirement.tolist() == requirements
    assert evidence.source_field.eq("experience_requirement").all()
    assert evidence.parse_status.str.startswith("Parsed").sum() == 6
    assert evidence.parse_status.eq("Not stated").sum() == 2
    assert evidence.loc[2, "min_years"] == 2 and evidence.loc[2, "max_years"] == 4
    assert evidence.loc[1, "min_years"] == 3 and pd.isna(evidence.loc[1, "max_years"])
    assert pd.isna(evidence.loc[4, "min_years"]) and evidence.loc[4, "max_years"] == 2
    assert evidence.loc[5, "min_years"] == evidence.loc[5, "max_years"] == 0
    summary = tables["experience_year_counts"]
    assert summary.job_ads.sum() == 6
    assert not summary.requirement.str.contains("10").any()
    assert summary.job_ads_pct.eq(12.5).all()
    assert tables["requirement_evidence"].source_field.eq("job_description").any()


def test_ambiguous_experience_clauses_remain_for_review():
    values = ["2 years and 6 months", "3 years SQL and 2 years Python", "2 or 4 years", "between 2 and 4 years",
              "More than 5 years", "5–2 years", "Fresh graduates welcome", "No experience required; 2 years preferred"]
    jobs = pd.DataFrame({"source_id": [str(index) for index in range(len(values))], "experience_requirement": values})
    tables = job_profile_tables(jobs)
    evidence = tables["experience_year_evidence"]
    assert evidence.parse_status.eq("Needs review").all()
    assert evidence.min_years.isna().all() and evidence.max_years.isna().all()
    assert tables["experience_year_counts"].empty
    assert tables["requirement_field_coverage"].set_index("source_field").loc["experience_requirement", "stated_job_ads"] == len(values)


def test_text_experience_recognizes_written_years_and_keeps_source_evidence():
    jobs = pd.DataFrame([{
        "source_id": "SYNTHETIC-ROLE-1", "job_title": "Data Analyst",
        "qualifications": "<ul><li>Two years of college</li><li>Seven years of experience in a similar role</li></ul>",
        "experience_requirement": "", "url": "https://example.invalid/role-1",
    }])
    original = jobs.copy(deep=True)

    tables = job_profile_tables(jobs)

    candidates = tables["experience_text_year_evidence"]
    assert len(candidates) == 1
    candidate = candidates.iloc[0]
    assert candidate.source_id == "SYNTHETIC-ROLE-1"
    assert candidate.source_field == "qualifications"
    assert candidate.url == "https://example.invalid/role-1"
    assert candidate.parse_status == "Parsed stated years"
    assert candidate.min_years == candidate.max_years == 7
    assert "Seven years of experience" in candidate.evidence
    assert "college" not in candidate.evidence.casefold()

    analysis = tables["experience_analysis_year_evidence"].iloc[0]
    assert analysis.evidence_origin == "text fallback"
    assert analysis.parse_status == "Parsed stated years"
    assert tables["experience_band_counts"].experience_band.tolist() == ["6–10 years"]
    pd.testing.assert_frame_equal(jobs, original)


def test_conflicting_text_experience_durations_stay_out_of_bands():
    jobs = pd.DataFrame([{
        "source_id": "SYNTHETIC-ROLE-2", "job_title": "Data Analyst",
        "qualifications": "Seven years of relevant experience.",
        "job_description": "Five years of experience in a similar role is preferred.",
        "experience_requirement": "", "url": "https://example.invalid/role-2",
    }])

    tables = job_profile_tables(jobs)

    candidates = tables["experience_text_year_evidence"]
    assert len(candidates) == 2
    assert candidates.source_id.eq("SYNTHETIC-ROLE-2").all()
    assert candidates.parse_status.str.startswith("Parsed").all()
    combined = tables["experience_analysis_year_evidence"].iloc[0]
    assert combined.parse_status == "Needs review"
    assert pd.isna(combined.min_years) and pd.isna(combined.max_years)
    assert tables["experience_band_counts"].empty
    assert len(tables["experience_band_evidence"]) == 1
    assert tables["experience_band_evidence"].iloc[0].band_status == "Needs review"


def test_empty_profile_retains_export_schemas():
    tables = job_profile_tables(pd.DataFrame())
    assert {"requirement", "job_ads", "job_ads_pct"} <= set(tables["experience_year_counts"].columns)
    assert {"source_id", "original_requirement", "parse_status"} <= set(tables["experience_year_evidence"].columns)
    assert tables["requirement_field_coverage"].job_ads.eq(0).all()


def test_location_variants_share_one_count_but_different_places_stay_distinct():
    jobs = pd.DataFrame({"source_id": ["A", "B", "C", "C"],
                         "location": ["Cebu City, Philippines", "  cebu city, Philippines  ", "Davao City, Philippines", "Davao City, Philippines"]})
    locations = job_profile_tables(jobs)["location_counts"].set_index("location")
    assert locations.loc["cebu city, philippines", "job_ads"] == 2
    assert locations.loc["davao city, philippines", "job_ads"] == 1
    assert locations.job_ads.sum() == 3


def test_age_and_negative_values_are_not_experience_and_trailing_plus_is_minimum():
    values = ["Must be 18 years old", "Age: 21 years", "-2 years", "\u22122 years", "3 years+"]
    jobs = pd.DataFrame({"source_id": [str(index) for index in range(len(values))], "experience_requirement": values})
    tables = job_profile_tables(jobs)
    evidence = tables["experience_year_evidence"]
    assert evidence.original_requirement.tolist() == values
    assert evidence.iloc[:4].parse_status.eq("Needs review").all()
    assert evidence.iloc[:4].min_years.isna().all()
    assert evidence.loc[4, "parse_status"] == "Parsed minimum"
    assert evidence.loc[4, "min_years"] == 3 and pd.isna(evidence.loc[4, "max_years"])
    assert tables["experience_year_counts"].requirement.tolist() == ["at least 3 years"]
    assert tables["experience_year_counts"].job_ads.tolist() == [1]


def test_related_titles_group_auditably_without_merging_distinct_or_composite_roles():
    values = ["Senior Data Analyst", "Junior Data Analyst", "Business Analyst", "Data Scientist", "AI Engineer",
              "ML Engineer", "Business Intelligence Analyst", "BI Analyst", "Data Analyst / Business Analyst",
              "Unknown Research Specialist", "Data Analyst Trainer", "Data Analyst - Python Developer"]
    jobs = pd.DataFrame({"source_id": [str(index) for index in range(len(values))], "job_title": values})
    original = jobs.copy(deep=True)
    tables = job_profile_tables(jobs)
    groups = tables["job_role_group_counts"].set_index("job_role_group")
    assert groups.loc["data analyst", "job_ads"] == 2
    assert groups.loc["business analyst", "job_ads"] == 1
    assert groups.loc["data scientist", "job_ads"] == 1
    assert groups.loc["business intelligence analyst", "job_ads"] == 2
    assert groups.loc["artificial intelligence engineer", "job_ads"] == 1
    assert groups.loc["machine learning engineer", "job_ads"] == 1
    assert groups.loc["data analyst / business analyst", "job_ads"] == 1
    assert groups.loc["data analyst trainer", "job_ads"] == 1
    assert groups.loc["data analyst - python developer", "job_ads"] == 1
    evidence = tables["job_title_group_evidence"]
    assert evidence.original_job_title.tolist() == values
    assert evidence.iloc[0].grouping_basis == "explicit title rule: data analyst"
    assert evidence.iloc[8:].grouping_basis.eq("specific or composite title retained").all()
    labels = tables["job_title_counts"].job_title.tolist()
    assert labels == sorted(value.lower() for value in values)
    pd.testing.assert_frame_equal(jobs, original)


def test_common_titles_collapse_clear_seniority_and_branch_variants_only():
    titles = ["Junior Business Analyst - Banking Branch", "Senior Business Analyst (Finance)",
              "Business Analyst II", "Business Analyst", "Business Analyst / Data Analyst",
              "Business Analyst Manager", "Unknown Research Specialist"]
    jobs = pd.DataFrame({"source_id": [str(i) for i in range(len(titles))], "job_title": titles,
                         "job_family": ["banking branch"] * len(titles)})
    original = jobs.copy(deep=True)
    tables = job_profile_tables(jobs)
    counts = tables["common_job_title_counts"].set_index("common_job_title")
    assert counts.loc["business analyst", "job_ads"] == 4
    assert counts.loc["business analyst / data analyst", "job_ads"] == 1
    assert counts.loc["business analyst manager", "job_ads"] == 1
    assert counts.loc["unknown research specialist", "job_ads"] == 1
    assert counts.job_ads.sum() == len(titles)
    evidence = tables["common_job_title_evidence"].set_index("source_id")
    assert evidence.loc["0", "common_job_title"] == "business analyst"
    assert evidence.loc["0", "original_job_title"] == titles[0]
    assert evidence.loc["0", "grouping_basis"] == "explicit occupation match; modifiers consolidated"
    assert tables["job_role_group_counts"].iloc[0].job_role_group == "banking branch"
    pd.testing.assert_frame_equal(jobs, original)


def test_documented_title_aliases_collapse_same_occupation_and_keep_source_evidence():
    titles = ["Business Analyst (ERP Functional Consultant)", "Business Analyst",
              "Data Engineer / Senior Data Engineer", "Data Engineer", "Senior Data Engineer",
              "Business Analyst / Data Analyst"]
    jobs = pd.DataFrame({"source_id": [str(i) for i in range(len(titles))], "job_title": titles})
    original = jobs.copy(deep=True)

    tables = job_profile_tables(jobs)
    counts = tables["common_job_title_counts"].set_index("common_job_title").job_ads
    evidence = tables["common_job_title_evidence"].set_index("source_id")

    assert counts["business analyst"] == 2
    assert counts["data engineer"] == 3
    assert counts["business analyst / data analyst"] == 1
    assert counts.sum() == len(titles)
    assert evidence.loc["0", "original_job_title"] == titles[0]
    assert evidence.loc["0", "common_job_title"] == "business analyst"
    assert evidence.loc["0", "grouping_basis"] == "documented occupation alias"
    assert evidence.loc["2", "original_job_title"] == titles[2]
    assert evidence.loc["2", "common_job_title"] == "data engineer"
    assert evidence.loc["2", "grouping_basis"] == "repeated same occupation; modifiers consolidated"
    pd.testing.assert_frame_equal(jobs, original)


def test_statistician_is_a_recognized_role_and_mixed_roles_stay_specific():
    titles = ["Statistician", "Senior Statistician", "Statistician / Data Analyst"]
    jobs = pd.DataFrame({"source_id": list("ABC"), "job_title": titles})

    counts = job_profile_tables(jobs)["common_job_title_counts"].set_index("common_job_title").job_ads

    assert counts["statistician"] == 2
    assert counts["statistician / data analyst"] == 1


def test_exact_missing_titles_are_not_graph_categories_but_source_evidence_is_retained():
    titles = ["Unknown", "N/A", "Not provided", "Senior Data Analyst", "Unknown Research Specialist"]
    jobs = pd.DataFrame({"source_id": list("ABCDE"), "job_title": titles,
                         "job_family": ["Unknown", "None", "Unknown", "Analytics", "Analytics"]})
    tables = job_profile_tables(jobs)

    assert set(tables["common_job_title_counts"].common_job_title) == {
        "data analyst", "unknown research specialist"
    }
    assert set(tables["job_title_counts"].job_title) == {
        "senior data analyst", "unknown research specialist"
    }
    assert tables["job_role_group_counts"].job_role_group.tolist() == ["analytics"]
    evidence = tables["common_job_title_evidence"].set_index("source_id")
    assert evidence.original_job_title.tolist() == titles
    assert evidence.loc["A", "common_job_title"] == ""
    assert evidence.loc["A", "grouping_basis"] == "missing title placeholder"
    assert "unknown" not in set(tables["job_title_family_counts"].job_family)


def test_leading_requisition_code_is_removed_from_analysis_labels_but_preserved_as_evidence():
    jobs = pd.DataFrame([
        {"source_id": "SYNTHETIC-1", "job_title": "DE033824-Health Operations Analyst", "job_family": "Analytics"},
        {"source_id": "SYNTHETIC-2", "job_title": "Health Operations Analyst", "job_family": "Analytics"},
        {"source_id": "SYNTHETIC-3", "job_title": "3D Artist", "job_family": "Creative"},
    ])
    original = jobs.copy(deep=True)

    tables = job_profile_tables(jobs)

    titles = tables["job_title_counts"].set_index("job_title")
    assert titles.loc["health operations analyst", "job_ads"] == 2
    assert "de033824-health operations analyst" not in titles.index
    evidence = tables["job_title_source_evidence"].set_index("source_id")
    assert evidence.loc["SYNTHETIC-1", "job_title"] == "health operations analyst"
    assert evidence.loc["SYNTHETIC-1", "original_job_title"] == "DE033824-Health Operations Analyst"
    assert tables["common_job_title_evidence"].set_index("source_id").loc[
        "SYNTHETIC-1", "normalized_job_title"] == "health operations analyst"
    assert tables["job_title_group_evidence"].set_index("source_id").loc[
        "SYNTHETIC-1", "normalized_job_title"] == "health operations analyst"
    assert tables["job_title_counts"].set_index("job_title").loc["3d artist", "job_ads"] == 1
    pd.testing.assert_frame_equal(jobs, original)


def test_source_family_takes_priority_and_normalized_outputs_are_lowercase():
    jobs = pd.DataFrame([
        {"source_id": "A", "job_title": "Senior Data Analyst", "job_family": "  CUSTOM Analytics  ", "education_requirement": "Bachelor's Degree", "experience_requirement": "3+ years"},
        {"source_id": "B", "job_title": "Junior Data Analyst", "job_family": "Unknown", "education_requirement": "Not Stated", "experience_requirement": "No experience required"},
        {"source_id": "C", "job_title": "Data Engineer", "job_family": "N/A", "education_requirement": "Diploma", "experience_requirement": "Up to 2 years"},
    ])
    tables = job_profile_tables(jobs)
    evidence = tables["job_title_group_evidence"].set_index("source_id")
    assert evidence.loc["A", "job_role_group"] == "custom analytics"
    assert evidence.loc["A", "grouping_basis"] == "source-provided job family"
    assert evidence.loc["B", "job_role_group"] == "data analyst"
    assert evidence.loc["C", "job_role_group"] == "data engineer"
    for key, column in (("job_title_counts", "job_title"), ("job_family_counts", "job_family"),
                        ("education_requirement_counts", "requirement"), ("experience_year_counts", "requirement")):
        values = tables[key][column]
        assert values.eq(values.str.lower()).all()
    assert tables["experience_year_evidence"].original_requirement.tolist() == jobs.experience_requirement.tolist()


def test_education_levels_follow_progression_and_preserve_ambiguous_credentials():
    values = ["Ph.D.", "  BS in Computer Science  ", "Bachelors degree", "Master’s degree", "MSc", "SHS graduate",
              "College-level", "Associate degree", "High school", "Bachelor or master's degree", "Degree preferred",
              "Bachelor's degree or equivalent experience", "", "not specified", "Certificate"]
    jobs = pd.DataFrame({"source_id": [str(index) for index in range(len(values))], "education_requirement": values})
    original = jobs.copy(deep=True)
    tables = job_profile_tables(jobs)
    summary = tables["education_level_counts"]
    assert summary.education_level.tolist() == ["high school", "senior high school", "undergraduate / college level",
                                               "associate degree", "bachelor's degree", "master's degree", "doctoral degree"]
    assert summary.job_ads.tolist() == [1, 1, 1, 1, 2, 2, 1]
    assert summary.set_index("education_level").loc["bachelor's degree", "job_ads_pct"] == 13.3
    evidence = tables["education_level_evidence"]
    assert evidence.original_requirement.tolist() == values
    assert evidence.iloc[9:12].parse_status.eq("Needs review").all()
    assert evidence.iloc[12:14].parse_status.eq("Not stated").all()
    assert evidence.iloc[14].parse_status == "Needs review"
    assert "bachelor's degree" in evidence.iloc[9].mentioned_levels
    assert "master's degree" in evidence.iloc[9].mentioned_levels
    pd.testing.assert_frame_equal(jobs, original)


def test_experience_bands_keep_spanning_and_unbounded_requirements_out_of_counts():
    values = ["No experience required", "0.5 years", "1–2 years", "3-5 years", "6 to 10 years", "11 years", "1-5 years",
              "3+ years", "Up to 2 years", "Relevant experience", "", "2.5 years", "2 years"]
    jobs = pd.DataFrame({"source_id": [str(index) for index in range(len(values))], "experience_requirement": values})
    tables = job_profile_tables(jobs)
    summary = tables["experience_band_counts"]
    assert summary.experience_band.tolist() == ["no experience required", "less than 1 year", "1–2 years", "3–5 years", "6–10 years", "more than 10 years"]
    assert summary.job_ads.tolist() == [1, 1, 2, 1, 1, 1]
    assert summary.set_index("experience_band").loc["1–2 years", "job_ads_pct"] == 15.4
    evidence = tables["experience_band_evidence"]
    assert evidence.original_requirement.tolist() == values
    assert evidence.iloc[6:10].band_status.eq("Needs review").all()
    assert evidence.iloc[10].band_status == "Not stated"
    assert evidence.iloc[11].band_status == "Needs review"
    assert evidence.loc[7, "min_years"] == 3 and pd.isna(evidence.loc[7, "max_years"])


def test_family_title_table_is_alphabetical_source_linked_and_keeps_seniority():
    jobs = pd.DataFrame([
        {"source_id": "A", "job_title": "Senior Data Analyst", "job_family": "Analytics", "source": "Provider B", "url": "https://example.invalid/A"},
        {"source_id": "B", "job_title": "Junior Data Analyst", "job_family": "ANALYTICS", "source": "Provider A", "url": "https://example.invalid/B"},
        {"source_id": "C", "job_title": "  senior Data Analyst  ", "job_family": "analytics", "source": "provider b", "url": "https://example.invalid/C"},
        {"source_id": "D", "job_title": "Data Engineer", "job_family": "Engineering", "source": "Provider A"},
    ])
    tables = job_profile_tables(jobs)
    summary = tables["job_title_family_counts"]
    assert summary.job_family.tolist() == ["analytics", "analytics", "engineering"]
    assert summary.job_title.tolist() == ["junior data analyst", "senior data analyst", "data engineer"]
    assert summary.job_ads.tolist() == [1, 2, 1]
    assert summary.sources.tolist() == ["provider a", "provider b", "provider a"]
    evidence = tables["job_title_source_evidence"]
    assert evidence.original_job_title.tolist() == jobs.job_title.tolist()
    assert evidence.loc[0, "url"] == "https://example.invalid/A"
    assert evidence.source_id.tolist() == jobs.source_id.tolist()
