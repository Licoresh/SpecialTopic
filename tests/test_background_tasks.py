"""Synthetic isolated jobs only; never train or publish real research data."""
import time
from threading import Event
from unittest.mock import Mock
import pandas as pd
import pytest
from src import background_tasks as tasks, supabase_store as backend, storage


@pytest.fixture
def worker(workspace, monkeypatch):
    credentials = {"_configuration": ("https://example.test", "public-test-key"),
                   "supabase_access_token": "test-user", "supabase_expires_at": time.time() + 300}
    monkeypatch.setattr(backend, "worker_credentials", lambda: dict(credentials))
    return credentials


def finished(job):
    assert job.done.wait(10), job.snapshot()
    return job.snapshot()


def test_worker_returns_immediately_and_isolates_session(worker, monkeypatch):
    ui_state = {"private_draft": "do not touch"}
    monkeypatch.setattr(backend.st, "session_state", ui_state)
    release, entered = Event(), Event()
    def work(*, progress):
        assert backend.get_token() == "test-user"
        assert "private_draft" not in backend.session_state()
        backend.session_state()["worker_only"] = True
        progress(.3, "Working")
        entered.set()
        assert release.wait(5)
        return "Saved"
    job = tasks.start("Test", work)
    try:
        assert entered.wait(5)
        assert not job.done.is_set()
        assert job.snapshot()["value"] == .3
        assert ui_state == {"private_draft": "do not touch"}
        with pytest.raises(ValueError, match="already running"):
            tasks.start("Duplicate", work)
    finally:
        release.set()
    assert finished(job)["status"] == "complete"
    assert backend.session_state() is ui_state


def test_cancel_stops_before_publication_and_sign_out_cancels(worker, monkeypatch):
    entered, release = Event(), Event()
    write = Mock()
    def work(*, progress):
        entered.set()
        assert release.wait(5)
        tasks.begin_publication()
        write()
        return "Published"
    job = tasks.start("Test", work)
    state = {"_background_job": job, "supabase_access_token": "test-user"}
    monkeypatch.setattr(backend.st, "session_state", state)
    try:
        assert entered.wait(5)
        backend.sign_out()
        assert not state
    finally:
        release.set()
    assert finished(job)["status"] == "cancelled"
    write.assert_not_called()


def test_cancel_does_not_interrupt_publication(worker):
    entered, release = Event(), Event()
    def work(*, progress):
        tasks.begin_publication()
        entered.set()
        assert release.wait(5)
        tasks.checkpoint()
        return "Published completely"
    job = tasks.start("Test", work)
    try:
        assert entered.wait(5)
        job.cancel()
        assert not job.snapshot()["cancel_requested"]
        assert not job.snapshot()["cancellable"]
    finally:
        release.set()
    assert finished(job)["status"] == "complete"


def test_failed_job_releases_slot_and_does_not_expose_credentials(worker):
    def fail(*, progress):
        raise ValueError("Invalid reviewed data")
    job = tasks.start("Test", fail)
    assert finished(job)["status"] == "failed"
    assert "test-user" not in repr(job.snapshot())
    retry = tasks.start("Retry", lambda progress: "Done")
    assert finished(retry)["status"] == "complete"


def test_worker_expiry_never_refreshes_ui_session(worker, monkeypatch):
    credentials = worker | {"supabase_expires_at": 0}
    request = Mock(side_effect=AssertionError("No refresh-token request allowed"))
    monkeypatch.setattr(backend.requests, "post", request)
    ui_state = {"supabase_access_token": "different-user"}
    monkeypatch.setattr(backend.st, "session_state", ui_state)
    with backend.worker_session(credentials):
        with pytest.raises(backend.SupabaseError, match="expired"):
            backend.get_token()
    assert backend.session_state() is ui_state
    request.assert_not_called()


def test_worker_closes_its_own_http_connection(worker, monkeypatch):
    connection = Mock()
    with backend.worker_session(worker):
        backend.session_state()["_supabase_http"] = ("https://example.test", connection)
    connection.close.assert_called_once()


def test_changed_inputs_cannot_publish_extraction(workspace, monkeypatch):
    from src import workflow
    monkeypatch.setattr(workflow, "input_signature", Mock(side_effect=["old", "new"]))
    monkeypatch.setattr(storage, "read_json", lambda name, default=None: default)
    monkeypatch.setattr(storage, "read_frame", lambda name: pd.DataFrame())
    monkeypatch.setattr(workflow, "extract_skills", lambda *args, **kwargs:
                        (pd.DataFrame({"source_id": ["TEST"]}), pd.DataFrame()))
    save = Mock()
    monkeypatch.setattr(storage, "save_frame", save)
    with pytest.raises(ValueError, match="inputs changed"):
        workflow.run_extraction()
    save.assert_not_called()


def test_draft_cancellation_retains_completed_batches_only(worker, monkeypatch):
    from src import pretrained_suggestions
    entered, release = Event(), Event()
    saved = []
    def predict(batch, taxonomy):
        if batch[0]["phrase"] == "5":
            entered.set()
            assert release.wait(5)
        return [{"category": "SYNTHETIC"} for row in batch]
    monkeypatch.setattr(pretrained_suggestions, "suggest_labels", predict)
    monkeypatch.setattr(pretrained_suggestions, "save_ai_suggestions", lambda root, rows, predictions: saved.extend(rows))
    rows = [{"phrase": str(i)} for i in range(10)]
    job = tasks.start("Drafts", tasks.suggest, rows, pd.DataFrame(), storage.ROOT)
    try:
        assert entered.wait(5)
        job.cancel()
    finally:
        release.set()
    assert finished(job)["status"] == "cancelled"
    assert saved == rows[:5]


def test_concurrent_draft_saves_preserve_all_records(workspace):
    from concurrent.futures import ThreadPoolExecutor
    from src.pretrained_suggestions import save_ai_suggestions
    def save(number):
        row = {"phrase": f"Synthetic competency {number}", "source_type": "jobs", "source_id": f"TEST-{number}"}
        save_ai_suggestions(workspace, [row], [{"label": "Data / Analytics"}])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(save, range(12)))
    result = pd.read_csv(workspace / "data/processed/pretrained_label_suggestions.csv")
    assert len(result) == 12
    assert result.source_id.nunique() == 12
    assert not (workspace / "train/labeled_competencies.csv").exists()


def test_progress_completion_does_not_reset_unsaved_ui(worker):
    from streamlit.testing.v1 import AppTest
    entered, release = Event(), Event()
    def work(*, progress):
        progress(.2, "Synthetic processing")
        entered.set()
        assert release.wait(10)
        return "Finished"
    job = tasks.start("Test job", work)
    app = AppTest.from_string('from src.ui import _processing_status\nimport streamlit as st\n_processing_status()\nst.text_input("Unsaved review", key="pending_text")')
    app.session_state["_background_job"] = job
    try:
        assert entered.wait(5)
        app.run(timeout=10)
        assert not app.exception
        app.text_input[0].set_value("Keep my manual edit").run(timeout=10)
    finally:
        release.set()
    assert finished(job)["status"] == "complete"
    app.run(timeout=10)
    assert not app.exception
    assert app.text_input[0].value == "Keep my manual edit"
    assert any("Finished" in item.value for item in app.success)
