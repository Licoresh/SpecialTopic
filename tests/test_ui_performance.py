"""Session-local performance cache tests; synthetic values only."""
from streamlit.testing.v1 import AppTest
from unittest.mock import Mock
import pandas as pd
import pytest
from src import storage, supabase_store as backend


@pytest.fixture
def loading_phases(monkeypatch):
    from contextlib import contextmanager
    import streamlit as st
    from src import ui
    active, events = set(), []

    @contextmanager
    def region(key, kind, **kwargs):
        active.add(key)
        events.append(("pending", key))
        def content():
            active.discard(key)
            events.append(("render", key))
            return st.container(key=f"synthetic_{key}_body")
        try:
            yield content
        finally:
            active.discard(key)

    def read(key, name, value):
        assert key in active, f"{name} ran after {key} was replaced"
        events.append(("read", name))
        return value

    monkeypatch.setattr(ui, "loading_content", region)
    return read, events


def test_upload_preview_and_archive_receive_original_bytes(workspace, monkeypatch, loading_phases):
    from types import SimpleNamespace
    from src import ui
    read, events = loading_phases
    payload = b"job_title,job_description\nSynthetic analyst,Use SQL for synthetic reporting.\n"
    uploaded = SimpleNamespace(name="synthetic-upload.csv", getvalue=lambda: payload)
    monkeypatch.setattr(ui.st, "file_uploader", lambda *a, **k: uploaded)
    def parse(data, filename, sheet, encoding):
        assert data is payload
        assert filename == uploaded.name
        return read("upload_preview", "preview", pd.DataFrame({"job_title": ["Synthetic analyst"]}))
    monkeypatch.setattr(ui, "cached_load", parse)
    monkeypatch.setattr(ui, "column_mapping", lambda *args: None)
    archived = Mock()
    monkeypatch.setattr(storage, "archive_raw", archived)
    app = AppTest.from_string("from src.ui import upload\nupload('jobs')").run(timeout=30)
    assert not app.exception and not app.error
    next(button for button in app.button if button.label == "Save raw upload").click().run(timeout=30)
    assert not app.exception and not app.error
    archived.assert_called_once_with(payload, uploaded.name, "jobs")
    assert events.index(("read", "preview")) < events.index(("render", "upload_preview"))


def test_evaluation_checks_snapshot_and_eligibility_before_showing_scores(workspace, monkeypatch, loading_phases):
    from src import ui
    read, events = loading_phases
    name = "Logistic Regression"
    metadata = {"model_name": name, "accuracy": .5, "macro_f1": .4, "weighted_f1": .45,
                "number_of_classes": 2, "selection_basis": ui.SELECTION_BASIS,
                "split": {"strategy": "source-disjoint", "test_source_ids": ["SYNTHETIC-C", "SYNTHETIC-D"]},
                "cross_validation_results": {name: {"synthetic": True}}}
    frames = {
        "model_metrics": pd.DataFrame({"model": [name], "accuracy": [.5], "macro_f1": [.4], "weighted_f1": [.45]}),
        "training_snapshot": pd.DataFrame({"source_id": ["SYNTHETIC-A", "SYNTHETIC-C"]}),
        "evaluation_lr_confusion": pd.DataFrame({"actual": ["A", "B"], "A": [1, 0], "B": [0, 1]}),
        "evaluation_lr_per_class": pd.DataFrame({"label": ["A"], "f1": [.4]}),
        "evaluation_lr_predictions": pd.DataFrame({"actual": ["A"], "predicted": ["A"]}),
    }
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(ui, "read_model_metadata", lambda: read("evaluation_eligibility", "metadata", metadata))
    def frame(key, *a, **k):
        region = "evaluation_details" if key.startswith("evaluation_") else "evaluation_eligibility"
        return read(region, key, frames[key])
    monkeypatch.setattr(storage, "read_frame", frame)
    monkeypatch.setattr(ui, "source_overlap", lambda *a: read("evaluation_eligibility", "overlap", set()))
    monkeypatch.setattr(ui, "training_data_changed", lambda: read("evaluation_eligibility", "changed", False))
    app = AppTest.from_string("from src.ui import evaluation\nevaluation()").run(timeout=30)
    assert not app.exception and not app.error
    replacement = events.index(("render", "evaluation_eligibility"))
    assert all(events.index(("read", key)) < replacement for key in ("training_snapshot", "overlap", "changed"))
    assert {item.label: item.value for item in app.metric}["Selected holdout Macro F1"] == "0.400"
    content = " ".join(item.proto.body for item in app.get("html"))
    assert "ranges from 0.400 to 0.400" in content
    frames["model_metrics"].loc[0, "macro_f1"] = .7
    metadata["macro_f1"] = .7
    app.run(timeout=30)
    assert not app.exception and not app.error
    content = " ".join(item.proto.body for item in app.get("html"))
    assert "ranges from 0.700 to 0.700" in content
    assert "ranges from 0.400 to 0.400" not in content


