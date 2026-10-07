import re
from concurrent.futures import ThreadPoolExecutor
import json
import os
import stat

from fastapi.testclient import TestClient
import pytest

from server.app import create_app
from server.auth import AuthError
from server.security import PUBLIC, audit_routes, secret_file

PASSWORD = "security fixture password"


def protected(tmp_path, monkeypatch, owner=True):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(tmp_path / "nas"))
    app = create_app(tmp_path)
    if owner:
        identity = app.state.auth.create_owner("mark", PASSWORD)
    else:
        identity = None
    return app, identity


def request_paths(app):
    for route in app.routes:
        if getattr(route, "path", "").startswith("/api/"):
            path = route.path
            for name in route.param_convertors:
                path = path.replace("{" + name + "}", "fixture")
            for method in route.methods:
                yield method, path


def test_every_api_route_is_anonymous_denied_and_bootstrap_closed(
    tmp_path, monkeypatch
):
    app, _ = protected(tmp_path, monkeypatch, owner=False)
    with TestClient(app, base_url="https://private.ts.net") as client:
        for method, path in request_paths(app):
            response = client.request(
                method, path, json={} if method not in {"GET", "HEAD"} else None
            )
            if path == "/api/health":
                assert response.status_code in {200, 405}
            else:
                assert response.status_code == 503, (method, path, response.text)
    owner = app.state.auth.create_owner("mark", PASSWORD)
    with TestClient(app, base_url="https://private.ts.net") as client:
        for method, path in request_paths(app):
            if (method, path) in PUBLIC:
                continue
            response = client.request(
                method, path, json={} if method not in {"GET", "HEAD"} else None
            )
            assert response.status_code == 401, (method, path, response.text)
        health = client.get("/api/health").json()
        assert set(health) == {"status", "https", "storage_available"}


def test_member_cannot_see_unscoped_legacy_routes(tmp_path, monkeypatch):
    app, owner = protected(tmp_path, monkeypatch)
    setup = app.state.auth.setup_code(owner, "member", "Member")
    app.state.auth.activate(setup["code"], PASSWORD, "fixture")
    token = app.state.auth.login(
        "member", PASSWORD, "device", "phone", "ios", "fixture"
    )["token"]
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        personal_paths = {
            route.path
            for route in app.routes
            if "personal-library" in getattr(route, "tags", [])
        }
        for method, path in request_paths(app):
            if any(
                path == re.sub(r"\{[^}]+\}", "fixture", route.path)
                for route in app.routes
                if getattr(route, "path", "") in personal_paths
                for name in route.param_convertors
            ):
                continue
            if path in personal_paths:
                continue
            if path.startswith(
                (
                    "/api/v1/playback/",
                    "/api/playback/files/",
                    "/api/artwork/",
                    "/api/library-artwork/",
                )
            ):
                assert client.request(method, path, json={}).status_code == 404
                continue
            if (method, path) in PUBLIC or path.startswith(
                ("/api/v1/me", "/api/v1/auth/logout")
            ):
                continue
            response = client.request(
                method, path, json={} if method not in {"GET", "HEAD"} else None
            )
            assert response.status_code == 403, (method, path, response.text)
        assert client.get("/api/v1/me").json()["username"] == "member"


def test_route_audit_detects_an_unprotected_api(tmp_path, monkeypatch):
    app, _ = protected(tmp_path, monkeypatch)
    route = next(r for r in app.routes if getattr(r, "path", "") == "/api/library")
    route.dependant.dependencies = []
    with pytest.raises(RuntimeError, match="missing its default-deny guard"):
        audit_routes(app, app.state.security.current_user)


def test_signed_playback_ranges_tamper_expiry_and_revocation(tmp_path, monkeypatch):
    nas = tmp_path / "nas"
    nas.mkdir()
    (nas / "song.mp3").write_bytes(b"fixture audio bytes")
    (tmp_path / "library-snapshot.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": "song",
                        "title": "Song",
                        "artist": "Artist",
                        "album": "Album",
                        "relative_path": "song.mp3",
                    }
                ]
            }
        )
    )
    app, _ = protected(tmp_path, monkeypatch)
    auth = app.state.auth
    clock = [1700000000]
    auth.clock = lambda: clock[0]
    token = auth.login("mark", PASSWORD, "device", "phone", "ios", "fixture")["token"]
    with TestClient(app, base_url="https://private.ts.net") as client:
        result = client.post(
            "/api/v1/playback/song/url", headers={"Authorization": "Bearer " + token}
        )
        assert result.status_code == 200, result.text
        url = result.json()["url"]
        response = client.get(url, headers={"Range": "bytes=0-6"})
        assert response.status_code == 206 and response.content == b"fixture"
        assert client.get(url.replace("/song?", "/other?")).status_code == 403
        assert client.get(url + "x").status_code == 403
        clock[0] += 6 * 3600
        assert client.get(url).status_code == 403
        clock[0] -= 6 * 3600
        _, session = auth.authenticate(token)
        auth.revoke(session["user_id"], session["public_id"])
        assert client.get(url).status_code == 403


def test_cookie_mutations_require_header_and_https(tmp_path, monkeypatch):
    app, _ = protected(tmp_path, monkeypatch)
    with TestClient(
        app, base_url="https://private.ts.net", headers={"X-Pig-Request": "1"}
    ) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "mark", "password": PASSWORD}
            ).status_code
            == 200
        )
        client.headers.pop("X-Pig-Request")
        assert client.post("/api/queue/clear", json={}).status_code == 403
        assert (
            client.post(
                "/api/queue/clear", json={}, headers={"X-Pig-Request": "1"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/queue/clear",
                json={},
                headers={"X-Pig-Request": "1", "Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert client.get("/api/library").status_code == 200


def test_secret_is_atomic_private_persistent_and_rejects_symlinks(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: secret_file(tmp_path), range(8)))
    assert all(value == values[0] for value in values)
    assert len(values[0]) == 32
    assert stat.S_IMODE((tmp_path / "auth-secret").stat().st_mode) == 0o600
    (tmp_path / "linked").mkdir()
    (tmp_path / "linked/auth-secret").symlink_to(tmp_path / "auth-secret")
    with pytest.raises(OSError):
        secret_file(tmp_path / "linked")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad/auth-secret").write_bytes(b"bad")
    with pytest.raises(ValueError):
        secret_file(tmp_path / "bad")
