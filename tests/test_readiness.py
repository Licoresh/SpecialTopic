"""SYNTHETIC DATA — NOT RESEARCH DATA. These tests exercise audit warnings only."""
import pandas as pd
from src.readiness import (assess_research_readiness, source_overlap,
                           historical_category_disagreements, research_data_profile)


def test_detects_source_leakage_and_concentrated_sources():
    frame = pd.DataFrame({
        "phrase": ["written and", "data engineering", "machine learning", "communication skills"],
        "source_id": ["ad-a", "ad-a", "ad-a", "ad-b"],
        "reviewer": ["Researcher1", "Researcher1", "Researcher1", "Researcher1"],
    })
    metadata = {"split": {"train_source_rows": [2, 3], "test_source_rows": [4, 5]}}
    assert source_overlap(frame, metadata) == {"ad-a"}
    audit = assess_research_readiness(frame, metadata)
    titles = {finding["title"] for finding in audit["findings"]}
    assert "Saved evaluation leaks job-ad sources across partitions" in titles
    assert "Labels are concentrated in two postings" in titles
    assert "Independent annotation quality is not established by the app" in titles
    assert not audit["ready"]


def test_flags_reviewer_id_variants_and_short_phrases():
    frame = pd.DataFrame({
        "phrase": ["written and", "Excellent time", "Python programming"],
        "source_id": ["ad-a", "ad-b", "ad-c"],
        "reviewer": ["JC_Researcher1", "JC_Reasercher1", "JC_Reseracher1"],
    })
    audit = assess_research_readiness(frame)
    titles = {finding["title"] for finding in audit["findings"]}
    assert "Reviewer IDs need reconciliation" in titles
    assert "Some saved phrases end at a connector" in titles

def test_two_word_skill_terms_are_not_flagged_as_fragments():
    frame = pd.DataFrame({"phrase": ["data analysis", "time management", "Python programming"]})
    audit = assess_research_readiness(frame)
    assert "Some saved phrases end at a connector" not in {finding["title"] for finding in audit["findings"]}

def test_historical_disagreements_are_reported_without_modifying_current_rows():
    history = pd.DataFrame({
        "phrase": ["data analysis", "Data analysis"],
        "normalized_phrase": ["data analysis", "data analysis"],
        "label": ["Data / Analytics", "IRRELEVANT"],
        "reviewer": ["Reviewer A", "Reviewer B"],
        "source_id": ["ad-1", "ad-1"],
    })
    before = history.copy(deep=True)
    disagreements = historical_category_disagreements(history)
    assert len(disagreements) == 1
    assert "Data / Analytics" in disagreements.iloc[0].historical_categories
    assert "IRRELEVANT" in disagreements.iloc[0].historical_categories
    pd.testing.assert_frame_equal(history, before)


def test_research_data_profile_shows_source_and_reviewer_coverage_without_merging():
    frame = pd.DataFrame({
        "phrase": ["Data analysis", "data analysis", "Team leadership", "written and"],
        "normalized_phrase": ["data analysis", "data analysis", "team leadership", "written and"],
        "label": ["Data / Analytics", "Data / Analytics", "Leadership / Management", "IRRELEVANT"],
        "source_type": ["jobs"] * 4,
        "source_id": ["ad-1", "ad-1", "ad-2", "ad-2"],
        "reviewer": ["Reviewer_A", "Reviewer_A", "ReviewerA", "Reviewer_A"],
    })
    profile = research_data_profile(frame)
    sources = profile["sources"].set_index("source_id")
    assert sources.loc["ad-1", "annotation_rows"] == 2
    assert sources.loc["ad-1", "distinct_phrases"] == 1
    assert sources.loc["ad-2", "competency_phrases"] == 1
    assert sources.loc["ad-2", "irrelevant_phrases"] == 1
    assert profile["top_two_source_row_share"] == 1.0
    assert set(profile["reviewers"].reviewer) == {"Reviewer_A", "ReviewerA"}
