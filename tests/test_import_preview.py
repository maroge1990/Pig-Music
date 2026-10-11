from fastapi.testclient import TestClient
from test_personal_libraries import household
from test_playlists import export


def test_preview_is_read_only_and_counts_personal_vs_household(tmp_path, monkeypatch):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        before = client.get("/api/v1/playlists").json()
        response = client.post(
            "/api/v1/imports/apple/preview",
            content=export(),
            headers={"Content-Type": "application/xml"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["playlists"] > 0 and result["tracks"] > 0
        assert (
            result["saved"] + result["household"] + result["missing"]
            == result["tracks"]
        )
        assert client.get("/api/v1/playlists").json() == before
        assert app.state.store.queue()["items"] == []
        assert app.state.store.user_libraries.summary(member)["stats"]["tracks"] == 0
        assert (
            client.post("/api/v1/imports/apple/preview", content=b"not xml").status_code
            == 400
        )
