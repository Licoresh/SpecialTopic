"""Synthetic chart data only; no research records or labels are changed."""
import pandas as pd
from src.alignment import calculate_mapping
from src.analytics import accepted_skills, skill_chart_tables


def rows(values):
    return pd.DataFrame([dict(source_id=source, source_type="jobs", normalized_phrase=phrase,
                             original_phrase=phrase, competency_category=category,
                             human_label=category, extraction_id=f"test-{index}",
                             original_text="SYNTHETIC SOURCE EVIDENCE")
                         for index, (source, phrase, category) in enumerate(values)])


def test_case_list_and_unicode_variants_count_distinct_selected_ads():
    skills = rows([("A", "Collaboration", "Soft / Enabling"),
                   ("A", " • COLLABORATION ", "Soft / Enabling"),
                   ("B", "collaboration\u200b", "Soft / Enabling"),
                   ("EXTERNAL", "collaboration", "Soft / Enabling")])
    before = skills.copy(deep=True)
    jobs = pd.DataFrame({"source_id": ["A", "B", "C", "A"]})
    tables = skill_chart_tables(skills, jobs)
    demand = tables["chart_skill_demand"]
    assert len(demand) == 1
    assert demand.iloc[0].employer_skill == "collaboration"
    assert demand.iloc[0].employer_demand_count == 2
    assert demand.iloc[0].employer_demand_pct == 2 / 3 * 100
    assert len(tables["chart_skill_occurrences"]) == 2
    family = tables["chart_skill_family_demand"].iloc[0]
    assert family.job_family == "not stated" and family.skill_label == "collaboration"
    assert family.job_ads == 2 and family.family_ads == 3
    assert round(family.job_ads_pct, 1) == 66.7
    assert tables["chart_phrase_review"].empty
    pd.testing.assert_frame_equal(skills, before)


def test_unclear_phrases_keep_original_evidence_and_reviewer_judgments():
    skills = rows([("A", "Build", "Technical / Digital"),
                   ("A", "with strong", "Soft / Enabling"),
                   ("A", "123", "Technical / Digital"),
                   ("A", "", "Technical / Digital"),
                   ("A", "🌐 Remote", "Technical / Digital"),
                   ("A", "Bachelor", "Education / Qualification"),
                   ("A", "Something", "IRRELEVANT"),
                   ("A", "statistical analysis", "Data / Analytics")])
    before = skills.copy(deep=True)
    tables = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))
    assert tables["chart_skill_demand"].employer_skill.tolist() == ["statistical analysis"]
    audit = tables["chart_phrase_review"]
    assert len(audit) == 7
    assert audit.review_reason.str.len().gt(0).all()
    assert audit.iloc[0].original_phrase == "Build"
    assert audit.iloc[0].human_label == "Technical / Digital"
    assert audit.original_text.eq("SYNTHETIC SOURCE EVIDENCE").all()
    pd.testing.assert_frame_equal(skills, before)


def test_technical_symbols_and_distinct_skill_meanings_are_preserved():
    phrases = ["C++", "C#", ".NET", "R", "SQL", "Power BI", "communication", "communication skills"]
    tables = skill_chart_tables(rows([("A", phrase, "Technical / Digital") for phrase in phrases]),
                               pd.DataFrame({"source_id": ["A"]}))
    assert set(tables["chart_skill_demand"].employer_skill) == {phrase.casefold() for phrase in phrases}
    assert len(tables["chart_skill_demand"]) == len(phrases)
    assert tables["chart_phrase_review"].empty


def test_not_reported_and_experience_phrases_are_counts_not_skills_or_psf_inputs():
    skills = rows([("A", "SQL", "Technical / Digital"),
                   ("B", "Not mentioned.", "IRRELEVANT"),
                   ("C", "3+year", "Technical / Digital"),
                   ("D", "+year", "Technical / Digital"),
                   ("E", "General note", "IRRELEVANT"),
                   ("F", "Bachelor's degree", "Education / Qualification")])
    skills["accepted"] = [True, False, True, False, False, False]
    jobs = pd.DataFrame({"source_id": list("ABCDEF")})

    views = skill_chart_tables(skills, jobs)

    assert views["chart_skill_demand"].employer_skill.tolist() == ["sql"]
    review = views["chart_phrase_review"].set_index("original_phrase").review_reason
    assert review["Not mentioned."] == "Not reported (missing placeholder); count only, not a skill"
    assert review["3+year"] == "Experience-duration requirement, not a skill"
    assert review["+year"] == "Unclear year-duration phrase, not a skill"
    assert "irrelevant" in review["General note"]
    assert review["Bachelor's degree"] == "Credential requirement, not a skill"
    accepted = accepted_skills(skills)
    assert accepted.normalized_phrase.tolist() == ["SQL"]
    taxonomy = pd.DataFrame({"competency_id": ["TEST-SQL"], "competency_name": ["SQL"],
                             "competency_category": ["Technical / Digital"], "job_role": ["Analyst"]})
    mapping = calculate_mapping(accepted, taxonomy)
    assert mapping.source_id.tolist() == ["A"]
    assert mapping.psf_competency.tolist() == ["SQL"]


def test_job_titles_and_context_fragments_are_not_skill_demand():
    phrases = ["analyst", "business analyst", "base", "data", "engineer", "data analyst", "data engineer",
               "industry experience", "SQL", "data analysis", "Python", "communication", "data engineering"]
    skills = rows([("A", phrase, "Technical / Digital") for phrase in phrases])
    skills["accepted"] = True
    skills.loc[skills.normalized_phrase.eq("base"), "original_phrase"] = "based"
    original = skills.copy(deep=True)

    views = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))

    assert set(views["chart_skill_demand"].employer_skill) == {
        "sql", "data analysis", "python", "communication", "data engineering"
    }
    audit = views["chart_phrase_review"].set_index("normalized_phrase").review_reason
    assert audit["base"] == "Incomplete or context-only wording; not a skill"
    assert audit["analyst"] == "Job title or occupational wording; not a skill"
    assert audit["business analyst"] == "Job title or occupational wording; not a skill"
    assert audit["data engineer"] == "Job title or occupational wording; not a skill"
    assert set(accepted_skills(skills).normalized_phrase.str.casefold()) == {
        "sql", "data analysis", "python", "communication", "data engineering"
    }
    pd.testing.assert_frame_equal(skills, original)


def test_status_filtered_skill_charts_keep_only_allowed_original_phrase_variants():
    skills = rows([("A", "powerbi", "Technical / Digital"),
                   ("B", "power bi", "Technical / Digital"),
                   ("C", "sql", "Technical / Digital")])
    jobs = pd.DataFrame({"source_id": list("ABC")})

    views = skill_chart_tables(skills, jobs, allowed_phrases={"powerbi"})

    assert views["chart_skill_demand"].employer_skill.tolist() == ["power bi"]
    assert views["chart_skill_demand"].employer_demand_count.tolist() == [1]
    assert views["chart_phrase_review"].empty


def test_empty_tables_keep_exportable_schema():
    tables = skill_chart_tables(pd.DataFrame(), pd.DataFrame())
    assert set(tables) == {"chart_skill_occurrences", "chart_skill_demand", "chart_phrase_review",
                           "chart_skill_family_demand", "chart_family_ad_counts"}
    assert all(frame.empty for frame in tables.values())
    assert {"normalized_phrase", "employer_skill", "employer_demand_count", "employer_demand_pct"} <= set(tables["chart_skill_demand"])
    assert "review_reason" in tables["chart_phrase_review"]
