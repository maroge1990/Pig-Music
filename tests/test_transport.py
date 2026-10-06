import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.transport import public_origin, proxy_trust


@pytest.mark.parametrize(
    "value",
    [
        "http://private.ts.net",
        "https://user:password@private.ts.net",
        "https://private.ts.net/path",
        "https://private.ts.net?token=x",
        "https://private.ts.net#fragment",
    ],
)
def test_public_origin_rejects_unsafe_configuration(monkeypatch, value):
    monkeypatch.setenv("PIG_MUSIC_PUBLIC_ORIGIN", value)
    with pytest.raises(ValueError):
        public_origin()


def test_https_origin_and_health_preserve_lan_transition(tmp_path, monkeypatch):
    monkeypatch.setenv("PIG_MUSIC_PUBLIC_ORIGIN", "https://private.ts.net")
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/health").json()["https"] is False
        assert (
            client.get("/api/health", headers={"X-Forwarded-Proto": "https"}).json()[
                "https"
            ]
            is False
        )
        assert (
            client.post(
                "/does-not-exist", headers={"Origin": "https://private.ts.net"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/does-not-exist", headers={"Origin": "http://testserver"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/does-not-exist", headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
    with TestClient(create_app(tmp_path), base_url="https://private.ts.net") as client:
        assert client.get("/api/health").json()["https"] is True


@pytest.mark.parametrize("value", ["*", "0.0.0.0/0", "192.168.1.0/24", "localhost", ""])
def test_proxy_trust_rejects_wildcard_and_broad_networks(monkeypatch, value):
    monkeypatch.setenv("PIG_MUSIC_TRUSTED_PROXIES", value)
    with pytest.raises(ValueError):
        proxy_trust()


def test_proxy_trust_accepts_exact_private_proxy(monkeypatch):
    monkeypatch.setenv("PIG_MUSIC_TRUSTED_PROXIES", "127.0.0.1,192.168.1.235")
    assert proxy_trust() == "127.0.0.1,192.168.1.235"
