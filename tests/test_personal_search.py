import json
from fastapi.testclient import TestClient
from test_personal_libraries import household


def test_search_pages_preserve_personal_scope_and_reject_changed_revision(
    tmp_path, monkeypatch
):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    tracks = [
        {**track, "id": str(i), "title": f"Song {i:03}", "album": "Song album"}
        for i in range(205)
    ]
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    app.state.store.refresh_library()
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        first = client.get("/api/v1/search", params={"q": "Song"})
        assert first.status_code == 200, first.text
        page = first.json()
        assert page["tracks"] == []
        assert page["total_household_tracks"] == 205
        assert page["next_offset"] == 100
        assert "private/" not in first.text
        seen = [t["id"] for t in page["household_tracks"]]
        for offset in (100, 200):
            response = client.get(
                "/api/v1/search",
                params={"q": "Song", "offset": offset, "revision": page["revision"]},
            )
            assert response.status_code == 200, response.text
            seen += [t["id"] for t in response.json()["household_tracks"]]
        assert len(seen) == len(set(seen)) == 205
        app.state.store.user_libraries.add(member, ["0"])
        assert (
            client.get(
                "/api/v1/search",
                params={"q": "Song", "offset": 100, "revision": page["revision"]},
            ).status_code
            == 409
        )
        fresh = client.get("/api/v1/search", params={"q": "Song"}).json()
        assert fresh["total_tracks"] == 1
        assert fresh["total_albums"] == 1
        assert fresh["albums"][0]["title"] == "Song album"
        assert fresh["total_household_tracks"] == 204
        for params in ({"offset": -1}, {"limit": 201}, {"limit": 0}):
            assert client.get("/api/v1/search", params=params).status_code == 422
        assert (
            client.get("/api/v1/search", params={"q": " "}).json()[
                "total_household_tracks"
            ]
            == 0
        )
