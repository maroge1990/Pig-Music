import json

from fastapi.testclient import TestClient

from server.app import create_app
from server.auth import Auth
from server.catalogue import Catalogue, release_tracks
from server.store import Store
from test_catalogue import ARTIST, RELEASE, fixture_release


def member_client(tmp_path, monkeypatch, provider):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    track = release_tracks(fixture_release())[0]
    track.update(id="physical-file-id", available=True, path="/private/owner-only.mp3")
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    store = Store(tmp_path)
    auth = Auth(store)
    owner = auth.create_owner("mark", "conditional fixture password")
    tokens, ids = {}, {}
    for name in ("one", "two"):
        code = auth.setup_code(owner, name, name)
        ids[name] = auth.activate(code["code"], "conditional fixture password", "f")[
            "id"
        ]
        tokens[name] = auth.login(
            name, "conditional fixture password", "device", "phone", "ios", "f"
        )["token"]
    monkeypatch.setattr(Catalogue, "get", provider)
    app = create_app(tmp_path)
    return app, track, tokens, ids


def test_release_and_editions_answer_304_for_the_saved_etag(tmp_path, monkeypatch):
    async def provider(self, client, path, **params):
        if path == "release":
            return {
                "release-count": 1,
                "releases": [{"id": RELEASE, "title": "Edition", "media": []}],
            }
        credited = {"name": "Example", "artist": {"id": ARTIST, "name": "Example"}}
        return {**fixture_release(), "artist-credit": [credited]}

    app, track, tokens, ids = member_client(tmp_path, monkeypatch, provider)
    with TestClient(app, base_url="https://private.ts.net") as client:

        def get(path, name, etag=None):
            headers = {"Authorization": "Bearer " + tokens[name]}
            if etag:
                headers["If-None-Match"] = etag
            return client.get(path, headers=headers)

        release = f"/api/v1/catalogue/releases/{RELEASE}"
        first = get(release, "one")
        assert first.status_code == 200
        etag = first.headers["etag"]
        assert etag.startswith('"') and first.headers["cache-control"].startswith(
            "private"
        )
        assert first.json()["tracks"][0]["server_state"] == "household_available"
        unchanged = get(release, "one", etag)
        assert unchanged.status_code == 304 and unchanged.content == b""
        assert unchanged.headers["etag"] == etag
        assert get(release, "one", 'W/"other", ' + etag).status_code == 304
        # The native client sends the validator percent-encoded.
        assert get(release, "one", etag.replace('"', "%22")).status_code == 304
        assert get(release, "one", '"stale"').status_code == 200
        # The hash covers the person's own projection: adding the song to one
        # library changes that person's body and validator only.
        app.state.store.user_libraries.add(ids["one"], [track["id"]])
        changed = get(release, "one", etag)
        assert changed.status_code == 200
        assert changed.json()["tracks"][0]["server_state"] == "in_library"
        assert changed.headers["etag"] != etag
        assert get(release, "two", etag).status_code == 304

        editions = f"/api/v1/catalogue/groups/{RELEASE}/editions"
        page = get(editions, "two")
        assert page.status_code == 200 and page.json()["editions"][0]["id"] == RELEASE
        assert get(editions, "two", page.headers["etag"]).status_code == 304
        assert get(
            editions + "?offset=50", "two", page.headers["etag"]
        ).status_code == (200)


def test_playlist_detail_answers_304_until_it_changes(tmp_path, monkeypatch):
    async def provider(self, client, path, **params):
        return fixture_release()

    app, _, tokens, _ = member_client(tmp_path, monkeypatch, provider)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + tokens["one"]},
    ) as client:
        created = client.post("/api/v1/playlists", json={"name": "Road"}).json()
        path = "/api/v1/playlists/" + created["id"]
        first = client.get(path)
        assert first.status_code == 200 and first.json()["name"] == "Road"
        etag = first.headers["etag"]
        assert client.get(path, headers={"If-None-Match": etag}).status_code == 304
        client.patch(path, json={"revision": first.json()["revision"], "name": "Trip"})
        renamed = client.get(path, headers={"If-None-Match": etag})
        assert renamed.status_code == 200 and renamed.json()["name"] == "Trip"
        assert renamed.headers["etag"] != etag
        assert client.get("/api/v1/playlists/missing").status_code == 404


def test_conditional_routes_publish_etag_and_304_in_the_contract(tmp_path):
    app = create_app(tmp_path)
    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/catalogue/releases/{release_id}",
        "/api/v1/catalogue/groups/{group_id}/editions",
        "/api/v1/playlists/{playlist_id}",
    ):
        operation = paths[path]["get"]
        assert "304" in operation["responses"]
        assert "ETag" in operation["responses"]["200"]["headers"]
        assert any(p["name"] == "if-none-match" for p in operation["parameters"])