def test_training_saved_metrics_load_before_their_result_slot(workspace, monkeypatch, loading_phases):
    from src import ui
    read, events = loading_phases
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "is_admin", lambda: False)
    labels = pd.DataFrame(columns=["phrase", "label"])
    report = {"total_rows": 0, "rows_used": 0, "number_of_classes": 0,
              "warnings": [], "errors": ["Synthetic empty labels; do not train."]}
    def frame(key, *a, **k):
        if key == "labeled_competencies":
            return read("training_validation", key, labels)
        assert key == "model_metrics"
        return read("training_saved_model", key, pd.DataFrame({"model": ["Synthetic saved model"], "accuracy": [.5]}))
    monkeypatch.setattr(storage, "read_frame", frame)
    monkeypatch.setattr(ui, "cached_label_validation", lambda *a, **k: (labels, report))
    monkeypatch.setattr(ui, "training_data_changed", lambda: False)
    monkeypatch.setattr(ui, "read_model_metadata", lambda: read("training_saved_model", "saved_metadata", {"model_name": "Synthetic saved model"}))
    app = AppTest.from_string("from src.ui import training\ntraining()").run(timeout=30)
    assert not app.exception and not app.error
    assert events.index(("read", "model_metrics")) < events.index(("render", "training_saved_model"))
    assert next(button for button in app.button if button.label == "Train / Retrain Models").disabled


def test_quality_metadata_and_cleaning_load_inside_their_result_regions(workspace, jobs, monkeypatch, loading_phases):
    from src import ui
    read, events = loading_phases
    storage.save_frame("mapped_jobs", jobs)
    original_frame, original_json, original_clean = storage.read_frame, storage.read_json, ui.cached_clean
    def frame(key, *a, **k):
        value = original_frame(key, *a, **k)
        return read("quality_source_jobs", key, value) if key == "mapped_jobs" else value
    def state(key, *a, **k):
        value = original_json(key, *a, **k)
        return read("quality_source_jobs", key, value) if key == "cleaning_jobs" else value
    monkeypatch.setattr(storage, "read_frame", frame)
    monkeypatch.setattr(storage, "read_json", state)
    monkeypatch.setattr(ui, "cached_clean", lambda *a, **k: read("quality_preview_jobs", "clean", original_clean(*a, **k)))
    app = AppTest.from_string("from src.ui import quality\nquality()").run(timeout=30)
    assert not app.exception and not app.error
    assert events.index(("read", "cleaning_jobs")) < events.index(("render", "quality_source_jobs"))
    assert events.index(("read", "clean")) < events.index(("render", "quality_preview_jobs"))


@pytest.mark.parametrize("page", ["feedback", "settings_page"])
def test_feedback_tables_and_settings_load_inside_their_result_regions(workspace, monkeypatch, loading_phases, page):
    from src import ui
    from src.config import DEFAULTS
    read, events = loading_phases
    monkeypatch.setattr(ui, "current_analysis", lambda: read("feedback_records", "freshness", False))
    monkeypatch.setattr(ui, "corrections", lambda: read("feedback_correction_history", "corrections", pd.DataFrame()))
    settings_region = "feedback_usability_form" if page == "feedback" else "settings_form_content"
    monkeypatch.setattr(storage, "settings", lambda: read(settings_region, "settings", dict(DEFAULTS)))
    def frame(key, *a, **k):
        regions = {"usability": "feedback_usability_results", "cleaned_stakeholder": "feedback_stakeholders"}
        return read(regions[key], key, pd.DataFrame())
    monkeypatch.setattr(storage, "read_frame", frame)
    app = AppTest.from_string(f"from src.ui import {page}\n{page}()").run(timeout=30)
    assert not app.exception and not app.error
    assert events.index(("read", "settings")) < events.index(("render", settings_region))
    if page == "feedback":
        assert {("read", "corrections"), ("read", "usability"), ("read", "cleaned_stakeholder")}.issubset(events)


