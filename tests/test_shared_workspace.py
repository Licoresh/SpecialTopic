"""Synthetic isolated tests only. No live credentials or research writes."""
import time
import json
from pathlib import Path
from unittest.mock import Mock
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest
from src import supabase_store as backend, storage, labeling
from src.training_sources import ANNOTATION_COLUMNS


@pytest.fixture
def shared(monkeypatch):
    state = {"supabase_access_token": "test-token", "supabase_expires_at": time.time()+3600,
             "supabase_user_email": "synthetic@example.test"}
    monkeypatch.setattr(backend.st, "session_state", state)
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "configuration", lambda: ("https://example.test", "public-test-key"))
    return state


def test_empty_cloud_annotations_have_schema(shared, monkeypatch):
    monkeypatch.setattr(backend, "_request", lambda *a, **k: [])
    result = storage.read_frame("labeled_competencies")
    assert result.empty and set(ANNOTATION_COLUMNS).issubset(result)


def test_local_dotenv_reader_handles_comments_quotes_and_export(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# local shared-workspace settings\n"
        "SUPABASE_URL=https://example.test # comment\n"
        "export SUPABASE_PUBLISHABLE_KEY='public-test-key'\n",
        encoding="utf-8",
    )
    assert backend._read_dotenv(dotenv) == {
        "SUPABASE_URL": "https://example.test",
        "SUPABASE_PUBLISHABLE_KEY": "public-test-key",
    }


def test_no_local_fallback_when_shared_is_empty(shared, workspace, monkeypatch):
    (workspace / "data/processed/cleaned_jobs.csv").write_text("job_id\nLOCAL-PRIVATE\n")
    monkeypatch.setattr(backend, "_request", lambda *a, **k: [])
    assert storage.read_frame("cleaned_jobs").empty
    assert storage.read_json("settings", {}) == {}


def test_unauthenticated_read_cannot_read_local_backup(shared, workspace):
    shared.clear()
    with pytest.raises(backend.SupabaseError, match="Sign in"):
        storage.read_frame("cleaned_jobs")


def test_cache_is_per_session_copied_and_invalidated_on_save(shared, monkeypatch):
    request = Mock(return_value=[{"payload": {"x": [1]}}])
    monkeypatch.setattr(backend, "_request", request)
    backend.read_state("frame:jobs", "token-a")["x"].append(2)
    assert backend.read_state("frame:jobs", "token-a") == {"x": [1]}
    assert request.call_count == 1
    backend.read_state("frame:jobs", "token-b")
    assert request.call_count == 2
    backend.write_state("frame:jobs", {}, "token-a")
    backend.read_state("frame:jobs", "token-a")
    assert request.call_count == 4


def test_large_shared_frames_are_saved_and_read_in_chunks(shared, monkeypatch):
    monkeypatch.setattr(storage, "REMOTE_FRAME_CHUNK_BYTES", 200)
    saved = {}
    monkeypatch.setattr(storage, "_remote_write", lambda kind, name, payload: saved.__setitem__(name, payload))
    monkeypatch.setattr(storage, "_remote_payload", lambda kind, name: saved.get(name))
    monkeypatch.setattr(storage, "_remote_payloads", lambda kind, names: {name: saved.get(name) for name in names if name in saved})
    frame = pd.DataFrame({"source_id": [f"SYNTHETIC-{i}" for i in range(8)],
                          "text": ["x" * 70 for _ in range(8)]})

    storage._save_remote_frame("nlp_processed", frame)
    manifest = saved["nlp_processed"]
    assert manifest["_storage_codec"] == "frame-chunks-v1"
    assert manifest["chunk_count"] > 1
    result = storage._read_remote_frame("nlp_processed", manifest)
    assert result["records"] == frame.to_dict(orient="records")


def test_shared_extractions_omit_duplicated_job_context(shared, monkeypatch):
    saved = {}
    monkeypatch.setattr(storage, "REMOTE_FRAME_CHUNK_BYTES", 2000)
    monkeypatch.setattr(storage, "_remote_write", lambda kind, name, payload: saved.__setitem__(name, payload))
    frame = pd.DataFrame({"source_id": ["SYNTHETIC-1"], "original_text": ["long job description"]})

    storage._save_remote_frame("extractions_original", frame)

    assert saved["extractions_original"]["records"][0]["original_text"] == ""


