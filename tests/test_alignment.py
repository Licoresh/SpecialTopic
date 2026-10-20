"""SYNTHETIC DATA — NOT RESEARCH DATA."""
import pandas as pd
from src.analytics import filter_frame
import pytest
from src.alignment import calculate_alignment


def detections(terms):
    return pd.DataFrame({"normalized_phrase": [t.lower() for t in terms], "original_phrase": terms, "source_id": [str(i) for i in range(len(terms))]})


def test_alignment_all_statuses_and_thresholds(taxonomy):
    skills = detections(["Python", "data mining", "zzzzzz"])
    result = calculate_alignment(skills, taxonomy, .9, .4).set_index("normalized_skill")
    assert result.loc["python", "status"] == "ALIGNED"
    assert result.loc["data mining", "status"] == "PARTIALLY ALIGNED"
    assert result.loc["zzzzzz", "status"] == "NOT MAPPED"
    unknown = calculate_alignment(skills, pd.DataFrame())
    assert set(unknown.status) == {"UNCLASSIFIED"}
    assert unknown.similarity_score.isna().all()
    with pytest.raises(ValueError):
        calculate_alignment(skills, taxonomy, .4, .8)


def test_alignment_correction_identity_depends_on_reference(taxonomy):
    skills = detections(["Python"])
    first = calculate_alignment(skills, taxonomy)
    taxonomy.loc[0, "competency_description"] = "Different source description"
    second = calculate_alignment(skills, taxonomy)
    assert first.alignment_id.iloc[0] != second.alignment_id.iloc[0]


def test_reference_traceability_and_human_assignment(taxonomy):
    taxonomy.loc[1, ["source_page", "source_url", "source_hash"]] = ["99", "https://example.test/reference", "SYNTHETIC-HASH"]
    skills = detections(["database querying"])
    skills["matching_method"] = "human_annotation"
    skills["psf_competency"] = "SQL"
    result = calculate_alignment(skills, taxonomy).iloc[0]
    assert result.psf_competency == "SQL" and result.source_page == "99"
    assert result.match_method == "human_annotation" and result.status == "ALIGNED"


def test_verified_range_of_application_is_retained_in_alignment(taxonomy):
    taxonomy.loc[0, "range_of_application"] = "SYNTHETIC RANGE: code review and deployment"
    taxonomy.loc[0, "competency_description"] = "SYNTHETIC DESCRIPTION: build and test programs"
    result = calculate_alignment(detections(["Python"]), taxonomy).iloc[0]
    assert result.psf_range_of_application == "SYNTHETIC RANGE: code review and deployment"
    assert result.psf_competency_description == "SYNTHETIC DESCRIPTION: build and test programs"
def test_skill_phrase_filter_is_case_insensitive_literal_substring():
    frame = pd.DataFrame({"normalized_phrase": ["sql querying", "python programming", "c++"]})
    filtered = filter_frame(frame, {"normalized_phrase_contains": "SQL"})
    assert filtered.normalized_phrase.tolist() == ["sql querying"]