def test_session_cache_reuses_derived_values_without_leaking_mutations():
    app = AppTest.from_string(
        """
import streamlit as st
from src.ui import _session_cached_value
st.session_state.setdefault('synthetic_loads', 0)
def loader():
    st.session_state.synthetic_loads += 1
    return {'rows': []}
value = _session_cached_value('synthetic_cache', 'same-inputs', loader)
value['rows'].append('per-render mutation')
st.session_state.synthetic_rows = len(value['rows'])
"""
    ).run()
    assert not app.exception
    assert app.session_state["synthetic_loads"] == 1
    app.run()
    assert not app.exception
    assert app.session_state["synthetic_loads"] == 1
    assert app.session_state["synthetic_rows"] == 1


def test_visible_page_rerun_does_not_create_another_loading_region(workspace, monkeypatch):
    from src import loading_ui
    wireframe = Mock(wraps=loading_ui._wireframe)
    monkeypatch.setattr(loading_ui, "_wireframe", wireframe)
    app = AppTest.from_string("from src.ui import render\nrender('Home')").run(timeout=30)
    assert not app.exception
    first_calls = list(wireframe.call_args_list)
    assert [call.args[0] for call in first_calls] == ["overview", "notice"]
    assert app.session_state["_fow_loading_ready"]["overview_summary_content"]
    before = [(item.label, item.value) for item in app.metric]
    app.run(timeout=30)
    assert not app.exception
    assert wireframe.call_args_list == first_calls
    assert [(item.label, item.value) for item in app.metric] == before


def test_reports_preload_tables_and_reload_only_changed_revisions(workspace, monkeypatch):
    from contextlib import contextmanager
    import streamlit as st
    from src import ui
    from test_result_views import result_tables
    tables = result_tables()
    phase = {"loading": False}
    reads = []

    @contextmanager
    def region(key, kind, **kwargs):
        assert key == "research_results_content" and kind == "reports"
        phase["loading"] = True
        def content():
            phase["loading"] = False
            return st.container()
        try:
            yield content
        finally:
            phase["loading"] = False

    def loaded(name, value):
        assert phase["loading"], name
        reads.append(name)
        return value

    monkeypatch.setattr(ui, "loading_content", region)
    monkeypatch.setattr(ui, "current_analysis", lambda: loaded("freshness", True))
    monkeypatch.setattr(ui, "filtered_bundle", lambda: loaded("bundle", (tables, {})))
    monkeypatch.setattr(ui, "job_profile_tables", Mock(side_effect=AssertionError("Bundle already has job profiles")))
    monkeypatch.setattr(ui, "corrections", lambda: loaded("corrections", pd.DataFrame()))
    revisions = dict.fromkeys(ui.REPORT_AUXILIARY_TABLES, 1)
    monkeypatch.setattr(storage, "frame_revisions", lambda names: revisions.copy())
    monkeypatch.setattr(storage, "read_frame", lambda name: loaded(name, pd.DataFrame()))
    def render_cards(tables, meta):
        assert not phase["loading"]
        assert set(ui.REPORT_AUXILIARY_TABLES).issubset(tables)
    monkeypatch.setattr(ui, "report_deliverables", render_cards)
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('Reports')").run(timeout=30)
    assert not app.exception and not app.error
    assert reads == ["freshness", "bundle", "corrections", *ui.REPORT_AUXILIARY_TABLES]
    reads.clear()
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert reads == ["freshness", "bundle", "corrections"]
    reads.clear()
    revisions["usability"] += 1
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert reads == ["freshness", "bundle", "corrections", "usability"]


