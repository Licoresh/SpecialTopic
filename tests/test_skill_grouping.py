"""Synthetic grouping checks; never research data or training inputs."""
import pandas as pd
import pytest

from src.analytics import chart_skill_key, chart_mapping_rows, psf_demand_tables, skill_chart_tables, unmapped_chart_counts


GROUPS = [
    ("cloud computing", ["cloud compute", "cloud computing"]),
    ("quality standards", ["quality standard", "quality standards"]),
    ("data visualization", ["data visualisation", "data visualization", "data-visualization"]),
    ("excel", ["Excel", "knowledge of Excel", "strong knowledge of Excel", "proficiency with Microsoft Excel"]),
    ("problem solving", ["problem solving skills", "problem-solving skill", "problem solving"]),
    ("dashboard development", ["build dashboard", "develop dashboards", "create dashboards", "dashboard development"]),
    ("dashboard improvement", ["enhance dashboard", "improve dashboards", "dashboard improvement"]),
    ("dashboard maintenance", ["maintain dashboard", "maintaining dashboards", "dashboard maintenance"]),
    ("due diligence", ["conduct due diligence", "perform due diligence", "due diligence"]),
    ("training and development", ["train and development", "training and development"]),
    ("data analysis", ["perform advanced data analysis", "advanced data analysis", "data analysis"]),
    ("communication", ["conduct strong communication", "strong communication", "communication"]),
    ("dashboard development", ["perform building dashboards", "build dashboards"]),
]


def skills(values):
    return pd.DataFrame([
        {"source_id": source, "source_type": "jobs", "extraction_id": f"SYNTHETIC-{index}",
         "normalized_phrase": phrase, "original_phrase": phrase, "original_text": "SYNTHETIC SOURCE EVIDENCE",
         "accepted": True, "competency_category": "Technical / Digital", "skill_type": "Technical",
         "human_label": "Technical / Digital"}
        for index, (source, phrase) in enumerate(values)])


@pytest.mark.parametrize("label,variants", GROUPS)
def test_wording_families_have_one_idempotent_key(label, variants):
    for variant in variants:
        assert chart_skill_key(variant) == label
        assert chart_skill_key(chart_skill_key(variant)) == label


@pytest.mark.parametrize("left,right", [
    ("data analysis", "data analytics"), ("data analysis", "data engineering"),
    ("written communication skills", "verbal communication skills"),
    ("machine learning", "deep learning"),
    ("dashboard development", "dashboard maintenance"),
    ("dashboard maintenance", "dashboard improvement"),
    ("training and development", "learning and development"),
    ("knowledge of SQL", "SQL injection testing"),
])
def test_substantive_skill_distinctions_survive(left, right):
    assert chart_skill_key(left) != chart_skill_key(right)


def test_aliases_count_ads_once_and_keep_all_variant_evidence():
    frame = skills([("A", "cloud compute"), ("A", "cloud computing"),
                    ("B", "cloud computing"), ("OUTSIDE", "cloud computing")])
    original = frame.copy(deep=True)
    jobs = pd.DataFrame({"source_id": list("ABC"), "job_family": ["analytics", "analytics", "operations"]})
    tables = skill_chart_tables(frame, jobs)
    assert tables["chart_skill_demand"].employer_skill.tolist() == ["cloud computing"]
    assert tables["chart_skill_demand"].employer_demand_count.tolist() == [2]
    assert tables["chart_skill_demand"].employer_demand_pct.tolist() == [pytest.approx(200 / 3)]
    assert len(tables["chart_skill_occurrences"]) == 2
    assert tables["chart_skill_family_demand"].job_ads.tolist() == [2]
    audit = tables["chart_skill_variants"]
    assert set(audit.original_normalized_phrase) == {"cloud compute", "cloud computing"}
    assert audit.set_index("original_normalized_phrase").job_ads.to_dict() == {"cloud compute": 1, "cloud computing": 2}
    assert audit.skill_label.eq("cloud computing").all()
    assert "grouping_basis" in audit
    assert audit.grouping_basis.str.len().gt(0).all()
    pd.testing.assert_frame_equal(frame, original)
    alignment = pd.DataFrame({"normalized_skill": ["cloud compute", "cloud computing"], "status": ["NOT MAPPED"] * 2})
    counts = unmapped_chart_counts(tables["chart_skill_occurrences"], alignment, minimum_jobs=2)
    assert counts.skill_label.tolist() == ["cloud computing"] and counts.job_ads.tolist() == [2]
    assert unmapped_chart_counts(tables["chart_skill_occurrences"], alignment, minimum_jobs=3).empty
    alignment.loc[0, "status"] = "ALIGNED"
    assert unmapped_chart_counts(tables["chart_skill_occurrences"], alignment).empty


