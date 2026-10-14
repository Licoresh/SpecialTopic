"""Synthetic tests for the local, resumable suggestion workflow."""
import pandas as pd

from src import storage
from src.labeling import save_annotations
from src.unattended_suggestions import run_local_suggestions


def test_local_suggestion_run_is_resumable_and_never_saves_labels(workspace, monkeypatch):
    taxonomy = pd.DataFrame([{
        "competency_name": "SQL",
        "competency_category": "Data / Analytics",
        "source_page": "SYNTHETIC TEST FIXTURE",
        "source_url": "https://example.invalid/synthetic",
    }])
    taxonomy_path = workspace / "data/processed/cleaned_psf_aai.csv"
    taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
    taxonomy.to_csv(taxonomy_path, index=False)

    save_annotations(pd.DataFrame([{
        "phrase": "reviewed phrase",
        "label": "Technical / Digital",
        "source_type": "Philippine job advertisement",
        "source_id": "SYNTHETIC-REVIEWED-1",
    }]), "SYNTHETIC TEST REVIEWER")

    candidate_path = workspace / "train/raw/synthetic_candidates.csv"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"phrase": "reviewed phrase", "label": "", "source_type": "Philippine job advertisement", "source_id": "SYNTHETIC-REVIEWED-1"},
        {"phrase": "new phrase", "label": "", "source_type": "Philippine job advertisement", "source_id": "SYNTHETIC-PENDING-1", "original_text": "SYNTHETIC TEST DATA"},
        {"phrase": "untraceable phrase", "label": "", "source_type": "Philippine job advertisement", "source_id": ""},
    ]).to_csv(candidate_path, index=False)

    def fake_suggest(records, active_taxonomy):
        assert len(active_taxonomy) == 1
        return [{"label": "Data / Analytics", "psf_competency": "SQL", "score": 0.7, "psf_score": 0.8} for _ in records]

    monkeypatch.setattr("src.unattended_suggestions.suggest_labels", fake_suggest)
    first = run_local_suggestions(workspace, chunksize=2, batch_size=1)
    saved_labels = storage.read_frame("labeled_competencies")
    assert first["suggestions_generated"] == 1
    assert first["already_reviewed"] == 1
    assert first["missing_source_id"] == 1
    assert len(saved_labels) == 1
    assert saved_labels.label.iloc[0] == "Technical / Digital"

    second = run_local_suggestions(workspace, chunksize=2, batch_size=1)
    assert second["suggestions_generated"] == 0
    assert second["already_suggested"] == 1


def test_draft_limit_resumes_without_skipping_unsaved_rows(workspace, monkeypatch):
    from src import unattended_suggestions as runner
    candidate = workspace / "train/raw/synthetic_candidates.csv"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"phrase": f"synthetic skill {i}", "source_type": "jobs", "source_id": f"synthetic-{i}"} for i in range(7)]).to_csv(candidate, index=False)
    monkeypatch.setattr(runner, "training_taxonomy", lambda root: pd.DataFrame([{"competency_name": "Synthetic"}]))
    monkeypatch.setattr(runner, "read_annotations", lambda root: pd.DataFrame())
    monkeypatch.setattr(runner, "suggest_labels", lambda rows, taxonomy: [{"label": "Data / Analytics"} for _ in rows])
    assert runner.run_local_suggestions(workspace, batch_size=2, max_drafts=3)["suggestions_generated"] == 3
    assert runner.run_local_suggestions(workspace, batch_size=2, max_drafts=3)["suggestions_generated"] == 3
    assert runner.run_local_suggestions(workspace, batch_size=2, max_drafts=3)["suggestions_generated"] == 1