def test_missing_results_remain_unmaterialized_until_successful_retry(workspace, monkeypatch):
    from src import ui, loading_ui
    from test_result_views import result_tables
    available = {"value": False}
    wireframe = Mock(wraps=loading_ui._wireframe)
    monkeypatch.setattr(loading_ui, "_wireframe", wireframe)
    monkeypatch.setattr(ui, "current_analysis", lambda: available["value"])
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (result_tables(), {}))
    monkeypatch.setattr(ui, "job_profile_tables", lambda jobs: {})
    monkeypatch.setattr(ui, "corrections", lambda: pd.DataFrame())
    monkeypatch.setattr(storage, "read_frame", lambda name: pd.DataFrame())
    monkeypatch.setattr(ui, "report_deliverables", lambda *args, **kwargs: None)
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('Reports')").run(timeout=30)
    assert not app.exception
    assert not app.session_state["_fow_loading_ready"]
    available["value"] = True
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state["_fow_loading_ready"]["research_results_content"]
    assert wireframe.call_count == 2
    app.run(timeout=30)
    assert wireframe.call_count == 2


def test_review_source_and_mapping_reads_stay_inside_their_pending_content(workspace, jobs, taxonomy, monkeypatch):
    from contextlib import contextmanager
    import streamlit as st
    from src import ui
    from src.workflow import run_extraction
    storage.save_frame("cleaned_jobs", jobs)
    storage.save_frame("cleaned_psf_aai", taxonomy)
    run_extraction()
    active, checked = set(), []

    @contextmanager
    def region(key, kind, **kwargs):
        active.add(key)
        def content():
            active.discard(key)
            return st.container()
        try:
            yield content
        finally:
            active.discard(key)

    read_frame, contexts, extractions = storage.read_frame, ui._review_contexts, ui.current_extractions
    def read(name, *args, **kwargs):
        if name in {"labeled_competencies", "cleaned_psf_aai", "psf_mapping_reviews"}:
            assert active, name
            checked.append(name)
        return read_frame(name, *args, **kwargs)
    def evidence(rows):
        assert "manual_review_table_content" in active
        checked.append("evidence")
        return contexts(rows)
    def extracted(*args, **kwargs):
        assert "manual_review_table_content" in active
        checked.append("occurrences")
        return extractions(*args, **kwargs)
    monkeypatch.setattr(ui, "loading_content", region)
    monkeypatch.setattr(storage, "read_frame", read)
    monkeypatch.setattr(ui, "_review_contexts", evidence)
    monkeypatch.setattr(ui, "current_extractions", extracted)
    app = AppTest.from_string("from src.ui import render\nrender('Manual Labeling')").run(timeout=60)
    assert not app.exception and not app.error
    assert {"labeled_competencies", "cleaned_psf_aai", "psf_mapping_reviews", "evidence", "occurrences"}.issubset(checked)


@pytest.mark.parametrize("page,kind,cards", [
    ("Job Market Analysis", "market", 4),
    ("Employer–PSF Alignment", "alignment", 3),
    ("PSF Mapping", "mapping", None),
    ("Unmapped / Emerging Skills", "unmapped", None),
    ("Reports", "reports", None),
])
def test_initial_results_wireframe_matches_the_first_real_component(workspace, monkeypatch, page, kind, cards):
    from src import ui, loading_ui
    wireframe = Mock(wraps=loading_ui._wireframe)
    monkeypatch.setattr(loading_ui, "_wireframe", wireframe)
    monkeypatch.setattr(ui, "current_analysis", lambda: False)
    app = AppTest.from_string(f"from src.ui import research_page\nresearch_page({page!r})").run(timeout=30)
    assert not app.exception
    assert wireframe.call_args.args == (kind,)
    assert wireframe.call_args.kwargs["cards"] == cards
    assert not app.session_state["_fow_loading_ready"]
    if page == "Unmapped / Emerging Skills":
        assert wireframe.call_args.kwargs["columns"] is None
    if page == "Job Market Analysis":
        assert any("Analysis Pipeline" in item.proto.body for item in app.get("html"))