def test_status_scope_matches_original_phrase_before_alias_deduplication():
    frame = skills([("A", "cloud compute"), ("A", "cloud computing"), ("B", "cloud computing")])
    jobs = pd.DataFrame({"source_id": ["A", "B"]})
    tables = skill_chart_tables(frame, jobs, allowed_phrases={"cloud compute"})
    assert tables["chart_skill_demand"].employer_demand_count.tolist() == [1]
    assert tables["chart_skill_occurrences"].original_normalized_phrase.tolist() == ["cloud compute"]
    assert tables["chart_skill_variants"].original_normalized_phrase.tolist() == ["cloud compute"]


def test_aliases_do_not_merge_or_spread_occurrence_specific_psf_links():
    mapping = pd.DataFrame({"source_id": ["A", "B"], "extraction_id": ["SYNTHETIC-A", "SYNTHETIC-B"],
                            "normalized_skill": ["cloud compute", "cloud computing"],
                            "psf_competency": ["Cloud Computing", "System Integration"],
                            "psf_job_role": ["Reference role one", "Reference role two"],
                            "status": ["ALIGNED", "PARTIALLY ALIGNED"]})
    original = mapping.copy(deep=True)
    pd.testing.assert_frame_equal(chart_mapping_rows(mapping), original)
    jobs = pd.DataFrame({"source_id": ["A", "B", "C"]})
    taxonomy = pd.DataFrame({"competency_id": ["SYNTHETIC-1", "SYNTHETIC-2"],
                             "competency_name": ["Cloud Computing", "System Integration"]})
    demand = psf_demand_tables(mapping, jobs, taxonomy)
    assert demand["psf_chart_demand"].set_index("psf_competency").job_ads.to_dict() == {
        "cloud computing": 1, "system integration": 1}
    assert demand["psf_role_competency_demand"].set_index("psf_job_role").psf_competency.to_dict() == {
        "reference role one": "cloud computing", "reference role two": "system integration"}
    pd.testing.assert_frame_equal(mapping, original)


def test_conflicting_variant_types_do_not_make_split_charts_row_order_dependent():
    frame = skills([("A", "SQL"), ("A", "knowledge of SQL")])
    frame.loc[1, ["competency_category", "skill_type", "human_label"]] = ["Soft / Enabling"] * 3
    original = frame.copy(deep=True)
    jobs = pd.DataFrame({"source_id": ["A"]})
    for ordered in (frame, frame.iloc[::-1]):
        tables = skill_chart_tables(ordered, jobs)
        occurrences = tables["chart_skill_occurrences"]
        assert tables["chart_skill_demand"].employer_demand_count.tolist() == [1]
        assert occurrences.skill_type.tolist() == ["Other / Unclassified"]
        assert occurrences.category_conflict.tolist() == [True]
        audit = tables["chart_skill_variants"]
        assert set(audit.skill_type) == {"Technical", "Soft / Enabling"}
        assert audit.category_conflict.all()
    pd.testing.assert_frame_equal(frame, original)
