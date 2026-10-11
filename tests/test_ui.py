"""SYNTHETIC DATA — NOT RESEARCH DATA; real Streamlit script execution."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from src import storage, ui
from src.labeling import save_annotations
from src.workflow import run_extraction

PAGES = list(ui.PAGES)

def page_app(title):
    return AppTest.from_string(f"from src.ui import render\nrender({title!r})").run(timeout=60)

@pytest.fixture
def ui_workspace(workspace, monkeypatch):
    monkeypatch.setattr(ui, "ROOT", workspace)
    return workspace

@pytest.mark.parametrize("title", PAGES)
def test_empty_pages(title, ui_workspace):
    app = page_app(title)
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]

@pytest.mark.parametrize("title", PAGES)
def test_populated_pages(title, ui_workspace, jobs, taxonomy, labeled):
    for kind, frame in (("jobs",jobs),("psf_aai",taxonomy)):
        storage.save_frame("cleaned_"+kind, frame)
        storage.save_frame("mapped_"+kind, frame)
    save_annotations(labeled, "Synthetic reviewer")
    run_extraction()
    app = page_app(title)
    assert not app.exception, [e.message for e in app.exception]
    assert not app.error, [e.value for e in app.error]

def test_training_selection_and_evaluation(ui_workspace, labeled):
    save_annotations(labeled, "Synthetic reviewer")
    app = page_app("ML Training")
    app.button[0].click().run(timeout=60)
    assert not app.exception and not app.error
    assert len(storage.read_frame("model_metrics")) == 2
    assert (ui_workspace/"models/competency_classifier.joblib").exists()
    assert (ui_workspace/"models/model_metadata.json").exists()
    before = (ui_workspace/"models/competency_classifier.joblib").stat().st_mtime_ns
    app.run(timeout=60)
    assert (ui_workspace/"models/competency_classifier.joblib").stat().st_mtime_ns == before
    evaluation = page_app("Model Evaluation")
    assert not evaluation.exception and not evaluation.error
    evaluation.text_input[0].set_value("Python programming").run(timeout=60)
    evaluation.button[0].click().run(timeout=60)
    assert not evaluation.exception and not evaluation.error

def test_training_disabled_with_no_or_insufficient_labels(ui_workspace, labeled):
    app = page_app("ML Training")
    assert app.button[0].disabled
    assert not list((ui_workspace/"models").glob("*.joblib"))
    save_annotations(labeled.iloc[:8], "Synthetic reviewer")
    app.run(timeout=60)
    assert app.button[0].disabled
    evaluation = page_app("Model Evaluation")
    assert not evaluation.metric
    assert any("No research model" in message.value for message in evaluation.info)

def test_changed_dataset_warns_without_automatic_retraining(ui_workspace, labeled):
    save_annotations(labeled, "Synthetic reviewer")
    app = page_app("ML Training")
    app.button[0].click().run(timeout=60)
    model = ui_workspace/"models/competency_classifier.joblib"
    before = model.stat().st_mtime_ns
    path = ui_workspace/"train/labeled_competencies.csv"
    path.write_bytes(path.read_bytes()+b"\n")
    app.run(timeout=60)
    assert any("Training data has changed since this model was trained" in warning.value for warning in app.warning)
    assert model.stat().st_mtime_ns == before

def test_manual_labels_not_invented_from_candidates(ui_workspace, jobs):
    storage.save_frame("cleaned_jobs", jobs)
    run_extraction()
    app = page_app("Manual Labeling")
    assert not app.exception and not app.error
    assert storage.read_frame("labeled_competencies").empty
    assert app.checkbox[0].value is False

def test_manual_retraining_is_opt_in_by_default(ui_workspace):
    app = page_app("Manual Labeling")
    retrain = next(box for box in app.checkbox if box.label == "Automatically retrain after saving reviewed labels")
    assert retrain.value is False

def test_manual_labeling_can_resolve_all_saved_category_conflicts(ui_workspace):
    import pandas as pd
    from src.training_data import LABEL_COLUMNS
    legacy = pd.DataFrame([
        {"phrase":"SQL", "normalized_phrase":"sql", "label":"Technical / Digital", "source_type":"Philippine job advertisement", "source_id":"SYNTHETIC-1", "reviewer":"old", "timestamp":"old"},
        {"phrase":"sql", "normalized_phrase":"sql", "label":"Data / Analytics", "source_type":"Philippine job advertisement", "source_id":"SYNTHETIC-2", "reviewer":"old", "timestamp":"old"},
    ])
    for column in LABEL_COLUMNS:
        if column not in legacy:
            legacy[column] = ""
    storage.save_frame("labeled_competencies", legacy[LABEL_COLUMNS])
    script = '''import pandas as pd
from unittest.mock import patch
from src.ui import render
def choose_one_category(frame, **kwargs):
    assert list(frame.columns) == ["Phrase", "Existing categories", "Choose category"]
    resolved = frame.copy()
    if "Choose category" in resolved.columns:
        resolved.iloc[0, resolved.columns.get_loc("Choose category")] = "Data / Analytics"
    return resolved
with patch("streamlit.data_editor", side_effect=choose_one_category):
    render("Manual Labeling")
'''
    app = AppTest.from_string(script).run(timeout=60)
    app.text_input(key="label_reviewer").set_value("Synthetic resolver").run(timeout=60)
    next(button for button in app.button if button.label == "Save annotations").click().run(timeout=60)
    assert not app.exception and not app.error
    saved = storage.read_frame("labeled_competencies")
    assert set(saved.label) == {"Data / Analytics"}

def test_mapping_cleaning_extraction_buttons(ui_workspace):
    storage.archive_raw(b"Position,Details\nSynthetic analyst,Python and SQL", "jobs.csv", "jobs")
    storage.save_json("read_options_jobs", {"sheet":0,"encoding":"utf-8-sig"})
    app = page_app("Job Data Upload")
    for box in app.selectbox:
        if box.label == "Job Title":
            box.select("Position")
        if box.label == "Job Description":
            box.select("Details")
    app.button[0].click().run(timeout=60)
    assert not app.error and not app.exception
    quality = page_app("Data Quality")
    quality.checkbox[0].check()
    quality.button[0].click().run(timeout=60)
    assert len(storage.read_frame("cleaned_jobs")) == 1
    extraction = page_app("Competency Extraction")
    extraction.button[0].click().run(timeout=60)
    assert not extraction.error and not extraction.exception
    assert not storage.read_frame("extractions_original").empty

def test_main_app_launch(ui_workspace):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py")).run(timeout=60)
    assert not app.exception and not app.error

@pytest.mark.parametrize("kind,content", [
    ("jobs", "role,text\nSynthetic analyst,Python"),
    ("psf_aai", "name,category\nSynthetic competency,Test category"),
    ("stakeholder", "role,rating\nSynthetic reviewer,4"),
])
def test_upload_save_action(ui_workspace, kind, content):
    # Simulate uploaded bytes because AppTest does not expose file uploader setters.
    script = f'''from io import BytesIO
from unittest.mock import patch
from src.ui import render
uploaded = BytesIO({content.encode()!r})
uploaded.name = "synthetic.csv"
with patch("streamlit.file_uploader", return_value=uploaded):
    from src.ui import upload
    upload({kind!r})
'''
    app = AppTest.from_string(script).run(timeout=60)
    app.button[0].click().run(timeout=60)
    assert not app.exception and not app.error
    manifest = storage.read_json("uploads", {})
    assert Path(manifest[kind]["path"]).read_bytes() == content.encode()

def test_annotation_editor_save_action(ui_workspace):
    import pandas as pd
    candidate_path = ui_workspace / "train/raw/synthetic_manual.csv"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"phrase":"synthetic SQL", "normalized_phrase":"synthetic sql", "label":"",
                   "source_type":"Philippine job advertisement", "source_id":"SYNTHETIC-MANUAL-1"}]).to_csv(candidate_path,index=False)
    script = '''from unittest.mock import patch
from src.ui import render
def enter_category(frame, **kwargs):
    edited = frame.copy()
    if "Category" in edited.columns and len(edited):
        edited.loc[edited.index[0], "Category"] = "Technical / Digital"
    return edited
with patch("streamlit.data_editor", side_effect=enter_category):
    render("Manual Labeling")
'''
    app = AppTest.from_string(script).run(timeout=60)
    app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    next(button for button in app.button if button.label == "Save annotations").click().run(timeout=60)
    assert not app.exception and not app.error
    assert storage.read_frame("labeled_competencies").phrase.tolist() == ["synthetic SQL"]

def test_team_csv_import_preserves_original_reviewer_and_timestamp(ui_workspace):
    from io import BytesIO
    from unittest.mock import patch
    team_csv = (
        "phrase,normalized_phrase,label,psf_competency,source_type,source_id,reviewer,timestamp\n"
        "synthetic Python,synthetic python,Technical / Digital,,Philippine job advertisement,SYNTHETIC-JOB-1,teammate-7,2026-10-01T09:00:00+08:00\n"
    ).encode("utf-8")
    script = f'''from io import BytesIO
from unittest.mock import patch
from src.ui import render
uploaded = BytesIO({team_csv!r})
uploaded.name = "teammate_labels.csv"
with patch("streamlit.file_uploader", return_value=uploaded):
    render("Manual Labeling")
'''
    app = AppTest.from_string(script).run(timeout=60)
    app.text_input(key="label_reviewer").set_value("coordinator-1").run(timeout=60)
    next(button for button in app.button if button.label == "Import annotations").click().run(timeout=60)
    assert not app.exception and not app.error
    saved = storage.read_frame("labeled_competencies").iloc[0]
    assert saved.reviewer == "teammate-7"
    assert saved.timestamp == "2026-10-01T09:00:00+08:00"

def test_auto_training_runs_only_when_reviewed_dataset_passes_validation(ui_workspace, labeled):
    from unittest.mock import patch
    reviewed = save_annotations(labeled, "Synthetic reviewer")
    valid_script = '''from unittest.mock import patch
from src import storage
from src.ui import _auto_train_after_review
with patch("src.ui.train_and_save_models", return_value=({"rows_used": 20}, None)) as train:
    _auto_train_after_review(storage.read_frame("labeled_competencies"), True)
    assert train.called
'''
    valid_app = AppTest.from_string(valid_script).run(timeout=60)
    assert not valid_app.exception, [e.message for e in valid_app.exception]

    conflicting = reviewed.copy()
    conflicting.loc[0, "label"] = "A contradictory category"
    storage.save_frame("labeled_competencies", conflicting)
    invalid_script = '''from unittest.mock import patch
from src import storage
from src.ui import _auto_train_after_review
with patch("src.ui.train_and_save_models") as train:
    _auto_train_after_review(storage.read_frame("labeled_competencies"), True)
    assert not train.called
'''
    invalid_app = AppTest.from_string(invalid_script).run(timeout=60)
    assert not invalid_app.exception, [e.message for e in invalid_app.exception]
    assert any("waiting for the labeled dataset to pass validation" in warning.value for warning in invalid_app.warning)

def test_pretrained_drafts_stay_blank_until_researcher_explicitly_copies(ui_workspace, taxonomy):
    import pandas as pd
    storage.save_frame("cleaned_psf_aai", taxonomy)
    source = ui_workspace / "train/raw/synthetic_candidates.csv"
    source.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "phrase": "spoken English", "normalized_phrase": "spoken english", "label": "",
        "source_type": "Philippine job advertisement", "source_id": "SYNTHETIC-POSTING-1",
        "original_text": "Synthetic ad: strong spoken English skills required.",
    }]).to_csv(source, index=False)
    script = '''from unittest.mock import patch
from src.pretrained_suggestions import MODEL_ID, MODEL_REVISION, PSF_MODEL_ID, PSF_MODEL_REVISION
from src.ui import render
import streamlit as st
suggestions = [{"label":"Soft / Enabling", "score":0.91, "incomplete_phrase":False,
               "model":MODEL_ID, "revision":MODEL_REVISION,
               "psf_competency":"communication skills", "psf_score":0.84,
               "psf_model":PSF_MODEL_ID, "psf_revision":PSF_MODEL_REVISION}]
def leave_blank(frame, **kwargs):
    if "AI category draft" in frame.columns:
        assert frame.loc[frame.index[0], "Category"] == ""
        assert frame.loc[frame.index[0], "PSF-AAI competency"] == ""
        assert not frame.loc[frame.index[0], "Copy category draft"]
        assert not frame.loc[frame.index[0], "Copy PSF-AAI draft"]
    return frame
with patch("src.pretrained_suggestions.suggest_labels", return_value=suggestions), patch("streamlit.data_editor", side_effect=leave_blank):
    render("Manual Labeling")
'''
    app = AppTest.from_string(script).run(timeout=60)
    app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    suggest_button = next(button for button in app.button if button.label == "Generate AI suggestions for this page")
    suggest_button.click().run(timeout=60)
    assert storage.read_frame("labeled_competencies").empty
    assert (ui_workspace / "data/processed/pretrained_label_suggestions.csv").exists()
    assert next(button for button in app.button if button.label == "Save annotations").disabled
    copy_script = '''from unittest.mock import patch
from src.ui import render
def explicitly_copy(frame, **kwargs):
    copied = frame.copy()
    if "Copy category draft" in copied.columns and len(copied):
        copied.loc[copied.index[0], "Copy category draft"] = True
        copied.loc[copied.index[0], "Copy PSF-AAI draft"] = True
    return copied
with patch("streamlit.data_editor", side_effect=explicitly_copy):
    render("Manual Labeling")
'''
    copied_app = AppTest.from_string(copy_script).run(timeout=60)
    copied_app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    next(button for button in copied_app.button if button.label == "Save annotations").click().run(timeout=60)
    saved = storage.read_frame("labeled_competencies")
    assert saved.label.tolist() == ["Soft / Enabling"]
    assert saved.psf_competency.tolist() == ["communication skills"]
    assert saved.reviewer.tolist() == ["Synthetic reviewer"]

def test_settings_and_usability_save_actions(ui_workspace):
    app = page_app("Settings")
    app.button[0].click().run(timeout=60)
    assert not app.exception and not app.error
    assert storage.read_json("settings")["aligned_threshold"] == .8
    feedback = page_app("Feedback")
    feedback.text_input(key="feedback_reviewer").set_value("Synthetic reviewer")
    feedback.button[0].click().run(timeout=60)
    assert not feedback.exception and not feedback.error
    assert len(storage.read_frame("usability")) == 1

def test_correction_and_report_save_actions(ui_workspace, jobs, taxonomy):
    for kind, frame in (("jobs",jobs),("psf_aai",taxonomy)):
        storage.save_frame("cleaned_"+kind, frame)
    run_extraction()
    feedback = page_app("Feedback")
    feedback.text_input(key="feedback_reviewer").set_value("Synthetic reviewer")
    feedback.button[0].click().run(timeout=60)
    assert not feedback.exception and not feedback.error
    assert (ui_workspace/"data/feedback/corrections.csv").exists()
    reports = page_app("Reports")
    reports.button[0].click().run(timeout=60)
    assert not reports.exception and not reports.error
    assert len(list((ui_workspace/"outputs/reports").glob("*/research_results.xlsx"))) == 1