def test_review_queue_reuses_preparation_and_detects_source_updates(workspace, monkeypatch):
    from src import ui
    monkeypatch.setattr(ui.st, "session_state", {})
    build = Mock(return_value=(pd.DataFrame({"phrase": ["SYNTHETIC"]}), pd.DataFrame()))
    monkeypatch.setattr(ui, "_build_manual_review_data", build)
    first, _ = ui._load_manual_review_data(pd.DataFrame())
    first.loc[0, "phrase"] = "unsaved edit"
    second, _ = ui._load_manual_review_data(pd.DataFrame())
    assert second.phrase.tolist() == ["SYNTHETIC"]
    assert build.call_count == 1
    storage.save_frame("extractions_original", pd.DataFrame({"original_phrase": ["NEW"]}))
    ui._load_manual_review_data(pd.DataFrame())
    assert build.call_count == 2
    (workspace / "train").mkdir(exist_ok=True)
    (workspace / "train/new_candidates.csv").write_text("phrase\nNEW\n", encoding="utf-8")
    ui._load_manual_review_data(pd.DataFrame())
    assert build.call_count == 3
    backend.clear_read_cache()
    ui._load_manual_review_data(pd.DataFrame())
    assert build.call_count == 4


def test_draft_poll_retains_previous_values_during_atomic_save(workspace, monkeypatch):
    from filelock import FileLock
    from src import ui
    from src.pretrained_suggestions import save_ai_suggestions, suggestion_key
    monkeypatch.setattr(ui.st, "session_state", {})
    path = workspace / "data/processed/pretrained_label_suggestions.csv"
    row = {"phrase": "Synthetic skill", "source_type": "jobs", "source_id": "TEST-A"}
    save_ai_suggestions(workspace, [row], [{"label": "Soft / Enabling"}])
    assert ui._page_ai_suggestions(path)[suggestion_key(row)]["category"] == "Soft / Enabling"
    save_ai_suggestions(workspace, [row], [{"label": "Data / Analytics"}])
    with FileLock(str(path) + ".lock"):
        assert ui._page_ai_suggestions(path)[suggestion_key(row)]["category"] == "Soft / Enabling"
    assert ui._page_ai_suggestions(path)[suggestion_key(row)]["category"] == "Data / Analytics"


def test_local_frame_cache_detects_changes_and_never_leaks_edits(workspace, monkeypatch):
    monkeypatch.setattr(backend.st, "session_state", {})
    path = workspace / "data/processed/test.csv"
    path.write_text("phrase,value\nSYNTHETIC,1\n", encoding="utf-8")
    reader = Mock(wraps=pd.read_csv)
    monkeypatch.setattr(pd, "read_csv", reader)
    editable = storage.read_frame("test")
    editable.loc[0, "value"] = "edited"
    assert storage.read_frame("test", columns=["value"]).to_dict("list") == {"value": ["1"]}
    assert reader.call_count == 1
    path.write_text("phrase,value\nSYNTHETIC,updated\n", encoding="utf-8")
    assert storage.read_frame("test").value.tolist() == ["updated"]
    assert reader.call_count == 2


def test_frame_cache_is_bounded_and_clearable(monkeypatch):
    state = {}
    monkeypatch.setattr(backend.st, "session_state", state)
    for index in range(8):
        storage._cached_frame(index, "v1", lambda: pd.DataFrame({"x": ["synthetic"]}))
    assert len(state["_fow_frame_cache"]) == 4
    backend.clear_read_cache(frames=True)
    assert "_fow_frame_cache" not in state


def test_cold_projection_does_not_materialize_large_context(workspace, monkeypatch):
    state = {}
    monkeypatch.setattr(backend.st, "session_state", state)
    path = workspace / "data/processed/extractions_original.csv"
    pd.DataFrame({"source_id": ["TEST-1"], "original_phrase": ["SQL"],
                  "original_text": ["SYNTHETIC " * 10000]}).to_csv(path, index=False)
    result = storage.read_frame("extractions_original", columns=["source_id", "original_phrase"])
    assert list(result) == ["source_id", "original_phrase"]
    assert all("original_text" not in item[1] for item in state["_fow_frame_cache"].values())
    assert storage.read_frame("extractions_original").original_text.iloc[0] == "SYNTHETIC " * 10000


