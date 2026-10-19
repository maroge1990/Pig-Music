import asyncio
import json

from fastapi.testclient import TestClient

from server.app import create_app
from server.downloader import Downloader
from server.runtime import start_engine
from server.store import Store


def test_missing_mount_keeps_ui_available_and_no_nas_paths_created(
    tmp_path, monkeypatch
):
    data = tmp_path / "data"
    data.mkdir()
    nas = tmp_path / "absent-nas"
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(nas))
    monkeypatch.setenv("PIG_MUSIC_DOWNLOAD_ROOT", str(nas / ".pig-music-work"))
    (data / "library-export.json").write_text(json.dumps({"library_id": "expected"}))
    assert start_engine(data) == (None, None)
    with TestClient(create_app(data)) as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ok" and health["storage_available"] is False
        assert client.get("/api/v1/admin/library").status_code == 200
        assert not nas.exists()


def test_waiting_job_resumes_only_after_correct_marker_returns(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    nas = tmp_path / "nas"
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(nas))
    monkeypatch.setenv("PIG_MUSIC_DOWNLOAD_ROOT", str(nas / ".pig-music-work"))
    (data / "library-export.json").write_text(json.dumps({"library_id": "expected"}))
    store = Store(data)
    worker = Downloader(store, providers={})
    assert not nas.exists()
    nas.mkdir()
    (nas / ".pig-music-library.json").write_text(json.dumps({"library_id": "wrong"}))
    import pytest

    with pytest.raises(ValueError):
        worker.prepare_storage()
    assert not (nas / ".pig-music-work").exists()
    (nas / ".pig-music-library.json").write_text(json.dumps({"library_id": "expected"}))
    worker.prepare_storage()
    assert worker.staging.is_dir() and worker.library_root.is_dir()
