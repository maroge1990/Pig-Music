"""A live/remix/demo release's songs are other recordings than the studio
ones, from catalogue presence through the request a client sends back."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.auth import Auth
from server.store import Store

RELEASE = "33333333-3333-4333-8333-333333333333"
GROUP = "22222222-2222-4222-8222-222222222222"
RECORDING = "44444444-4444-4444-8444-444444444444"


def release(kind):
    return {
        "id": RELEASE,
        "title": "Concert Night",
        "date": "2001",
        "artist-credit": [{"name": "Artist", "joinphrase": ""}],
        "release-group": {
            "id": GROUP,
            "title": "Concert Night",
            "primary-type": "Album",
            "secondary-types": [kind],
        },
        "media": [
            {
                "position": 1,
                "tracks": [
                    {
                        "id": "t1",
                        "position": 1,
                        "title": "Song",
                        "length": 200000,
                        "recording": {"id": RECORDING, "title": "Song"},
                    }
                ],
            }
        ],
    }


def app_with_studio_song(tmp_path, monkeypatch):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    studio = {
        "id": "studio",
        "title": "Song",
        "artist": "Artist",
        "album": "Studio Album",
        "album_artist": "Artist",
        "duration": 200,
        "disc_number": 1,
        "track_number": 1,
    }
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [studio]}))
    auth = Auth(Store(tmp_path))
    auth.create_owner("mark", "release kinds fixture password")
    token = auth.login(
        "mark", "release kinds fixture password", "device", "phone", "ios", "f"
    )["token"]
    return create_app(tmp_path), {"Authorization": "Bearer " + token}


@pytest.mark.parametrize(
    "kind, recording_kind", [("Live", "live"), ("Remix", "remix"), ("Demo", "demo")]
)
def test_a_live_remix_or_demo_release_is_not_the_studio_song(
    tmp_path, monkeypatch, kind, recording_kind
):
    def transport(request):
        if request.url.path.endswith("/release"):
            return httpx.Response(
                200, json={"release-count": 1, "releases": [release(kind)]}
            )
        return httpx.Response(200, json=release(kind))

    app, headers = app_with_studio_song(tmp_path, monkeypatch)
    with TestClient(app, base_url="https://private.ts.net", headers=headers) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        (track,) = client.get(f"/api/v1/catalogue/releases/{RELEASE}").json()["tracks"]
        assert track["server_state"] == "not_in_library"
        assert track["recording_kind"] == [recording_kind]
        # The web marks rows from the library lookup: not the studio file.
        found = client.post(
            "/api/v1/library/lookup",
            json={
                "songs": [
                    {k: track[k] for k in ("title", "artist", "duration")}
                    | {"recording_kind": track["recording_kind"]}
                ]
            },
        ).json()["tracks"]
        assert found == [None]
        fields = (
            "title",
            "artist",
            "album",
            "album_artist",
            "duration",
            "track_number",
            "disc_number",
            "musicbrainz_release_id",
            "musicbrainz_recording_id",
        )
        body = {k: track[k] for k in fields} | {"year": "2001"}
        # A client that sends the kind, and one that doesn't (an older app):
        # the server reconstructs it from the release it served.
        for sent in (
            {**body, "recording_kind": track["recording_kind"]},
            {**body, "album": "Concert Night"},
        ):
            result = client.post("/api/v1/requests", json={"tracks": [sent]}).json()
            assert result["skipped"] == 0
        (job,) = app.state.store.queue()["items"]
        assert job["recording_kind"] == [recording_kind]
        app.state.http = original


def test_a_studio_release_still_finds_the_studio_song(tmp_path, monkeypatch):
    studio = release("Live")
    studio["release-group"]["secondary-types"] = []
    studio["title"] = studio["release-group"]["title"] = "Deluxe Album"

    def transport(request):
        return httpx.Response(200, json=studio)

    app, headers = app_with_studio_song(tmp_path, monkeypatch)
    with TestClient(app, base_url="https://private.ts.net", headers=headers) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        (track,) = client.get(f"/api/v1/catalogue/releases/{RELEASE}").json()["tracks"]
        assert track["server_state"] == "in_library"
        assert track["recording_kind"] == []
        app.state.http = original
