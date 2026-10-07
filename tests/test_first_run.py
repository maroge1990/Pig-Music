from concurrent.futures import ThreadPoolExecutor
import json

from fastapi.testclient import TestClient

from server.app import create_app
from server.auth import AuthError, COOKIE
from server.security import Security

PASSWORD = "first run fixture password"


def unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(tmp_path / "nas"))
    return create_app(tmp_path)


def payload(app, name="mark"):
    return {
        "code": app.state.security.installation_code(),
        "username": name,
        "display_name": "Mark",
        "password": PASSWORD,
    }


def test_first_run_https_code_cookie_and_permanent_closure(tmp_path, monkeypatch):
    app = unconfigured(tmp_path, monkeypatch)
    with TestClient(app, base_url="https://private.ts.net") as client:
        assert client.get("/api/v1/setup/owner").json() == {"setup_required": True}
        assert client.get("/api/v1/library").status_code == 503
        body = payload(app)
        assert client.post("/api/v1/setup/owner", json=body).status_code == 403
        headers = {"X-Pig-Request": "1"}
        assert (
            client.post(
                "/api/v1/setup/owner",
                json={**body, "code": "wrong-code-only-for-fixture"},
                headers=headers,
            ).status_code
            == 403
        )
        response = client.post("/api/v1/setup/owner", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["user"]["role"] == "owner"
        cookie = response.headers["set-cookie"]
        assert COOKIE in cookie and "Secure" in cookie and "HttpOnly" in cookie
        assert client.get("/api/v1/me").json()["username"] == "mark"
        assert client.get("/api/v1/setup/owner").json() == {"setup_required": False}
        assert (
            client.post(
                "/api/v1/setup/owner", json=payload(app, "another"), headers=headers
            ).status_code
            == 409
        )
        # Even a disabled/deleted-password owner cannot reopen claim registration.
        with app.state.store.connect() as conn:
            conn.execute(
                "UPDATE users SET disabled=1,password_hash=NULL WHERE role='owner'"
            )
            assert PASSWORD not in "\n".join(conn.iterdump())
        assert not app.state.auth.ready()
        assert client.get("/api/v1/setup/owner").json() == {"setup_required": False}
        assert (
            client.post("/api/v1/setup/owner", json=body, headers=headers).status_code
            == 409
        )
    with TestClient(app, base_url="http://private.ts.net") as client:
        assert client.get("/api/v1/setup/owner").status_code == 400
        assert (
            client.post("/api/v1/setup/owner", json=body, headers=headers).status_code
            == 400
        )


def test_code_survives_restart_is_not_exposed_and_attempts_are_bounded(
    tmp_path, monkeypatch
):
    app = unconfigured(tmp_path, monkeypatch)
    expected = app.state.security.installation_code()
    assert expected == Security(app.state.auth).installation_code()
    with TestClient(app, base_url="https://private.ts.net") as client:
        assert expected not in client.get("/api/v1/setup/owner").text
        assert expected not in client.get("/api/health").text
        body = {**payload(app), "code": "incorrect-fixture-code"}
        for _ in range(5):
            assert (
                client.post(
                    "/api/v1/setup/owner", json=body, headers={"X-Pig-Request": "1"}
                ).status_code
                == 403
            )
        assert (
            client.post(
                "/api/v1/setup/owner", json=payload(app), headers={"X-Pig-Request": "1"}
            ).status_code
            == 429
        )
        response = client.post(
            "/api/v1/setup/owner",
            json=payload(app),
            headers={"X-Pig-Request": "1", "Origin": "https://other.invalid"},
        )
        assert response.status_code == 403
        assert expected not in response.text and PASSWORD not in response.text


def test_concurrent_claims_create_exactly_one_owner(tmp_path, monkeypatch):
    app = unconfigured(tmp_path, monkeypatch)
    auth = app.state.auth

    def claim(name):
        try:
            return auth.claim_owner(
                app.state.security.installation_code(),
                app.state.security.installation_code(),
                name,
                PASSWORD,
                name,
                "fixture",
            )["user"]["username"]
        except AuthError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["first", "second"]))
    assert results.count("owner_already_exists") == 1
    with auth.store.connect() as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM users WHERE role='owner'").fetchone()[0]
            == 1
        )
        assert PASSWORD not in "\n".join(conn.iterdump())
