import pytest

from server.catalogue import Catalogue
from server.popularity import Popularity


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_rate_limits: keep the production provider request spacing"
    )


@pytest.fixture(autouse=True)
def isolate_startup_enrichment(monkeypatch, tmp_path_factory, request):
    # Provider tests supply their own mock HTTP transport after app startup.
    # Keep unrelated background requests out of those explicit scenarios.
    monkeypatch.setenv("PIG_MUSIC_PRELOAD", "false")

    # The default /library resolves to the host's /Library on macOS, which the
    # startup scanner would walk. Tests that need a library set their own.
    monkeypatch.setenv(
        "PIG_MUSIC_LIBRARY", str(tmp_path_factory.getbasetemp() / "no-library")
    )

    # Mocked providers need no politeness delay; test_rate_limits covers it.
    if not request.node.get_closest_marker("real_rate_limits"):
        monkeypatch.setattr(Catalogue, "min_interval", 0)
        monkeypatch.setattr(Popularity, "min_interval", 0)

    # Legacy functional fixtures are deliberately unauthenticated and isolated.
    # Security tests explicitly revoke this bypass; runtime strips it.
    monkeypatch.setenv("PIG_MUSIC_TEST_LEGACY_API", "1")
