"""Atomic native edit receipts allow safe replay after a connection drops."""


def up(conn):
    conn.execute(
        "CREATE TABLE native_mutations (user_id TEXT NOT NULL REFERENCES users(id), operation_id TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(user_id,operation_id))"
    )
