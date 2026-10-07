"""Personal quality preferences and the administrator's scan inbox."""


def up(conn):
    conn.execute(
        """CREATE TABLE quality_preferences (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        scope TEXT NOT NULL CHECK(scope IN ('system','artist','album')),
        item_id TEXT NOT NULL, preferred TEXT NOT NULL CHECK(preferred IN ('mp3_128','mp3_320','aac_256','lossless')),
        PRIMARY KEY(user_id,scope,item_id))"""
    )
    conn.execute(
        "CREATE TABLE unassigned_tracks (track_id TEXT PRIMARY KEY, discovered_at INTEGER NOT NULL)"
    )