def test_review_context_only_resolved_for_visible_job_rows(workspace, monkeypatch):
    from src.ui import _review_contexts
    monkeypatch.setattr(backend.st, "session_state", {})
    storage.save_frame("cleaned_jobs", pd.DataFrame({"source_id": ["TEST-A", "TEST-B"],
                                                    "original_text": ["Full SQL evidence", "Full Python evidence"]}))
    queue = pd.DataFrame({"source_id": ["TEST-B"], "_job_context": ["jobs"], "original_text": [""]})
    result = _review_contexts(queue)
    assert result.original_text.tolist() == ["Full Python evidence"]
    assert queue.original_text.tolist() == [""]


def test_review_restores_unmarked_candidates_and_blank_text_fallback(workspace, monkeypatch):
    from src.ui import _review_contexts
    from src.review_queue import manual_mapping_occurrences
    monkeypatch.setattr(backend.st, "session_state", {})
    storage.save_frame("cleaned_jobs", pd.DataFrame({
        "source_id": ["TEST-A", "TEST-B"], "original_text": ["Full SQL evidence", " "],
        "job_description": ["SQL", "Build data models using Python"],
    }))
    queue = pd.DataFrame([
        dict(source_id="TEST-B", source_type="jobs", normalized_phrase="build data models",
             phrase="Build data models", original_text=""),
        dict(source_id="OLD-AD", source_type="jobs", normalized_phrase="sql",
             phrase="SQL", original_text=""),
        dict(source_id="TEST-A", source_type="jobs", normalized_phrase="sql",
             phrase="SQL", original_text="Existing exact evidence"),
    ], index=[10, 11, 12])
    restored = _review_contexts(queue)
    assert restored.original_text.tolist() == [
        "Build data models using Python", "", "Existing exact evidence"]
    extracted = restored.iloc[:1].drop(columns="original_text").assign(extraction_id="exact-id")
    occurrences = manual_mapping_occurrences(restored, extracted)
    assert occurrences.loc[occurrences.source_id.eq("TEST-B"), "original_text"].item() == "Build data models using Python"


def test_review_recovers_exact_archived_ad_and_rejects_changed_archive(workspace, monkeypatch):
    from src.ui import _review_contexts
    from src.utils import digest
    monkeypatch.setattr(backend.st, "session_state", {})
    content = b"job_title,job_description\nFirst,Uses SQL\nSecond,Build data models\n"
    upload_hash = digest(content)
    path = workspace / "data/raw" / f"jobs_{upload_hash}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    queue = pd.DataFrame([dict(source_id=f"jobs:{upload_hash[:16]}:3",
                               source_type="jobs", original_text="")])
    restored = _review_contexts(queue)
    assert "Build data models" in restored.original_text.iloc[0]
    assert "Uses SQL" not in restored.original_text.iloc[0]
    path.write_bytes(content + b"Third,Different content\n")
    assert _review_contexts(queue).original_text.iloc[0] == ""


def test_chunk_download_once_per_generation_and_authenticated_session(monkeypatch):
    state = {}
    monkeypatch.setattr(backend.st, "session_state", state)
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "configuration", lambda: ("https://example.test", "test-key"))
    monkeypatch.setattr(backend, "get_token", lambda: "user-one")
    manifest = {"_storage_codec": "frame-chunks-v1", "generation": "one", "chunk_count": 1,
                "record_count": 1, "columns": ["phrase"]}
    monkeypatch.setattr(storage, "_remote_payload", lambda *args: manifest)
    download = Mock(side_effect=lambda kind, names: {name: {"records": [{"phrase": "SYNTHETIC"}]} for name in names})
    monkeypatch.setattr(storage, "_remote_payloads", download)
    editable = storage.read_frame("test")
    editable.loc[0, "phrase"] = "unsaved edit"
    assert storage.read_frame("test").phrase.tolist() == ["SYNTHETIC"]
    assert download.call_count == 1
    backend.clear_read_cache()
    storage.read_frame("test")
    assert download.call_count == 1
    manifest["generation"] = "two"
    storage.read_frame("test")
    assert download.call_count == 2
    monkeypatch.setattr(backend, "get_token", lambda: "user-two")
    storage.read_frame("test")
    assert download.call_count == 3
    monkeypatch.setattr(backend, "get_token", lambda: "")
    with pytest.raises(backend.SupabaseError, match="Sign in"):
        storage.read_frame("test")
    assert download.call_count == 3
    monkeypatch.setattr(backend, "get_token", lambda: "user-two")
    monkeypatch.setattr(backend.st, "session_state", {})
    storage.read_frame("test")
    assert download.call_count == 4


