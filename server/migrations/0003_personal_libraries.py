"""Personal membership, playlists and history; bootstrap attribution is transactional."""

STATEMENTS = (
    """CREATE TABLE library_members (user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        track_id TEXT NOT NULL, added_at INTEGER NOT NULL,
        source TEXT NOT NULL CHECK(source IN ('migration','request','scan-assign','household-add','import')),
        PRIMARY KEY(user_id,track_id))""",
    "CREATE INDEX library_members_track ON library_members(track_id)",
    "ALTER TABLE playlists ADD COLUMN owner_id TEXT REFERENCES users(id)",
    "CREATE INDEX playlists_owner ON playlists(owner_id)",
    """CREATE TABLE membership_versions (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE play_events (id INTEGER PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        track_id TEXT NOT NULL,played_at INTEGER NOT NULL,seconds INTEGER NOT NULL,
        device_session_id TEXT NOT NULL,event_id TEXT NOT NULL,UNIQUE(user_id,event_id))""",
    "CREATE INDEX play_events_user ON play_events(user_id,played_at)",
    "CREATE TABLE user_preferences (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,payload TEXT NOT NULL)",
)


def up(conn):
    for statement in STATEMENTS:
        conn.execute(statement)
