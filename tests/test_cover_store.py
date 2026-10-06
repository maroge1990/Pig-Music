import base64
import hashlib
import io
import json
import os
import time

import pytest
import ijson
from PIL import Image

from server.cover_store import CoverStore, WEEK
from server.scanner import LibraryScanner
from server.store import Store


def image_bytes(colour="red"):
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(stream, "PNG")
    return stream.getvalue()


def track(id="one", release=None):
    return {
        "id": id,
        "title": id,
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Album",
        "relative_path": id + ".mp3",
        **({"musicbrainz_release_id": release} if release else {}),
    }


def legacy(path, tracks=None, cover=None):
    payload = {
        "schema_version": 2,
        "tracks": tracks or [track()],
        "covers": {
            "Artist\x1fAlbum": {
                "data": base64.b64encode(cover or image_bytes()).decode()
            }
        },
        "source": "fixture",
        "read_failures": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path.read_bytes()


def test_legacy_migration_preserves_metadata_and_is_idempotent(tmp_path):
    path = tmp_path / "library-snapshot.json"
    original = legacy(path)
    store = Store(tmp_path)
    migrated = json.loads(path.read_text())
    assert "covers" not in migrated and migrated["schema_version"] == 3
    current = migrated["tracks"][0]
    assert {
        k: v for k, v in current.items() if k not in {"cover_sha", "cover_rescan"}
    } == track()
    assert current["cover_rescan"] is True
    cover = store.covers.path(current["cover_sha"])
    assert hashlib.sha256(cover.read_bytes()).hexdigest() == current["cover_sha"]
    assert (tmp_path / "library-snapshot.pre-v3.json").read_bytes() == original
    before = path.read_bytes()
    album_id = store.library["albums"][0]["id"]
    assert Store(tmp_path).library["albums"][0]["id"] == album_id
    assert path.read_bytes() == before
    assert len(list(store.cover_dir.glob("*.jpg"))) == 1


def test_migration_handles_bom_covers_first_and_dotted_keys(tmp_path):
    payload = {
        "covers": {
            "Artist.Name\x1fAlbum.Live": {
                "data": base64.b64encode(image_bytes()).decode()
            }
        },
        "tracks": [
            {
                **track(),
                "artist": "Artist.Name",
                "album_artist": "Artist.Name",
                "album": "Album.Live",
            }
        ],
        "schema_version": 1,
    }
    path = tmp_path / "library-snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig")
    assert Store(tmp_path).library["albums"][0]["cover_sha"]


@pytest.mark.parametrize("failure", ["image", "json", "write"])
def test_failed_migration_retains_original_snapshot(tmp_path, monkeypatch, failure):
    path = tmp_path / "library-snapshot.json"
    original = legacy(path, cover=b"invalid" if failure == "image" else None)
    if failure == "json":
        original = original[:-1]
        path.write_bytes(original)
    if failure == "write":

        def broken(*args):
            raise OSError("fixture disk full")

        monkeypatch.setattr(CoverStore, "write_snapshot", broken)
    with pytest.raises((ValueError, OSError, ijson.JSONError)):
        Store(tmp_path)
    assert path.read_bytes() == original


def test_normalised_cover_deduplication_and_hash_validation(tmp_path):
    covers = CoverStore(tmp_path)
    sha = covers.save(image_bytes())
    assert covers.save(image_bytes()) == sha
    assert len(list(tmp_path.glob("*.jpg"))) == 1
    assert covers.path("../outside") is None
    assert covers.path(sha.upper()) is None
    with pytest.raises(ValueError):
        covers.save(b"a" * 5_000_001)


def fake_scanner(tmp_path, monkeypatch, images):
    root = tmp_path / "music"
    root.mkdir()
    for id in images:
        (root / (id + ".mp3")).write_bytes(b"audio")
    calls = []

    def inspect(path, relative):
        calls.append(relative)
        stat = path.stat()
        return {
            **track(path.stem, path.stem),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "available": True,
        }, images[path.stem]

    monkeypatch.setattr("server.scanner.inspect_file", inspect)
    store = Store(tmp_path / "data")
    return store, root, LibraryScanner(store, root), calls