def test_incomplete_generation_is_never_cached(monkeypatch):
    monkeypatch.setattr(backend.st, "session_state", {})
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: "synthetic")
    monkeypatch.setattr(backend, "configuration", lambda: ("https://example.test", "public"))
    manifest = {"_storage_codec": "frame-chunks-v1", "generation": "broken", "chunk_count": 1,
                "record_count": 1, "columns": ["phrase"]}
    monkeypatch.setattr(storage, "_remote_payload", lambda *args: manifest)
    download = Mock(return_value={})
    monkeypatch.setattr(storage, "_remote_payloads", download)
    for _ in range(2):
        with pytest.raises(ValueError, match="missing chunk"):
            storage.read_frame("test")
    assert download.call_count == 2


def test_scoped_extraction_keeps_exact_evidence(workspace, monkeypatch):
    from src.workflow import current_extractions
    monkeypatch.setattr(backend.st, "session_state", {})
    data = pd.DataFrame([
        {"extraction_id": "TEST-1", "source_id": "TEST-A", "original_text": "Full original source A",
         "normalized_phrase": "sql", "psf_competency": "", "competency_category": "Data / Analytics"},
        {"extraction_id": "TEST-2", "source_id": "TEST-B", "original_text": "Full original source B",
         "normalized_phrase": "python", "psf_competency": "", "competency_category": "Technical / Digital"},
    ])
    storage.save_frame("extractions_original", data)
    full = current_extractions()
    scoped = current_extractions(source_ids=["TEST-A"])
    pd.testing.assert_frame_equal(scoped, full[full.source_id.eq("TEST-A")])
    assert scoped.original_text.iloc[0] == "Full original source A"


def test_revision_cached_analysis_outlives_timer_but_changes_with_inputs(monkeypatch):
    from src import ui
    monkeypatch.setattr(backend.st, "session_state", {})
    clock = Mock(return_value=0)
    monkeypatch.setattr(ui.time, "monotonic", clock)
    loader = Mock(return_value={"rows": []})
    ui._session_cached_value("test", "revision-1", loader, ttl=None)
    clock.return_value = 120
    ui._session_cached_value("test", "revision-1", loader, ttl=None)["rows"].append("edit")
    assert ui._session_cached_value("test", "revision-1", loader, ttl=None) == {"rows": []}
    assert loader.call_count == 1
    ui._session_cached_value("test", "revision-2", loader, ttl=None)
    assert loader.call_count == 2


def test_display_paginates_without_losing_rows():
    app = AppTest.from_string("""
import streamlit as st
import pandas as pd
from src.ui import display
st.session_state["_table_number"] = 0
display(pd.DataFrame({"id": range(205)}))
""").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 100
    app.number_input[0].set_value(3).run()
    assert not app.exception
    assert app.dataframe[0].value.id.tolist() == list(range(200, 205))


def test_reports_do_not_generate_files_until_requested(workspace, monkeypatch):
    from src import ui
    tables = {name: pd.DataFrame() for name in (
        "cleaned_jobs", "extracted_job_skills", "employer_skill_demand", "alignment_results")}
    monkeypatch.setattr(ui, "current_analysis", lambda: True)
    monkeypatch.setattr(ui, "filtered_bundle", lambda: (tables, {}))
    monkeypatch.setattr(ui, "job_profile_tables", lambda jobs: {})
    monkeypatch.setattr(storage, "read_frame", lambda *args, **kwargs: pd.DataFrame())
    excel = Mock(side_effect=AssertionError("An unopened download must not build a workbook"))
    monkeypatch.setattr(ui, "export_excel", excel)
    app = AppTest.from_string("from src.ui import research_page\nresearch_page('Reports')").run()
    assert not app.exception
    assert len(app.get("download_button")) == 4
    assert all(not button.disabled for button in app.get("download_button"))
    assert not app.button(key="save_report_snapshot").disabled
    assert excel.call_count == 0


