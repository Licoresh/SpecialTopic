"""SYNTHETIC DATA — NOT RESEARCH DATA. Training packs below exist only in tmp_path."""
from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src import storage, ui
from src.labeling import save_annotations
from src.training_sources import (inspect_training_folder, resolve_training_file, training_candidates,
                                  select_training_file, ANNOTATION_COLUMNS)
from src.training_data import load_labeled_data, validate_labeled_data
from src.model_training import train_and_save_models, training_data_changed

def pack(root):
    folder = root/"train/raw"
    folder.mkdir(parents=True)
    pd.DataFrame([{"job_id":"TEST-PH-1", "job_title":"Synthetic analyst", "skills_summary":"SQL; Python", "source_url":"https://example.test/synthetic"}]).to_csv(folder/"source_table.csv", index=False)
    pd.DataFrame([{"phrase":"SQL", "normalized_phrase":"sql", "label":"", "psf_competency":"", "source_type":"Philippine job advertisement", "source_id":"TEST-PH-1", "source_url":"https://example.test/synthetic", "job_title":"Synthetic analyst"},
                  {"phrase":"SQL", "normalized_phrase":"sql", "label":"", "psf_competency":"", "source_type":"Philippine job advertisement", "source_id":"TEST-PH-2", "source_url":"https://example.test/synthetic2", "job_title":"Synthetic analyst 2"}]).to_csv(folder/"unusual_candidates_name.csv", index=False)
    pd.DataFrame(columns=ANNOTATION_COLUMNS).to_csv(folder/"empty_schema.csv", index=False)
    (root/"train/README.md").write_text("SYNTHETIC DATA — NOT RESEARCH DATA", encoding="utf-8")
    return folder

def test_content_based_discovery_and_candidate_context(workspace):
    folder = pack(workspace)
    inventory = inspect_training_folder(workspace)
    purposes = {row["filename"]:row["purpose"] for row in inventory}
    assert purposes[str(Path("raw/unusual_candidates_name.csv"))] == "candidate phrases"
    assert purposes[str(Path("raw/source_table.csv"))] == "job-ad source data"
    path = resolve_training_file(workspace)
    assert path == workspace/"train/labeled_competencies.csv"
    assert list(pd.read_csv(path)) == ANNOTATION_COLUMNS
    candidates = training_candidates(workspace)
    assert len(candidates) == 2
    assert candidates.loc[candidates.source_id.eq("TEST-PH-1"), "original_text"].iloc[0] == "SQL; Python"
    assert storage.read_frame("labeled_competencies").empty

def test_reviews_preserve_occurrences_and_source_files(workspace):
    folder = pack(workspace)
    original = {p:p.read_bytes() for p in folder.glob("*.csv")}
    candidates = training_candidates(workspace)
    reviewed = candidates[["phrase","source_type","source_id"]].assign(label="Technical", psf_competency="")
    saved = save_annotations(reviewed, "SYNTHETIC REVIEWER")
    assert len(saved) == 2 and saved.source_id.nunique() == 2
    assert list(pd.read_csv(workspace/"train/labeled_competencies.csv")) == ANNOTATION_COLUMNS
    assert not (workspace/"data/processed/labeled_competencies.csv").exists()
    data, report = validate_labeled_data(saved, require_provenance=True)
    assert len(data) == 1 and report["duplicate_phrase_label_pairs"] == 1
    assert all(path.read_bytes() == content for path,content in original.items())
    reloaded = training_candidates(workspace)
    assert len(reloaded) == 2
    assert reloaded.source_url.str.startswith("https://example.test/").all()
    assert reloaded.loc[reloaded.source_id.eq("TEST-PH-1"), "original_text"].iloc[0] == "SQL; Python"

def test_detect_populated_actual_filename_and_explicit_selection(workspace, labeled):
    folder = pack(workspace)
    rows = labeled.assign(normalized_phrase=labeled.phrase, reviewer="SYNTHETIC REVIEWER", timestamp="2026-10-10T00:00:00+00:00", psf_competency="")
    path = folder/"reviewed_annotations.csv"
    rows.to_csv(path, index=False)
    assert resolve_training_file(workspace) == path
    metadata, _ = train_and_save_models()
    assert metadata["training_file"] == str(path.resolve())
    assert metadata["rows_available"] == metadata["rows_used"] == 30
    assert not training_data_changed()
    (folder/"another_review.csv").write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="Multiple populated"):
        resolve_training_file(workspace)
    selected = select_training_file(workspace, "raw/reviewed_annotations.csv")
    assert selected == path.resolve()
    assert resolve_training_file(workspace) == selected
    assert not training_data_changed()
    path.write_bytes(path.read_bytes()+b"\n")
    assert training_data_changed()

def test_unknown_or_unreviewed_files_cannot_be_selected(workspace):
    pack(workspace)
    with pytest.raises(ValueError, match="unreviewed candidate"):
        select_training_file(workspace, "raw/unusual_candidates_name.csv")
    with pytest.raises(ValueError, match="within"):
        select_training_file(workspace, "../../outside.csv")

def test_missing_provenance_excludes_rows(workspace, labeled):
    rows = labeled.assign(reviewer="", timestamp="", normalized_phrase=labeled.phrase, psf_competency="")
    path = resolve_training_file(workspace)
    rows.to_csv(path,index=False)
    _, report = validate_labeled_data(load_labeled_data(path), require_provenance=True)
    assert not report["valid"] and report["rows_used"] == 0
    assert report["additional_distinct_labels_needed"] == 30
    assert report["additional_classes_needed"] == 2
    with pytest.raises(ValueError):
        train_and_save_models()
    assert not list((workspace/"models").glob("*.joblib"))

def test_pack_manual_labeling_and_disabled_training_pages(workspace, monkeypatch):
    folder = pack(workspace)
    monkeypatch.setattr(ui, "ROOT", workspace)
    app = AppTest.from_string("from src.ui import render\nrender('Manual Labeling')").run(timeout=60)
    assert not app.exception and not app.error
    assert any("2 candidate occurrences" in caption.value for caption in app.caption)
    assert storage.read_frame("labeled_competencies").empty
    training = AppTest.from_string("from src.ui import render\nrender('ML Training')").run(timeout=60)
    assert not training.exception and not training.error
    button = next(button for button in training.button if button.label == "Train / Retrain Models")
    assert button.disabled
    assert any("Training data file" in caption.value for caption in training.caption)
    assert not list((workspace/"models").glob("*.joblib"))
