"""Synthetic fixtures for phrase-level review grouping; never research data."""

import pandas as pd
import pytest

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


def _previous_labels_by_phrase(labels):
    result = {}
    if labels.empty or "normalized_phrase" not in labels:
        return result
    for normalized, group in labels.groupby("normalized_phrase", sort=False):
        result[str(normalized)] = {}
        for field in ("label", "psf_competency"):
            values = group.get(field, pd.Series(dtype=str)).fillna("").astype(str).str.strip()
            distinct = list(dict.fromkeys(value for value in values if value))
            result[str(normalized)][field] = distinct[0] if len(distinct) == 1 else ""
    return result


@pytest.mark.parametrize("missing_columns", [[], ["label"], ["psf_competency"], ["label", "psf_competency"], ["normalized_phrase"]])
def test_phrase_label_lookup_matches_previous_conflict_and_missing_value_rules(missing_columns):
    labels = pd.DataFrame([
        {"normalized_phrase": " Python ", "label": " Technical / Digital ", "psf_competency": None},
        {"normalized_phrase": "sql", "label": "Data / Analytics", "psf_competency": "Data Engineering"},
        {"normalized_phrase": " Python ", "label": None, "psf_competency": " Programming "},
        {"normalized_phrase": "sql", "label": " Technical / Digital ", "psf_competency": "Data Engineering"},
        {"normalized_phrase": "empty", "label": " \t ", "psf_competency": ""},
        {"normalized_phrase": None, "label": "Ignored", "psf_competency": "Ignored"},
        {"normalized_phrase": "psf conflict", "label": "Soft / Enabling", "psf_competency": "Communication"},
        {"normalized_phrase": "psf conflict", "label": " Soft / Enabling ", "psf_competency": "Collaboration"},
        {"normalized_phrase": "python", "label": "AI / Machine Learning", "psf_competency": pd.NA},
        {"normalized_phrase": "", "label": "Literal empty phrase", "psf_competency": ""},
        {"normalized_phrase": float("nan"), "label": "Ignored", "psf_competency": "Ignored"},
    ], index=[9, 3, 3, 8, 12, -1, 30, 18, 1, 55, 7]).drop(columns=missing_columns)
    before = labels.copy(deep=True)
    expected = _previous_labels_by_phrase(labels)
    actual = labels_by_phrase(labels)
    assert actual == expected
    assert list(actual) == list(expected)
    pd.testing.assert_frame_equal(labels, before)


def test_phrase_label_lookup_keeps_stringified_keys_and_empty_input_behavior():
    labels = pd.DataFrame({"normalized_phrase": [2, "SQL", 2, 1],
                           "label": [0, "Technical / Digital", " 0 ", False],
                           "psf_competency": [None, "", "", None]})
    assert labels_by_phrase(labels) == _previous_labels_by_phrase(labels)
    assert list(labels_by_phrase(labels)) == ["2", "SQL", "1"]
    assert labels_by_phrase(pd.DataFrame(columns=labels.columns)) == {}
    assert labels_by_phrase(pd.DataFrame({"normalized_phrase": [None, pd.NA, float("nan")]})) == {}


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


def test_manual_mapping_restores_shared_extraction_context_from_same_candidate():
    from src.review_queue import manual_mapping_occurrences
    candidate = dict(phrase="Build data models", normalized_phrase="build data models",
                     source_type="jobs", source_id="SYNTH-2",
                     original_text="Ad 2: Build data models using Python.")
    extracted = dict(extraction_id="exact-id", original_phrase="Build data models",
                     normalized_phrase="build data models", source_type="jobs",
                     source_id="SYNTH-2")  # Shared extraction index omits long text.

    rows = manual_mapping_occurrences(pd.DataFrame([candidate]), pd.DataFrame([extracted]))

    assert len(rows) == 1
    assert rows.iloc[0].extraction_id == "exact-id"
    assert rows.iloc[0].original_text == candidate["original_text"]


def test_manual_mapping_never_borrows_context_from_another_ad():
    from src.review_queue import manual_mapping_occurrences
    candidates = pd.DataFrame([
        dict(phrase="SQL", normalized_phrase="sql", source_type="jobs", source_id="SYNTH-1",
             original_text="Ad 1 mentions SQL."),
        dict(phrase="SQL", normalized_phrase="sql", source_type="jobs", source_id="SYNTH-2",
             original_text="Ad 2 mentions SQL."),
    ])
    extracted = pd.DataFrame([dict(extraction_id="exact-id", original_phrase="SQL",
                                   normalized_phrase="sql", source_type="jobs", source_id="SYNTH-2")])

    rows = manual_mapping_occurrences(candidates, extracted)

    context = rows.loc[rows.source_id.eq("SYNTH-2"), "original_text"].item()
    assert context == "Ad 2 mentions SQL."
