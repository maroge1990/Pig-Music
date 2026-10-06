import json
import pytest
from server.store import Store
from server.recovery import Recovery


def setup(tmp_path, monkeypatch):
    root = tmp_path / "music"
    root.mkdir()
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(root))
    path = root / "Artist" / "Album" / "Song.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"original music")
    track = {
        "id": "saved",
        "title": "Song",
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Album",
        "relative_path": "Artist/Album/Song.mp3",
        "duration": 100,
        "year": 2020,
        "disc_number": 1,
        "track_number": 1,
    }
    data = tmp_path / "data"
    data.mkdir()
    (data / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    store = Store(data)
    return store, root, path, track


def test_remove_restore_and_monitor_exclusion(tmp_path, monkeypatch):
    store, root, path, track = setup(tmp_path, monkeypatch)
    recovery = Recovery(store)
    record = recovery.remove("saved")
    assert not path.exists() and not store.library["albums"]
    result = store.submit_catalogue([{**track, "status": "missing"}])
    assert result["skipped"] == 1 and result["created"] == 0
    recovery.restore(record["id"])
    assert path.read_bytes() == b"original music" and store.library["albums"]
    assert store.submit_catalogue([{**track, "status": "missing"}])["created"] == 1


def test_restore_refuses_collision_and_keeps_recoverable_file(tmp_path, monkeypatch):
    store, root, path, track = setup(tmp_path, monkeypatch)
    recovery = Recovery(store)
    record = recovery.remove("saved")
    path.write_bytes(b"another file")
    with pytest.raises(ValueError):
        recovery.restore(record["id"])
    assert path.read_bytes() == b"another file" and (root / record["trash"]).exists()


def test_recovery_finishes_interrupted_removal(tmp_path, monkeypatch):
    store, root, path, track = setup(tmp_path, monkeypatch)
    recovery = Recovery(store)
    record = recovery.remove("saved")
    record["status"] = "removing"
    recovery.save("removed:" + record["id"], record)
    Recovery(Store(store.directory)).recover()
    assert recovery.list()[0]["status"] == "removed"


def test_removal_keeps_completed_download_history(tmp_path, monkeypatch):
    store, root, path, track = setup(tmp_path, monkeypatch)
    store.submit_catalogue([{**track, "status": "missing"}])
    with store.connect() as c:
        c.execute("UPDATE queue SET status='completed'")
    Recovery(store).remove("saved")
    assert store.queue()["items"][0]["status"] == "completed"


def test_removal_rejects_changed_library_mount(tmp_path, monkeypatch):
    store, root, path, track = setup(tmp_path, monkeypatch)
    (store.directory / "library-export.json").write_text(
        json.dumps({"library_id": "expected"})
    )
    with pytest.raises(ValueError):
        Recovery(store).remove("saved")
    assert path.read_bytes() == b"original music" and not Recovery(store).list()
