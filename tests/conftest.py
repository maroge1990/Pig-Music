import pytest


@pytest.fixture(autouse=True)
def isolate_startup_enrichment(monkeypatch):
    # Provider tests supply their own mock HTTP transport after app startup.
    # Keep unrelated background requests out of those explicit scenarios.
    monkeypatch.setenv("PIG_MUSIC_PRELOAD", "false")
