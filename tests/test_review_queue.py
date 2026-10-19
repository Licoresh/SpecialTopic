"""Synthetic fixtures for phrase-level review grouping; never research data."""

import pandas as pd

from src.review_queue import expand_phrase_annotations, group_candidates_by_phrase, labels_by_phrase


def test_repeated_phrase_is_one_review_row_but_retains_all_source_ads():
    candidates = pd.DataFrame([
        {"phrase": "Python", "normalized_phrase": "python", "source_type": "jobs", "source_id": "SYNTH-1",
         "job_title": "Analyst", "original_text": "Uses Python for analysis."},
        {"phrase": "python", "normalized_phrase": "python", "source_type": "jobs", "source_id": "SYNTH-2",
         "job_title": "Engineer", "original_text": "Build tools in python and automate reporting."},
        {"phrase": " Python ", "normalized_phrase": "python", "source_type": "jobs", "source_id": "SYNTH-2",
         "job_title": "Engineer", "original_text": "Duplicate extraction from the same ad."},
    ])

    grouped = group_candidates_by_phrase(candidates)

    assert len(grouped) == 1
    assert grouped.iloc[0].source_ads == 2
    assert grouped.iloc[0].source_id == "SYNTH-2"  # most informative context is the representative

    reviewed = pd.DataFrame([{
        "phrase": "Python", "normalized_phrase": "python", "source_type": "jobs", "source_id": "SYNTH-2",
        "label": "Technical / Digital", "psf_competency": "",
    }])
    expanded = expand_phrase_annotations(reviewed, candidates)

    assert set(expanded.source_id) == {"SYNTH-1", "SYNTH-2"}
    assert len(expanded) == 2
    assert set(expanded.label) == {"Technical / Digital"}


def test_saved_category_conflict_is_not_silently_selected():
    labels = pd.DataFrame([
        {"normalized_phrase": "python", "label": "Technical / Digital", "psf_competency": ""},
        {"normalized_phrase": "python", "label": "Data / Analytics", "psf_competency": ""},
    ])

    assert labels_by_phrase(labels)["python"]["label"] == ""


def test_category_only_save_preserves_each_ads_legacy_reference():
    from src.review_queue import preserve_occurrence_references
    rows = pd.DataFrame([
        dict(phrase="Python", normalized_phrase="python", source_type="jobs", source_id=key,
             label="Technical / Digital", psf_competency="") for key in ("a", "b", "c")
    ])
    previous = rows.iloc[:2].copy()
    previous["psf_competency"] = ["Python", "SQL"]
    result = preserve_occurrence_references(rows, previous)
    assert result.psf_competency.tolist() == ["Python", "SQL", ""]


def test_manual_mapping_prefers_exact_extracted_context():
    from src.review_queue import manual_mapping_occurrences
    from src.psf_reviews import occurrence_hash
    candidate = dict(phrase="Python", normalized_phrase="python", source_type="Philippine job advertisement",
                     source_id="a", original_text="Partial candidate context")
    extracted = dict(extraction_id="exact-id", original_phrase="Python", normalized_phrase="python",
                     source_type="jobs", source_id="a", original_text="Full source context used by analysis")
    rows = manual_mapping_occurrences(pd.DataFrame([candidate]), pd.DataFrame([extracted]))
    assert len(rows) == 1
    assert rows.iloc[0].extraction_id == "exact-id"
    assert occurrence_hash(rows.iloc[0]) == occurrence_hash(extracted)
