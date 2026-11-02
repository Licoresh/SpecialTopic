"""Synthetic chart data only; no research records or labels are changed."""
import pandas as pd
import pytest
from src.alignment import calculate_mapping
from src.analytics import accepted_skills, psf_demand_tables, skill_chart_tables, unmapped_chart_counts


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
    assert accepted_skills(skills).normalized_phrase.tolist() == ["ability to learn"]
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
    assert accepted_skills(skills).normalized_phrase.tolist() == ["SQL"]
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


@pytest.mark.parametrize("mapped_status", ["ALIGNED", "PARTIALLY ALIGNED"])
def test_mapped_alias_suppresses_unmapped_group_even_after_same_ad_deduplication(mapped_status):
    skills = rows([("A", "\u2022sql", "Technical / Digital"),
                   ("A", "sql", "Technical / Digital")])
    jobs = pd.DataFrame({"source_id": ["A"]})
    occurrences = skill_chart_tables(skills, jobs)["chart_skill_occurrences"]
    assert occurrences.original_normalized_phrase.tolist() == ["\u2022sql"]
    alignment = pd.DataFrame({"normalized_skill": ["\u2022sql", "sql"],
                              "status": ["NOT MAPPED", mapped_status]})
    before_occurrences, before_alignment = occurrences.copy(deep=True), alignment.copy(deep=True)

    assert unmapped_chart_counts(occurrences, alignment).empty

    pd.testing.assert_frame_equal(occurrences, before_occurrences)
    pd.testing.assert_frame_equal(alignment, before_alignment)


def test_recurring_unmapped_threshold_uses_combined_alias_demand():
    skills = rows([("A", "communication", "Soft / Enabling"),
                   ("B", "communication", "Soft / Enabling"),
                   ("C", "communication skills", "Soft / Enabling"),
                   ("D", "communication skills", "Soft / Enabling")])
    occurrences = skill_chart_tables(skills, pd.DataFrame({"source_id": list("ABCD")}))["chart_skill_occurrences"]
    alignment = pd.DataFrame({"normalized_skill": ["communication", "communication skills"],
                              "status": ["NOT MAPPED", "NOT MAPPED"]})

    counted = unmapped_chart_counts(occurrences, alignment, minimum_jobs=3)

    assert counted.to_dict("records") == [{"normalized_skill": "communication", "skill_label": "communication", "job_ads": 4}]
    assert unmapped_chart_counts(occurrences, alignment, minimum_jobs=4).job_ads.tolist() == [4]
    assert unmapped_chart_counts(occurrences, alignment, minimum_jobs=5).empty


def test_unmapped_counts_distinct_selected_ads_despite_repeated_evidence_rows():
    skills = rows([("A", "communication", "Soft / Enabling"),
                   ("A", "communication skills", "Soft / Enabling"),
                   ("B", "communication skills", "Soft / Enabling"),
                   ("EXTERNAL", "communication", "Soft / Enabling")])
    jobs = pd.DataFrame({"source_id": ["A", "B", "A"]})
    screened = skill_chart_tables(skills, jobs)["chart_skill_occurrences"]
    occurrences = pd.concat([screened, screened], ignore_index=True)
    alignment = pd.DataFrame({"normalized_skill": ["communication", "communication skills", "communication"],
                              "status": ["NOT MAPPED"] * 3})
    before_skills, before_occurrences, before_alignment = (frame.copy(deep=True) for frame in (skills, occurrences, alignment))

    assert unmapped_chart_counts(occurrences, alignment).job_ads.tolist() == [2]

    for current, before in ((skills, before_skills), (occurrences, before_occurrences), (alignment, before_alignment)):
        pd.testing.assert_frame_equal(current, before)


def test_unmapped_counts_exclude_unclassified_unclear_and_rejected_phrases():
    skills = rows([("A", "Build", "Technical / Digital"),
                   ("A", "sql", "Technical / Digital"),
                   ("A", "python", "Technical / Digital"),
                   ("A", "Something", "IRRELEVANT"),
                   ("A", "java", "Technical / Digital")])
    skills["accepted"] = [True, True, True, True, False]
    occurrences = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))["chart_skill_occurrences"]
    alignment = pd.DataFrame({"normalized_skill": ["Build", "sql", "python", "Something", "java"],
                              "status": ["NOT MAPPED", "UNCLASSIFIED", "NOT MAPPED", "NOT MAPPED", "NOT MAPPED"]})

    assert unmapped_chart_counts(occurrences, alignment).to_dict("records") == [
        {"normalized_skill": "python", "skill_label": "python", "job_ads": 1}]
    empty = unmapped_chart_counts(occurrences.iloc[:0], alignment)
    assert empty.empty and empty.columns.tolist() == ["normalized_skill", "skill_label", "job_ads"]


