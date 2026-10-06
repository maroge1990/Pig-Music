import json
from fastapi.testclient import TestClient
from server.app import create_app


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
