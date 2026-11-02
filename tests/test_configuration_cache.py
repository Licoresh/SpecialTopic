"""Local configuration caching uses temporary synthetic settings only."""
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import supabase_store as backend


@pytest.fixture(autouse=True)
def isolated_cache():
    backend._parse_dotenv.cache_clear()
    yield
    backend._parse_dotenv.cache_clear()


def test_unchanged_dotenv_is_read_once_and_returns_independent_values(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("NAME=original\n", encoding="utf-8")
    original_read = Path.read_text
    reads = []
    def read(path, **kwargs):
        reads.append(path)
        return original_read(path, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    first = backend._read_dotenv(path)
    first["NAME"] = "changed by caller"
    assert backend._read_dotenv(path) == {"NAME": "original"}
    assert backend._read_dotenv(tmp_path / "." / ".env") == {"NAME": "original"}
    assert reads == [path.resolve()]


def test_dotenv_changes_and_atomic_replacement_invalidate_cache(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NAME=first\n", encoding="utf-8")
    assert backend._read_dotenv(path) == {"NAME": "first"}
    stamp = path.stat().st_mtime_ns
    path.write_text("NAME=other\n", encoding="utf-8")
    os.utime(path, ns=(stamp + 1_000_000, stamp + 1_000_000))
    assert backend._read_dotenv(path) == {"NAME": "other"}
    replacement = tmp_path / "replacement.env"
    replacement.write_text("NAME=third\n", encoding="utf-8")
    stamp = path.stat().st_mtime_ns
    os.utime(replacement, ns=(stamp, stamp))
    replacement.replace(path)
    assert backend._read_dotenv(path) == {"NAME": "third"}
    path.unlink()
    assert backend._read_dotenv(path) == {}
    path.write_text("NAME=recreated\n", encoding="utf-8")
    assert backend._read_dotenv(path) == {"NAME": "recreated"}


def test_size_change_refreshes_when_timestamp_is_preserved(tmp_path):
    path = tmp_path / ".env"
    path.write_text("NAME=first\n", encoding="utf-8")
    assert backend._read_dotenv(path) == {"NAME": "first"}
    stamp = path.stat().st_mtime_ns
    path.write_text("NAME=longer value\n", encoding="utf-8")
    os.utime(path, ns=(stamp, stamp))
    assert backend._read_dotenv(path) == {"NAME": "longer value"}


def test_transient_read_failure_is_not_cached(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("NAME=recovered\n", encoding="utf-8")
    original_read = Path.read_text
    with monkeypatch.context() as temporary:
        temporary.setattr(Path, "read_text", Mock(side_effect=PermissionError("Synthetic locked file")))
        assert backend._read_dotenv(path) == {}
    assert Path.read_text is original_read
    assert backend._read_dotenv(path) == {"NAME": "recovered"}


def test_dotenv_cache_is_bounded_and_separates_paths(tmp_path):
    for index in range(7):
        path = tmp_path / str(index) / ".env"
        path.parent.mkdir()
        path.write_text(f"NAME=synthetic-{index}\n", encoding="utf-8")
        assert backend._read_dotenv(path) == {"NAME": f"synthetic-{index}"}
    assert backend._parse_dotenv.cache_info().currsize == 4


def test_configuration_environment_and_secret_precedence_remain_live(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, "ROOT", tmp_path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    secrets = {"SUPABASE_URL": "https://secrets.example.test", "SUPABASE_PUBLISHABLE_KEY": "synthetic-secret-source"}
    monkeypatch.setattr(backend, "st", SimpleNamespace(secrets=secrets))
    path = tmp_path / ".env"
    path.write_text("SUPABASE_URL=https://file.example.test/\nSUPABASE_PUBLISHABLE_KEY=synthetic-file-source\n", encoding="utf-8")
    assert backend.configuration() == ("https://file.example.test", "synthetic-file-source")
    monkeypatch.setenv("SUPABASE_URL", "https://environment.example.test/")
    assert backend.configuration()[0] == "https://environment.example.test"
    monkeypatch.delenv("SUPABASE_URL")
    assert backend.configuration()[0] == "https://file.example.test"
    path.unlink()
    assert backend.configuration() == ("https://secrets.example.test", "synthetic-secret-source")
    secrets["SUPABASE_URL"] = "https://changed-secrets.example.test/"
    assert backend.configuration()[0] == "https://changed-secrets.example.test"


def test_worker_configuration_does_not_read_local_settings(monkeypatch):
    reader = Mock(side_effect=AssertionError("Worker configuration must use its captured settings"))
    monkeypatch.setattr(backend, "_read_dotenv", reader)
    token = backend._worker_state.set({"_configuration": ("https://worker.example.test", "synthetic-worker")})
    try:
        assert backend.configuration() == ("https://worker.example.test", "synthetic-worker")
    finally:
        backend._worker_state.reset(token)
    reader.assert_not_called()
