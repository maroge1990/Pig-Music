import pytest


@pytest.fixture(autouse=True)
def isolate_startup_enrichment(monkeypatch):
    # Provider tests supply their own mock HTTP transport after app startup.
    # Keep unrelated background requests out of those explicit scenarios.
    monkeypatch.setenv("PIG_MUSIC_PRELOAD", "false")

    # Legacy functional fixtures are deliberately unauthenticated and isolated.
    # Security tests explicitly revoke this bypass; runtime strips it.
    monkeypatch.setenv("PIG_MUSIC_TEST_LEGACY_API", "1")
