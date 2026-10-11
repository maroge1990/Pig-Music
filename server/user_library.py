"""Personal projections over shared immutable household metadata.

Membership and request beneficiaries are durable; projection caches only retain
references and small per-user lists. User data never changes household identity.
"""

from collections import OrderedDict, defaultdict
import hashlib
import json
import time
from urllib.parse import urlsplit

from .library import identifier, normalise
from .media import public_settings
from .lifecycle import coordinated

TRACK_FIELDS = frozenset(
    {
        "id",
        "title",
        "artist",
        "album",
        "album_artist",
        "year",
        "track_number",
        "disc_number",
        "duration",
        "codec",
        "bitrate",
        "album_id",
        "cover_sha",
        "cover_url",
        "available",
        "musicbrainz_release_id",
        "musicbrainz_recording_id",
        "isrcs",
        "genre",
    }
)


class SearchChanged(ValueError):
    pass


def track_dto(track):
    source_revision = hashlib.sha256(
        json.dumps(
            [
                track.get("id"),
                track.get("sha256"),
                track.get("size_bytes"),
                track.get("mtime_ns"),
            ]
        ).encode()
    ).hexdigest()
    return {
        **{key: value for key, value in track.items() if key in TRACK_FIELDS},
        "source_sha": track.get("sha256"),
        "source_revision": source_revision,
        "server_state": track.get("server_state")
        or ("in_library" if track.get("available", True) else "failed"),
    }


def bump(conn, user_id):
    conn.execute(
        "INSERT INTO membership_versions(user_id,revision) VALUES (?,1) ON CONFLICT(user_id) DO UPDATE SET revision=revision+1",
        (user_id,),
    )


def initialise_owner(store):
    with store.library_lock, store.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        owner = conn.execute(
            "SELECT id FROM users WHERE role='owner' AND disabled=0 ORDER BY created_at LIMIT 1"
        ).fetchone()
        if (
            not owner
            or conn.execute(
                "SELECT 1 FROM documents WHERE name='household-membership-initialised'"
            ).fetchone()
        ):
            return
        identity = owner[0]
        now = int(time.time())
        for album in store.library["albums"]:
            conn.executemany(
                "INSERT OR IGNORE INTO library_members VALUES (?,?,?,'migration')",
                [(identity, t["id"], now) for t in album["tracks"]],
            )
        conn.execute(
            "UPDATE playlists SET owner_id=? WHERE owner_id IS NULL", (identity,)
        )
        favourites = conn.execute(
            "SELECT payload FROM playlists WHERE id='pig-favourites'"
        ).fetchone()
        if favourites:
            renamed = "pig-favourites:" + identity
            payload = {**json.loads(favourites[0]), "id": renamed}
            conn.execute(
                "UPDATE playlists SET id=?,payload=? WHERE id='pig-favourites'",
                (renamed, json.dumps(payload)),
            )
            legacy = conn.execute(
                "SELECT payload FROM documents WHERE name='plex-playlist:pig-favourites'"
            ).fetchone()
            if legacy:
                conn.execute(
                    "INSERT OR IGNORE INTO documents VALUES (?,?)",
                    ("plex-playlist:" + renamed, legacy[0]),
                )
        for key, payload in conn.execute("SELECT id,payload FROM queue").fetchall():
            value = json.loads(payload)
            if "requested_by" not in value:
                value["requested_by"] = [identity]
                conn.execute(
                    "UPDATE queue SET payload=? WHERE id=?", (json.dumps(value), key)
                )
        for key, raw in conn.execute(
            "SELECT name,payload FROM documents WHERE name LIKE 'artist-job:%'"
        ).fetchall():
            if key.count(":") == 1:
                artist_id = key.split(":")[1]
                value = {**json.loads(raw), "id": artist_id, "user_id": identity}
                conn.execute(
                    "INSERT OR IGNORE INTO documents VALUES (?,?)",
                    ("artist-job:" + identity + ":" + artist_id, json.dumps(value)),
                )
        bump(conn, identity)
        conn.execute(
            "INSERT INTO documents VALUES ('household-membership-initialised',?)",
            (json.dumps({"owner_id": identity}),),
        )


