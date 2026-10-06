import json

from server.catalogue import Catalogue
from server.library import build_library, build_migration
from server.matching import LibraryIndex
from server.playlists import Playlists
from server.recovery import Recovery
from server.store import Store


def song(**extra):
    return {
        "id": "saved",
        "artist": "Artist",
        "album_artist": "Artist",
        "title": "Song",
        "album": "Album",
        "duration": 100,
        "year": 2020,
        "disc_number": 1,
        "track_number": 1,
        "musicbrainz_release_id": "edition-a",
        "musicbrainz_recording_id": "recording-a",
        **extra,
    }


def test_all_consumers_agree_on_conflicting_editions_and_recordings(tmp_path):
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [song()]}))
    store = Store(tmp_path)
    playlists = Playlists(store)
    for requested in (
        song(musicbrainz_release_id="edition-b"),
        song(musicbrainz_recording_id="recording-b"),
    ):
        migration = build_migration({"tracks": [requested]}, store.library, set())
        assert migration["albums"][0]["tracks"][0]["status"] == "review"
        assert Catalogue(store).presence([dict(requested)])[0]["status"] == "review"
        playlist = playlists.create("Test")
        assert (
            playlists.add(playlist["id"], requested)["entries"][0]["status"] == "review"
        )


def test_duplicate_unknown_bytes_require_review_and_identical_bytes_match():
    tracks = [song(), song(id="second")]
    assert (
        LibraryIndex(build_library({"tracks": tracks})).match(song()).kind == "conflict"
    )
    tracks = [{**t, "sha256": "same-bytes"} for t in tracks]
    assert (
        LibraryIndex(build_library({"tracks": tracks})).match(song()).status
        == "downloaded"
    )


def test_library_revision_is_content_based_across_restarts(tmp_path):
    snapshot = tmp_path / "library-snapshot.json"
    snapshot.write_text(json.dumps({"tracks": [song()]}))
    store = Store(tmp_path)
    original = store.library_revision
    store.refresh_library()
    assert store.library_revision == original
    assert Store(tmp_path).library_revision == original
    snapshot.write_text(json.dumps({"tracks": [song(title="Changed title")]}))
    assert Store(tmp_path).library_revision != original


def test_edition_anchor_preserves_links_and_preferences_after_restart(tmp_path):
    path = tmp_path / "library-snapshot.json"
    path.write_text(json.dumps({"tracks": [song()]}))
    store = Store(tmp_path)
    original = store.library["albums"][0]["id"]
    store.categorise(original, "soundtrack")
    store.quality_override("album", original, "lossless")
    path.write_text(
        json.dumps(
            {"tracks": [song(id="second", musicbrainz_release_id="edition-b"), song()]}
        )
    )
    restarted = Store(tmp_path)
    assert len(restarted.library["albums"]) == 2
    first = next(a for a in restarted.library["albums"] if a["id"] == original)
    assert first["tracks"][0]["id"] == "saved" and first["category"] == "soundtrack"
    assert restarted.quality_policy(song())["preferred"] == "lossless"
    # A catalogue reference may reuse an ID but cannot inherit another edition's override.
    assert (
        restarted.quality_policy(song(musicbrainz_release_id="edition-b"))["preferred"]
        == "mp3_320"
    )
    assert (
        restarted.quality_policy(song(id="second", musicbrainz_release_id="edition-b"))[
            "preferred"
        ]
        == "mp3_320"
    )


def test_removal_does_not_cancel_other_edition_and_exclusions_restore_independently(
    tmp_path, monkeypatch
):
    root = tmp_path / "music"
    root.mkdir()
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(root))
    tracks = [
        song(relative_path="a.mp3"),
        song(id="second", musicbrainz_release_id="edition-b", relative_path="b.mp3"),
    ]
    for track in tracks:
        (root / track["relative_path"]).write_bytes(b"original " + track["id"].encode())
    data = tmp_path / "data"
    data.mkdir()
    (data / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    store = Store(data)
    store.submit_catalogue([{**t, "status": "missing"} for t in tracks])
    recovery = Recovery(store)
    first = recovery.remove("saved")
    states = {t["musicbrainz_release_id"]: t["status"] for t in store.queue()["items"]}
    assert states == {"edition-a": "cancelled", "edition-b": "waiting_for_sources"}
    recovery.remove("second")
    recovery.restore(first["id"])
    assert store.submit_catalogue([{**tracks[1], "status": "missing"}])["skipped"] == 1
