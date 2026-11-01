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
    assert set(tables["chart_skill_demand"].employer_skill) == {
        "c++", "c#", ".net", "r", "sql", "power bi", "communication"
    }
    assert len(tables["chart_skill_demand"]) == len(phrases) - 1
    assert tables["chart_phrase_review"].empty


def test_clear_skill_wording_variants_share_one_chart_label_across_views():
    skills = rows([
        ("A", "communication", "Soft / Enabling"),
        ("A", "communication skills", "Soft / Enabling"),
        ("A", "strong communication skills", "Soft / Enabling"),
        ("B", "communication skill", "Soft / Enabling"),
        ("A", "problem solve", "Soft / Enabling"),
        ("A", "problem-solving", "Soft / Enabling"),
        ("B", "problem solving skills", "Soft / Enabling"),
        ("A", "collaboration", "Soft / Enabling"),
        ("A", "strong collaboration", "Soft / Enabling"),
        ("B", "collaboration skills", "Soft / Enabling"),
        ("C", "written communication", "Soft / Enabling"),
        ("C", "verbal communication", "Soft / Enabling"),
        ("D", "communication and train", "Soft / Enabling"),
    ])
    skills["accepted"] = True
    before = skills.copy(deep=True)
    jobs = pd.DataFrame({"source_id": list("ABCD"), "job_family": ["analytics"] * 4})

    charts = skill_chart_tables(skills, jobs)
    demand = charts["chart_skill_demand"].set_index("employer_skill").employer_demand_count
    family = charts["chart_skill_family_demand"].set_index("skill_label").job_ads

    assert demand["communication"] == family["communication"] == 2
    assert demand["problem solving"] == family["problem solving"] == 2
    assert demand["collaboration"] == family["collaboration"] == 2
    assert demand["written communication"] == demand["verbal communication"] == 1
    assert not {"communication skills", "communication skill", "strong communication skills",
                "problem solve", "problem-solving", "problem solving skills",
                "strong collaboration", "collaboration skills"} & set(demand.index)
    occurrences = charts["chart_skill_occurrences"]
    for label, expected_ads in (("communication", 2), ("problem solving", 2), ("collaboration", 2)):
        assert occurrences.loc[occurrences.skill_label.eq(label), "source_id"].nunique() == expected_ads
    review = charts["chart_phrase_review"].set_index("original_phrase").review_reason
    assert review["communication and train"].startswith("Duty wording")
    pd.testing.assert_frame_equal(skills, before)


def test_chart_aliases_merge_same_concept_without_rewriting_phrase_evidence():
    skills = rows([
        ("A", "Agile scrum", "Technical / Digital"),
        ("A", "Agile scrum methodology", "Technical / Digital"),
        ("A", "Scrum methodology", "Technical / Digital"),
        ("B", "Scrum", "Technical / Digital"),
        ("A", "Agile", "Technical / Digital"),
        ("A", "data governance", "Technical / Digital"),
        ("A", "datum governance", "Technical / Digital"),
        ("B", "datum governance", "Technical / Digital"),
    ])
    before = skills.copy(deep=True)
    tables = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A", "B"]}))
    counts = tables["chart_skill_demand"].set_index("employer_skill").employer_demand_count

    assert counts["agile scrum"] == 2
    assert counts["agile"] == 1  # Agile alone is broader than the Scrum framework.
    assert counts["data governance"] == 2  # Duplicate variants in one ad count once.
    assert "datum governance" not in counts.index
    aliases = tables["chart_skill_occurrences"]
    assert aliases.normalized_phrase.eq("agile scrum").sum() == 2  # One displayed occurrence per ad.
    assert set(skills.loc[skills.normalized_phrase.str.contains("governance"), "normalized_phrase"]) == {
        "data governance", "datum governance"
    }
    pd.testing.assert_frame_equal(skills, before)


def test_learning_phrases_share_broader_chart_label_and_count_each_ad_once():
    skills = rows([
        ("A", "ability to learn", "Soft / Enabling"),
        ("A", "learn and apply", "Soft / Enabling"),
        ("B", "learn and apply", "Soft / Enabling"),
        ("C", "ability to learn", "Soft / Enabling"),
        ("D", "ability to learn and apply", "Soft / Enabling"),
        ("E", "willingness to learn", "Soft / Enabling"),
    ])
    before = skills.copy(deep=True)
    jobs = pd.DataFrame({"source_id": list("ABCDE"), "job_family": ["analytics"] * 5})

    charts = skill_chart_tables(skills, jobs)
    counts = charts["chart_skill_demand"].set_index("employer_skill").employer_demand_count
    learning_rows = charts["chart_skill_occurrences"].loc[
        charts["chart_skill_occurrences"].skill_label.eq("learning and application")]

    assert counts["learning and application"] == 4
    assert counts["willingness to learn"] == 1
    assert learning_rows.source_id.nunique() == 4  # A has both variants but counts once.
    family = charts["chart_skill_family_demand"].set_index("skill_label")
    assert family.loc["learning and application", "job_ads"] == 4
    assert set(skills.normalized_phrase) == {
        "ability to learn", "learn and apply", "ability to learn and apply", "willingness to learn"
    }
    pd.testing.assert_frame_equal(skills, before)


