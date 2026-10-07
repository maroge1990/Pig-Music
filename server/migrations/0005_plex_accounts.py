def up(conn):
    conn.execute(
        "CREATE TABLE plex_accounts (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, token_encrypted TEXT NOT NULL, plex_user_label TEXT NOT NULL)"
    )
