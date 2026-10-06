"""Ordered, persistent playlist membership, independent of the migration inventory."""

import json, uuid
from datetime import datetime, timezone
from .library import identifier
from .library import normalise


class Playlists:
    def __init__(self, store, user_id=None):
        self.store = store
        self.user_id = user_id

    def owner(self):
        if self.user_id:
            return self.user_id
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE role='owner' ORDER BY created_at LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def clause(self):
        identity = self.owner()
        if self.user_id:
            return " AND owner_id=?", (identity,)
        if identity:
            return " AND (owner_id=? OR owner_id IS NULL)", (identity,)
        return " AND owner_id IS NULL", ()

    def raw(self, playlist_id):
        clause, params = self.clause()
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM playlists WHERE id=?" + clause,
                (playlist_id, *params),
            ).fetchone()
        if not row:
            raise ValueError("Playlist not found.")
        return json.loads(row[0])

    def detail(self, playlist_id):
        playlist = self.raw(playlist_id)
        entries = []
        index = self.store.index
        if self.user_id:
            from .matching import LibraryIndex

            index = LibraryIndex(self.store.user_libraries.projection(self.user_id))
        for position, track in enumerate(playlist["tracks"]):
            result = index.match(track)
            match = result.track
            entries.append(
                {
                    **track,
                    "entry_id": playlist_id + ":" + str(position),
                    "position": position,
                    "status": result.status,
                    "match_kind": result.kind,
                    "saved_id": match["id"] if match else None,
                    "saved_track": match,
                }
            )
        sync = self.store.read_document("plex-playlist:" + playlist_id)
        return {
            **playlist,
            "entries": entries,
            "track_count": len(entries),
            "available_count": sum(e["status"] == "downloaded" for e in entries),
            "review_count": sum(e["status"] == "review" for e in entries),
            "plex": {
                k: sync.get(k)
                for k in (
                    "status",
                    "available_count",
                    "pending_count",
                    "repeated_count",
                    "updated_at",
                )
            },
        }

    def list(self):
        clause, params = self.clause()
        with self.store.connect() as conn:
            ids = [
                r[0]
                for r in conn.execute(
                    "SELECT id FROM playlists WHERE 1=1" + clause, params
                )
            ]
        return [
            {
                k: v
                for k, v in self.detail(i).items()
                if k not in {"tracks", "track_ids", "entries"}
            }
            for i in ids
        ]

    def review(self, playlist_id):
        playlist = self.raw(playlist_id)
        source = {
            "tracks": playlist["tracks"],
            "source_name": playlist["name"],
            "imported_at": playlist["imported_at"],
        }
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES ('migration',?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (json.dumps(source),),
            )
            conn.execute("DELETE FROM selections")
            conn.execute("DELETE FROM migration_decisions")
        self.store.source = source
        migration = self.store.migration()
        self.store.update_selection(
            [
                t["id"]
                for a in migration["albums"]
                for t in a["tracks"]
                if t["status"] != "downloaded"
            ],
            True,
        )
        return self.store.migration()

    def create(self, name):
        name = name.strip()
        if not name or len(name) > 100:
            raise ValueError("Choose a playlist name up to 100 characters.")
        identity = str(uuid.uuid4())
        payload = {
            "id": identity,
            "name": name,
            "tracks": [],
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "source": "pig-music",
        }
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO playlists(id,payload,owner_id) VALUES (?,?,?)",
                (identity, json.dumps(payload), self.owner()),
            )
            if self.owner():
                from .user_library import bump

                bump(conn, self.owner())
        return self.detail(identity)

    def membership(self, track):
        key = identifier(
            "song-membership",
            track.get("musicbrainz_release_id") or "",
            track.get("musicbrainz_recording_id") or "",
            *[
                normalise(track.get(k, ""))
                for k in ("artist", "title", "album", "album_artist")
            ],
        )
        return key

    def same_song(self, left, right):
        from .matching import same_song

        return same_song(left, right)

    def add(self, playlist_id, track):
        clause, params = self.clause()
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload FROM playlists WHERE id=?" + clause,
                (playlist_id, *params),
            ).fetchone()
            if not row:
                raise ValueError("Playlist not found.")
            payload = json.loads(row[0])
            key = self.membership(track)
            if not any(self.same_song(t, track) for t in payload["tracks"]):
                payload["tracks"].append(track)
            conn.execute(
                "UPDATE playlists SET payload=? WHERE id=?",
                (json.dumps(payload), playlist_id),
            )
            if self.owner():
                from .user_library import bump

                bump(conn, self.owner())
        return self.detail(playlist_id)

    def favourite(self, track, value=None):
        owner_id = self.owner()
        identity = "pig-favourites:" + owner_id if owner_id else "pig-favourites"
        key = self.membership(track)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload FROM playlists WHERE id=?", (identity,)
            ).fetchone()
            payload = (
                json.loads(row[0])
                if row
                else {
                    "id": identity,
                    "name": "Favourites",
                    "tracks": [],
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "source": "pig-music",
                    "favourites": True,
                }
            )
            exists = any(self.same_song(t, track) for t in payload["tracks"])
            if value is None:
                return {"favourited": exists}
            payload["tracks"] = [
                t for t in payload["tracks"] if not self.same_song(t, track)
            ]
            if value:
                payload["tracks"].append(track)
            conn.execute(
                "INSERT INTO playlists(id,payload,owner_id) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (identity, json.dumps(payload), owner_id),
            )
            if owner_id:
                from .user_library import bump

                bump(conn, owner_id)
        return {"favourited": value}
