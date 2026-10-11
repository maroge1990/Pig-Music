"""Add a durable, disposable device-copy cache without touching library rows."""


def up(conn):
    conn.execute(
        "CREATE TABLE device_copies (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
    )