class UserLibrary:
    def __init__(self, store):
        self.store = store
        self.cache = OrderedDict()
        self.artwork_cache = {}
        self.lookup_cache = {}

    def artwork_access(self, user_id):
        """Artwork a person may load, indexed once per projection revision."""
        data = self.projection(user_id)
        cached = self.artwork_cache.get(user_id)
        if cached and cached[0] == data["revision"]:
            return cached[1]
        access = {
            "items": {
                kind: {item["id"]: item for item in data[kind]}
                for kind in ("artists", "albums")
            },
            "paths": {
                urlsplit(item.get(field) or "").path
                for kind in ("artists", "albums", "tracks")
                for item in data[kind]
                for field in ("cover_url", "fallback_cover_url")
                if item.get(field)
            },
        }
        self.artwork_cache[user_id] = (data["revision"], access)
        return access

    def projection(self, user_id):
        initialise_owner(self.store)
        with self.store.library_lock, self.store.connect() as conn:
            membership_revision = conn.execute(
                "SELECT revision FROM membership_versions WHERE user_id=?", (user_id,)
            ).fetchone()
            # The person is part of the validator: equal membership counters
            # for two people must never let a shared browser reuse a 304.
            signature = (
                user_id,
                self.store.library_revision,
                membership_revision[0] if membership_revision else 0,
                json.dumps(public_settings(self.store), sort_keys=True),
            )
            previous = self.cache.get(user_id)
            if previous and previous[0] == signature:
                self.cache.move_to_end(user_id)
                return previous[1]
            members = {
                r[0]
                for r in conn.execute(
                    "SELECT track_id FROM library_members WHERE user_id=?", (user_id,)
                )
            }
            albums = []
            for album in self.store.library["albums"]:
                tracks = [track for track in album["tracks"] if track["id"] in members]
                if tracks:
                    albums.append(
                        {
                            **album,
                            "tracks": tracks,
                            "track_count": len(tracks),
                            "duration": sum(t.get("duration", 0) for t in tracks),
                            "codecs": sorted(
                                {t.get("codec", "") for t in tracks if t.get("codec")}
                            ),
                        }
                    )
            by_album = {a["id"]: a for a in albums}
            album_by_track = {t["id"]: a["id"] for a in albums for t in a["tracks"]}
            all_tracks = {t["id"]: t for a in albums for t in a["tracks"]}
            credited_by_artist = defaultdict(list)
            artist_ids = {}
            for track in all_tracks.values():
                name = track.get("artist", "")
                if name not in artist_ids:
                    artist_ids[name] = identifier("artist", normalise(name))
                credited_by_artist[artist_ids[name]].append(track)
            artists = []
            for artist in self.store.library["artists"]:
                owned = [i for i in artist["album_ids"] if i in by_album]
                credited = credited_by_artist[artist["id"]]
                associated = {t["id"] for t in credited}
                associated.update(
                    t["id"] for key in owned for t in by_album[key]["tracks"]
                )
                if associated:
                    representative = (
                        owned[0] if owned else album_by_track[credited[0]["id"]]
                    )
                    artists.append(
                        {
                            **artist,
                            "album_ids": owned,
                            "album_count": len(owned),
                            "track_count": len(associated),
                            "compilation_only": not bool(owned),
                            "cover_album_id": representative,
                            "cover_url": by_album[representative].get("cover_url"),
                            "fallback_cover_url": by_album[representative].get(
                                "cover_url"
                            ),
                        }
                    )
            revision = hashlib.sha256(json.dumps(signature).encode()).hexdigest()
            value = {
                "artists": artists,
                "albums": albums,
                "tracks": list(all_tracks.values()),
                "stats": {
                    "tracks": len(all_tracks),
                    "artists": len(artists),
                    **{
                        kind + "s": sum(a["category"] == kind for a in albums)
                        for kind in ("album", "compilation", "soundtrack", "musical")
                    },
                },
                "revision": revision,
                "media": public_settings(self.store),
                "snapshot": {
                    "captured_at": self.store.library.get("snapshot", {}).get(
                        "captured_at"
                    )
                },
            }
            self.cache[user_id] = (signature, value)
            self.cache.move_to_end(user_id)
            while len(self.cache) > 8:
                self.cache.popitem(last=False)
            return value

    def search(self, user_id, query, offset=0, limit=100, revision=None):
        if offset < 0 or offset > 1000000 or not 1 <= limit <= 200:
            raise ValueError("Invalid search page")
        query = normalise(query[:150])
        with self.store.library_lock:
            data = self.projection(user_id)
            if revision is not None and revision != data["revision"]:
                raise SearchChanged("Search changed. Refresh before loading more.")
            personal_ids = {t["id"] for t in data["tracks"]}

            def matches(track):
                return query and query in normalise(
                    track["artist"] + " " + track["title"] + " " + track["album"]
                )

            tracks = [t for t in data["tracks"] if matches(t)]
            household = [
                t
                for album in self.store.library["albums"]
                for t in album["tracks"]
                if t["id"] not in personal_ids
                and t.get("available", True)
                and matches(t)
            ]
            artists = [
                a for a in data["artists"] if query and query in normalise(a["name"])
            ]
            albums = [
                a
                for a in data["albums"]
                if query and query in normalise(a["artist"] + " " + a["title"])
            ]
            end = offset + limit
            return {
                "tracks": [track_dto(t) for t in tracks[offset:end]],
                "household_tracks": [
                    {
                        **track_dto(t),
                        "household_available": True,
                        "server_state": "household_available",
                    }
                    for t in household[offset:end]
                ],
                "artists": artists[offset:end],
                "albums": [
                    {k: v for k, v in a.items() if k not in {"tracks", "cover_key"}}
                    for a in albums[offset:end]
                ],
                "total_tracks": len(tracks),
                "total_household_tracks": len(household),
                "total_artists": len(artists),
                "total_albums": len(albums),
                "offset": offset,
                "next_offset": (
                    end
                    if end < max(len(tracks), len(household), len(artists), len(albums))
                    else None
                ),
                "revision": data["revision"],
            }

    def lookup(self, user_id, songs):
        """Which of these songs are already in a person's library.

        A recording ID is decisive; otherwise title and artist must both match.
        """
        data = self.projection(user_id)
        cached = self.lookup_cache.get(user_id)
        if not cached or cached[0] != data["revision"]:
            recordings, names = {}, {}
            for track in data["tracks"]:
                if track.get("available", True) is False:
                    continue
                if track.get("musicbrainz_recording_id"):
                    recordings.setdefault(track["musicbrainz_recording_id"], track)
                names.setdefault(
                    (normalise(track["title"]), normalise(track["artist"])), track
                )
            cached = (data["revision"], recordings, names)
            self.lookup_cache[user_id] = cached
        _, recordings, names = cached
        found = []
        for song in songs:
            track = recordings.get(song.get("musicbrainz_recording_id") or "") or (
                names.get((normalise(song["title"]), normalise(song["artist"])))
            )
            found.append(track_dto(track) if track else None)
        return found

    def recently_added(self, user_id, limit=12):
        """Albums most recently added to a person's library.

        One-off bootstrap attribution ('migration') is not "recent" music.
        """
        projection = self.projection(user_id)
        album_for = {
            track["id"]: album
            for album in projection["albums"]
            for track in album["tracks"]
        }
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT track_id FROM library_members WHERE user_id=? "
                "AND source != 'migration' ORDER BY added_at DESC LIMIT 2000",
                (user_id,),
            ).fetchall()
        albums, seen = [], set()
        for (track_id,) in rows:
            album = album_for.get(track_id)
            if album and album["id"] not in seen:
                seen.add(album["id"])
                albums.append(
                    {k: v for k, v in album.items() if k not in {"tracks", "cover_key"}}
                )
                if len(albums) == limit:
                    break
        return {"albums": albums, "revision": projection["revision"]}

    def summary(self, user_id):
        projection = self.projection(user_id)
        from .playlists import Playlists

        return {
            **{key: value for key, value in projection.items() if key != "tracks"},
            "albums": [
                {k: v for k, v in a.items() if k not in {"tracks", "cover_key"}}
                for a in projection["albums"]
            ],
            "playlist_count": len(Playlists(self.store, user_id).list()),
        }

    def contains(self, user_id, track_id):
        initialise_owner(self.store)
        with self.store.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM library_members WHERE user_id=? AND track_id=?",
                    (user_id, track_id),
                ).fetchone()
                is not None
            )

    @coordinated
    def add(self, user_id, track_ids, source="household-add"):
        initialise_owner(self.store)
        with self.store.library_lock, self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            available = {
                t["id"]
                for a in self.store.library["albums"]
                for t in a["tracks"]
                if t.get("available", True)
            }
            removing = {
                json.loads(raw)["track_id"]
                for (raw,) in conn.execute(
                    "SELECT payload FROM documents WHERE name LIKE 'removed:%'"
                )
                if json.loads(raw).get("status") in {"removing", "removed"}
            }
            available -= removing
            if not set(track_ids).issubset(available):
                raise ValueError("One or more files are unavailable")
            changed = 0
            for identity in set(track_ids):
                changed += conn.execute(
                    "INSERT OR IGNORE INTO library_members VALUES (?,?,?,?)",
                    (user_id, identity, int(time.time()), source),
                ).rowcount
            if changed:
                bump(conn, user_id)
                from .household_policy import HouseholdPolicy

                HouseholdPolicy(self.store).membership_changed(conn, track_ids)
        return {"added": changed, "revision": self.projection(user_id)["revision"]}

    def clear_requests(self, user_id):
        """Dismiss this person's finished history, retaining files and shared jobs."""
        cleared = 0
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT id,payload FROM queue WHERE status IN ('completed','downloaded','failed','cancelled') "
                "AND EXISTS (SELECT 1 FROM json_each(queue.payload,'$.requested_by') WHERE value=?)",
                (user_id,),
            ).fetchall()
            for key, raw in rows:
                payload = json.loads(raw)
                payload["requested_by"] = [
                    value
                    for value in payload.get("requested_by", [])
                    if value != user_id
                ]
                conn.execute(
                    "UPDATE queue SET payload=? WHERE id=?", (json.dumps(payload), key)
                )
                cleared += 1
        return {"cleared": cleared}

    @coordinated
    def cancel_request(self, user_id, request_id):
        """Withdraw one beneficiary; shared downloads continue for remaining people."""
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status,payload FROM queue WHERE id=?", (request_id,)
            ).fetchone()
            if not row or user_id not in json.loads(row[1]).get("requested_by", []):
                raise LookupError("Request not found")
            if row[0] not in {
                "waiting_for_sources",
                "searching",
                "downloading",
                "validating",
            }:
                raise ValueError("Only active requests can be cancelled")
            payload = json.loads(row[1])
            payload["requested_by"] = [
                identity for identity in payload["requested_by"] if identity != user_id
            ]
            remaining = bool(payload["requested_by"])
            conn.execute(
                "UPDATE queue SET payload=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (json.dumps(payload), row[0] if remaining else "cancelled", request_id),
            )
        return {"cancelled": True, "continues_for_others": remaining}

    def retry_request(self, user_id, request_id):
        """Requeue one of this person's failed or cancelled requests."""
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            result = conn.execute(
                "UPDATE queue SET status='waiting_for_sources',updated_at=CURRENT_TIMESTAMP "
                "WHERE id=? AND status IN ('failed','cancelled') AND EXISTS "
                "(SELECT 1 FROM json_each(queue.payload,'$.requested_by') WHERE value=?)",
                (request_id, user_id),
            )
            if result.rowcount:
                return {"retried": True}
            mine = conn.execute(
                "SELECT 1 FROM queue WHERE id=? AND EXISTS "
                "(SELECT 1 FROM json_each(queue.payload,'$.requested_by') WHERE value=?)",
                (request_id, user_id),
            ).fetchone()
        if not mine:
            raise LookupError("Request not found")
        raise ValueError("Only failed or cancelled requests can be retried")

    def queue(self, user_id, offset=0, limit=200):
        if offset < 0 or not 1 <= limit <= 200:
            raise ValueError("Invalid request page bounds")
        where = "EXISTS (SELECT 1 FROM json_each(queue.payload,'$.requested_by') WHERE value=?)"
        with self.store.connect() as conn:
            total = conn.execute(
                "SELECT count(*) FROM queue WHERE " + where, (user_id,)
            ).fetchone()[0]
            in_progress = conn.execute(
                "SELECT count(*) FROM queue WHERE status IN ('waiting_for_sources','searching','downloading','validating','importing') AND "
                + where,
                (user_id,),
            ).fetchone()[0]
            records = conn.execute(
                "SELECT id,payload,status,created_at,updated_at FROM queue WHERE "
                + where
                + " ORDER BY CASE WHEN status IN ('waiting_for_sources','searching','downloading','validating','importing') THEN 0 ELSE 1 END,created_at DESC,id LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        result = {
            "library_revision": self.store.library_revision,
            "downloads_enabled": self.store.download_settings()["enabled"],
            "total": total,
            "active": in_progress,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None,
            "items": [],
        }
        allowed = TRACK_FIELDS | {
            "status",
            "created_at",
            "updated_at",
            "progress",
            "quality_profile",
            "received_bytes",
            "total_bytes",
            "error",
        }
        for key, raw, status, created, updated in records:
            job = {
                "id": key,
                **json.loads(raw),
                "status": status,
                "created_at": created,
                "updated_at": updated,
            }
            result["items"].append({k: v for k, v in job.items() if k in allowed})
        for job in result["items"]:
            active = job["status"] in {
                "waiting_for_sources",
                "searching",
                "downloading",
                "validating",
                "importing",
            }
            job["server_state"] = (
                "requested"
                if active
                else (
                    "in_library"
                    if job["status"] == "completed"
                    else "failed" if job["status"] == "failed" else "not_in_library"
                )
            )
            total = job.get("total_bytes") or 0
            job["request_progress"] = (
                min(1, (job.get("received_bytes") or 0) / total)
                if active and total
                else None
            )
            if job.get("error"):
                job["error"] = "Acquisition failed. Retry or ask your administrator."
        return result

    @coordinated
    def import_playlists(self, user_id, raw):
        from .library import parse_apple

        source = parse_apple(raw)
        by_track = {t["id"]: track_dto(t) for t in source["tracks"]}
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for playlist in source.get("playlists", []):
                identity = identifier("user-playlist", user_id, playlist["id"])
                previous = conn.execute(
                    "SELECT payload FROM playlists WHERE id=? AND owner_id=?",
                    (identity, user_id),
                ).fetchone()
                revision = (
                    json.loads(previous[0]).get("revision", 0) + 1 if previous else 0
                )
                payload = {
                    **playlist,
                    "revision": revision,
                    "id": identity,
                    "tracks": [by_track[i] for i in playlist["track_ids"]],
                    "imported_at": source["imported_at"],
                }
                conn.execute(
                    "INSERT INTO playlists(id,payload,owner_id) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                    (identity, json.dumps(payload), user_id),
                )
            conn.execute(
                "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                ("migration:" + user_id, json.dumps(source)),
            )
            bump(conn, user_id)
        return {
            "playlists": len(source.get("playlists", [])),
            "tracks": len(source["tracks"]),
        }

    def request(self, user_id, tracks):
        prepared = []
        for track in tracks:
            result = self.store.index.match(track)
            prepared.append({**track, "status": result.status})
        return self.store.submit_catalogue(prepared, user_id=user_id)

    def history(self, user_id, events, session_id):
        now = int(time.time())
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            added = 0
            for event in events:
                if not conn.execute(
                    "SELECT 1 FROM library_members WHERE user_id=? AND track_id=?",
                    (user_id, event["track_id"]),
                ).fetchone():
                    raise ValueError("A played track is outside your library")
                if (
                    event["played_at"] > now + 300
                    or event["played_at"] < now - 30 * 86400
                ):
                    raise ValueError(
                        "Playback event timestamp is outside the accepted window"
                    )
                added += conn.execute(
                    "INSERT OR IGNORE INTO play_events(user_id,track_id,played_at,seconds,device_session_id,event_id) VALUES (?,?,?,?,?,?)",
                    (
                        user_id,
                        event["track_id"],
                        event["played_at"],
                        event["seconds"],
                        session_id,
                        event["event_id"],
                    ),
                ).rowcount
        return {"recorded": added}
