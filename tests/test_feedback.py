import pandas as pd
import pytest
from src.labeling import annotation_conflicts, save_annotations, save_correction, apply_corrections, corrections
from src.storage import read_frame

def test_audited_corrections_and_annotations(workspace):
    save_annotations(pd.DataFrame([{"phrase":"SQL", "label":"Technical"}]), "test-reviewer")
    save_annotations(pd.DataFrame([{"phrase":"sql", "label":"Data"}]), "test-reviewer", conflict_resolutions={"sql": "Data"})
    assert len(read_frame("labeled_competencies")) == 1
    assert len(pd.read_csv(workspace/"data/feedback/annotation_history.csv")) == 3
    frame = pd.DataFrame({"extraction_id":["one"], "competency_category":["Technical"]})
    save_correction("extraction", "one", "competency_category", "Technical", "Data", "test-reviewer")
    result = apply_corrections(frame, "extraction", "extraction_id")
    assert result.competency_category.iloc[0] == "Data"
    assert frame.competency_category.iloc[0] == "Technical"
    assert corrections().original_prediction.iloc[0] == "Technical"

def test_category_correction_updates_dependent_filters(workspace, jobs):
    from src import storage
    from src.workflow import run_extraction, analysis_bundle
    storage.save_frame("cleaned_jobs", jobs)
    result = run_extraction()
    row = result[result.normalized_phrase.eq("python")].iloc[0]
    save_correction("extraction", row.extraction_id, "competency_category", row.competency_category, "Soft / Enabling", "test-reviewer")
    tables, _ = analysis_bundle(skill_filters={"skill_type":["Soft / Enabling"]})
    assert row.extraction_id in set(tables["extracted_job_skills"].extraction_id)
    corrected = tables["extracted_job_skills"].set_index("extraction_id").loc[row.extraction_id]
    assert corrected.human_label == "Soft / Enabling"

def test_annotation_saving_preserves_headers_and_rejects_conflicts(workspace):
    import pytest
    from src.training_data import LABEL_COLUMNS
    assert list(read_frame("labeled_competencies")) == LABEL_COLUMNS
    rows = pd.DataFrame([{"phrase":"SQL", "label":"Data"}, {"phrase":"sql", "label":"Soft"}])
    with pytest.raises(ValueError, match="conflicting"):
        save_annotations(rows, "Synthetic reviewer")
    assert read_frame("labeled_competencies").empty
    save_annotations(rows.iloc[:1], "Synthetic reviewer")
    saved = read_frame("labeled_competencies")
    assert list(saved) == LABEL_COLUMNS
    assert saved.reviewer.iloc[0] == "Synthetic reviewer" and saved.timestamp.iloc[0]

def test_conflicting_categories_can_be_resolved_consistently_and_audited(workspace):
    import pytest

    first = pd.DataFrame([
        {"phrase": "SQL", "label": "Technical", "source_type": "job", "source_id": "one"},
        {"phrase": "sql", "label": "Data", "source_type": "job", "source_id": "two"},
    ])
    assert annotation_conflicts(first)["sql"]["labels"] == ["Data", "Technical"]
    with pytest.raises(ValueError, match="Resolve each conflicting phrase"):
        save_annotations(first, "researcher-1")

    resolved = save_annotations(first, "researcher-1", conflict_resolutions={"sql": "Data"})
    assert set(resolved.label) == {"Data"}
    assert resolved.normalized_phrase.tolist() == ["sql", "sql"]
    assert len(pd.read_csv(workspace / "data/feedback/annotation_history.csv")) == 2

def test_resolution_can_reconcile_existing_saved_rows(workspace):
    first = pd.DataFrame([
        {"phrase": "SQL", "label": "Technical", "source_type": "job", "source_id": "one"},
    ])
    save_annotations(first, "researcher-1")
    second = pd.DataFrame([
        {"phrase": "sql", "label": "Data", "source_type": "job", "source_id": "two"},
    ])
    assert annotation_conflicts(second, read_frame("labeled_competencies"))["sql"]["labels"] == ["Data", "Technical"]
    saved = save_annotations(second, "researcher-2", conflict_resolutions={"sql": "Data"})
    assert set(saved.label) == {"Data"}
    assert set(saved.reviewer) == {"researcher-2"}
    history = pd.read_csv(workspace / "data/feedback/annotation_history.csv")
    assert len(history) == 3  # original save plus the audited correction and new occurrence

def test_existing_conflicts_can_be_resolved_without_adding_new_labels(workspace):
    from src import storage
    from src.training_data import LABEL_COLUMNS

    legacy = pd.DataFrame([
        {"phrase":"SQL", "normalized_phrase":"sql", "label":"Technical", "source_type":"job", "source_id":"one", "reviewer":"old", "timestamp":"old"},
        {"phrase":"sql", "normalized_phrase":"sql", "label":"Data", "source_type":"job", "source_id":"two", "reviewer":"old", "timestamp":"old"},
    ])
    for column in LABEL_COLUMNS:
        if column not in legacy:
            legacy[column] = ""
    storage.save_frame("labeled_competencies", legacy[LABEL_COLUMNS])
    assert annotation_conflicts(pd.DataFrame(columns=["phrase", "label"]), read_frame("labeled_competencies"))["sql"]["labels"] == ["Data", "Technical"]

    empty = pd.DataFrame(columns=["phrase", "label"])
    with pytest.raises(ValueError, match="Resolve each conflicting phrase"):
        save_annotations(pd.DataFrame([{"phrase":"Python", "label":"Technical"}]), "reviewer")
    resolved = save_annotations(empty, "reviewer", conflict_resolutions={"sql":"Data"})
    assert set(resolved.label) == {"Data"}
    assert len(resolved) == 2
    assert not annotation_conflicts(empty, resolved)

def test_team_annotation_merge_preserves_each_reviewers_provenance(workspace):
    team_rows = pd.DataFrame([
        {"phrase":"SQL querying", "label":"Data / Analytics", "psf_competency":"", "source_type":"Philippine job advertisement", "source_id":"JOB-1", "reviewer":"reviewer-A", "timestamp":"2026-10-01T09:00:00+08:00"},
        {"phrase":"Python programming", "label":"Technical / Digital", "psf_competency":"", "source_type":"Philippine job advertisement", "source_id":"JOB-2", "reviewer":"reviewer-B", "timestamp":"2026-10-02T10:30:00+08:00"},
    ])
    merged = save_annotations(team_rows, "coordinator", preserve_row_provenance=True)
    saved = merged.set_index("source_id")
    assert saved.loc["JOB-1", "reviewer"] == "reviewer-A"
    assert saved.loc["JOB-1", "timestamp"] == "2026-10-01T09:00:00+08:00"
    assert saved.loc["JOB-2", "reviewer"] == "reviewer-B"

def test_team_annotation_merge_rejects_missing_reviewer_provenance(workspace):
    rows = pd.DataFrame([{"phrase":"SQL", "label":"Data / Analytics", "source_type":"jobs", "source_id":"JOB-1"}])
    with pytest.raises(ValueError, match="reviewer, and timestamp"):
        save_annotations(rows, "coordinator", preserve_row_provenance=True)
