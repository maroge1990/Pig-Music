import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from server.artist_identity import Ambiguous, resolve_artist
from server.catalogue import Catalogue
from server.store import Store
from test_catalogue import ARTIST, OTHER, RELEASE
from test_personal_libraries import household

ARTIST_ROW = {"id": "lib-artist", "name": "Artist"}
ALBUMS = [
    {"id": "alb", "title": "Studio", "musicbrainz_release_id": RELEASE},
]
NAMESAKES = [
    {"id": ARTIST, "name": "Artist", "disambiguation": "rock band"},
    {"id": OTHER, "name": "Artist", "disambiguation": "dj"},
]


class Fake:
    def __init__(self, **handlers):
        self.handlers, self.paths = handlers, []

    async def get(self, client, path, **params):
        self.paths.append(path)
        return self.handlers[path.split("/")[0]](path, params)


def resolve(store, catalogue, albums=ALBUMS):
    return asyncio.run(resolve_artist(store, catalogue, None, ARTIST_ROW, albums))


def test_release_credit_resolves_without_name_search(tmp_path):
    store = Store(tmp_path)
    catalogue = Fake(
        release=lambda path, params: {
            "artist-credit": [{"artist": {"id": ARTIST, "name": "Artist"}}]
        }
    )
    assert resolve(store, catalogue) == {"id": ARTIST, "name": "Artist"}
    assert catalogue.paths == ["release/" + RELEASE]
    assert store.read_document("library-artist:lib-artist")["id"] == ARTIST


def test_cached_identity_short_circuits(tmp_path):
    store = Store(tmp_path)
    store.write_document("library-artist:lib-artist", {"id": ARTIST, "name": "Artist"})
    assert resolve(store, Fake()) == {"id": ARTIST, "name": "Artist"}


def test_cached_identity_for_another_name_is_ignored(tmp_path):
    store = Store(tmp_path)
    store.write_document("library-artist:lib-artist", {"id": OTHER, "name": "Renamed"})
    catalogue = Fake(
        artist=lambda path, params: {"count": 1, "artists": [NAMESAKES[0]]}
    )
    assert resolve(store, catalogue, [])["id"] == ARTIST


def test_namesakes_resolved_by_owned_album_overlap(tmp_path):
    catalogue = Fake(
        artist=lambda path, params: {"count": 2, "artists": NAMESAKES},
        release=lambda path, params: {"artist-credit": []},
        **{
            "release-group": lambda path, params: {
                "count": 1,
                "release-groups": [
                    {
                        "title": "Studio",
                        "artist-credit": [{"artist": {"id": OTHER, "name": "Artist"}}],
                    }
                ],
            }
        },
    )
    assert resolve(Store(tmp_path), catalogue)["id"] == OTHER


def test_ambiguous_namesakes_carry_candidates(tmp_path):
    store = Store(tmp_path)
    catalogue = Fake(
        artist=lambda path, params: {"count": 2, "artists": NAMESAKES},
        release=lambda path, params: {"artist-credit": []},
        **{"release-group": lambda path, params: {"count": 0, "release-groups": []}},
    )
    with pytest.raises(Ambiguous) as caught:
        resolve(store, catalogue)
    assert caught.value.candidates == [
        {"id": ARTIST, "name": "Artist", "disambiguation": "rock band"},
        {"id": OTHER, "name": "Artist", "disambiguation": "dj"},
    ]
    assert store.read_document("library-artist:lib-artist") == {}


def test_no_match_is_ambiguous_with_no_candidates(tmp_path):
    catalogue = Fake(artist=lambda path, params: {"count": 0, "artists": []})
    with pytest.raises(Ambiguous) as caught:
        resolve(Store(tmp_path), catalogue, [])
    assert caught.value.candidates == []


def client_for(app, token):
    return TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token, "X-Pig-Request": "1"},
    )


def prepared(tmp_path, monkeypatch):
    from test_security import PASSWORD

    app, owner, member, member_token, track = household(tmp_path, monkeypatch)
    app.state.store.user_libraries.add(member, [track["id"]])
    owner_token = app.state.auth.login(
        "mark", PASSWORD, "device", "laptop", "web", "fixture"
    )["token"]
    artist = app.state.store.user_libraries.projection(member)["artists"][0]
    return app, owner_token, member_token, artist["id"]


def test_ambiguous_saved_artist_returns_candidates_and_owner_can_link(
    tmp_path, monkeypatch
):
    app, owner_token, member_token, artist_id = prepared(tmp_path, monkeypatch)
    path = "/api/v1/catalogue/library-artists/" + artist_id

    async def metadata(self, client, path, **params):
        if path == "artist/" + OTHER:
            return {"id": OTHER, "name": "Artist"}
        if path.startswith("artist/") and path != "artist/":
            request = httpx.Request("GET", "https://musicbrainz.org/")
            raise httpx.HTTPStatusError(
                "missing", request=request, response=httpx.Response(404)
            )
        return {"count": 2, "artists": NAMESAKES, "release-groups": []}

    monkeypatch.setattr(Catalogue, "get", metadata)
    with client_for(app, member_token) as client:
        as_member = {"Authorization": "Bearer " + member_token}
        as_owner = {"Authorization": "Bearer " + owner_token}
        response = client.get(path, headers=as_member)
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "conflict" and isinstance(body["detail"], str)
        assert [c["id"] for c in body["candidates"]] == [ARTIST, OTHER]
        assert body["candidates"][0]["disambiguation"] == "rock band"
        forbidden = client.put(path, json={"id": OTHER}, headers=as_member)
        assert forbidden.status_code == 403
        for bad in ("nope", ARTIST):
            rejected = client.put(path, json={"id": bad}, headers=as_owner)
            assert rejected.status_code == 400
        linked = client.put(path, json={"id": OTHER}, headers=as_owner)
        assert linked.json()["id"] == OTHER
        stored = app.state.store.read_document("library-artist:" + artist_id)
        assert stored["id"] == OTHER
        assert client.get(path, headers=as_member).json()["id"] == OTHER
