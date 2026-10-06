import json
from server.store import Store
from server.scanner import LibraryScanner
from server.scanner import tag


def test_vorbis_rejects_mp4_aliases_without_failing_scan():
    from mutagen._vorbis import VCommentDict

    tags = VCommentDict()
    tags["album"] = ["Album"]
    assert tag(tags, "TCON", "genre", "\xa9gen") == ""
    assert tag(tags, "TALB", "album", "\xa9alb") == "Album"


def test_scan_is_incremental_read_only_and_missing_files_remain_visible(
    tmp_path, monkeypatch
):
    root = tmp_path / "music"
    root.mkdir()
    path = root / "song.mp3"
    path.write_bytes(b"fixture")
    (root / ".pig-music-organise-incomplete.mp3").write_bytes(b"partial transfer")
    calls = []

    def inspect(path, relative):
        calls.append(relative)
        stat = path.stat()
        return {
            "id": "song",
            "title": "One",
            "artist": "Artist",
            "album_artist": "Artist",
            "album": "Album",
            "relative_path": relative,
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "available": True,
        }, None

    monkeypatch.setattr("server.scanner.inspect_file", inspect)
    store = Store(tmp_path / "data")
    scanner = LibraryScanner(store, root)
    assert scanner.run()["status"] == "completed"
    assert path.read_bytes() == b"fixture"
    scanner.run()
    assert calls == ["song.mp3"]
    second = root / "second.mp3"
    second.write_bytes(b"fixture2")
    path.unlink()
    scanner.run()
    snapshot = json.loads((store.directory / "library-snapshot.json").read_text())
    assert (
        next(t for t in snapshot["tracks"] if t["relative_path"] == "song.mp3")[
            "available"
        ]
        is False
    )
    assert scanner.status()["missing"] == 1


def test_unavailable_mount_or_empty_rescan_retains_previous_index(tmp_path):
    store = Store(tmp_path / "data")
    previous = json.dumps(
        {
            "tracks": [
                {
                    "id": "x",
                    "title": "Song",
                    "artist": "Artist",
                    "relative_path": "x.mp3",
                }
            ]
        }
    )
    (store.directory / "library-snapshot.json").write_text(previous)
    root = tmp_path / "music"
    root.mkdir()
    assert LibraryScanner(store, root).run()["status"] == "failed"
    assert (store.directory / "library-snapshot.json").read_text() == previous
