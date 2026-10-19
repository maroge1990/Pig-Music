import json

from fastapi.testclient import TestClient

from server.app import create_app
from server.auth import Auth
from server.catalogue import Catalogue
from server.library import identifier, normalise
from server.store import Store
from test_catalogue import ARTIST

GROUP = "8f1e2d3c-1111-4222-8333-944455556666"
OTHER = "8f1e2d3c-1111-4222-8333-944455556667"


def song(index, album):
    return {
        "id": f"{album}-{index}",
        "title": f"{album} song {index}",
        "artist": "Charli",
        "album_artist": "Charli",
        "album": album,
        "track_number": index,
        "duration": 100,
        "path": f"/private/{album}-{index}.mp3",
        "available": True,
    }


def test_catalogue_releases_mark_what_the_person_owns(tmp_path, monkeypatch):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    tracks = [song(1, "Brat"), song(2, "Brat"), song(1, "Crash")]
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    store = Store(tmp_path)
    auth = Auth(store)
    owner = auth.create_owner("mark", "catalogue fixture password")
    code = auth.setup_code(owner, "member", "Member")
    member = auth.activate(code["code"], "catalogue fixture password", "f")["id"]
    token = auth.login(
        "member", "catalogue fixture password", "device", "phone", "ios", "f"
    )["token"]
    calls = []

    async def provider(self, client, path, **params):
        calls.append(path)
        return {
            "release-group-count": 2,
            "release-groups": [
                {"id": GROUP, "title": "Brat (Deluxe)", "primary-type": "Album"},
                {"id": OTHER, "title": "Crash", "primary-type": "Album"},
            ],
        }

    monkeypatch.setattr(Catalogue, "get", provider)
    app = create_app(tmp_path)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        # Only Brat's songs are in this person's library.
        app.state.store.user_libraries.add(member, ["Brat-1", "Brat-2"])
        path = f"/api/v1/catalogue/artists/{ARTIST}/releases"
        unknown = client.get(path).json()["releases"]
        assert [r["saved_album_id"] for r in unknown] == [None, None]
        named = client.get(path, params={"name": "charli"}).json()["releases"]
        assert named[0]["saved_album_id"] and named[0]["saved_songs"] == 2
        assert named[1]["saved_album_id"] is None and named[1]["saved_songs"] == 0
        # A resolved library identity is enough, without a name.
        artist_id = identifier("artist", normalise("Charli"))
        app.state.store.write_document(
            "library-artist:" + artist_id, {"id": ARTIST, "name": "Charli"}
        )
        resolved = client.get(path).json()["releases"]
        assert resolved[0]["saved_album_id"] == named[0]["saved_album_id"]
        album = client.get("/api/v1/albums/" + resolved[0]["saved_album_id"])
        assert album.json()["title"] == "Brat"
        # The library artist page carries the owned songs for Play all.
        detail = client.get("/api/v1/artists/" + artist_id).json()
        assert [t["id"] for t in detail["tracks"]] == ["Brat-1", "Brat-2"]
        assert "/private/" not in json.dumps(detail)
    assert all(path.startswith("release-group") for path in calls)
