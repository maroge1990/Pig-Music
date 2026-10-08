import json

from fastapi.testclient import TestClient

from server.catalogue import Catalogue
from server.playlists import Playlists
from server.remote import RemoteAudio
from test_personal_libraries import household
from test_catalogue import ARTIST, RELEASE, OTHER, fixture_release, release_tracks


def client_for(app, token):
    return TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    )


def test_album_request_preserves_year_and_edition(tmp_path, monkeypatch):
    app, _, _, token, _ = household(tmp_path, monkeypatch)
    track = release_tracks(fixture_release())[0]
    # The catalogue's numeric year was rejected before album requests used songBody.
    with client_for(app, token) as client:
        assert (
            client.post("/api/v1/requests", json={"tracks": [track]}).status_code == 422
        )
        track["year"] = str(track["year"])
        response = client.post("/api/v1/requests", json={"tracks": [track]})
        assert response.status_code == 200, response.text
        item = app.state.store.queue()["items"][0]
        assert item["year"] == "2020"
        assert item["musicbrainz_release_id"] == RELEASE
        assert item["album"] == "Live at Home"


def test_clear_downloads_preserves_active_shared_jobs_and_library(
    tmp_path, monkeypatch
):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    store = app.state.store
    with store.connect() as conn:
        for status in [
            "completed",
            "failed",
            "cancelled",
            "downloading",
            "importing",
            "waiting_for_sources",
        ]:
            conn.execute(
                "INSERT INTO queue(id,payload,status) VALUES (?,?,?)",
                (
                    status,
                    json.dumps({"title": status, "requested_by": [owner, member]}),
                    status,
                ),
            )
    before = store.user_libraries.summary(owner)["stats"]
    with client_for(app, token) as client:
        assert client.delete("/api/v1/requests").json() == {"cleared": 3}
        assert {i["id"] for i in client.get("/api/v1/requests").json()["items"]} == {
            "downloading",
            "importing",
            "waiting_for_sources",
        }
        assert client.delete("/api/v1/requests").json() == {"cleared": 0}
    assert store.user_libraries.queue(owner)["total"] == 6
    assert store.user_libraries.summary(owner)["stats"] == before
    assert len(store.queue()["items"]) == 6


def test_saved_artist_reuses_identity_and_scopes_access(tmp_path, monkeypatch):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    store = app.state.store
    artist = store.user_libraries.projection(owner)["artists"][0]
    store.write_document(
        "library-artist:" + artist["id"], {"id": ARTIST, "name": artist["name"]}
    )

    async def unexpected(*args, **kwargs):
        raise AssertionError("Known identity must not search names again")

    monkeypatch.setattr(Catalogue, "get", unexpected)
    with client_for(app, token) as client:
        path = "/api/v1/catalogue/library-artists/" + artist["id"]
        assert client.get(path).status_code == 404
        store.user_libraries.add(member, [track["id"]])
        assert client.get(path).json() == {"id": ARTIST, "name": artist["name"]}


def test_namesake_artist_resolved_by_owned_album_credits(tmp_path, monkeypatch):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    store = app.state.store
    store.user_libraries.add(member, [track["id"]])
    artist = store.user_libraries.projection(member)["artists"][0]

    async def metadata(self, client, path, **params):
        if path == "artist/":
            return {
                "count": 2,
                "artists": [
                    {"id": ARTIST, "name": "Artist"},
                    {"id": OTHER, "name": "Artist"},
                ],
            }
        assert path == "release-group/"
        return {
            "count": 1,
            "release-groups": [
                {
                    "title": "Studio",
                    "artist-credit": [{"artist": {"id": ARTIST, "name": "Artist"}}],
                }
            ],
        }

    monkeypatch.setattr(Catalogue, "get", metadata)
    with client_for(app, token) as client:
        assert client.get(
            "/api/v1/catalogue/library-artists/" + artist["id"]
        ).json() == {"id": ARTIST, "name": "Artist"}


def test_ambiguous_album_credits_still_require_choice(tmp_path, monkeypatch):
    app, _, member, token, track = household(tmp_path, monkeypatch)
    store = app.state.store
    store.user_libraries.add(member, [track["id"]])
    artist = store.user_libraries.projection(member)["artists"][0]

    async def metadata(self, client, path, **params):
        namesakes = [{"id": ARTIST, "name": "Artist"}, {"id": OTHER, "name": "Artist"}]
        return {
            "count": 2,
            "artists": namesakes,
            "release-groups": [
                {"title": "Studio", "artist-credit": [{"artist": a}]} for a in namesakes
            ],
        }

    monkeypatch.setattr(Catalogue, "get", metadata)
    with client_for(app, token) as client:
        assert (
            client.get("/api/v1/catalogue/library-artists/" + artist["id"]).status_code
            == 409
        )


def test_cloud_playlist_remote_metadata_does_not_download(tmp_path, monkeypatch):
    app, _, member, token, _ = household(tmp_path, monkeypatch)
    store = app.state.store
    (tmp_path / "media-settings.json").write_text(json.dumps({"remote_playback": True}))
    calls = []

    async def resolve(self, client, track):
        calls.append(track)
        return "https://example.saavncdn.com/song.mp3"

    monkeypatch.setattr(RemoteAudio, "resolve", resolve)
    track = {
        "title": "Cloud song",
        "artist": "Artist",
        "album": "Remote album",
        "duration": 201,
    }
    playlist = Playlists(store, member).create("Mixed")
    Playlists(store, member).add(playlist["id"], track)
    with client_for(app, token) as client:
        response = client.post("/api/v1/remote-playback", json=track)
        assert response.status_code == 200, response.text
        assert response.json()["url"].endswith("/song.mp3")
        assert calls[0]["album"] == "Remote album"
        assert store.queue()["items"] == []
        (tmp_path / "media-settings.json").write_text(
            json.dumps({"remote_playback": False})
        )
        assert client.post("/api/v1/remote-playback", json=track).status_code == 409


def test_saved_release_credit_resolves_madonna_without_name_search(
    tmp_path, monkeypatch
):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    track.update(
        artist="Madonna",
        album_artist="Madonna",
        album="Like a Prayer",
        musicbrainz_release_id=RELEASE,
    )
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    store = app.state.store
    store.refresh_library()
    store.user_libraries.add(member, [track["id"]])
    artist = store.user_libraries.projection(member)["artists"][0]

    async def metadata(self, client, path, **params):
        assert path == "release/" + RELEASE
        assert params["inc"] == "artist-credits"
        return {
            "id": RELEASE,
            "artist-credit": [{"artist": {"id": ARTIST, "name": "Madonna"}}],
        }

    monkeypatch.setattr(Catalogue, "get", metadata)
    with client_for(app, token) as client:
        assert client.get(
            "/api/v1/catalogue/library-artists/" + artist["id"]
        ).json() == {"id": ARTIST, "name": "Madonna"}
