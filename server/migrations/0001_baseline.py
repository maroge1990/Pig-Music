"""Baseline schema: preserve existing rows and create fresh installations."""

STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS documents (name TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS selections (track_id TEXT PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS migration_decisions (track_id TEXT PRIMARY KEY, decision TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS queue (\n                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL,\n                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n                )",
    "CREATE TABLE IF NOT EXISTS acquired (id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS album_categories (id TEXT PRIMARY KEY, category TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quality_versions (request_id TEXT PRIMARY KEY, track_id TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS quality_cleanup (request_id TEXT PRIMARY KEY, track_id TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS playlists (id TEXT PRIMARY KEY, payload TEXT NOT NULL)",
]


def up(conn):
    for statement in STATEMENTS:
        conn.execute(statement)
