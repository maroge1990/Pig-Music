"""Add accounts and revocable sessions without re-attributing existing music."""

STATEMENTS = (
    """CREATE TABLE users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('owner','member')),
        password_hash TEXT, password_changed_at INTEGER, disabled INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL)""",
    """CREATE TABLE sessions (
        id TEXT PRIMARY KEY, public_id TEXT NOT NULL UNIQUE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('web','device')), device_name TEXT NOT NULL,
        platform TEXT NOT NULL, created_at INTEGER NOT NULL, last_seen_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL, revoked_at INTEGER)""",
    "CREATE INDEX sessions_user ON sessions(user_id)",
    """CREATE TABLE setup_codes (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        code_hash TEXT NOT NULL UNIQUE, expires_at INTEGER NOT NULL, used_at INTEGER)""",
    """CREATE TABLE auth_events (
        id INTEGER PRIMARY KEY, at INTEGER NOT NULL, user_id TEXT,
        event TEXT NOT NULL, ip TEXT NOT NULL, detail TEXT NOT NULL)""",
    """CREATE TABLE login_attempts (
        key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_started INTEGER NOT NULL,
        lockouts INTEGER NOT NULL, locked_until INTEGER NOT NULL, updated_at INTEGER NOT NULL)""",
)


def up(conn):
    for statement in STATEMENTS:
        conn.execute(statement)
