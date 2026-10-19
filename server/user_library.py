"""Personal projections over shared immutable household metadata.

Membership and request beneficiaries are durable; projection caches only retain
references and small per-user lists. User data never changes household identity.
"""

from collections import OrderedDict, defaultdict
import hashlib
import json
import re
import time
from urllib.parse import urlsplit

from .library import identifier, normalise
from .media import public_settings
from .quality import LABELS as QUALITY_LABELS
from .lifecycle import coordinated
from .playlists import MAX_PLAYLIST_ENTRIES

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


def _text(value):
    """SQLite's UTC "2026-10-19 07:00:00" as ISO 8601 with its zone."""
    text = str(value or "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", text):
        return text.replace(" ", "T") + "Z"
    return text


def _stamp(item):
    """Sortable creation order for a queue item (SQLite timestamp text)."""
    digits = re.sub(r"\D", "", _text(item.get("created_at")))
    return int(digits or 0)


def _quality(item):
    """What the file is (or was asked to be), in words: "FLAC", "MP3 320 kbps"."""
    codec = (item.get("codec") or "").upper()
    bitrate = item.get("bitrate_kbps") or item.get("bitrate")
    if codec in {"FLAC", "ALAC"}:
        return codec
    if codec and bitrate:
        return f"{codec} {round(bitrate)} kbps"
    profile = item.get("effective_quality") or item.get("quality_profile")
    return QUALITY_LABELS.get(profile, codec or None)


class SearchChanged(ValueError):
    pass


def stored_cover_sha(item):
    """Embedded art hash, else the hash of server-fetched art in the cover store.

    Native clients address artwork only by hash; albums without embedded art
    (catalogue covers fetched by the server) would otherwise never show one.
    """
    if item.get("cover_sha"):
        return item["cover_sha"]
    match = re.fullmatch(
        r"/api/artwork/([0-9a-f]{64})\.jpg", item.get("cover_url") or ""
    )
    return match[1] if match else None