@pytest.mark.parametrize("phrase", [
    "long and successful", "tool and service", "accept", "accept usage", "acceptance",
    "access to clean", "activity", "ad hoc", "adjacent enterprise system",
    "improvement opportunity", "enterprise ai tool", "technical workflow",
    "build in room", "basis a protect", "case include schedule", "business center",
    "creation be complete", "database be accurate", "gender identity", "identity or expression",
    "job description", "global professional", "critical success measures", "work closely",
    "configure and deploy", "develop and retain", "quality and consistency",
    "analysis be accurate", "design work closely",
    "long and successful research", "free training", "opportunity for learning",
    "opportunities for career development", "participate in development",
])
def test_generic_fragments_require_review_before_skill_and_psf_demand(phrase):
    skills = rows([("A", phrase, "Technical / Digital")])
    skills["accepted"] = True
    before = skills.copy(deep=True)

    charts = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))

    assert accepted_skills(skills).empty
    assert charts["chart_skill_demand"].empty
    assert charts["chart_skill_occurrences"].empty
    assert charts["chart_skill_family_demand"].empty
    audit = charts["chart_phrase_review"]
    assert audit.original_phrase.tolist() == [phrase]
    assert audit.review_reason.str.len().gt(0).all()
    pd.testing.assert_frame_equal(audit[before.columns], before)
    pd.testing.assert_frame_equal(skills, before)


def test_ambiguous_solution_design_wording_remains_available_for_review():
    skills = rows([("A", "actionable solution design", "Technical / Digital")])
    skills["accepted"] = True
    before = skills.copy(deep=True)

    charts = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))

    assert accepted_skills(skills).empty
    assert charts["chart_skill_demand"].empty
    audit = charts["chart_phrase_review"]
    assert audit.original_phrase.tolist() == ["actionable solution design"]
    assert audit.review_reason.str.len().gt(0).all()
    pd.testing.assert_frame_equal(audit[before.columns], before)
    pd.testing.assert_frame_equal(skills, before)


@pytest.mark.parametrize("phrase,label", [
    ("ad hoc analysis", "ad hoc analysis"),
    ("user acceptance testing", "user acceptance testing"),
    ("solution design", "solution design"),
    ("enterprise architecture", "enterprise architecture"),
    ("API integration", "api integration"),
    ("Rust", "rust"), ("Julia", "julia"), ("R", "r"),
    ("C++", "c++"), ("C#", "c#"), (".NET", ".net"),
    ("research", "research"), ("leadership", "leadership"), ("learning", "learning"),
    ("ability to learn", "learning and application"),
    ("learn and apply", "learning and application"),
    ("build dashboards", "build dashboards"),
    ("maintain data pipelines", "maintain data pipelines"),
    ("design APIs", "design apis"),
    ("configure network devices", "configure network devices"),
    ("deploy ML models", "deploy ml models"),
    ("perform statistical analysis", "perform statistical analysis"),
    ("ensure regulatory compliance", "ensure regulatory compliance"),
    ("attention to detail", "attention to detail"), ("resilience", "resilience"),
    ("emotional intelligence", "emotional intelligence"), ("financial acumen", "financial acumen"),
    ("numerical literacy", "numerical literacy"), ("stakeholder engagement", "stakeholder engagement"),
    ("conflict resolution", "conflict resolution"), ("incident response", "incident response"),
    ("visual storytelling", "visual storytelling"), ("load balancing", "load balancing"),
    ("feature selection", "feature selection"), ("dimensionality reduction", "dimensionality reduction"),
    ("data cleaning", "data cleaning"), ("quality assurance", "quality assurance"),
    ("decision making", "decision making"), ("as-is process analysis", "as-is process analysis"),
    ("end-to-end testing", "end-to-end testing"), ("in-memory analytics", "in-memory analytics"),
    ("active listening", "active listening"), ("public speaking", "public speaking"),
    ("creative thinking", "creative thinking"), ("customer service", "customer service"),
    ("TypeScript", "typescript"), ("PySpark", "pyspark"), ("XGBoost", "xgboost"),
    ("knowledge of SQL", "knowledge of sql"), ("proficiency in Python", "proficiency in python"),
    ("ability to communicate", "ability to communicate"), ("statistical methods", "statistical methods"),
    ("participate in model development", "participate in model development"),
    ("strong knowledge of SQL", "strong knowledge of sql"),
    ("proficiency in Microsoft Excel", "proficiency in microsoft excel"),
    ("experience with Microsoft Power BI", "experience with microsoft power bi"),
    ("knowledge of advanced SQL", "knowledge of advanced sql"),
])
def test_specific_skills_survive_conservative_fragment_screen(phrase, label):
    skills = rows([("A", phrase, "Technical / Digital")])
    skills["accepted"] = True
    before = skills.copy(deep=True)

    charts = skill_chart_tables(skills, pd.DataFrame({"source_id": ["A"]}))

    assert accepted_skills(skills).normalized_phrase.tolist() == [phrase]
    assert charts["chart_skill_demand"].employer_skill.tolist() == [label]
    assert charts["chart_phrase_review"].empty
    pd.testing.assert_frame_equal(skills, before)


