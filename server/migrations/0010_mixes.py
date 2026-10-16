"""Private daily mix editions and reference-retained temporary audio."""


def up(conn):
    for statement in (
        """CREATE TABLE mix_editions (
            id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, day TEXT NOT NULL, payload TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 0, retired_at REAL, lease_until REAL NOT NULL DEFAULT 0,
            UNIQUE(user_id,kind,day))""",
        "CREATE INDEX mix_editions_user ON mix_editions(user_id,active)",
        """CREATE TABLE mix_audio (
            key TEXT PRIMARY KEY, filename TEXT NOT NULL, probe TEXT NOT NULL,
            bytes INTEGER NOT NULL, lease_until REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL)""",
        """CREATE TABLE mix_feedback (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL, PRIMARY KEY(user_id,key))""",
        """CREATE TABLE mix_listens (
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key TEXT NOT NULL, played_at INTEGER NOT NULL, event_id TEXT NOT NULL,
            PRIMARY KEY(user_id,event_id))""",
    ):
        conn.execute(statement)
