"""Retire Plex playlist sync: per-person tokens and sync state are discarded."""


def up(conn):
    conn.execute("DROP TABLE IF EXISTS plex_accounts")
    conn.execute(
        "DELETE FROM documents WHERE name LIKE 'plex-status%' OR name LIKE 'plex-playlist:%' OR name='plex-refresh-required'"
    )
