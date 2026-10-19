import json
from fastapi.testclient import TestClient
from server.app import create_app
from server.auth import Auth
from server.store import Store
from server.playlists import Playlists


def song(title="Song", album="Album"):
    return {
        "id": "one",
        "title": title,
        "artist": "Artist",
        "album_artist": "Artist",
        "album": album,
        "duration": 100,
    }


def test_created_playlist_survives_restart_and_add_is_idempotent(tmp_path):
    p = Playlists(Store(tmp_path))
    identity = p.create("Household")["id"]
    p.add(identity, song())
    p.add(identity, song())
    assert len(Playlists(Store(tmp_path)).raw(identity)["tracks"]) == 1
    assert not p.store.queue()["items"]


def test_favourites_do_not_download_and_preserve_release_context(tmp_path):
    p = Playlists(Store(tmp_path))
    p.favourite(song(), True)
    p.favourite(song(album="Live recording"), True)
    assert p.favourite(song())["favourited"]
    assert len(p.raw("pig-favourites")["tracks"]) == 2 and not p.store.queue()["items"]
    p.favourite(song(), False)
    assert (
        not p.favourite(song())["favourited"]
        and p.favourite(song(album="Live recording"))["favourited"]
    )


def test_tag_only_song_and_discovered_song_share_membership_without_merging_editions(
    tmp_path,
):
    p = Playlists(Store(tmp_path))
    identity = p.create("Listening")["id"]
    tagged = song()
    discovered = {
        **tagged,
        "musicbrainz_release_id": "edition-one",
        "musicbrainz_recording_id": "recording-one",
    }
    p.add(identity, tagged)
    p.add(identity, discovered)
    assert len(p.raw(identity)["tracks"]) == 1
    p.favourite(discovered, True)
    assert p.favourite(tagged)["favourited"]
    assert not p.favourite({**discovered, "musicbrainz_release_id": "edition-two"})[
        "favourited"
    ]
    p.favourite(tagged, False)
    assert not p.raw("pig-favourites")["tracks"]


# HTTP layer


def signed_in(tmp_path, monkeypatch, track):
    """The owner on the versioned API, with one household song."""
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    auth = Auth(Store(tmp_path))
    auth.create_owner("mark", "membership fixture password")
    token = auth.login(
        "mark", "membership fixture password", "device", "phone", "ios", "f"
    )["token"]
    return TestClient(
        create_app(tmp_path),
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    )


SONG = {"title": "Song", "artist": "Artist", "album": "Album", "album_artist": "Artist"}


def test_saved_song_favourites_and_playlist_create_never_queue_downloads(
    tmp_path, monkeypatch
):
    track = {**SONG, "id": "saved", "duration": 100}
    with signed_in(tmp_path, monkeypatch, track) as client:
        result = client.post("/api/v1/favourites", json={"track": SONG}).json()
        assert result["favourited"] is False
        assert client.post(
            "/api/v1/favourites", json={"track": SONG, "favourite": True}
        ).json()["favourited"]
        p = client.post("/api/v1/playlists", json={"name": "New playlist"}).json()
        added = client.post(f"/api/v1/playlists/{p['id']}/songs", json=SONG).json()
        assert added["track_count"] == 1
        assert client.get("/api/v1/admin/queue").json()["items"] == []
        # Only song identity is accepted: no file paths.
        assert (
            client.post(
                "/api/v1/favourites", json={"track": {"relative_path": "/etc/passwd"}}
            ).status_code
            == 422
        )


def test_batched_membership_endpoint_is_removed(tmp_path, monkeypatch):
    with signed_in(tmp_path, monkeypatch, {**SONG, "id": "song"}) as client:
        assert client.post(
            "/api/v1/favourites", json={"track": SONG, "favourite": True}
        ).json()["favourited"]
        result = client.post("/api/membership", json={"songs": [{"saved_id": "song"}]})
        assert result.status_code in {404, 405}
        assert client.get("/api/v1/admin/queue").json()["items"] == []
        favourites = next(
            p
            for p in client.get("/api/v1/playlists").json()["playlists"]
            if p["id"].startswith("pig-favourites")
        )
        assert favourites["track_count"] == 1