def test_scan_separates_editions_and_updates_embedded_art(tmp_path, monkeypatch):
    images = {"standard": image_bytes("red"), "deluxe": image_bytes("blue")}
    store, root, scanner, calls = fake_scanner(tmp_path, monkeypatch, images)
    assert scanner.run()["status"] == "completed"
    before = {a["id"]: a["cover_sha"] for a in store.library["albums"]}
    assert len(set(before.values())) == 2
    scanner.run()
    assert len(calls) == 2
    images["deluxe"] = image_bytes("green")
    (root / "deluxe.mp3").write_bytes(b"retagged fixture")
    assert scanner.run()["status"] == "completed"
    after = {a["id"]: a["cover_sha"] for a in store.library["albums"]}
    assert before.keys() == after.keys()
    assert sum(before[id] != after[id] for id in before) == 1
    assert (
        json.loads((store.directory / "library-snapshot.json").read_text())[
            "schema_version"
        ]
        == 3
    )
    assert '"data"' not in (store.directory / "library-snapshot.json").read_text()


def test_folder_art_changes_and_removal_without_audio_reinspection(
    tmp_path, monkeypatch
):
    store, root, scanner, calls = fake_scanner(tmp_path, monkeypatch, {"one": None})
    image = root / "cover.png"
    image.write_bytes(image_bytes("red"))
    scanner.run()
    first = store.library["albums"][0]["cover_sha"]
    image.write_bytes(image_bytes("blue"))
    stat = image.stat()
    os.utime(image, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    scanner.run()
    assert store.library["albums"][0]["cover_sha"] != first
    assert calls == ["one.mp3"]
    image.unlink()
    scanner.run()
    assert store.library["albums"][0]["cover_sha"] is None


def test_invalid_display_art_does_not_remove_audio_or_duplicate_track(
    tmp_path, monkeypatch
):
    images = {"one": image_bytes()}
    store, root, scanner, _ = fake_scanner(tmp_path, monkeypatch, images)
    scanner.run()
    images["one"] = b"broken image"
    (root / "one.mp3").write_bytes(b"changed audio")
    scanner.run()
    assert store.library["stats"]["tracks"] == 1
    assert store.library["albums"][0]["cover_sha"] is None
    assert scanner.status()["read_failures"] == 1


def test_prune_preserves_referenced_missing_recent_and_legacy_files(tmp_path):
    store = Store(tmp_path)
    retained = store.covers.save(image_bytes("red"))
    orphan = store.covers.save(image_bytes("blue"))
    recent = store.covers.save(image_bytes("green"))
    now = time.time()
    for sha in (retained, orphan):
        os.utime(store.covers.path(sha), (now - WEEK - 1, now - WEEK - 1))
    # Missing audio remains in the snapshot and still protects its artwork.
    CoverStore.write_snapshot(
        tmp_path / "library-snapshot.json",
        {"tracks": [{**track(), "available": False, "cover_sha": retained}]},
    )
    legacy_file = store.cover_dir / ("a" * 24 + ".jpg")
    legacy_file.write_bytes(b"old remote cache")
    with store.connect() as conn:
        for name, data in [
            ("missing-artwork:expired", {"retry_after": now - 1}),
            ("missing-artwork:valid", {"retry_after": now + 10}),
            ("catalogue:expired", {"time": now - 86401}),
            ("catalogue:valid", {"time": now}),
            ("other", {"time": 0}),
        ]:
            conn.execute("INSERT INTO documents VALUES (?,?)", (name, json.dumps(data)))
    result = store.prune_artwork(now)
    assert result == {"covers_removed": 1, "documents_removed": 2}
    assert store.covers.path(retained) and store.covers.path(recent)
    assert store.covers.path(orphan) is None and legacy_file.exists()
    assert store.read_document("other") == {"time": 0}


def test_quality_replacement_retains_same_edition_scanned_art(tmp_path):
    path = tmp_path / "library-snapshot.json"
    legacy(path, tracks=[track(release="edition")])
    store = Store(tmp_path)
    before = store.library["albums"][0]["cover_sha"]
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO acquired VALUES (?,?)",
            ("one", json.dumps(track(release="edition"))),
        )
    store.refresh_library()
    assert store.library["albums"][0]["cover_sha"] == before
    with store.connect() as conn:
        conn.execute(
            "UPDATE acquired SET payload=?",
            (json.dumps(track(release="different-edition")),),
        )
    store.refresh_library()
    assert store.library["albums"][0]["cover_sha"] is None
