import json
from fastapi.testclient import TestClient
from server.app import create_app


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