def test_review_projection_and_source_partition_keep_full_evidence(shared, monkeypatch):
    monkeypatch.setattr(storage, "REMOTE_FRAME_CHUNK_BYTES", 1000)
    saved, fetched = {}, []
    monkeypatch.setattr(storage, "_remote_write", lambda kind, name, payload: saved.__setitem__(name, payload))
    monkeypatch.setattr(storage, "_remote_payload", lambda kind, name: saved.get(name))
    def fetch(kind, names):
        fetched.extend(names)
        return {name: saved[name] for name in names}
    monkeypatch.setattr(storage, "_remote_payloads", fetch)
    frame = pd.DataFrame({"source_id": [f"TEST-{i}" for i in range(6)],
                          "original_phrase": ["SQL"] * 6,
                          "psf_range_of_application": ["SYNTHETIC RANGE " * 30] * 6})
    storage._save_remote_frame("extractions_original", frame)
    view = storage.read_frame("extractions_original", columns=["source_id", "original_phrase"])
    pd.testing.assert_frame_equal(view, frame[["source_id", "original_phrase"]])
    assert fetched and all(":chunk:review:" in name for name in fetched)
    fetched.clear()
    evidence = storage.read_frame("extractions_original", source_ids=["TEST-3"])
    pd.testing.assert_frame_equal(evidence.reset_index(drop=True), frame.iloc[[3]].reset_index(drop=True))
    assert len(fetched) == 1 and ":review:" not in fetched[0]
    complete = storage.read_frame("extractions_original")
    pd.testing.assert_frame_equal(complete, frame)


def test_read_shared_extractions_restores_context_from_job_record(shared, monkeypatch):
    manifest = {"_storage_codec": "frame-chunks-v1", "generation": "test-generation",
                "chunk_count": 1, "record_count": 1,
                "columns": ["source_id", "original_text", "original_phrase"],
                "elided_columns": ["original_text"]}
    payloads = {
        "extractions_original": manifest,
        "cleaned_jobs": {"columns": ["source_id", "original_text"],
                         "records": [{"source_id": "SYNTHETIC-1", "original_text": "Source ad context"}]},
    }
    monkeypatch.setattr(storage, "_remote_payload", lambda kind, name: payloads.get(name))
    monkeypatch.setattr(storage, "_remote_payloads", lambda kind, names: {
        name: {"records": [{"source_id": "SYNTHETIC-1", "original_text": "", "original_phrase": "SQL"}]}
        for name in names})

    result = storage.read_frame("extractions_original")

    assert result.original_text.tolist() == ["Source ad context"]


def test_batched_state_read_uses_one_request_for_chunk_group(shared, monkeypatch):
    request = Mock(return_value=[{"name": "frame:part:0", "payload": {"value": 0}},
                                 {"name": "frame:part:1", "payload": {"value": 1}}])
    monkeypatch.setattr(backend, "_request", request)

    assert backend.read_states(["frame:part:0", "frame:part:1"], "test-token") == {
        "frame:part:0": {"value": 0}, "frame:part:1": {"value": 1}}
    assert request.call_count == 1
    assert request.call_args.kwargs["params"]["name"] == 'in.("frame:part:0","frame:part:1")'


def test_save_uses_one_atomic_rpc_and_preserves_versions(shared, monkeypatch):
    request = Mock(return_value=2)
    monkeypatch.setattr(backend, "_request", request)
    backend.save_reviewed_annotations([{"phrase": "SYNTHETIC"}], "test", {"synthetic": 4}, {"synthetic": "Technical"})
    assert request.call_count == 1
    assert request.call_args.kwargs["payload"]["expected_versions"] == {"synthetic": 4}


def test_no_bulk_promotion_of_csv_labels(shared):
    with pytest.raises(backend.SupabaseError, match="Bulk uploads"):
        backend.upsert_annotations([{"phrase": "SYNTHETIC"}], "test")


