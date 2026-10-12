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
