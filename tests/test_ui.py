"""SYNTHETIC DATA — NOT RESEARCH DATA; real Streamlit script execution."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from src import storage, ui
from src.labeling import save_annotations
from src.workflow import run_extraction

PAGES = list(ui.PAGES)


def wait_processing(app):
    job = app.session_state["_background_job"]
    assert job.done.wait(45), job.snapshot()
    assert job.snapshot()["status"] == "complete", job.snapshot()

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
    wait_processing(app)
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


def test_overview_reports_actual_counts_and_keeps_all_workflow_actions(ui_workspace, jobs, taxonomy, labeled):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("mapped_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    save_annotations(labeled, "Synthetic reviewer")
    app = page_app("Home")
    assert not app.exception and not app.error
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["Clean job ads"] == f"{len(jobs):,}"
    assert metrics["PSF-AAI competencies"] == f"{len(taxonomy):,}"
    assert metrics["Phrase extraction"] == "Not started"
    assert app.button(key="home_next_step").label == "Open phrase extraction"
    assert all(app.button(key=f"home_workflow_{index:02d}") for index in range(1, 7))


def test_upload_page_can_select_psf_reference(ui_workspace):
    app = page_app("Job Data Upload")
    selector = next(item for item in app.selectbox if item.label == "Dataset to upload")
    assert selector.options == ["Job advertisements (500-study dataset)", "TESDA PSF-AAI reference"]
    selector.set_value("TESDA PSF-AAI reference").run(timeout=60)
    assert app.title[0].value == "Upload PSF-AAI reference"
    assert any(item.label == "Load prepared Range of Application draft" for item in app.button)
    assert not app.exception and not app.error


def test_upload_page_removes_only_misfiled_psf_copy(ui_workspace):
    source = b"competency_name,range_of_application\nSYNTHETIC,Python"
    storage.archive_raw(source, "psf_aai_range_review_draft.csv", "jobs")
    storage.archive_raw(source, "psf_aai_range_review_draft.csv", "psf_aai")
    jobs_path = storage.raw_upload_path(storage.read_json("uploads")["jobs"], "jobs")
    psf_path = storage.raw_upload_path(storage.read_json("uploads")["psf_aai"], "psf_aai")

    app = page_app("Job Data Upload")
    next(item for item in app.button if item.label == "Remove mistaken PSF draft from job uploads").click().run(timeout=60)

    assert not app.exception and not app.error
    assert not jobs_path.exists()
    assert psf_path.read_bytes() == source
    assert "jobs" not in storage.read_json("uploads")


def test_psf_activation_syncs_verified_reference_and_clears_pending_upload(ui_workspace, taxonomy):
    from src.ui import activate_psf_reference
    from src.utils import frame_hash
    taxonomy = taxonomy.copy()
    taxonomy["source_page"] = "12"
    taxonomy["source_url"] = "https://example.test/synthetic-framework.pdf"
    taxonomy["source_hash"] = "SYNTHETIC-HASH"
    storage.save_json("uploads", {"psf_aai": {"hash": "stale-upload-hash", "filename": "draft.csv"}})

    activate_psf_reference(taxonomy, "Synthetic reviewer")

    assert storage.read_frame("verified_psf_aai").reviewer.tolist() == ["Synthetic reviewer"] * len(taxonomy)
    assert len(storage.read_frame("cleaned_psf_aai")) == len(taxonomy)
    assert storage.read_json("cleaning_psf_aai")["source_hash"] == frame_hash(storage.read_frame("mapped_psf_aai"))
    assert "psf_aai" not in storage.read_json("uploads")


def test_review_no_search_results_keeps_filters_and_disables_saves(ui_workspace, jobs, taxonomy):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    app = page_app("Manual Labeling")
    next(item for item in app.text_input if item.label == "Find candidate phrase").set_value("NO-SUCH-SYNTHETIC-PHRASE").run(timeout=60)
    assert not app.exception and not app.error
    assert any("No phrases match these filters" in item.value for item in app.info)
    assert next(item for item in app.button if item.label == "Save annotations").disabled
    assert next(item for item in app.button if item.label == "Generate missing AI drafts").disabled


def test_mapping_review_saves_multiple_links_and_no_match(ui_workspace, jobs, taxonomy):
    from src.psf_reviews import REVIEW_TABLE
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    app = page_app("PSF Mapping")
    choice = next(item for item in app.multiselect if item.label == "PSF-AAI competencies")
    choice.set_value(["TEST-1", "TEST-2"]).run(timeout=60)
    next(item for item in app.text_input if item.label == "Reviewer ID").set_value("Synthetic reviewer")
    reasons = [item for item in app.text_area if item.label == "Source evidence and rationale"]
    assert len(reasons) == 2
    reasons[0].set_value("Synthetic Python evidence")
    reasons[1].set_value("Synthetic SQL evidence")
    next(item for item in app.checkbox if item.label.startswith("I checked the source context")).check()
    next(item for item in app.button if item.label == "Save competency links").click().run(timeout=60)
    assert not app.exception and not app.error
    saved = storage.read_frame(REVIEW_TABLE)
    assert set(saved.competency_id) == {"TEST-1", "TEST-2"}
    assert saved.extraction_id.nunique() == 1
    next(item for item in app.multiselect if item.label == "PSF-AAI competencies").set_value([]).run(timeout=60)
    next(item for item in app.text_input if item.label == "Reviewer ID").set_value("Synthetic reviewer")
    next(item for item in app.text_area if item.label == "Reason for no mapping").set_value("Synthetic rejection after review")
    next(item for item in app.checkbox if item.label.startswith("I checked the source context")).check()
    next(item for item in app.button if item.label == "Save competency links").click().run(timeout=60)
    assert not app.exception and not app.error
    assert storage.read_frame(REVIEW_TABLE).competency_id.tolist() == [""]

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
    wait_processing(app)
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

def test_manual_review_keeps_source_specific_rows_with_ad_count(ui_workspace):
    import pandas as pd
    storage.save_frame("team_training_candidates", pd.DataFrame([
        {"phrase":"Python", "normalized_phrase":"python", "source_type":"jobs", "source_id":"SYNTH-1", "original_text":"Python used for reporting."},
        {"phrase":"python", "normalized_phrase":"python", "source_type":"jobs", "source_id":"SYNTH-2", "original_text":"Build Python data tools."},
    ]))
    app = page_app("Manual Labeling")
    assert not app.exception and not app.error
    table = next(editor.value for editor in app.dataframe if "Source ads" in editor.value.columns)
    assert len(table) == 2
    assert set(table["Source advertisement"]) == {"SYNTH-1", "SYNTH-2"}
    assert "Category" in table and "PSF-AAI competencies" in table
    assert table.iloc[0]["Phrase"].casefold() == "python"
    assert int(table.iloc[0]["Source ads"]) == 2

def test_extraction_exposes_reused_researcher_approved_labels(ui_workspace, jobs, taxonomy, labeled):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    save_annotations(labeled, "Synthetic reviewer")
    run_extraction()
    app = page_app("Competency Extraction")
    next(button for button in app.button if button.label == "Load saved results").click().run()
    wait_processing(app)
    app.run()
    assert not app.exception and not app.error
    assert any(metric.label == "Researcher-approved labels" and int(metric.value.replace(",", "")) > 0
               for metric in app.metric)
    view = next(item for item in app.selectbox if item.label == "View")
    assert "Researcher-approved labels" in view.options
    assert "Unreviewed candidates" in view.options

def test_manual_retraining_is_opt_in_by_default(ui_workspace):
    app = page_app("Manual Labeling")
    retrain = next(box for box in app.checkbox if box.label == "Automatically retrain after I save reviewed labels")
    assert retrain.value is False

def test_shared_admin_can_enable_automatic_retraining(monkeypatch):
    monkeypatch.setattr(ui.supabase_store, "configured", lambda: True)
    monkeypatch.setattr(ui.supabase_store, "is_admin", lambda: True)
    app = AppTest.from_string(
        "from src.ui import _auto_retraining_control\n_auto_retraining_control()"
    ).run()
    assert not app.exception
    assert not app.checkbox[0].disabled
    assert app.checkbox[0].value is False

def test_shared_reviewer_gets_reason_auto_retraining_is_unavailable(monkeypatch):
    monkeypatch.setattr(ui.supabase_store, "configured", lambda: True)
    monkeypatch.setattr(ui.supabase_store, "is_admin", lambda: False)
    app = AppTest.from_string(
        "from src.ui import _auto_retraining_control\n_auto_retraining_control()"
    ).run()
    assert not app.exception
    assert app.checkbox[0].disabled
    assert any("Only the project administrator" in item.value for item in app.caption)

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
    wait_processing(extraction)
    assert not extraction.error and not extraction.exception
    assert not storage.read_frame("extractions_original").empty

def test_main_app_launch(ui_workspace):
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py")).run(timeout=60)
    assert not app.exception and not app.error


def test_extraction_results_are_paginated(ui_workspace):
    import pandas as pd
    frame = pd.DataFrame({"row": range(250)})
    page, number, pages = ui._paginate_frame(frame, 3, 100)
    assert number == 3 and pages == 3
    assert page.row.tolist() == list(range(200, 250))
    page, number, _ = ui._paginate_frame(frame, 99, 100)
    assert number == 3 and page.row.tolist() == list(range(200, 250))


def test_extraction_page_sends_only_100_rows_to_browser(ui_workspace):
    script = '''
import pandas as pd
import streamlit as st
from unittest.mock import patch
from src.ui import render
frame = pd.DataFrame({
    "extraction_id": [str(i) for i in range(250)],
    "original_phrase": [f"SYNTHETIC phrase {i}" for i in range(250)],
    "human_label": [""] * 250,
    "model_prediction": [""] * 250,
    "accepted": ["True"] * 250,
})
st.session_state["_extraction_results_frame"] = frame
def read_frame(name, **kwargs):
    return frame if name == "extractions_original" else pd.DataFrame()
with patch("src.ui.storage.read_frame", side_effect=read_frame):
    render("Competency Extraction")
'''
    app = AppTest.from_string(script).run(timeout=60)
    assert not app.exception and not app.error
    assert len(app.dataframe[0].value) == 100
    assert any("Showing 1–100 of 250 rows" in item.value for item in app.caption)


def test_extraction_opens_without_downloading_results(ui_workspace, monkeypatch):
    read_frame = storage.read_frame
    def guarded(name, **kwargs):
        assert name not in {"extractions_original", "nlp_processed"}, "Page entry downloaded bulk results"
        return read_frame(name, **kwargs)
    monkeypatch.setattr(storage, "read_frame", guarded)
    app = page_app("Competency Extraction")
    assert not app.exception and not app.error
    assert any(button.label == "Load saved results" for button in app.button)


def test_saved_results_load_does_not_block_page_and_reports_failure(ui_workspace, monkeypatch):
    from threading import Event
    from src import background_tasks
    entered, release = Event(), Event()
    def slow_read(*, progress):
        entered.set()
        assert release.wait(15)
        raise ValueError("Synthetic shared connection timeout")
    monkeypatch.setattr(background_tasks, "extraction_preview", slow_read)
    app = page_app("Competency Extraction")
    try:
        next(button for button in app.button if button.label == "Load saved results").click().run(timeout=10)
        assert entered.wait(2)
        assert not app.session_state["_background_job"].done.is_set()
        assert any(button.label == "Stop processing" for button in app.button)
        assert not app.exception
    finally:
        release.set()
    assert app.session_state["_background_job"].done.wait(10)
    app.run()
    assert any("Synthetic shared connection timeout" in item.value for item in app.error)
    assert "_extraction_results_frame" not in app.session_state

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
    save_button = next(button for button in app.button if button.label == "Save raw upload")
    save_button.click().run(timeout=60)
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
with patch("src.ui._start_processing") as train:
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
with patch("src.ui._start_processing") as train:
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
               "psf_candidates":[{"competency_id":"TEST-4", "competency_name":"communication skills", "score":0.84}, {"competency_id":"TEST-5", "competency_name":"data analysis", "score":0.72}],
               "psf_model":PSF_MODEL_ID, "psf_revision":PSF_MODEL_REVISION}]
def leave_blank(frame, **kwargs):
    if "AI category draft" in frame.columns:
        assert frame.loc[frame.index[0], "Category"] == ""
        assert frame.iloc[0]["PSF-AAI competencies"] == []
        assert "Draft status" not in frame.columns
        if frame.iloc[0]["AI category draft"]:
            assert frame.iloc[0]["AI PSF-AAI drafts"] == ["communication skills", "data analysis"]
        else:
            assert frame.iloc[0]["AI category draft"] == ""
            assert frame.iloc[0]["AI PSF-AAI drafts"] == []
        assert "Context check" not in frame.columns and "Context note" not in frame.columns
        assert "Context check" not in kwargs["disabled"] and "Context note" not in kwargs["disabled"]
        assert "Copy category draft" not in frame.columns
        assert "Copy PSF-AAI draft" not in frame.columns
    return frame
with patch("src.pretrained_suggestions.suggest_labels", return_value=suggestions), patch("streamlit.data_editor", side_effect=leave_blank):
    render("Manual Labeling")
'''
    app = AppTest.from_string(script).run(timeout=60)
    app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    app.toggle(key="manual_review_fullscreen").set_value(True).run(timeout=60)
    suggest_button = next(button for button in app.button if button.label == "Generate missing AI drafts")
    suggest_button.click().run(timeout=60)
    wait_processing(app)
    app.run(timeout=60)
    assert not app.exception
    assert app.toggle(key="manual_review_fullscreen").value
    assert not any(item.label == "AI context notes and competency drafts" for item in app.expander)
    assert storage.read_frame("labeled_competencies").empty
    assert (ui_workspace / "data/processed/pretrained_label_suggestions.csv").exists()
    assert next(button for button in app.button if button.label == "Save annotations").disabled
    copy_script = '''from unittest.mock import patch
from src.ui import render
def explicitly_copy(frame, **kwargs):
    copied = frame.copy()
    if "AI category draft" in copied.columns and len(copied):
        assert "Copy category draft" not in copied.columns
        copied.loc[copied.index[0], "Category"] = copied.iloc[0]["AI category draft"]
        assert "Copy PSF-AAI draft" not in copied.columns
    return copied
with patch("streamlit.data_editor", side_effect=explicitly_copy):
    render("Manual Labeling")
'''
    copied_app = AppTest.from_string(copy_script).run(timeout=60)
    copied_app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    next(button for button in copied_app.button if button.label == "Save annotations").click().run(timeout=60)
    saved = storage.read_frame("labeled_competencies")
    assert saved.label.tolist() == ["Soft / Enabling"]
    assert saved.psf_competency.tolist() == [""]
    assert storage.read_frame("psf_mapping_reviews").empty
    assert saved.reviewer.tolist() == ["Synthetic reviewer"]


@pytest.mark.parametrize("page", [3, 4])
def test_later_review_pages_generate_only_missing_drafts(ui_workspace, taxonomy, monkeypatch, page):
    import pandas as pd
    from src import pretrained_suggestions as suggestions, ollama_review
    rows = [{"phrase": f"Synthetic competency {i}", "normalized_phrase": f"synthetic competency {i}",
             "source_type": "jobs", "source_id": f"TEST-{i}", "original_text": f"Synthetic competency {i} required."}
            for i in range(40)]
    storage.save_frame("team_training_candidates", pd.DataFrame(rows))
    storage.save_frame("cleaned_psf_aai", taxonomy)
    start = (page - 1) * 10
    ready = {"label": "Data / Analytics", "psf_competency": "SQL"}
    suggestions.save_ai_suggestions(ui_workspace, rows[start:start + 3],
                                    [ready, {"label": "IRRELEVANT"}, {"label": "Data / Analytics"}])
    predicted_rows = []
    def predict(batch, taxonomy, **kwargs):
        predicted_rows.extend(batch)
        return [dict(ready) for row in batch]
    monkeypatch.setattr(suggestions, "suggest_labels", predict)
    monkeypatch.setattr(ollama_review, "configured_model", lambda: "")
    app = page_app("Manual Labeling")
    next(item for item in app.number_input if item.label.startswith("Review page")).set_value(page).run(timeout=60)
    assert not app.exception and not app.error
    table = next(item.value for item in app.dataframe if "AI category draft" in item.value)
    assert "Draft status" not in table
    assert table["AI category draft"].tolist() == ["Data / Analytics", "IRRELEVANT", "Data / Analytics"] + [""] * 7
    assert table["Category"].eq("").all()
    next(item for item in app.button if item.label == "Generate missing AI drafts").click().run(timeout=60)
    wait_processing(app)
    app.run(timeout=60)
    assert not app.exception and not app.error
    assert [row["source_id"] for row in predicted_rows] == [row["source_id"] for row in rows[start + 2:start + 10]]
    table = next(item.value for item in app.dataframe if "AI category draft" in item.value)
    assert "Draft status" not in table
    assert table["AI category draft"].tolist() == ["Data / Analytics", "IRRELEVANT"] + ["Data / Analytics"] * 8
    assert table["Category"].eq("").all()
    assert all(len(value) == 0 for value in table["PSF-AAI competencies"])
    assert storage.read_frame("labeled_competencies").empty


def test_new_drafts_preserve_pending_browser_edits(ui_workspace, taxonomy):
    import pandas as pd
    from src.pretrained_suggestions import save_ai_suggestions
    row = {"phrase": "Synthetic skill", "normalized_phrase": "synthetic skill",
           "source_type": "jobs", "source_id": "TEST-A", "original_text": "Synthetic skill required."}
    storage.save_frame("team_training_candidates", pd.DataFrame([row]))
    storage.save_frame("cleaned_psf_aai", taxonomy)
    app = page_app("Manual Labeling")
    # Simulate edits arriving with a fragment poll before the editor is rendered.
    editor_key = next(key for key in app.session_state if key.startswith("manual_labels_"))
    app.session_state[editor_key] = {"edited_rows": {0: {"Category": "Business / Domain", "PSF-AAI competencies": ["TEST-1"]}},
                                   "added_rows": [], "deleted_rows": []}
    save_ai_suggestions(ui_workspace, [row], [{"label": "Data / Analytics", "psf_competency": "SQL"}])
    app.run(timeout=60)
    assert not app.exception and not app.error
    table = next(item.value for item in app.dataframe if "AI category draft" in item.value)
    assert table.iloc[0]["Category"] == "Business / Domain"
    assert list(table.iloc[0]["PSF-AAI competencies"]) == ["TEST-1"]
    assert table.iloc[0]["AI category draft"] == "Data / Analytics"
    assert storage.read_frame("labeled_competencies").empty

def test_settings_and_usability_save_actions(ui_workspace):
    app = page_app("Settings")
    next(button for button in app.button if button.label == "Save settings").click().run(timeout=60)
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


def test_individual_csv_exports_are_deferred_until_download(ui_workspace, jobs, taxonomy, monkeypatch):
    from unittest.mock import Mock
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    exporter = Mock(wraps=ui.export_csv)
    monkeypatch.setattr(ui, "export_csv", exporter)
    app = page_app("Reports")
    assert not app.exception and not app.error
    exporter.assert_not_called()
    app.session_state["individual_exports"] = True
    app.run(timeout=60)
    assert not app.exception and not app.error
    exporter.assert_not_called()
    assert len(app.get("download_button")) > 4


def test_training_reuses_file_inventory(ui_workspace, labeled, monkeypatch):
    from unittest.mock import Mock
    save_annotations(labeled, "Synthetic reviewer")
    inventory = Mock(wraps=ui.inspect_training_folder)
    monkeypatch.setattr(ui, "inspect_training_folder", inventory)
    app = page_app("ML Training")
    assert not app.exception and not app.error
    inventory.assert_called_once()


def table_mapping_app():
    return AppTest.from_string('''from unittest.mock import patch
import streamlit as st
from src.ui import render
original_editor = st.data_editor
def edit(frame, **kwargs):
    result = original_editor(frame, **kwargs)
    if "PSF-AAI competencies" in result and not result.empty:
        indices = result.index[result.Phrase.str.casefold().eq("python")]
        if len(indices):
            result.at[indices[0], "PSF-AAI competencies"] = ["TEST-1", "TEST-2"]
            result.at[indices[0], "Category"] = "Technical / Digital"
    return result
with patch("streamlit.data_editor", side_effect=edit):
    render("Manual Labeling")
''').run(timeout=60)


def test_manual_review_multiple_links_roundtrip_and_source_isolation(ui_workspace, jobs, taxonomy):
    from src.psf_reviews import REVIEW_TABLE
    from src.workflow import analysis_bundle
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    app = table_mapping_app()
    assert not app.exception and not app.tabs
    app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    reasons = [item for item in app.text_area if item.label == "Source evidence and rationale"]
    assert len(reasons) == 2
    reasons[0].set_value("Synthetic evidence: Python scripting requirement.")
    reasons[1].set_value("Synthetic evidence: SQL querying requirement.")
    next(item for item in app.checkbox if item.label.startswith("I checked the source context")).check()
    app.toggle(key="manual_review_fullscreen").set_value(True).run(timeout=60)
    app.toggle(key="manual_review_fullscreen").set_value(False).run(timeout=60)
    reasons = [item for item in app.text_area if item.label == "Source evidence and rationale"]
    assert reasons[0].value == "Synthetic evidence: Python scripting requirement."
    assert reasons[1].value == "Synthetic evidence: SQL querying requirement."
    app.toggle(key="manual_review_fullscreen").set_value(True).run(timeout=60)
    next(item for item in app.button if item.label == "Save annotations").click().run(timeout=60)
    assert not app.exception and not app.error
    assert app.toggle(key="manual_review_fullscreen").value
    saved = storage.read_frame(REVIEW_TABLE)
    assert set(saved.competency_id) == {"TEST-1", "TEST-2"}
    assert saved.source_id.nunique() == 1
    occurrence_id = saved.extraction_id.iloc[0]
    labels = storage.read_frame("labeled_competencies")
    assert labels.source_id.nunique() == 2
    assert labels.label.eq("Technical / Digital").all()
    assert labels.psf_competency.eq("").all()
    app = page_app("Manual Labeling")
    next(item for item in app.checkbox if item.label == "Only show phrases awaiting category review").uncheck()
    next(item for item in app.text_input if item.label == "Find candidate phrase").set_value("python").run(timeout=60)
    table = next(editor.value for editor in app.dataframe if "PSF-AAI competencies" in editor.value)
    reviewed = table[table["Source advertisement"].eq(saved.source_id.iloc[0])]
    assert set(reviewed.iloc[0]["PSF-AAI competencies"]) == {"TEST-1", "TEST-2"}
    others = table[~table["Source advertisement"].eq(saved.source_id.iloc[0])]
    assert all(len(value) == 0 for value in others["PSF-AAI competencies"])
    tables, _ = analysis_bundle()
    mapping = tables["psf_mapping"]
    assert set(mapping.loc[mapping.extraction_id.eq(occurrence_id), "competency_id"]) == {"TEST-1", "TEST-2"}
    assert mapping.loc[mapping.extraction_id.eq(occurrence_id), "mapping_review_status"].eq("REVIEWED").all()
    assert not mapping.loc[~mapping.extraction_id.eq(occurrence_id), "mapping_review_status"].eq("REVIEWED").any()


def test_manual_review_requires_each_rationale_before_saving_categories(ui_workspace, jobs, taxonomy):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    app = table_mapping_app()
    app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    next(item for item in app.checkbox if item.label.startswith("I checked the source context")).check()
    next(item for item in app.button if item.label == "Save annotations").click().run(timeout=60)
    assert not app.exception
    assert any("every selected competency" in error.value for error in app.error)
    assert storage.read_frame("psf_mapping_reviews").empty
    assert storage.read_frame("labeled_competencies").empty


@pytest.mark.parametrize("page", ["Manual Labeling", "PSF Mapping"])
def test_account_identity_replaces_manual_reviewer_prompt(ui_workspace, jobs, taxonomy, page):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    app = table_mapping_app() if page == "Manual Labeling" else page_app(page)
    app.session_state["supabase_user_email"] = "synthetic-reviewer@example.test"
    app.run(timeout=60)
    if page == "PSF Mapping":
        next(item for item in app.multiselect if item.label == "PSF-AAI competencies").set_value(["TEST-1", "TEST-2"]).run(timeout=60)
    assert not any(item.label == "Reviewer ID" for item in app.text_input)
    assert not any("Enter your Reviewer ID" in item.value for item in app.caption)
    reasons = [item for item in app.text_area if item.label == "Source evidence and rationale"]
    reasons[0].set_value("Synthetic Python scripting evidence.")
    reasons[1].set_value("Synthetic SQL querying evidence.")
    next(item for item in app.checkbox if item.label.startswith("I checked the source context")).check()
    label = "Save annotations" if page == "Manual Labeling" else "Save competency links"
    next(item for item in app.button if item.label == label).click().run(timeout=60)
    assert not app.exception and not app.error
    saved = storage.read_frame("psf_mapping_reviews")
    assert len(saved) == 2
    assert saved.reviewer.eq("synthetic-reviewer@example.test").all()
    if page == "Manual Labeling":
        assert storage.read_frame("labeled_competencies").reviewer.eq("synthetic-reviewer@example.test").all()


def test_combined_review_reports_partial_storage_failure(ui_workspace, jobs, taxonomy, monkeypatch):
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    app = table_mapping_app()
    app.text_input(key="label_reviewer").set_value("Synthetic reviewer").run(timeout=60)
    reasons = [item for item in app.text_area if item.label == "Source evidence and rationale"]
    reasons[0].set_value("Synthetic Python evidence")
    reasons[1].set_value("Synthetic SQL evidence")
    next(item for item in app.checkbox if item.label.startswith("I checked the source context")).check()
    def fail_mapping(*args, **kwargs):
        raise ui.supabase_store.SupabaseError("Synthetic storage failure")
    monkeypatch.setattr(ui, "save_mapping_review", fail_mapping)
    next(item for item in app.button if item.label == "Save annotations").click().run(timeout=60)
    assert not app.exception
    assert any("Partial save: category annotations were saved; 0" in warning.value for warning in app.warning)
    assert not storage.read_frame("labeled_competencies").empty
    assert storage.read_frame("psf_mapping_reviews").empty