def test_upload_manifest_shares_filename_but_not_machine_path(shared, workspace, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", workspace)
    request = Mock()
    monkeypatch.setattr(backend, "write_state", request)
    manifest = {"jobs": {"filename": "sample.csv", "sha256": "synthetic-hash", "path": r"C:\\Users\\reviewer\\private\\sample.csv"}}

    storage.save_json("uploads", manifest)

    shared_payload = request.call_args.args[1]
    assert shared_payload["jobs"] == {"filename": "sample.csv", "sha256": "synthetic-hash"}
    assert json.loads((workspace / "data/processed/uploads.json").read_text(encoding="utf-8")) == manifest


def test_missing_membership_does_not_pass_connection_check(shared, monkeypatch):
    monkeypatch.setattr(backend, "_request", lambda *a, **k: None)
    with pytest.raises(backend.SupabaseError, match="membership"):
        backend.check_connection("test")


def test_missing_schema_message_is_actionable(shared, monkeypatch):
    response = Mock(ok=False, status_code=404)
    response.json.return_value = {"message": "Could not find the table in the schema cache"}
    monkeypatch.setattr(backend, "_http_session", lambda: Mock(request=Mock(return_value=response)))
    with pytest.raises(backend.SupabaseError, match="database setup is incomplete"):
        backend._request("GET", "/rest/v1/app_state", token="test")


def test_connection_reset_retries_identical_snapshot_on_fresh_connection(shared, monkeypatch):
    import requests
    response = Mock(ok=True, status_code=201, content=b"")
    broken = Mock()
    broken.request.side_effect = requests.ConnectionError("Synthetic reset 10054")
    healthy = Mock()
    healthy.request.return_value = response
    monkeypatch.setattr(backend.requests, "Session", Mock(side_effect=[broken, healthy]))
    monkeypatch.setattr(backend.time, "sleep", lambda seconds: None)
    backend.write_state("frame:synthetic:chunk:fixed:0", {"records": [{"x": 1}]}, "test")
    broken.close.assert_called_once()
    assert broken.request.call_args == healthy.request.call_args
    assert healthy.request.call_count == 1


@pytest.mark.parametrize("method,endpoint,attempts", [("GET", "/rest/v1/app_state", 3),
    ("POST", "/rest/v1/rpc/save_reviewed_annotations", 1)])
def test_retry_limit_and_no_replay_of_review_rpc(shared, monkeypatch, method, endpoint, attempts):
    import requests
    session = Mock()
    session.request.side_effect = requests.ConnectionError("Synthetic reset")
    monkeypatch.setattr(backend, "_http_session", lambda: session)
    monkeypatch.setattr(backend.time, "sleep", lambda seconds: None)
    with pytest.raises(backend.SupabaseError, match=f"after {attempts} attempt"):
        backend._request(method, endpoint, token="test", payload={})
    assert session.request.call_count == attempts


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failures_are_not_retried(shared, monkeypatch, status):
    response = Mock(ok=False, status_code=status)
    response.json.return_value = {"message": "Synthetic auth failure"}
    session = Mock(request=Mock(return_value=response))
    monkeypatch.setattr(backend, "_http_session", lambda: session)
    with pytest.raises(backend.SupabaseError):
        backend._request("GET", "/rest/v1/app_state", token="test")
    assert session.request.call_count == 1


@pytest.mark.parametrize("content", [b"not JSON", b""])
def test_malformed_success_response_is_not_empty_data(shared, monkeypatch, content):
    response = Mock(ok=True, status_code=200, content=content)
    response.json.side_effect = ValueError("Synthetic invalid JSON")
    monkeypatch.setattr(backend, "_http_session", lambda: Mock(request=Mock(return_value=response)))
    with pytest.raises(backend.SupabaseError, match="no empty dataset"):
        backend.read_state("frame:synthetic", "test")


def test_temporary_gateway_failure_retries_but_tls_failure_does_not(shared, monkeypatch):
    import requests
    failed = Mock(ok=False, status_code=503)
    success = Mock(ok=True, status_code=200, content=b"[]")
    success.json.return_value = []
    session = Mock()
    session.request.side_effect = [failed, success]
    monkeypatch.setattr(backend, "_http_session", lambda: session)
    monkeypatch.setattr(backend.time, "sleep", lambda seconds: None)
    assert backend._request("GET", "/rest/v1/app_state", token="test") == []
    assert session.request.call_count == 2
    failed.close.assert_called_once()
    session.request.reset_mock()
    session.request.side_effect = requests.exceptions.SSLError("Synthetic certificate error")
    with pytest.raises(backend.SupabaseError, match="secure"):
        backend._request("GET", "/rest/v1/app_state", token="test")
    assert session.request.call_count == 1


def test_failed_chunk_does_not_publish_partial_snapshot(shared, monkeypatch):
    monkeypatch.setattr(storage, "REMOTE_FRAME_CHUNK_BYTES", 300)
    previous = {"records": [{"original_phrase": "previous synthetic result"}]}
    saved = {"extractions_original": previous}
    def write(kind, name, payload):
        if name.endswith(":1"):
            raise backend.SupabaseError("Synthetic connection failure")
        saved[name] = payload
    monkeypatch.setattr(storage, "_remote_write", write)
    frame = pd.DataFrame({"source_id": [f"TEST-{i}" for i in range(20)], "original_phrase": ["Synthetic phrase"] * 20})
    with pytest.raises(backend.SupabaseError):
        storage._save_remote_frame("extractions_original", frame)
    assert saved["extractions_original"] == previous


def test_signout_removes_previous_reviewers_drafts_and_data(shared):
    shared["review_snapshot"] = "private data"
    shared["manual_labels_123"] = "unsaved edits"
    backend.sign_out()
    assert shared == {}


def test_shared_refresh_clears_derived_session_views(shared):
    shared.update({"_fow_source_cache": {"source": "stale"},
                   "_fow_analysis_cache": {"analysis": "stale"},
                   "_fow_signature_cache": {"signature": "stale"}})
    backend.clear_read_cache()
    assert not any(key in shared for key in (
        "supabase_reads", "_fow_source_cache", "_fow_analysis_cache", "_fow_signature_cache"
    ))


def test_shared_save_sends_only_submitted_rows(workspace, shared, monkeypatch):
    old = pd.DataFrame([dict(zip(ANNOTATION_COLUMNS, ["Existing", "existing", "Technical", "", "jobs", "SYNTHETIC-1", "test", "2026-01-01"]))])
    old["version"] = "3"
    monkeypatch.setattr(labeling, "read_frame", lambda name: old.copy())
    monkeypatch.setattr(labeling, "training_taxonomy", lambda root: pd.DataFrame())
    submit = Mock()
    monkeypatch.setattr(backend, "save_reviewed_annotations", submit)
    labeling.save_annotations(pd.DataFrame([{"phrase": "New", "label": "Technical", "source_id": "SYNTHETIC-2", "source_type": "jobs"}]),
                              "forged reviewer", expected_versions={"new": 0})
    records = submit.call_args.args[0]
    assert len(records) == 1 and records[0]["phrase"] == "New"
    assert records[0]["reviewer"] == "synthetic@example.test"
    assert submit.call_args.args[2] == {"new": 0}


def test_login_does_not_keep_token_after_schema_failure(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "sign_in", lambda *a: {"access_token": "test", "refresh_token": "test", "user": {"email": "synthetic@example.test"}})
    def fail(*a):
        raise backend.SupabaseError("Database setup is incomplete")
    monkeypatch.setattr(backend, "check_connection", fail)
    app = AppTest.from_string("from src.auth_ui import login_page\nlogin_page()").run()
    app.text_input[0].set_value("synthetic@example.test")
    app.text_input[1].set_value("synthetic-test-password")
    app.button[0].click().run()
    assert not app.exception
    assert "incomplete" in app.error[0].value
    assert "supabase_access_token" not in app.session_state


def test_data_only_loader_does_not_insert_an_unrelated_skeleton():
    app = AppTest.from_string(
        "from contextlib import nullcontext\n"
        "from unittest.mock import patch\n"
        "import streamlit as st\n"
        "from src.loading_ui import load_data_with_skeleton\n"
        "st.title('Page UI stays outside the loading region')\n"
        "with patch('streamlit.skeleton', return_value=nullcontext()) as skeleton:\n"
        "    value = load_data_with_skeleton(lambda: 'loaded data', height=180)\n"
        "    assert value == 'loaded data'\n"
        "    assert skeleton.call_count == 0\n"
        "st.write(value)\n"
    ).run()
    assert not app.exception


def test_skeleton_load_uses_only_its_explicit_output_region():
    from contextlib import nullcontext
    from src.loading_ui import load_data_with_skeleton
    region = Mock()
    region.skeleton.return_value = nullcontext()
    expected = pd.DataFrame({"source_id": ["SYNTHETIC-A"]})
    assert load_data_with_skeleton(lambda: expected, region=region, height=180) is expected
    region.skeleton.assert_called_once_with(height=180)


def test_scoped_skeleton_clears_and_preserves_loader_errors():
    from contextlib import contextmanager
    from src.loading_ui import load_data_with_skeleton
    entered = []

    @contextmanager
    def scoped_placeholder(**kwargs):
        entered.append("loading")
        try:
            yield
        finally:
            entered.append("cleared")

    region = Mock()
    region.skeleton.side_effect = scoped_placeholder
    loader = Mock(side_effect=ValueError("Synthetic source load failed"))
    with pytest.raises(ValueError, match="Synthetic source load failed"):
        load_data_with_skeleton(loader, region=region)
    assert entered == ["loading", "cleared"]


def test_structured_loading_replaces_exact_slot_and_preserves_it_on_rerun(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from src import loading_ui
    state = {}
    host, pending = Mock(), Mock()
    host.empty.return_value = pending
    pending.container.return_value = nullcontext()
    host.container.return_value = nullcontext()
    monkeypatch.setattr(loading_ui, "st", SimpleNamespace(session_state=state, container=Mock(return_value=host)))
    with loading_ui.loading_content("synthetic-results", "results") as content:
        assert pending.html.call_count == 1
        assert not state["_fow_loading_ready"]
        with content():
            pass
    assert state["_fow_loading_ready"] == {"synthetic-results": True}
    pending.container.assert_called_once_with(key="synthetic-results_body")
    with loading_ui.loading_content("synthetic-results", "results") as content:
        with content():
            pass
    assert host.empty.call_count == 1
    assert pending.html.call_count == 1
    host.container.assert_called_once_with(key="synthetic-results_body")


def test_structured_loading_error_or_missing_result_clears_pending_and_allows_retry(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from src import loading_ui
    state = {}
    host, pending = Mock(), Mock()
    host.empty.return_value = pending
    pending.container.return_value = nullcontext()
    monkeypatch.setattr(loading_ui, "st", SimpleNamespace(session_state=state, container=Mock(return_value=host)))
    with pytest.raises(ValueError, match="Synthetic failed source"):
        with loading_ui.loading_content("synthetic-results", "reports"):
            raise ValueError("Synthetic failed source")
    assert pending.empty.call_count == 1
    assert not state["_fow_loading_ready"]
    with loading_ui.loading_content("synthetic-results", "reports"):
        pass  # A missing/stale extraction never materializes results.
    assert pending.empty.call_count == 2
    assert not state["_fow_loading_ready"]
    with loading_ui.loading_content("synthetic-results", "reports") as content:
        with content():
            pass
    assert state["_fow_loading_ready"] == {"synthetic-results": True}

    with loading_ui.loading_content("synthetic-results", "reports"):
        pass  # Previously visible results can become unavailable after cleanup.
    assert not state["_fow_loading_ready"]
    calls_before_retry = host.empty.call_count
    with loading_ui.loading_content("synthetic-results", "reports") as content:
        with content():
            pass
    assert host.empty.call_count == calls_before_retry + 1
    assert state["_fow_loading_ready"] == {"synthetic-results": True}


@pytest.mark.parametrize("failure", [False, True])
def test_deferred_loading_remains_until_the_output_finishes_and_clears_on_error(monkeypatch, failure):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from src import loading_ui
    state = {}
    host, pending = Mock(), Mock()
    host.empty.return_value = pending
    host.container.return_value = nullcontext()
    monkeypatch.setattr(loading_ui, "st", SimpleNamespace(session_state=state, container=Mock(return_value=host)))
    def render():
        with loading_ui.loading_content("synthetic-section", "market_section", view="Skills", defer=True) as content:
            pending.empty.assert_not_called()
            with content():
                pending.container.assert_not_called()
                pending.empty.assert_not_called()
                if failure:
                    raise ValueError("Synthetic rendering failure")
    if failure:
        with pytest.raises(ValueError, match="Synthetic rendering failure"):
            render()
        assert not state["_fow_loading_ready"]
    else:
        render()
        assert state["_fow_loading_ready"]["synthetic-section"]
    pending.empty.assert_called_once()


def test_structured_loading_keeps_existing_ready_state_during_streamlit_rerun(monkeypatch):
    from types import SimpleNamespace
    from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
    from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
    from src import loading_ui
    state = {"_fow_loading_ready": {"synthetic-review": True}}
    host = Mock()
    monkeypatch.setattr(loading_ui, "st", SimpleNamespace(session_state=state, container=Mock(return_value=host)))
    with pytest.raises(RerunException):
        with loading_ui.loading_content("synthetic-review", "review"):
            raise RerunException(RerunData())
    assert state["_fow_loading_ready"] == {"synthetic-review": True}
    host.empty.assert_not_called()


def test_structured_wireframes_match_content_shapes_without_fake_research_values():
    from src.loading_ui import _wireframe
    assert _wireframe("metrics").count('class="fow-skeleton-card"') == 4
    reports = _wireframe("reports")
    assert reports.count('class="fow-skeleton-card"') == 5
    assert reports.index('fow-skeleton-toolbar') < reports.index('fow-skeleton-heading') < reports.index('fow-skeleton-card')
    review = _wireframe("review")
    assert review.count('class="fow-skeleton-row"') == 11
    assert 'aria-busy="true"' in review and 'aria-hidden="true"' in review
    assert "93,622" not in review and "SQL" not in review
    assert _wireframe("metrics", cards=3).count('class="fow-skeleton-card"') == 3
    selector = _wireframe("selector")
    assert 'fow-skeleton-control' in selector and 'fow-skeleton-chart' not in selector
    assert _wireframe("table", columns=["source_id", "phrase"], rows=2).count('class="fow-skeleton-row"') == 3


def test_unknown_source_shape_does_not_invent_a_table_or_chart():
    from src.loading_ui import _wireframe
    for markup in (_wireframe("table"), _wireframe("pending")):
        assert "fow-skeleton-pending" in markup
        assert "fow-skeleton-table" not in markup
        assert "fow-skeleton-chart" not in markup
    schema_only = _wireframe("table", columns=["source", "skill"])
    assert schema_only.count('class="fow-skeleton-row"') == 6  # Neutral loading rows, never a reported record count.
    actual_page = _wireframe("review", columns=["phrase", "category"], rows=3)
    assert actual_page.count('class="fow-skeleton-row"') == 4


def test_settings_wireframe_uses_the_same_control_schema_as_the_form():
    from src.loading_ui import _wireframe
    from src.ui import SETTINGS_SECTIONS
    controls = [control for _, _, fields in SETTINGS_SECTIONS
                for control in ["heading", *(field[2] for field in fields)]] + ["button"]
    markup = _wireframe("form", controls=controls, field_columns=2)
    assert markup.count('class="fow-skeleton-form-heading"') == len(SETTINGS_SECTIONS)
    assert markup.count('fow-skeleton-field--slider') == 4
    assert markup.count('fow-skeleton-field--number') == 5
    assert markup.count('fow-skeleton-field--textarea') == 1
    assert markup.count('fow-skeleton-field--text"') == 1
    assert markup.count('fow-skeleton-field--button') == 1
    assert "--fow-field-columns:2" in markup


def test_loading_page_shapes_follow_visible_sections_and_controls():
    from src.loading_ui import _wireframe
    overview = _wireframe("overview", cards=4)
    assert overview.count('class="fow-skeleton-card"') == 4
    assert overview.count('class="fow-skeleton-workflow-card"') == 6
    assert 'class="fow-skeleton-callout"' in overview
    assert 'class="fow-skeleton-chart"' not in _wireframe("market", view=None)
    assert _wireframe("market", view="Skills").count('class="fow-skeleton-chart"') == 1
    assert _wireframe("mapping", view="selected").count('class="fow-skeleton-field"') > _wireframe("mapping").count('class="fow-skeleton-field"')
    psf = _wireframe("psf_charts", columns=["role a", "role b"], rows=3)
    assert psf.count('class="fow-skeleton-chart"') == 2
    assert 'class="fow-skeleton-matrix"' in psf and 'class="fow-skeleton-table"' not in psf
    assert 'data-view="usability"' in _wireframe("form", controls=["select", "slider", "textarea", "button"], view="usability")


def test_loading_geometry_is_bounded_and_does_not_repeat_live_regions():
    from src.loading_ui import _wireframe
    table = _wireframe("table", columns=range(1_000_000), rows=1_000_000)
    assert table.count('class="fow-skeleton-row"') == 11
    assert len(table.encode()) < 8_000
    assert _wireframe("metrics", cards=1_000_000).count('class="fow-skeleton-card"') == 8
    assert _wireframe("table", columns=["source", "phrase"], rows=0).count('class="fow-skeleton-row"') == 1
    for kind in ("overview", "market", "alignment", "mapping", "evaluation", "unmapped", "reports", "psf_charts", "readiness", "workspace_status"):
        markup = _wireframe(kind, view="Skills", columns=range(12), rows=15)
        assert markup.count('aria-busy="true"') == 1
        assert len(markup.encode()) < 20_000
        assert "<script" not in markup


def test_logged_out_app_only_shows_login(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    assert app.title[0].value == "Research team sign in"
    assert not app.sidebar.button
    auth_chrome = next(item.proto.body for item in app.get("html") if "data-fow-auth-sidebar" in item.proto.body)
    for element in ("stSidebar", "stSidebarCollapsed", "stSidebarCollapseButton", "stSidebarResizeHandle"):
        assert f'[data-testid="{element}"]' in auth_chrome
    assert "display: none !important" in auth_chrome


@pytest.mark.parametrize("page_file", sorted((Path(__file__).resolve().parents[1] / "pages").glob("*.py")))
def test_logged_out_direct_page_entry_shows_login(monkeypatch, page_file):
    monkeypatch.setattr(backend, "configured", lambda: True)
    app = AppTest.from_file(page_file, default_timeout=20).run()
    assert not app.exception, [item.message for item in app.exception]
    assert any(item.value == "Research team sign in" for item in app.title)
    assert not any(item.value in {"Job market", "Review and label phrases", "Train classifier"} for item in app.title)
    assert any("data-fow-auth-sidebar" in item.proto.body for item in app.get("html"))


@pytest.mark.parametrize("known_session", [False, True])
def test_authorized_workspace_releases_sidebar_guard_without_hiding_valid_session(monkeypatch, known_session):
    from src import auth_ui
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: "synthetic-token")
    monkeypatch.setattr(backend, "check_connection", lambda token: "reviewer")
    guard = Mock(wraps=auth_ui._hide_workspace_sidebar)
    monkeypatch.setattr(auth_ui, "_hide_workspace_sidebar", guard)
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from src.auth_ui import require_workspace_access\n"
        "require_workspace_access()\n"
        "st.sidebar.write('Authorized workspace')\n"
    )
    if known_session:
        for key, value in {"supabase_access_token": "synthetic-token", "supabase_role": "reviewer",
                           "supabase_expires_at": time.time() + 3600}.items():
            app.session_state[key] = value
    app.run()
    assert not app.exception
    assert app.sidebar.markdown[0].value == "Authorized workspace"
    assert not any("data-fow-auth-sidebar" in item.proto.body for item in app.get("html"))
    assert guard.call_count == (0 if known_session else 1)


@pytest.mark.parametrize("stage", ["refresh", "membership"])
def test_session_connection_errors_hide_workspace_sidebar(monkeypatch, stage):
    monkeypatch.setattr(backend, "configured", lambda: True)
    def fail(*args):
        raise backend.SupabaseError("Synthetic connection unavailable", status_code=503)
    monkeypatch.setattr(backend, "get_token", fail if stage == "refresh" else lambda: "synthetic-token")
    monkeypatch.setattr(backend, "check_connection", fail)
    app = AppTest.from_string(
        "from src.auth_ui import require_workspace_access\nrequire_workspace_access()"
    )
    for key, value in {"supabase_access_token": "synthetic-token", "supabase_role": "reviewer",
                       "supabase_expires_at": time.time() + 3600}.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    assert any("data-fow-auth-sidebar" in item.proto.body for item in app.get("html"))
    assert app.title[0].value == "Workspace unavailable"
    assert any("Synthetic connection unavailable" in item.proto.body for item in app.get("html"))
    assert {item.label for item in app.button} == {
        "Retry session connection" if stage == "refresh" else "Retry connection", "Return to sign in"}


def test_sign_out_returns_to_login_with_sidebar_hidden(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: backend.st.session_state.get("supabase_access_token", ""))
    monkeypatch.setattr(backend, "check_connection", lambda token: "reviewer")
    app = AppTest.from_string(
        "import streamlit as st\n"
        "from src.auth_ui import require_workspace_access, render_account_menu\n"
        "require_workspace_access()\n"
        "st.sidebar.write('Authorized workspace')\n"
        "render_account_menu()\n"
    )
    for key, value in {"supabase_access_token": "synthetic-token", "supabase_role": "reviewer",
                       "supabase_expires_at": time.time() + 3600,
                       "supabase_user_email": "synthetic@example.test"}.items():
        app.session_state[key] = value
    app.run()
    assert not app.exception
    app.button(key="sign_out").click().run()
    assert not app.exception
    assert app.title[0].value == "Research team sign in"
    assert not app.sidebar.markdown
    assert any("data-fow-auth-sidebar" in item.proto.body for item in app.get("html"))


def test_expired_workspace_session_returns_to_sign_in(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: "expired-token")
    monkeypatch.setattr(
        backend,
        "check_connection",
        lambda _token: (_ for _ in ()).throw(backend.SupabaseError("Expired", status_code=401)),
    )
    app = AppTest.from_string(
        "from src.auth_ui import require_workspace_access\nrequire_workspace_access()"
    ).run()
    assert not app.exception
    assert app.title[0].value == "Research team sign in"
    assert "session has expired" in app.error[0].value


def test_vercel_requires_supabase_configuration(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: False)
    monkeypatch.setenv("VERCEL", "1")
    app = AppTest.from_string(
        "from src.auth_ui import require_workspace_access\nrequire_workspace_access()"
    ).run()
    assert not app.exception
    assert app.title[0].value == "Sign-in configuration required"
    assert "SUPABASE_URL" in app.error[0].value


def test_large_state_compression_roundtrip():
    payload = {"records": [{"text": "synthetic repeated source " * 500}] * 40}
    packed = backend.pack_state(payload)
    assert packed["_codec"] == "gzip-json-v1"
    assert backend.unpack_state(packed) == payload
    assert len(str(packed)) < len(str(payload)) / 10


def test_corrupt_compressed_state_is_controlled_error():
    with pytest.raises(backend.SupabaseError, match="Could not read"):
        backend.unpack_state({"_codec": "gzip-json-v1", "data": "not-base64!"})


def test_unpublished_model_tables_are_not_visible(shared, monkeypatch):
    shared["training_run_id"] = "new-run"
    monkeypatch.setattr(backend, "read_state", lambda *a: {"shared_run_id": "published-run"})
    assert storage._shared_key("frame", "model_metrics", writing=True) == "frame:modelrun:new-run:model_metrics"
    assert storage._shared_key("frame", "model_metrics") == "frame:modelrun:published-run:model_metrics"


def test_shared_training_uses_snapshot_not_stale_local_csv(workspace, shared, labeled, monkeypatch):
    from src import model_training
    reviewed = labeled.copy()
    reviewed["reviewer"] = "SYNTHETIC TEST REVIEWER"
    reviewed["timestamp"] = "2026-01-01T00:00:00+00:00"
    reviewed["version"] = "1"
    monkeypatch.setattr(storage, "read_frame", lambda name: reviewed.copy())
    monkeypatch.setattr(storage, "save_frame", Mock())
    monkeypatch.setattr(storage, "save_json", Mock())
    monkeypatch.setattr(backend, "_request", Mock(return_value=True))
    metadata, _ = model_training.train_and_save_models()
    assert metadata["rows_available"] == 30
    assert metadata["shared_annotation_hash"]
    assert Path(metadata["training_file"]).parent.name == "snapshots"
    assert metadata["shared_run_id"]
    saved_metadata = storage.save_json.call_args_list[-1].args
    assert saved_metadata[0] == "model_metadata"


def test_training_lease_blocks_second_runner(workspace, shared, monkeypatch):
    from src.model_training import train_and_save_models
    monkeypatch.setattr(backend, "_request", Mock(return_value=False))
    with pytest.raises(ValueError, match="Another training run"):
        train_and_save_models()
    assert not list((workspace / "models").glob("*.joblib"))


def test_refresh_network_failure_preserves_unsaved_draft(shared, monkeypatch):
    shared.update(supabase_expires_at=0, supabase_refresh_token="test-refresh", review_snapshot="unsaved")
    monkeypatch.setattr(backend.requests, "post", Mock(side_effect=backend.requests.ConnectionError("offline")))
    with pytest.raises(backend.SupabaseError, match="unsaved work is retained"):
        backend.get_token()
    assert shared["review_snapshot"] == "unsaved"


def test_extraction_cleanup_uses_scoped_database_rpc(monkeypatch):
    request = Mock()
    monkeypatch.setattr(backend, "_request", request)
    monkeypatch.setattr(backend, "clear_read_cache", Mock())
    backend.clear_generated_extractions("admin-token")
    request.assert_called_once_with("POST", "/rest/v1/rpc/clear_generated_extractions",
                                    token="admin-token", payload={})


def test_extraction_results_can_skip_repeated_source_text(workspace):
    path = workspace / "data/processed/extractions_original.csv"
    pd.DataFrame({"original_phrase": ["Python"], "original_text": ["Large source text"]}).to_csv(path, index=False)
    result = storage.read_frame("extractions_original", include_source_text=False)
    assert result.original_phrase.tolist() == ["Python"]
    assert "original_text" not in result.columns


def test_shared_review_table_save_as_reviewer(workspace, monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: "test")
    monkeypatch.setattr(backend, "is_admin", lambda: False)
    monkeypatch.setattr(storage, "frame_revision", lambda name: "synthetic-revision")
    monkeypatch.setattr(backend, "candidate_contexts", lambda token, keys: {
        key: "Synthetic fixture only" for key in keys})
    candidate = {"phrase": "SYNTHETIC SQL", "normalized_phrase": "synthetic sql", "source_type": "jobs",
                 "source_id": "SYNTHETIC-TEST", "job_title": "Synthetic test", "company": "", "source_url": "", "original_text": "Synthetic fixture only"}
    saved = []
    def read_frame(name, **kwargs):
        if name == "labeled_competencies":
            return pd.DataFrame(saved, columns=ANNOTATION_COLUMNS+["version"])
        if name == "team_training_candidates":
            return pd.DataFrame([candidate])
        return pd.DataFrame()
    monkeypatch.setattr(storage, "read_frame", read_frame)
    monkeypatch.setattr(labeling, "read_frame", read_frame)
    def save_rows(rows, token, expected_versions, resolutions):
        assert expected_versions == {}
        saved.extend(dict(row, version="1") for row in rows)
    monkeypatch.setattr(backend, "save_reviewed_annotations", save_rows)
    script = '''import streamlit as st
from unittest.mock import patch
from src.ui import render
st.session_state['supabase_user_email']='synthetic@example.test'
def enter_category(frame, **kwargs):
    edited=frame.copy()
    if 'Category' in edited and len(edited):
        edited.loc[edited.index[0],'Category']='Technical / Digital'
    return edited
with patch('streamlit.data_editor',side_effect=enter_category):
    render('Manual Labeling')
'''
    app = AppTest.from_string(script).run(timeout=30)
    assert not app.exception and not app.error
    next(b for b in app.button if b.label == "Save annotations").click().run(timeout=30)
    assert not app.exception and not app.error
    assert len(saved)==1 and saved[0]["reviewer"]=="synthetic@example.test"
    assert (workspace / "data/processed/shared_labeled_competencies.csv").is_file()


def test_raw_upload_path_ignores_foreign_host_absolute_path(workspace):
    from src.utils import digest
    content = b"SYNTHETIC fixture"
    source_hash = digest(content)
    expected = workspace / "data/raw" / f"jobs_{source_hash}.csv"
    expected.write_bytes(content)
    assert storage.raw_upload_path({"hash": source_hash, "filename": "sample.csv", "path": "C:/another-device/private.txt"}, "jobs") == expected


def test_raw_upload_path_rejects_path_traversal(workspace):
    with pytest.raises(ValueError, match="hash"):
        storage.raw_upload_path({"hash": "../../private", "filename": "sample.csv"}, "jobs")


def test_restore_shared_evidence_only_patches_blank_text(shared, monkeypatch):
    monkeypatch.setattr(backend, "check_connection", lambda token: "admin")
    request = Mock(return_value=[{"source_id": "jobs:synthetic:7"}])
    monkeypatch.setattr(backend, "_request", request)
    assert backend.restore_candidate_evidence({"jobs:synthetic:7": "Verified archived ad text"}, "token") == 1
    assert request.call_args.args == ("PATCH", "/rest/v1/research_candidates")
    options = request.call_args.kwargs
    assert options["payload"] == {"original_text": "Verified archived ad text"}
    assert options["params"]["original_text"] == "eq."
    assert options["params"]["source_id"] == "eq.jobs:synthetic:7"
    assert options["retry_safe"] is True


def test_reviewers_cannot_restore_shared_evidence(shared, monkeypatch):
    monkeypatch.setattr(backend, "check_connection", lambda token: "reviewer")
    request = Mock()
    monkeypatch.setattr(backend, "_request", request)
    with pytest.raises(backend.SupabaseError, match="admin"):
        backend.restore_candidate_evidence({"jobs:synthetic:7": "Evidence"}, "token")
    request.assert_not_called()

def test_successful_login_replaces_form_with_workspace(monkeypatch):
    monkeypatch.setattr(backend, 'sign_in', lambda *args: {
        'access_token': 'synthetic-token', 'refresh_token': 'synthetic-refresh',
        'user': {'email': 'synthetic@example.test'}})
    monkeypatch.setattr(backend, 'check_connection', lambda *args: 'reviewer')
    app = AppTest.from_string("""
import streamlit as st
from src.auth_ui import login_page
if st.session_state.get('supabase_access_token'):
    st.title('Overview')
else:
    login_page()
""").run()
    app.text_input[0].set_value('synthetic@example.test')
    app.text_input[1].set_value('synthetic-test-password')
    app.button[0].click().run()
    assert not app.exception
    assert [heading.value for heading in app.title] == ['Overview']
    assert not app.text_input
    assert not app.button
    assert not app.caption
    assert app.session_state['supabase_role'] == 'reviewer'
