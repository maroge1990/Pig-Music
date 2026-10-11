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
    track.update(available=True, path="/private/owner-only.mp3")
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
        assert "/private/" not in response.text and owner not in response.text
        app.state.store.user_libraries.add(member, [track["id"]])
        assert client.get(path).json()["tracks"][0]["server_state"] == "in_library"
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
