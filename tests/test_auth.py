import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from server.auth import Auth, AuthError, COOKIE, DAY
from server.auth_logging import CredentialFilter, install_validation_redaction
from server.routes.auth import auth_router
from server.store import Store

PASSWORD = "fixture password only"


@pytest.fixture
def fixture(tmp_path):
    clock = [1700000000]
    store = Store(tmp_path)
    auth = Auth(store, lambda: clock[0])
    owner = auth.create_owner("mark", PASSWORD, "Mark")
    return auth, owner, clock


def token(auth, name="mark", password=PASSWORD, kind="device", ip="fixture"):
    return auth.login(
        name, password, kind, "fixture phone", "ios" if kind == "device" else "web", ip
    )["token"]


def test_owner_bootstrap_hash_and_single_owner(fixture):
    auth, owner, _ = fixture
    assert auth.ready()
    assert auth.user(owner)["password_hash"].startswith("$argon2id$")
    with pytest.raises(AuthError, match="owner_already_exists"):
        auth.create_owner("other", PASSWORD)
    with auth.store.connect() as conn:
        assert PASSWORD not in "\n".join(conn.iterdump())


def test_token_hash_only_revocation_and_session_scoping(fixture):
    auth, owner, _ = fixture
    first = token(auth)
    second = token(auth)
    person, session = auth.authenticate(first)
    assert person["id"] == owner
    assert "password_hash" not in person
    listed = auth.sessions(owner)
    assert all(len(row["id"]) == 36 for row in listed)
    assert session["id"] not in json.dumps(listed)
    with auth.store.connect() as conn:
        assert first not in "\n".join(conn.iterdump())
        assert second not in "\n".join(conn.iterdump())
    auth.revoke(owner, session["public_id"])
    with pytest.raises(AuthError):
        auth.authenticate(first)
    auth.authenticate(second)
    with pytest.raises(AuthError, match="session_not_found"):
        auth.revoke("another-user", listed[0]["id"])


def test_web_and_device_expiry_hourly_writes(fixture):
    auth, _, clock = fixture
    web = token(auth, kind="web")
    device = token(auth)
    _, s1 = auth.authenticate(device)
    clock[0] += 60
    _, s2 = auth.authenticate(device)
    assert s1["last_seen_at"] == s2["last_seen_at"]
    clock[0] += 3600
    auth.authenticate(device)
    _, s3 = auth.authenticate(device)
    assert s3["last_seen_at"] == clock[0]
    clock[0] += 15 * DAY
    with pytest.raises(AuthError):
        auth.authenticate(web)
    auth.authenticate(device)
    clock[0] += 181 * DAY
    with pytest.raises(AuthError):
        auth.authenticate(device)


def test_web_absolute_limit_despite_activity(fixture):
    auth, _, clock = fixture
    web = token(auth, kind="web")
    for _ in range(5):
        clock[0] += 10 * DAY
        auth.authenticate(web)
    clock[0] += 10 * DAY
    with pytest.raises(AuthError):
        auth.authenticate(web)


def test_setup_one_use_expiry_reset_and_disabled_user(fixture):
    auth, owner, clock = fixture
    setup = auth.setup_code(owner, "member", "Household member")
    with auth.store.connect() as conn:
        assert setup["code"] not in "\n".join(conn.iterdump())
    member = auth.activate(setup["code"], PASSWORD, "fixture2")
    device = token(auth, "member")
    with pytest.raises(AuthError, match="invalid_setup_code"):
        auth.activate(setup["code"], PASSWORD, "fixture2")
    reset = auth.setup_code(owner, identity=member["id"])
    with pytest.raises(AuthError):
        auth.authenticate(device)
    clock[0] += DAY
    with pytest.raises(AuthError, match="invalid_setup_code"):
        auth.activate(reset["code"], PASSWORD, "fixture2")
    reset = auth.setup_code(owner, identity=member["id"])
    auth.activate(reset["code"], PASSWORD, "fixture2")
    device = token(auth, "member")
    with auth.store.connect() as conn:
        conn.execute("UPDATE users SET disabled=1 WHERE id=?", (member["id"],))
    with pytest.raises(AuthError):
        auth.authenticate(device)


def test_password_change_keeps_current_and_revokes_others(fixture):
    auth, _, _ = fixture
    first, second = token(auth), token(auth)
    person, session = auth.authenticate(first)
    auth.change_password(person, session, PASSWORD, "new fixture password")
    auth.authenticate(first)
    with pytest.raises(AuthError):
        auth.authenticate(second)
    token(auth, password="new fixture password")
    auth.reset_password("mark", PASSWORD)
    with pytest.raises(AuthError):
        auth.authenticate(first)


