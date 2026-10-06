import json
from fastapi.testclient import TestClient
from server.app import create_app


def test_batched_membership_is_read_only_and_uses_snapshot_index(tmp_path):
    track = {
        "id": "song",
        "title": "Song",
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Artist",
    }
    snapshot = tmp_path / "library-snapshot.json"
    snapshot.write_text(json.dumps({"tracks": [track]}))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        assert client.post(
            "/api/favourites", json={"saved_id": "song", "favourite": True}
        ).json()["favourited"]
        # Once ingested, per-song queries do not reopen or parse the snapshot.
        snapshot.write_text("invalid JSON")
        result = client.post(
            "/api/membership",
            json={
                "songs": [
                    {"saved_id": "song"},
                    {"playlist_id": "pig-favourites", "position": 0},
                    {"saved_id": "missing"},
                ]
            },
        )
        assert result.status_code == 200
        assert [s["favourited"] for s in result.json()["songs"]] == [True, True, False]
        assert client.get("/api/queue").json()["items"] == []
        assert client.get("/api/playlists/pig-favourites").json()["track_count"] == 1
