import json
from fastapi.testclient import TestClient
from server.app import create_app
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


def test_saved_song_favourites_and_playlist_create_never_queue_downloads(tmp_path):
    track = {
        "id": "saved",
        "title": "Song",
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Album",
        "duration": 100,
    }
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    with TestClient(create_app(tmp_path)) as client:
        result = client.post("/api/favourites", json={"saved_id": "saved"}).json()
        assert result == {"favourited": False}
        assert client.get("/api/playlists").json() == []
        assert client.post(
            "/api/favourites", json={"saved_id": "saved", "favourite": True}
        ).json()["favourited"]
        p = client.post("/api/playlists", json={"name": "New playlist"}).json()
        assert (
            client.post(
                "/api/playlists/" + p["id"] + "/songs", json={"saved_id": "saved"}
            ).json()["track_count"]
            == 1
        )
        assert client.get("/api/queue").json()["items"] == []
        assert (
            client.post(
                "/api/favourites", json={"relative_path": "/etc/passwd"}
            ).status_code
            == 400
        )


def test_batched_membership_endpoint_is_removed(tmp_path):
    track = {
        "id": "song",
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Artist",
    }
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.post(
            "/api/favourites", json={"saved_id": "song", "favourite": True}
        ).json()["favourited"]
        result = client.post("/api/membership", json={"songs": [{"saved_id": "song"}]})
        assert result.status_code in {404, 405}
        assert client.get("/api/queue").json()["items"] == []
        assert client.get("/api/playlists/pig-favourites").json()["track_count"] == 1
