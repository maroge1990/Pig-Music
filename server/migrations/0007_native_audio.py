"""Allow opt-in native preferences without changing existing rows or defaults."""


def up(conn):
    conn.execute(
        """CREATE TABLE quality_preferences_native (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        scope TEXT NOT NULL CHECK(scope IN ('system','artist','album')),
        item_id TEXT NOT NULL,
        preferred TEXT NOT NULL CHECK(preferred IN ('mp3_128','mp3_320','aac_256','lossless','native_standard')),
        PRIMARY KEY(user_id,scope,item_id))"""
    )
    conn.execute(
        "INSERT INTO quality_preferences_native SELECT user_id,scope,item_id,preferred FROM quality_preferences"
    )
    conn.execute("DROP TABLE quality_preferences")
    conn.execute("ALTER TABLE quality_preferences_native RENAME TO quality_preferences")