def test_legal_boilerplate_duty_fragments_and_outcome_metrics_stay_out_of_skill_charts():
    skills = rows([
        ("A", "protect by applicable", "Functional Skills and Competencies"),
        ("B", "activities and work", "Functional Skills and Competencies"),
        ("C", "adoption of insight", "Enabling Skills and Competencies"),
        ("D", "ability to learn", "Enabling Skills and Competencies"),
        ("E", "adoption insight", "Enabling Skills and Competencies"),
    ])
    skills["accepted"] = True
    original = skills.copy(deep=True)
    tables = skill_chart_tables(skills, pd.DataFrame({"source_id": list("ABCDE")}))

    assert tables["chart_skill_demand"].employer_skill.tolist() == ["learning and application"]
    reasons = tables["chart_phrase_review"].set_index("normalized_phrase").review_reason
    assert reasons["protect by applicable"].startswith("Equal-employment legal boilerplate")
    assert reasons["activities and work"].startswith("Generic duty wording")
    assert reasons["adoption of insight"].startswith("Success-metric wording")
    assert reasons["adoption insight"].startswith("Success-metric wording")
    # These additions affect graph presentation only; saved extraction/mapping eligibility is unchanged.
    assert set(accepted_skills(skills).normalized_phrase) == set(skills.normalized_phrase)
    pd.testing.assert_frame_equal(skills, original)


def test_company_copy_title_fragments_and_occupational_wording_stay_out_of_skill_charts():
    phrases = ["allow individual", "allow individuals", "analyst work", "asset across strategy",
               "assets across strategy", "ai base", "ai based", "ai prompt", "SQL"]
    skills = rows([("A", phrase, "Technical / Digital") for phrase in phrases])
    skills["accepted"] = True
    original = skills.copy(deep=True)

    charts = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))

    assert charts["chart_skill_demand"].employer_skill.tolist() == ["sql"]
    audit = charts["chart_phrase_review"].set_index("normalized_phrase").review_reason
    assert audit["allow individual"].startswith("Company marketing wording")
    assert audit["allow individuals"].startswith("Company marketing wording")
    assert audit["analyst work"].startswith("Occupational experience wording")
    assert audit["asset across strategy"].startswith("Employer corporate-profile wording")
    assert audit["assets across strategy"].startswith("Employer corporate-profile wording")
    assert audit["ai base"].startswith("Malformed")
    assert audit["ai based"].startswith("Malformed")
    assert audit["ai prompt"].startswith("Job-title fragment")
    assert set(accepted_skills(skills).normalized_phrase) == set(phrases)
    pd.testing.assert_frame_equal(skills, original)


def test_shared_phrase_gate_feeds_every_employer_skill_chart_table():
    skills = rows([
        ("A", "agile scrum", "Technical / Digital"),
        ("A", "agile scrum methodology", "Technical / Digital"),
        ("A", "protect by applicable", "IRRELEVANT"),
        ("A", "activities and work", "IRRELEVANT"),
        ("B", "SQL", "Data / Analytics"),
        ("B", "adoption insight", "IRRELEVANT"),
    ])
    skills["accepted"] = True
    jobs = pd.DataFrame({"source_id": ["A", "B"], "job_family": ["Data Analytics", "Business Intelligence"]})

    charts = skill_chart_tables(skills, jobs)

    assert set(charts["chart_skill_demand"].employer_skill) == {"agile scrum", "sql"}
    assert set(charts["chart_skill_family_demand"].skill_label) == {"agile scrum", "sql"}
    assert set(charts["chart_skill_occurrences"].normalized_phrase) == {"agile scrum", "sql"}
    assert set(charts["chart_phrase_review"].normalized_phrase) >= {
        "protect by applicable", "activities and work", "adoption insight"
    }


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


def test_vague_and_unfinished_wording_is_withheld_from_every_skill_chart():
    skills = rows([
        ("A", "SQL", "Data / Analytics"),
        ("A", "Python", "Technical / Digital"),
        ("A", "Strong", "Soft / Enabling"),
        ("A", "Business experience", "Business / Domain"),
        ("A", "SQL and others", "Technical / Digital"),
        ("B", "Python, SQL, etc.", "Technical / Digital"),
        ("B", "IT experience", "Business / Domain"),
        ("B", "Advanced SQL", "Data / Analytics"),
        ("B", "Communication skills", "Soft / Enabling"),
        ("B", "Various", "IRRELEVANT"),
    ])
    skills["accepted"] = [True, True, True, True, True, True, True, True, True, False]

    views = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A", "B"],
                                                      "job_family": ["analytics", "analytics"]}))

    expected = {"sql", "python", "advanced sql", "communication"}
    assert set(views["chart_skill_demand"].employer_skill) == expected
    assert set(views["chart_skill_family_demand"].skill_label) == expected
    audit = views["chart_phrase_review"].set_index("original_phrase").review_reason
    assert audit["Strong"].startswith("Vague wording")
    assert audit["Business experience"].startswith("Vague wording")
    assert audit["SQL and others"].startswith("Unfinished list wording")
    assert audit["Python, SQL, etc."].startswith("Unfinished list wording")
    assert audit["IT experience"].startswith("Vague wording")
    assert audit["Various"].startswith("Vague wording")
    assert set(accepted_skills(skills).normalized_phrase.str.casefold()) == {
        "sql", "python", "advanced sql", "communication skills"
    }  # Chart aliases do not rewrite the reviewed or training phrase.


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
