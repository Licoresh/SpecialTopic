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
    monkeypatch.setattr(backend.requests, "request", lambda *a, **k: response)
    with pytest.raises(backend.SupabaseError, match="database setup is incomplete"):
        backend._request("GET", "/rest/v1/app_state", token="test")


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


def test_skeleton_is_scoped_to_the_slow_data_loader():
    app = AppTest.from_string(
        "from contextlib import nullcontext\n"
        "from unittest.mock import patch\n"
        "import streamlit as st\n"
        "from src.loading_ui import load_data_with_skeleton\n"
        "st.title('Page UI stays outside the loading region')\n"
        "with patch('src.loading_ui.st.skeleton', return_value=nullcontext()) as skeleton:\n"
        "    value = load_data_with_skeleton(lambda: 'loaded data', height=180)\n"
        "    assert value == 'loaded data'\n"
        "    assert skeleton.call_count == 1\n"
        "st.write(value)\n"
    ).run()
    assert not app.exception


def test_logged_out_app_only_shows_login(monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    assert app.title[0].value == "Research team sign in"
    assert not app.sidebar.button


@pytest.mark.parametrize("page_file", sorted((Path(__file__).resolve().parents[1] / "pages").glob("*.py")))
def test_logged_out_direct_page_entry_shows_login(monkeypatch, page_file):
    monkeypatch.setattr(backend, "configured", lambda: True)
    app = AppTest.from_file(page_file, default_timeout=20).run()
    assert not app.exception, [item.message for item in app.exception]
    assert any(item.value == "Research team sign in" for item in app.title)
    assert not any(item.value in {"Job market", "Review and label phrases", "Train classifier"} for item in app.title)


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


def test_shared_review_table_save_as_reviewer(workspace, monkeypatch):
    monkeypatch.setattr(backend, "configured", lambda: True)
    monkeypatch.setattr(backend, "get_token", lambda: "test")
    monkeypatch.setattr(backend, "is_admin", lambda: False)
    candidate = {"phrase": "SYNTHETIC SQL", "normalized_phrase": "synthetic sql", "source_type": "jobs",
                 "source_id": "SYNTHETIC-TEST", "job_title": "Synthetic test", "company": "", "source_url": "", "original_text": "Synthetic fixture only"}
    saved = []
    def read_frame(name):
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
