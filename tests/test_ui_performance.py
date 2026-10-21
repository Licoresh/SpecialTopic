"""Session-local performance cache tests; synthetic values only."""
from streamlit.testing.v1 import AppTest
from unittest.mock import Mock
import pandas as pd
import pytest
from src import storage, supabase_store as backend


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
