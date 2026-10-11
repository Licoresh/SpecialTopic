"""SYNTHETIC DATA — NOT RESEARCH DATA."""
import pandas as pd
import pytest
from src.gap_analysis import calculate_gaps
from src.alignment import calculate_alignment


def test_correct_denominators_and_duplicates(jobs, taxonomy):
    skills = pd.DataFrame({"source_id": [jobs.source_id.iloc[0], jobs.source_id.iloc[0], jobs.source_id.iloc[1]], "normalized_phrase": ["sql"]*3, "original_phrase": ["SQL"]*3})
    alignment = calculate_alignment(skills, taxonomy)
    demand, unmapped, emerging, rates = calculate_gaps(skills, jobs, alignment)
    assert demand.iloc[0].employer_demand_count == 2
    assert demand.iloc[0].employer_demand_pct == pytest.approx(200/3)
    assert rates["alignment_rate"] == 100 and rates["unmapped_rate"] == 0
    assert unmapped.empty and emerging.empty


def test_missing_reference_not_zero(jobs):
    skills = pd.DataFrame({"source_id": [jobs.source_id.iloc[0]], "normalized_phrase": ["sql"], "original_phrase": ["SQL"]})
    alignment = calculate_alignment(skills, pd.DataFrame())
    demand, unmapped, emerging, rates = calculate_gaps(skills, jobs, alignment)
    assert rates["alignment_rate"] is None and rates["unmapped_rate"] is None
    assert unmapped.empty and emerging.empty


def test_rates_and_emerging_screen_use_explicit_denominators():
    jobs = pd.DataFrame({"source_id": ["a", "b", "c"]})
    skills = pd.DataFrame({"source_id": ["a", "a", "a", "b", "a"], "normalized_phrase": ["x", "y", "z", "z", "q"]})
    alignment = pd.DataFrame({"normalized_skill": ["x", "y", "z", "q"], "status": ["ALIGNED", "PARTIALLY ALIGNED", "NOT MAPPED", "UNCLASSIFIED"]})
    demand, unmapped, emerging, rates = calculate_gaps(skills, jobs, alignment)
    assert rates["alignment_rate"] == rates["partially_aligned_rate"] == 50
    assert rates["unmapped_rate"] == pytest.approx(100/3)
    assert rates["mapped_competencies"] == 2 and rates["assessed_competencies"] == 3
    assert emerging.normalized_skill.tolist() == ["z"]
    assert demand.set_index("normalized_skill").loc["z", "employer_demand_pct"] == pytest.approx(200/3)
