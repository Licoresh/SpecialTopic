from pathlib import Path

import pytest

from src import storage


def test_atomic_bytes_retries_transient_windows_lock(tmp_path, monkeypatch):
    target = tmp_path / "result.csv"
    target.write_bytes(b"old")
    real_replace = storage.os.replace
    calls = 0

    def transient_lock(source, destination):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise PermissionError(5, "Access is denied")
        real_replace(source, destination)

    monkeypatch.setattr(storage.os, "replace", transient_lock)
    monkeypatch.setattr(storage.time, "sleep", lambda _: None)

    storage.atomic_bytes(target, b"new result")

    assert calls == 3
    assert target.read_bytes() == b"new result"
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_bytes_preserves_staged_output_after_persistent_lock(tmp_path, monkeypatch):
    target = tmp_path / "result.csv"
    target.write_bytes(b"old")
    monkeypatch.setattr(storage.os, "replace", lambda *_: (_ for _ in ()).throw(PermissionError(5, "Access is denied")))
    monkeypatch.setattr(storage.time, "sleep", lambda _: None)

    with pytest.raises(PermissionError, match="complete new result is preserved"):
        storage.atomic_bytes(target, b"new result")

    assert target.read_bytes() == b"old"
    staged = list(tmp_path.glob("*.tmp"))
    assert len(staged) == 1
    assert staged[0].read_bytes() == b"new result"


def test_bundled_psf_reference_is_used_when_local_copy_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    path = tmp_path / "data/reference/psf_aai_default.csv"
    path.parent.mkdir(parents=True)
    path.write_text("competency_id,competency_name\nTEST-1,Statistics\n", encoding="utf-8")

    result = storage.read_frame("cleaned_psf_aai")

    assert result.competency_name.tolist() == ["Statistics"]
    assert result.attrs["reference_source"] == "bundled_default"


def test_bundled_psf_reference_fills_empty_shared_slot(tmp_path, monkeypatch):
    from src import supabase_store
    monkeypatch.setattr(storage, "ROOT", tmp_path)
    monkeypatch.setattr(supabase_store, "configured", lambda: True)
    monkeypatch.setattr(supabase_store, "get_token", lambda: "test-token")
    monkeypatch.setattr(storage, "_remote_payload", lambda *_: None)
    path = tmp_path / "data/reference/psf_aai_default.csv"
    path.parent.mkdir(parents=True)
    path.write_text("competency_id,competency_name\nTEST-1,Statistics\n", encoding="utf-8")

    result = storage.read_frame("cleaned_psf_aai")

    assert result.competency_name.tolist() == ["Statistics"]
    assert result.attrs["reference_source"] == "bundled_default"
