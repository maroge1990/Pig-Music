import importlib
import sqlite3

import pytest

from server.migrations import migrate
from server.store import Store


def schema(conn):
    return list(
        conn.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    )


def test_fresh_and_existing_schema_match_and_rows_survive(tmp_path):
    fresh = sqlite3.connect(tmp_path / "fresh.sqlite3")
    legacy = sqlite3.connect(tmp_path / "legacy.sqlite3")
    baseline = importlib.import_module("server.migrations.0001_baseline")
    baseline.up(legacy)
    legacy.execute(
        "INSERT INTO documents VALUES ('preferences','{\"theme\":\"dark\"}')"
    )
    legacy.execute("INSERT INTO selections VALUES ('track-a')")
    legacy.execute("INSERT INTO playlists VALUES ('playlist-a','{}')")
    legacy.commit()
    migrate(fresh)
    migrate(legacy)
    assert schema(fresh) == schema(legacy)
    assert list(legacy.execute("SELECT * FROM selections")) == [("track-a",)]
    assert list(legacy.execute("SELECT * FROM playlists")) == [("playlist-a", "{}")]
    assert list(legacy.execute("SELECT * FROM documents")) == [
        ("preferences", '{"theme":"dark"}')
    ]
    ledger = list(legacy.execute("SELECT * FROM schema_migrations"))
    migrate(legacy)
    assert list(legacy.execute("SELECT * FROM schema_migrations")) == ledger


def test_failed_migration_rolls_back_ddl_and_ledger(tmp_path, monkeypatch):
    migrations = importlib.import_module("server.migrations")
    baseline = importlib.import_module("server.migrations.0001_baseline")
    conn = sqlite3.connect(tmp_path / "rollback.sqlite3")

    def failed(c):
        c.execute("CREATE TABLE partial (id TEXT)")
        raise ValueError("fixture failure")

    monkeypatch.setattr(baseline, "up", failed)
    with pytest.raises(ValueError, match="fixture failure"):
        migrations.migrate(conn)
    assert schema(conn) == []


def test_unknown_future_schema_is_rejected_without_changes(tmp_path):
    conn = sqlite3.connect(tmp_path / "future.sqlite3")
    migrate(conn)
    conn.execute("INSERT INTO schema_migrations VALUES (99,'future')")
    conn.commit()
    original = list(conn.iterdump())
    with pytest.raises(RuntimeError, match="newer schema"):
        migrate(conn)
    assert list(conn.iterdump()) == original


def test_store_connections_enable_wal_and_foreign_keys(tmp_path):
    store = Store(tmp_path)
    with store.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
