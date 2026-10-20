"""Songs the household has twice because another edition was not recognised.

Only PigMusic downloads are ever proposed for removal (never the NAS's own
files, never an explicitly chosen edition), always with another copy of the
same song kept. Removal goes through Trash, so it can be restored, and the
song's listeners gain the copy that stays.
"""

import json
import time
from collections import defaultdict

from .library import year_order
from .matching import flavour, primary_artist, same_length, song_key


def acquired(store):
    with store.connect() as conn:
        return {
            row[0]: json.loads(row[1])
            for row in conn.execute("SELECT id,payload FROM acquired")
        }


def find(store):
    """[{track, album, keeper, keeper_album}] for each removable duplicate."""
    downloads = acquired(store)
    songs = defaultdict(list)
    for album in store.library["albums"]:
        for track in album["tracks"]:
            if track.get("available") is not False:
                songs[(song_key(track), flavour(album["title"]))].append((album, track))

    def keep_rank(item):
        album, track = item
        return (
            track["id"] in downloads,
            primary_artist(album.get("artist")) != primary_artist(track["artist"]),
            -len(album["tracks"]),
            year_order(album.get("year")) or 9999,
            track["id"],
        )

    found = []
    for copies in songs.values():
        while len(copies) > 1:
            first = min(copies, key=keep_rank)
            same = [c for c in copies if same_length(c[1], first[1])]
            copies = [c for c in copies if c not in same]
            for album, track in same:
                if (
                    track is first[1]
                    or track["id"] not in downloads
                    or downloads[track["id"]].get("explicit_edition")
                ):
                    continue
                found.append(
                    {
                        "track": summary(track),
                        "album": album["title"],
                        "album_id": album["id"],
                        "keeper": summary(first[1]),
                        "keeper_album": first[0]["title"],
                    }
                )
    found.sort(
        key=lambda d: (d["track"]["artist"].casefold(), d["album"], d["track"]["title"])
    )
    return found


def summary(track):
    return {k: track.get(k) for k in ("id", "title", "artist", "album", "duration")}


def remove(store, recovery, track_ids):
    """Move the chosen duplicates to Trash, moving their listeners to the
    copy that stays. Songs no longer duplicated are left alone."""
    from .user_library import bump

    keepers = {d["track"]["id"]: d["keeper"]["id"] for d in find(store)}
    removed = skipped = 0
    for track_id in dict.fromkeys(track_ids):
        keeper = keepers.get(track_id)
        if not keeper:
            skipped += 1
            continue
        with store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for (user_id,) in conn.execute(
                "SELECT user_id FROM library_members WHERE track_id=?", (track_id,)
            ).fetchall():
                if conn.execute(
                    "INSERT OR IGNORE INTO library_members VALUES (?,?,?,'household-add')",
                    (user_id, keeper, int(time.time())),
                ).rowcount:
                    bump(conn, user_id)
        try:
            recovery.remove(track_id)
            removed += 1
        except (ValueError, OSError, FileNotFoundError):
            skipped += 1
    return {"removed": removed, "skipped": skipped}
