def up(conn):
    conn.execute(
        "CREATE TABLE sync_entities(user_id TEXT NOT NULL REFERENCES users(id), entity TEXT NOT NULL, entity_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(user_id,entity,entity_id))"
    )
    conn.execute(
        "CREATE TABLE sync_revisions(sequence INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES users(id), revision TEXT NOT NULL, signature TEXT NOT NULL, captured_at INTEGER NOT NULL, payload TEXT NOT NULL, UNIQUE(user_id,revision))"
    )
    conn.execute("CREATE INDEX sync_revision_user ON sync_revisions(user_id,sequence)")