def test_shared_candidate_index_omits_context_but_review_restores_exact_evidence(monkeypatch):
    from src.ui import _review_contexts
    monkeypatch.setattr(backend.st, "session_state", {})
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "configuration", lambda: ("https://example.test", "public"))
    monkeypatch.setattr(backend, "get_token", lambda: "synthetic-token")
    row = {"phrase": "SQL", "normalized_phrase": "sql", "source_type": "jobs", "source_id": "TEST-A"}
    request = Mock(return_value=[row])
    monkeypatch.setattr(backend, "_request", request)
    result = backend.read_candidates("synthetic-token", include_source_text=False)
    assert result == [row]
    assert "original_text" not in request.call_args.kwargs["params"]["select"]
    request.return_value = [row | {"original_text": "Use SQL for the original source's reporting task."}]
    queue = pd.DataFrame([row | {"_shared_candidate": True, "original_text": ""}])
    restored = _review_contexts(queue)
    assert restored.original_text.tolist() == ["Use SQL for the original source's reporting task."]
    assert queue.original_text.tolist() == [""]
    assert request.call_args.kwargs["params"]["or"] == (
        '(and(normalized_phrase.eq."sql",source_type.eq."jobs",source_id.eq."TEST-A"))')


def test_http_connections_reused_without_default_credentials(monkeypatch):
    state = {}
    monkeypatch.setattr(backend.st, "session_state", state)
    monkeypatch.setattr(backend, "configuration", lambda: ("https://example.test", "public"))
    session = Mock()
    response = Mock(ok=True, content=b"[]")
    response.json.return_value = []
    session.request.return_value = response
    factory = Mock(return_value=session)
    monkeypatch.setattr(backend.requests, "Session", factory)
    backend._request("GET", "/rest/v1/test", token="user-a")
    backend._request("GET", "/rest/v1/test", token="user-b")
    assert factory.call_count == 1
    assert session.request.call_args_list[0].kwargs["headers"]["Authorization"] == "Bearer user-a"
    assert session.request.call_args_list[1].kwargs["headers"]["Authorization"] == "Bearer user-b"
    backend.sign_out()
    session.close.assert_called_once()
    assert not state


def test_closed_source_tools_do_not_scan_training_folder(workspace, monkeypatch):
    from src import ui
    monkeypatch.setattr(ui, "training_candidates", lambda root: pd.DataFrame())
    monkeypatch.setattr(ui, "training_taxonomy", lambda root: pd.DataFrame())
    inventory = Mock(side_effect=AssertionError("Closed tools must not scan local datasets"))
    monkeypatch.setattr(ui, "inspect_training_folder", inventory)
    app = AppTest.from_string("from src.ui import render\nrender('Manual Labeling')").run()
    assert not app.exception and not app.error
    inventory.assert_not_called()


def test_small_shared_extraction_restores_elided_context(monkeypatch):
    monkeypatch.setattr(backend.st, "session_state", {})
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: "synthetic-token")
    saved = {
        "cleaned_jobs": {"columns": ["source_id", "original_text"],
                         "records": [{"source_id": "TEST-A", "original_text": "Original synthetic evidence"}]},
    }
    monkeypatch.setattr(storage, "_remote_write", lambda kind, name, payload: saved.__setitem__(name, payload))
    monkeypatch.setattr(storage, "_remote_payload", lambda kind, name: saved.get(name))
    frame = pd.DataFrame({"source_id": ["TEST-A"], "original_text": ["Original synthetic evidence"]})
    storage._save_remote_frame("extractions_original", frame)
    pd.testing.assert_frame_equal(storage.read_frame("extractions_original"), frame)