def test_shared_fragment_screen_preserves_evidence_and_selected_ad_denominators():
    skills = rows([("A", "SQL", "Technical / Digital"),
                   ("A", "sql", "Technical / Digital"),
                   ("B", "sql", "Technical / Digital"),
                   ("C", "long and successful", "Technical / Digital"),
                   ("D", "activity", "Technical / Digital"),
                   ("A", "technical workflow", "Technical / Digital"),
                   ("EXTERNAL", "sql", "Technical / Digital")])
    skills["accepted"] = True
    jobs = pd.DataFrame({"source_id": ["A", "B", "C", "D", "A"],
                         "job_family": ["analytics", "analytics", "analytics", "operations", "analytics"]})
    alignment = pd.DataFrame({"normalized_skill": ["sql", "long and successful", "activity", "technical workflow"],
                              "status": ["NOT MAPPED"] * 4})
    before_skills, before_jobs, before_alignment = (frame.copy(deep=True) for frame in (skills, jobs, alignment))

    charts = skill_chart_tables(skills, jobs)
    demand = charts["chart_skill_demand"]
    occurrences = charts["chart_skill_occurrences"]
    unmapped = unmapped_chart_counts(occurrences, alignment)

    assert demand.employer_skill.tolist() == ["sql"]
    assert demand.employer_demand_count.tolist() == [2]
    assert demand.employer_demand_pct.tolist() == [50.0]
    assert set(occurrences.source_id) == {"A", "B"}
    assert not occurrences.duplicated(["source_id", "normalized_phrase"]).any()
    family = charts["chart_skill_family_demand"]
    assert family[["job_family", "skill_label", "job_ads", "family_ads"]].to_dict("records") == [
        {"job_family": "analytics", "skill_label": "sql", "job_ads": 2, "family_ads": 3}]
    assert family.job_ads_pct.tolist() == [pytest.approx(2 / 3 * 100)]
    assert charts["chart_family_ad_counts"].set_index("job_family").family_ads.to_dict() == {
        "analytics": 3, "operations": 1}
    assert unmapped.to_dict("records") == [{"normalized_skill": "sql", "skill_label": "sql", "job_ads": 2}]
    assert unmapped_chart_counts(occurrences, alignment, minimum_jobs=3).empty
    audit = charts["chart_phrase_review"]
    assert set(audit.original_phrase) == {"long and successful", "activity", "technical workflow"}
    assert audit.review_reason.str.len().gt(0).all()
    pd.testing.assert_frame_equal(audit[before_skills.columns], before_skills.loc[audit.index])
    for current, before in ((skills, before_skills), (jobs, before_jobs), (alignment, before_alignment)):
        pd.testing.assert_frame_equal(current, before)


def test_psf_demand_screens_employer_noise_before_all_aggregations_and_preserves_reference_labels():
    jobs = pd.DataFrame({"source_id": ["A", "B", "C", "D", "A"],
                         "job_family": ["analytics", "analytics", "operations", "operations", "analytics"]})
    mapping = pd.DataFrame({
        "source_id": ["A", "A", "B", "C", "C", "EXTERNAL", "B", "C"],
        "normalized_skill": ["sql", "sql", "build dashboards", "job description", "gender identity", "sql", "Rust", "sql"],
        "psf_competency": ["activity"] * 4 + ["technical workflow", "activity", "work closely", "work closely"],
        "psf_job_role": ["global professional"] * 4 + ["noise role", "external role", "engineer", "engineer"],
        "status": ["ALIGNED"] * 7 + ["NOT MAPPED"],
    })
    taxonomy = pd.DataFrame({"competency_id": ["A", "T", "W"],
                             "competency_name": ["Activity", "Technical workflow", "Work closely"]})
    before_mapping, before_jobs, before_taxonomy = (frame.copy(deep=True) for frame in (mapping, jobs, taxonomy))

    tables = psf_demand_tables(mapping, jobs, taxonomy)

    demand = tables["psf_chart_demand"].set_index("psf_competency")
    assert demand.job_ads.to_dict() == {"activity": 2, "work closely": 1}
    assert demand.job_ads_pct.to_dict() == {"activity": 50.0, "work closely": 25.0}
    assert demand.framework_order.to_dict() == {"activity": 0, "work closely": 2}
    assert tables["psf_role_competency_demand"].set_index(["psf_job_role", "psf_competency"]).job_ads.to_dict() == {
        ("engineer", "work closely"): 1, ("global professional", "activity"): 2}
    assert tables["psf_role_family_demand"].set_index(["psf_job_role", "job_family"]).job_ads.to_dict() == {
        ("engineer", "analytics"): 1, ("global professional", "analytics"): 2}
    assert tables["psf_framework_order"].psf_competency.tolist() == ["activity", "technical workflow", "work closely"]
    for current, before in ((mapping, before_mapping), (jobs, before_jobs), (taxonomy, before_taxonomy)):
        pd.testing.assert_frame_equal(current, before)
