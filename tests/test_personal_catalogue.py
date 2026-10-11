import json
import httpx
from fastapi.testclient import TestClient
from server.app import create_app
from server.catalogue import Catalogue, release_tracks
from test_catalogue import fixture_release, RELEASE, ARTIST
from server.auth import Auth
from server.store import Store


def test_member_catalogue_is_scoped_and_contract_published(tmp_path, monkeypatch):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    track = release_tracks(fixture_release())[0]
    track.update(id="physical-file-id", available=True, path="/private/owner-only.mp3")
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    store = Store(tmp_path)
    auth = Auth(store)
    owner = auth.create_owner("mark", "catalogue fixture password")
    code = auth.setup_code(owner, "member", "Member")
    member = auth.activate(code["code"], "catalogue fixture password", "fixture")["id"]
    token = auth.login(
        "member", "catalogue fixture password", "device", "phone", "ios", "fixture"
    )["token"]
    calls = []

    async def provider(self, client, path, **params):
        calls.append(path)
        return fixture_release()

    monkeypatch.setattr(Catalogue, "get", provider)
    app = create_app(tmp_path)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        path = f"/api/v1/catalogue/releases/{RELEASE}"
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert response.json()["tracks"][0]["server_state"] == "household_available"
        assert response.json()["tracks"][0]["saved_track"] is None
        shared = response.json()["tracks"][0]["household_track"]
        assert shared["id"] == "physical-file-id"
        assert shared["server_state"] == "household_available"
        assert shared["source_revision"]
        assert "/private/" not in response.text and owner not in response.text
        app.state.store.user_libraries.add(member, [track["id"]])
        personal_track = client.get(path).json()["tracks"][0]
        assert personal_track["server_state"] == "in_library"
        assert personal_track["saved_track"]["id"] == track["id"]
        assert personal_track["saved_track"]["source_revision"]
        assert "/private/" not in json.dumps(personal_track)
        assert client.get("/api/v1/catalogue/releases/not-an-id").status_code == 400
        assert (
            client.get(
                f"/api/v1/catalogue/artists/{ARTIST}/releases?offset=-1"
            ).status_code
            == 422
        )
        assert client.get("/api/catalogue/artists").status_code == 403
        contract = client.get("/api/v1/openapi.json")
        assert contract.status_code == 200
        assert contract.json()["openapi"] == "3.0.3"
        assert "/api/v1/library/tracks" in contract.json()["paths"]
    assert calls == ["release/" + RELEASE, "release/" + RELEASE]


def test_release_reports_requested_only_for_the_requesting_member(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    track = release_tracks(fixture_release())[0]
    store = Store(tmp_path)
    auth = Auth(store)
    owner = auth.create_owner("mark", "catalogue fixture password")
    tokens = {}
    ids = {}
    for name in ("one", "two"):
        code = auth.setup_code(owner, name, name)
        ids[name] = auth.activate(code["code"], "catalogue fixture password", "f")["id"]
        tokens[name] = auth.login(
            name, "catalogue fixture password", "device", "phone", "ios", "f"
        )["token"]

    async def provider(self, client, path, **params):
        return fixture_release()

    monkeypatch.setattr(Catalogue, "get", provider)
    app = create_app(tmp_path)
    with TestClient(app, base_url="https://private.ts.net") as client:
        app.state.store.submit_catalogue(
            [{**track, "status": "missing"}], user_id=ids["one"]
        )
        path = f"/api/v1/catalogue/releases/{RELEASE}"

        def state(name):
            response = client.get(
                path, headers={"Authorization": "Bearer " + tokens[name]}
            )
            return response.json()["tracks"][0]["server_state"]

        assert state("one") == "requested"
        assert state("two") == "not_in_library"


def test_typed_catalogue_pages_accept_unknown_provider_metadata(tmp_path, monkeypatch):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    store = Store(tmp_path)
    auth = Auth(store)
    auth.create_owner("mark", "catalogue fixture password")
    token = auth.login(
        "mark", "catalogue fixture password", "device", "phone", "ios", "fixture"
    )["token"]

    async def provider(self, client, path, **params):
        if path == "release-group":
            return {
                "release-group-count": 1,
                "release-groups": [
                    {
                        "id": RELEASE,
                        "title": "Unknown date",
                        "first-release-date": None,
                        "primary-type": None,
                    }
                ],
            }
        return {
            "release-count": 1,
            "releases": [
                {
                    "id": RELEASE,
                    "title": "Edition",
                    "date": None,
                    "country": None,
                    "disambiguation": None,
                    "status": None,
                    "media": [{"format": None, "track-count": None}],
                }
            ],
        }

    monkeypatch.setattr(Catalogue, "get", provider)
    app = create_app(tmp_path)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        groups = client.get(f"/api/v1/catalogue/artists/{ARTIST}/releases")
        assert groups.status_code == 200, groups.text
        assert groups.json()["releases"][0]["date"] == ""
        assert groups.json()["releases"][0]["type"] == "Release"
        editions = client.get(f"/api/v1/catalogue/groups/{RELEASE}/editions")
        assert editions.status_code == 200, editions.text
        assert editions.json()["editions"][0]["country"] == ""
        assert editions.json()["editions"][0]["formats"] == [""]
        assert editions.json()["editions"][0]["track_count"] == 0


def test_artist_search_forwards_paging_and_normalises_unknown_description(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    store = Store(tmp_path)
    auth = Auth(store)
    auth.create_owner("mark", "catalogue fixture password")
    token = auth.login(
        "mark", "catalogue fixture password", "device", "phone", "ios", "fixture"
    )["token"]
    calls = []

    async def provider(self, client, path, **params):
        calls.append((path, params))
        return {
            "count": "23",
            "artists": [{"id": ARTIST, "name": "Artist", "disambiguation": None}],
        }

    monkeypatch.setattr(Catalogue, "get", provider)
    with TestClient(
        create_app(tmp_path),
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        page = client.get(
            "/api/v1/catalogue/artists",
            params={"q": "Artist", "offset": 20, "limit": 1},
        )
        assert page.status_code == 200, page.text
        assert page.json() == {
            "offset": 20,
            "total": 23,
            "next_offset": 21,
            "artists": [{"id": ARTIST, "name": "Artist", "description": ""}],
        }
        assert calls == [("artist/", {"query": "Artist", "offset": 20, "limit": 1})]
        assert client.get("/api/v1/catalogue/artists?offset=-1").status_code == 422