def test_login_limits_unknown_user_same_errors_and_exponential_lock(fixture):
    auth, _, clock = fixture
    for cycle, seconds in enumerate([60, 120, 240]):
        for _ in range(5):
            with pytest.raises(AuthError, match="invalid_credentials"):
                token(auth, password="wrong fixture", ip="bad-ip")
        with auth.store.connect() as conn:
            assert (
                conn.execute(
                    "SELECT locked_until FROM login_attempts WHERE key=?",
                    (auth.keys("mark", "bad-ip")[0],),
                ).fetchone()[0]
                == clock[0] + seconds
            )
        with pytest.raises(AuthError, match="invalid_credentials"):
            token(auth, ip="another-ip")
        clock[0] += seconds + 1
    for _ in range(5):
        with pytest.raises(AuthError, match="invalid_credentials"):
            token(auth, name="missing-user", ip="unknown-ip")
    with pytest.raises(AuthError, match="invalid_credentials"):
        token(auth, name="another-missing", ip="unknown-ip")


@pytest.mark.parametrize(
    "password", ["short", "password1234", "123456789012", "x" * 257]
)
def test_weak_or_unbounded_password_rejected(fixture, password):
    auth, _, _ = fixture
    with pytest.raises(AuthError, match="password_not_accepted"):
        auth.create_owner("another", password)


def app_for(auth):
    app = FastAPI()
    install_validation_redaction(app)
    app.include_router(auth_router(auth))
    return app


def test_https_cookie_flags_csrf_and_device_bearer(fixture):
    auth, owner, _ = fixture
    with TestClient(
        app_for(auth), base_url="https://private.ts.net", headers={"X-Pig-Request": "1"}
    ) as client:
        response = client.post(
            "/api/v1/auth/login", json={"username": "mark", "password": PASSWORD}
        )
        assert response.status_code == 200, response.text
        cookie = response.headers["set-cookie"]
        assert (
            COOKIE in cookie
            and "HttpOnly" in cookie
            and "Secure" in cookie
            and "SameSite=strict" in cookie
            and "Path=/" in cookie
        )
        assert "token" not in response.json()
        assert client.get("/api/v1/me").json()["id"] == owner
        result = client.post(
            "/api/v1/auth/device",
            json={
                "username": "mark",
                "password": PASSWORD,
                "device_name": "test phone",
                "platform": "ios",
            },
        )
        device = result.json()["token"]
        assert (
            client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + device}
            ).status_code
            == 200
        )
        client.headers.pop("X-Pig-Request")
        assert client.post("/api/v1/auth/logout").status_code == 403
        assert (
            client.post(
                "/api/v1/auth/logout", headers={"Authorization": "Bearer " + device}
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/v1/me", headers={"Authorization": "Bearer " + device}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/login",
                headers={"X-Pig-Request": "1", "Origin": "https://evil.example"},
                json={"username": "mark", "password": PASSWORD},
            ).status_code
            == 403
        )
    with TestClient(app_for(auth)) as client:
        assert (
            client.post(
                "/api/v1/auth/login", json={"username": "mark", "password": PASSWORD}
            ).status_code
            == 400
        )


def test_members_cannot_issue_accounts_and_errors_do_not_echo_secrets(fixture, caplog):
    auth, owner, _ = fixture
    setup = auth.setup_code(owner, "member", "Member")
    auth.activate(setup["code"], PASSWORD, "fixture2")
    device = token(auth, "member")
    with TestClient(app_for(auth), base_url="https://private.ts.net") as client:
        assert (
            client.post(
                "/api/v1/people",
                headers={"Authorization": "Bearer " + device},
                json={"username": "extra", "display_name": "Extra"},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/v1/setup",
            headers={"X-Pig-Request": "1"},
            json={
                "code": "sensitive invalid code",
                "password": "sensitive invalid password" * 20,
            },
        )
        assert response.status_code == 422
        assert "sensitive invalid" not in response.text
    assert (
        PASSWORD not in caplog.text
        and device not in caplog.text
        and setup["code"] not in caplog.text
    )


def test_credential_filter_redacts_diagnostic_fields():
    record = logging.LogRecord(
        "fixture",
        logging.INFO,
        "",
        1,
        {
            "password": "secret-value",
            "nested": {
                "Authorization": "Bearer secret-value",
                "Cookie": "secret-value",
                "token": "secret-value",
                "code": "secret-value",
            },
        },
        (),
        None,
    )
    CredentialFilter().filter(record)
    assert "secret-value" not in record.getMessage()
    text = logging.LogRecord(
        "fixture",
        logging.INFO,
        "",
        1,
        "POST /api?token=secret-value&sig=secret-signature Cookie=secret-cookie",
        (),
        None,
    )
    CredentialFilter().filter(text)
    assert (
        "secret-value" not in text.getMessage()
        and "secret-signature" not in text.getMessage()
        and "secret-cookie" not in text.getMessage()
    )
