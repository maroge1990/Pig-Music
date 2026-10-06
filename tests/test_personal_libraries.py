import json
import time

from fastapi.testclient import TestClient
import pytest

from server.playlists import Playlists
from tests.test_playlists import export
from tests.test_security import protected, PASSWORD


def household(tmp_path, monkeypatch):
    track = {
        "id": "song",
        "title": "One",
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Studio",
        "duration": 200,
        "relative_path": "private/song.mp3",
        "absolute_path": "/nas/private/song.mp3",
    }
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    app, owner = protected(tmp_path, monkeypatch)
    code = app.state.auth.setup_code(owner, "member", "Member")
    member = app.state.auth.activate(code["code"], PASSWORD, "fixture")
    with app.state.store.connect() as conn:
        member_id = conn.execute(
            "SELECT id FROM users WHERE username='member'"
        ).fetchone()[0]
    token = app.state.auth.login(
        "member", PASSWORD, "device", "phone", "ios", "fixture"
    )["token"]
    return app, owner, member_id, token, track


def test_private_imports_favourites_and_shared_membership(tmp_path, monkeypatch):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    store = app.state.store
    assert store.user_libraries.summary(owner)["stats"]["tracks"] == 1
    assert store.user_libraries.summary(member)["stats"]["tracks"] == 0
    store.user_libraries.import_playlists(owner, export())
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        assert client.post("/api/v1/imports/apple", content=export()).status_code == 200
        personal = client.get("/api/v1/playlists").json()["playlists"]
        assert len(personal) == 1
        owner_playlist = Playlists(store, owner).list()[0]["id"]
        assert client.get("/api/v1/playlists/" + owner_playlist).status_code == 404
        assert (
            client.post(
                "/api/v1/playlists/" + owner_playlist + "/songs",
                json={
                    k: track[k]
                    for k in ("title", "artist", "album", "album_artist", "duration")
                },
            ).status_code
            == 404
        )
        assert store.queue()["items"] == []
        result = client.post(
            "/api/v1/requests",
            json={
                "tracks": [
                    {
                        k: track[k]
                        for k in (
                            "title",
                            "artist",
                            "album",
                            "album_artist",
                            "duration",
                        )
                    }
                ]
            },
        )
        assert result.status_code == 200, result.text
        assert store.queue()["items"] == []
        assert client.get("/api/v1/library").json()["stats"]["tracks"] == 1
        response = client.get("/api/v1/playlists/" + personal[0]["id"])
        assert (
            "relative_path" not in response.text
            and "absolute_path" not in response.text
        )
        new = client.post("/api/v1/playlists", json={"name": "Private"}).json()
        response = client.post(
            "/api/v1/playlists/" + new["id"] + "/songs",
            json={
                k: track[k]
                for k in ("title", "artist", "album", "album_artist", "duration")
            },
        )
        assert response.status_code == 200 and "relative_path" not in response.text
        assert (
            client.post(
                "/api/v1/favourites",
                json={
                    "track": {"title": "One", "artist": "Artist", "album": "Studio"},
                    "favourite": True,
                },
            ).status_code
            == 200
        )
        assert Playlists(store, owner).favourite(track)["favourited"] is False


def test_shared_request_beneficiaries_and_atomic_history(tmp_path, monkeypatch):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    store = app.state.store
    missing = {
        **track,
        "title": "Missing",
        "album": "Other",
        "year": "",
        "disc_number": 1,
        "track_number": 1,
    }
    assert store.user_libraries.request(owner, [missing])["created"] == 1
    assert store.user_libraries.request(member, [missing])["existing"] == 1
    job = store.queue()["items"][0]
    assert set(job["requested_by"]) == {owner, member}
    assert "requested_by" not in store.user_libraries.queue(member)["items"][0]
    with store.connect() as conn:
        store._grant_request_membership(conn, json.dumps(job), "arrived")
    assert store.user_libraries.contains(member, "arrived")
    assert store.user_libraries.contains(owner, "arrived")
    store.user_libraries.add(member, ["song"])
    event = {
        "track_id": "song",
        "event_id": "event",
        "played_at": int(time.time()),
        "seconds": 10,
    }
    assert store.user_libraries.history(member, [event], "session")["recorded"] == 1
    assert store.user_libraries.history(member, [event], "session")["recorded"] == 0
    with pytest.raises(ValueError):
        store.user_libraries.history(
            member,
            [{**event, "event_id": "rollback"}, {**event, "track_id": "outside"}],
            "session",
        )
    with store.connect() as conn:
        assert conn.execute("SELECT count(*) FROM play_events").fetchone()[0] == 1


def test_owner_backfill_once_and_external_scan_stays_unassigned(tmp_path, monkeypatch):
    app, owner, member, _, track = household(tmp_path, monkeypatch)
    store = app.state.store
    baseline = store.user_libraries.projection(owner)["revision"]
    assert store.user_libraries.projection(owner)["revision"] == baseline
    added = {**track, "id": "external", "title": "External"}
    (tmp_path / "library-snapshot.json").write_text(
        json.dumps({"tracks": [track, added]})
    )
    store.refresh_library()
    assert not store.user_libraries.contains(owner, "external")
    assert not store.user_libraries.contains(member, "external")
    assert store.user_libraries.summary(owner)["stats"]["tracks"] == 1