def add_pending(albums, household_albums, pending):
    """Show requested songs in the album they will join, with their state.

    A request joins the person's album for its release (or title and artist),
    else the household album, else a new album named by the request. Returns
    {artist_id: (name, [album ids])} for albums that exist only as requests.
    """

    def key(album_artist, title):
        return normalise(album_artist or ""), normalise(title or "")

    personal = {a["id"]: a for a in albums}
    releases, titles = {}, {}
    for album in list(albums) + list(household_albums):
        if album.get("musicbrainz_release_id"):
            releases.setdefault(album["musicbrainz_release_id"], album["id"])
        titles.setdefault(key(album.get("artist"), album.get("title")), album["id"])
    household = {a["id"]: a for a in household_albums}
    extra = {}
    for job in sorted(
        pending, key=lambda j: (j.get("disc_number", 1), j.get("track_number", 0))
    ):
        album_artist = job.get("album_artist") or job["artist"]
        title = job.get("album") or job["title"]
        album_id = releases.get(job.get("musicbrainz_release_id")) or titles.get(
            key(album_artist, title)
        )
        if album_id is None:
            seed = job.get("musicbrainz_release_id") or "|".join(
                key(album_artist, title)
            )
            album_id = "requested-" + hashlib.sha256(seed.encode()).hexdigest()[:24]
            titles[key(album_artist, title)] = album_id
            if job.get("musicbrainz_release_id"):
                releases[job["musicbrainz_release_id"]] = album_id
        album = personal.get(album_id)
        if album is None:
            source = household.get(album_id)
            artist_id = (source or {}).get("artist_id") or identifier(
                "artist", normalise(album_artist)
            )
            album = {
                **(source or {}),
                "id": album_id,
                "title": (source or {}).get("title") or title,
                "artist": (source or {}).get("artist") or album_artist,
                "artist_id": artist_id,
                "year": (source or {}).get("year") or job.get("year") or 0,
                "category": (source or {}).get("category") or "album",
                "musicbrainz_release_id": (source or {}).get("musicbrainz_release_id")
                or job.get("musicbrainz_release_id"),
                "cover_sha": stored_cover_sha(source or {}),
                "tracks": [],
            }
            albums.append(album)
            personal[album_id] = album
            extra.setdefault(artist_id, (album["artist"], []))[1].append(album_id)
        position = (job.get("disc_number") or 1, job.get("track_number") or 0)
        if any(
            (t.get("disc_number") or 1, t.get("track_number") or 0) == position
            and position[1]
            or (
                job.get("musicbrainz_recording_id")
                and t.get("musicbrainz_recording_id") == job["musicbrainz_recording_id"]
            )
            for t in album["tracks"]
        ):
            continue
        album["tracks"].append(
            {
                **{k: job[k] for k in TRACK_FIELDS if k in job and k != "id"},
                "id": "request-" + job["id"],
                "album_id": album_id,
                "cover_url": album.get("cover_url"),
                "cover_sha": album.get("cover_sha"),
                "available": False,
                "server_state": "failed" if job["status"] == "failed" else "requested",
            }
        )
    for album in personal.values():
        if any(
            t.get("server_state") in {"requested", "failed"} for t in album["tracks"]
        ):
            album["tracks"].sort(
                key=lambda t: (t.get("disc_number") or 1, t.get("track_number") or 0)
            )
            album["track_count"] = len(album["tracks"])
            album["duration"] = sum(t.get("duration", 0) for t in album["tracks"])
    return extra


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
            pending = self.pending_requests(conn, user_id)
            signature += (sorted((job["id"], job["status"]) for job in pending),)
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
                cover_sha = stored_cover_sha(album)
                # Copies: the shared household library is never mutated.
                tracks = [
                    {
                        **track,
                        "album_id": album["id"],
                        "cover_url": album.get("cover_url"),
                        "cover_sha": track.get("cover_sha") or cover_sha,
                    }
                    for track in album["tracks"]
                    if track["id"] in members
                ]
                if tracks:
                    albums.append(
                        {
                            **album,
                            "cover_sha": cover_sha,
                            "tracks": tracks,
                            "track_count": len(tracks),
                            "duration": sum(t.get("duration", 0) for t in tracks),
                            "codecs": sorted(
                                {t.get("codec", "") for t in tracks if t.get("codec")}
                            ),
                        }
                    )
            extra_albums = add_pending(albums, self.store.library["albums"], pending)
            extra_ids = {i for _, ids in extra_albums.values() for i in ids}
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
            saved_artists = set()
            household_artists = list(self.store.library["artists"])
            known = {artist["id"] for artist in household_artists}
            # Artists whose only music here is still requested.
            for artist_id, (name, _) in extra_albums.items():
                if artist_id not in known:
                    household_artists.append(
                        {"id": artist_id, "name": name, "album_ids": []}
                    )
            for artist in household_artists:
                owned = [i for i in artist["album_ids"] if i in by_album]
                owned += [
                    i
                    for i in extra_albums.get(artist["id"], ("", []))[1]
                    if i not in owned
                ]
                credited = credited_by_artist[artist["id"]]
                associated = {t["id"] for t in credited}
                associated.update(
                    t["id"] for key in owned for t in by_album[key]["tracks"]
                )
                if associated & members:
                    saved_artists.add(artist["id"])
                if associated:
                    representative = (
                        owned[0] if owned else album_by_track[credited[0]["id"]]
                    )
                    # A household portrait (or its lazy alias) is not personal
                    # data; keep it rather than replacing it with album art.
                    portrait = (
                        artist.get("cover_url")
                        if artist.get("cover_url") != artist.get("fallback_cover_url")
                        else None
                    )
                    artists.append(
                        {
                            **artist,
                            "album_ids": owned,
                            "album_count": len(owned),
                            "track_count": len(associated),
                            "compilation_only": not bool(owned),
                            "cover_album_id": representative,
                            "cover_url": portrait
                            or by_album[representative].get("cover_url"),
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
                # Counts describe saved music; requested songs are not counted.
                "stats": {
                    "tracks": sum(t["id"] in members for t in all_tracks.values()),
                    "artists": len(saved_artists),
                    **{
                        kind
                        + "s": sum(
                            a["category"] == kind and a["id"] not in extra_ids
                            for a in albums
                        )
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

    def pending_requests(self, conn, user_id):
        """This person's requested songs that are not yet saved, newest state.

        Quality replacements of saved songs are not shown; cancelled and
        completed requests leave the projection.
        """
        jobs = []
        for request_id, status, raw in conn.execute(
            "SELECT id,status,payload FROM queue WHERE status IN "
            "('waiting_for_sources','searching','downloading','validating','importing','failed') "
            "AND EXISTS (SELECT 1 FROM json_each(queue.payload,'$.requested_by') WHERE value=?)",
            (user_id,),
        ):
            payload = json.loads(raw)
            if (
                payload.get("library_track_id")
                or not payload.get("title")
                or not payload.get("artist")
            ):
                continue
            jobs.append({**payload, "id": request_id, "status": status})
        return jobs

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
            "source",
            "effective_quality",
            "bitrate_kbps",
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

    def request_groups(self, user_id, offset=0, limit=50):
        """This person's requests, one entry per album request (a single song
        stands alone), newest first with unfinished ones on top.

        A song requested again after a failure appears once: the most
        advanced, then the newest, of its jobs.
        """
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid request page bounds")
        everything = self.queue(user_id, 0, 200)
        items = list(everything["items"])
        while len(items) < everything["total"]:
            more = self.queue(user_id, len(items), 200)["items"]
            if not more:
                break
            items += more
        rank = {"active": 0, "waiting": 1, "done": 2, "failed": 3}

        def phase(item):
            status = item["status"]
            if status in {"searching", "downloading", "validating", "importing"}:
                return "active"
            if status == "waiting_for_sources":
                return "waiting"
            return "done" if status in {"completed", "downloaded"} else "failed"

        groups = {}
        for item in items:
            artist = item.get("album_artist") or item.get("artist", "")
            album = item.get("album") or ""
            key = (
                ("album", normalise(artist), normalise(album))
                if album
                else ("song", item["id"])
            )
            group = groups.setdefault(key, {"key": key, "songs": {}})
            song = (
                normalise(item.get("title", "")),
                item.get("disc_number") or 1,
                item.get("track_number") or 0,
            )
            current = group["songs"].get(song)
            if current is None or (rank[phase(item)], -_stamp(item)) < (
                rank[phase(current)],
                -_stamp(current),
            ):
                group["songs"][song] = item
        result = []
        for group in groups.values():
            songs = sorted(
                group["songs"].values(),
                key=lambda i: (
                    i.get("disc_number") or 1,
                    i.get("track_number") or 0,
                    i.get("title", ""),
                ),
            )
            phases = [phase(i) for i in songs]
            first = songs[0]
            done = phases.count("done")
            partial = sum(
                i.get("request_progress") or 0
                for i, p in zip(songs, phases)
                if p == "active"
            )
            album = group["key"][0] == "album"
            result.append(
                {
                    "id": identifier("request-group", *group["key"]),
                    "kind": "album" if album else "song",
                    "title": first.get("album") if album else first.get("title", ""),
                    "artist": first.get("album_artist") or first.get("artist", ""),
                    "release_id": next(
                        (
                            i["musicbrainz_release_id"]
                            for i in songs
                            if i.get("musicbrainz_release_id")
                        ),
                        None,
                    ),
                    "state": min(phases, key=rank.get),
                    "songs": len(songs),
                    "done": done,
                    "active": phases.count("active"),
                    "waiting": phases.count("waiting"),
                    "failed": phases.count("failed"),
                    "progress": (done + partial) / len(songs),
                    "requested_at": min(_text(i.get("created_at")) for i in songs),
                    "updated_at": max(_text(i.get("updated_at")) for i in songs),
                    "items": [
                        {
                            **i,
                            "created_at": _text(i.get("created_at")),
                            "updated_at": _text(i.get("updated_at")),
                            "source": i.get("source"),
                            "quality": _quality(i),
                        }
                        for i in songs
                    ],
                }
            )
        result.sort(key=lambda g: g["updated_at"], reverse=True)
        result.sort(key=lambda g: g["state"] not in {"active", "waiting"})
        return {
            "total": len(result),
            "active": everything["active"],
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(result) else None,
            "downloads_enabled": everything["downloads_enabled"],
            "groups": result[offset : offset + limit],
        }

    @coordinated
    def import_playlists(self, user_id, raw):
        from .library import parse_apple

        source = parse_apple(raw)
        by_track = {t["id"]: track_dto(t) for t in source["tracks"]}
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for playlist in source.get("playlists", []):
                if len(playlist["track_ids"]) > MAX_PLAYLIST_ENTRIES:
                    raise ValueError(
                        f"“{playlist.get('name', 'A playlist')}” has more than "
                        "10,000 songs. Split it in Music, then import again."
                    )
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
        mix_tracks = {}
        for event in events:
            if event["track_id"].startswith("mix:"):
                try:
                    mix_tracks[event["track_id"]] = self.store.mixes.entry(
                        user_id, event["track_id"]
                    )
                except (LookupError, AttributeError):
                    raise ValueError("A played track is outside your library")
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            added = 0
            for event in events:
                if (
                    event["track_id"] not in mix_tracks
                    and not conn.execute(
                        "SELECT 1 FROM library_members WHERE user_id=? AND track_id=?",
                        (user_id, event["track_id"]),
                    ).fetchone()
                ):
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
                if event["track_id"] in mix_tracks:
                    from .mix_cache import song_key

                    conn.execute(
                        "INSERT OR IGNORE INTO mix_listens VALUES (?,?,?,?)",
                        (
                            user_id,
                            song_key(mix_tracks[event["track_id"]]),
                            event["played_at"],
                            event["event_id"],
                        ),
                    )
        return {"recorded": added}
