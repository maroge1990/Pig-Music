"""Private, reproducible daily listening editions prepared before publication."""

import asyncio
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import time
import uuid
import httpx
from zoneinfo import ZoneInfo

from .catalogue import background_metadata, credit
from .home import release_choice
from .media import chart_region, settings, track_file
from .mix_cache import MixCache, MixDownloader, song_key
from .playlists import Playlists
from .api_models import TrackDTO

log = logging.getLogger("pig_music.mixes")
PASS_SECONDS = 240
SHUTDOWN_SECONDS = 10
KINDS = {
    "daily": "Daily blend",
    "back": "Back in the mix",
    "artist": "Around an artist",
    "genre": "Genre rotation",
    "popular": "In rotation",
}


def choose(tracks, count, salt, history=None, weights=None, previous=None):
    """Daily weighted shuffle with diversity; identity is never guessed from title."""
    history = history or {}
    weights = weights or {}
    previous = previous or set()
    unique = {
        t.get("musicbrainz_recording_id") or song_key(t): t for t in reversed(tracks)
    }
    now = time.time()

    def rank(track):
        key = song_key(track)
        random = (int(hashlib.sha256((salt + key).encode()).hexdigest(), 16) + 1) / (
            2**256 + 1
        )
        return (
            history.get(key, 0) > now - 7 * 86400,
            key in previous,
            -(random ** (1 / weights.get(key, 1))),
        )

    ordered = sorted(unique.values(), key=rank)
    result, artists = [], Counter()
    while ordered and len(result) < count:
        candidate = next(
            (
                t
                for t in ordered
                if artists[t["artist"]] < 2
                and (not result or result[-1]["artist"] != t["artist"])
            ),
            None,
        )
        if candidate is None:
            break
        ordered.remove(candidate)
        result.append(candidate)
        artists[candidate["artist"]] += 1
    return result


class Mixes:
    def __init__(self, store, home, runtime):
        self.store, self.home, self.runtime = store, home, runtime
        self.cache = MixCache(store)
        store.mix_cache = self.cache
        store.mixes = self
        self.stopping = asyncio.Event()
        self.task = None

    def day(self):
        return datetime.now(ZoneInfo(self.cache.settings()["timezone"])).date()

    def start(self, client):
        self.task = asyncio.create_task(self.run(client))

    async def close(self):
        self.stopping.set()
        if not self.task:
            return
        # Workers poll the stop flag, but a provider call can outlast the
        # supervisor's 25 s grace; durable cursors make cancellation safe.
        try:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=SHUTDOWN_SECONDS)
        except TimeoutError:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def run(self, client):
        background_metadata.set(True)
        while not self.stopping.is_set():
            try:
                await self.prepare_pass(client)
            except Exception:
                log.exception("Mix preparation failed; retaining ready editions")
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=60)
            except TimeoutError:
                pass

    def people(self):
        with self.store.connect() as conn:
            return [r[0] for r in conn.execute("SELECT id FROM users WHERE disabled=0")]

    def history(self, user_id, tracks):
        with self.store.connect() as conn:
            recent = dict(
                conn.execute(
                    "SELECT track_id,MAX(played_at) FROM play_events WHERE user_id=? GROUP BY track_id",
                    (user_id,),
                )
            )
            history = dict(
                conn.execute(
                    "SELECT key,MAX(played_at) FROM mix_listens WHERE user_id=? GROUP BY key",
                    (user_id,),
                )
            )
        for track in tracks:
            history[song_key(track)] = max(
                history.get(song_key(track), 0), recent.get(track.get("id"), 0)
            )
        return history

    def hidden(self, user_id):
        with self.store.connect() as conn:
            return {
                r[0]
                for r in conn.execute(
                    "SELECT key FROM mix_feedback WHERE user_id=?", (user_id,)
                )
            }

    def exposure(self, user, day):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM mix_editions WHERE user_id=? AND kind='daily' AND day<? ORDER BY day DESC LIMIT 1",
                (user, str(day)),
            ).fetchone()
        return {song_key(t) for t in json.loads(row[0])["tracks"]} if row else set()

    def favourite_weights(self, user):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM playlists WHERE id=? AND owner_id=?",
                ("pig-favourites:" + user, user),
            ).fetchone()
        return (
            {song_key(t): 3 for t in json.loads(row[0]).get("tracks", [])}
            if row
            else {}
        )

    async def candidates(self, client, projection):
        """Use public artist/tag seeds only; personal listening never leaves PigMusic."""
        seeds = await self.home.seeds(client, projection, {"unavailable": False})
        records = []
        for identity, name in seeds[:3]:
            if self.stopping.is_set():
                break
            data, _ = await self.home.feed(
                client,
                "lb-radio/artist/" + identity,
                mode="easy",
                max_similar_artists=8,
                max_recordings_per_artist=4,
                pop_begin=20,
                pop_end=100,
            )
            seed_records = []
            pools = [items for items in data.values() if isinstance(items, list)]
            for position in range(4):
                for items in pools:
                    if position < len(items) and isinstance(items[position], dict):
                        seed_records.append(
                            (
                                items[position].get("recording_mbid"),
                                "Similar to " + name,
                                "related",
                            )
                        )
            records.extend(seed_records[:6])
        labels = {
            t["genre"].casefold(): t["genre"]
            for t in projection.get("tracks", [])
            if t.get("genre")
        }
        genres = Counter(
            genre
            for artist, genre in {
                (t["artist"].casefold(), t["genre"].casefold())
                for t in projection.get("tracks", [])
                if t.get("genre")
            }
        )
        themes = [
            key
            for key, count in sorted(
                genres.items(), key=lambda item: (-item[1], item[0])
            )[:3]
        ]
        ordinal = date.fromisoformat(
            projection.get("mix_day") or str(self.day())
        ).toordinal()
        genre = labels[themes[ordinal % len(themes)]] if themes else None
        if genre:
            data, _ = await self.home.feed(
                client,
                "lb-radio/tags",
                tag=genre,
                operator="or",
                count=6,
                pop_begin=20,
                pop_end=100,
            )
            records.extend(
                (r.get("recording_mbid"), genre, "genre")
                for r in data.get("recordings", [])[:6]
                if isinstance(r, dict)
            )
        # Current regional charts are a separate signal from lifetime popularity.
        popular = await self.home.popular(client)
        candidates, seen = [], set()
        for recording, reason, bucket in records[:100]:
            if self.stopping.is_set() or len(candidates) >= 24:
                break
            if not self.home.identity(recording):
                continue
            if recording in seen:
                if bucket == "genre":
                    for item in candidates:
                        if item["musicbrainz_recording_id"] == recording:
                            item["genre"] = genre
                continue
            seen.add(recording)
            try:
                data = await self.home.catalogue.get(
                    client,
                    "recording/" + recording,
                    inc="releases+artist-credits+isrcs",
                )
                release = release_choice(data.get("releases", []))
                if not release or not credit(data.get("artist-credit", [])):
                    continue
                candidates.append(
                    {
                        "title": data["title"],
                        "artist": credit(data["artist-credit"]),
                        "album": release["title"],
                        "duration": (data.get("length") or 0) / 1000,
                        "musicbrainz_recording_id": recording,
                        "musicbrainz_release_id": release["id"],
                        "isrcs": data.get("isrcs", []),
                        "reason": reason,
                        "bucket": bucket,
                        "genre": genre if bucket == "genre" else None,
                    }
                )
            except (ValueError, KeyError, httpx.HTTPError):
                continue
        # Chart songs only enter a personalised popular mix with an artist/genre affinity.
        artist_names = {
            t["artist"].casefold() for t in projection.get("tracks", []) + candidates
        }
        for item in popular.get("songs", []):
            if (
                item.get("release_id")
                and item.get("artist", "").casefold() in artist_names
            ):
                candidates.append(
                    {
                        "title": item["name"],
                        "artist": item["artist"],
                        "album": item.get("album", ""),
                        "musicbrainz_recording_id": item["id"],
                        "musicbrainz_release_id": item["release_id"],
                        "bucket": "popular",
                        "reason": "Popular in "
                        + chart_region(settings(self.store)).upper(),
                    }
                )
        # A recording gets one allocation bucket, even when it is both a radio
        # recommendation and in today's chart. Retain the richer recording data.
        unique = {}
        for track in candidates:
            key = track.get("musicbrainz_recording_id") or song_key(track)
            if key not in unique:
                unique[key] = track
            elif track["bucket"] == "popular":
                unique[key].update(bucket="popular", reason=track["reason"])
            if track.get("genre"):
                unique[key]["genre"] = track["genre"]
        return list(unique.values()), genre

    def edition(self, user_id, kind, day):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT id,payload,active FROM mix_editions WHERE user_id=? AND kind=? AND day=?",
                (user_id, kind, str(day)),
            ).fetchone()
        return row

    def stage(self, user_id, kind, day, title, reason, tracks):
        identity = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"pig-mix:v1:{user_id}:{kind}:{day}")
        )
        payload = {
            "title": title,
            "reason": reason,
            "tracks": tracks,
            # The intended songs stay visible to Admin after failures shorten tracks.
            "planned": tracks,
            "state": "preparing",
            "attempts": 0,
            "retry_at": 0,
        }
        with self.store.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mix_editions(id,user_id,kind,day,payload) VALUES (?,?,?,?,?)",
                (identity, user_id, kind, str(day), json.dumps(payload)),
            )
        return identity

    def publish(self, identity, tracks, today):
        with self.store.lifecycle_lock, self.store.connect() as conn:
            row = conn.execute(
                "SELECT user_id,kind,day,payload FROM mix_editions WHERE id=?",
                (identity,),
            ).fetchone()
            payload = {**json.loads(row[3]), "tracks": tracks, "state": "ready"}
            available_keys = {song_key(t) for t in tracks}
            payload["failures"] = {
                key: error
                for key, error in payload.get("failures", {}).items()
                if key not in available_keys
            }
            payload.pop("blocked", None)
            active = row[2] <= str(today) and not row[1].startswith("saved:")
            if active:
                conn.execute(
                    "UPDATE mix_editions SET active=0,retired_at=? WHERE user_id=? AND kind=? AND active=1",
                    (time.time(), row[0], row[1]),
                )
            conn.execute(
                "UPDATE mix_editions SET payload=?,active=? WHERE id=?",
                (json.dumps(payload), int(active), identity),
            )
        log.info(
            "Mixes: published %s for %s on %s with %d of %d songs",
            payload["title"],
            row[0],
            row[2],
            len(tracks),
            len(payload.get("planned") or tracks),
        )

    def activate(self, today):
        with self.store.lifecycle_lock, self.store.connect() as conn:
            conn.execute(
                "UPDATE mix_editions SET active=0,retired_at=? WHERE user_id IN (SELECT id FROM users WHERE disabled=1) AND (active=1 OR retired_at IS NULL)",
                (time.time(),),
            )
            conn.execute(
                "UPDATE mix_editions SET retired_at=? WHERE active=0 AND retired_at IS NULL AND day<?",
                (time.time(), str(today)),
            )
            for identity, user, kind, payload in conn.execute(
                "SELECT id,user_id,kind,payload FROM mix_editions WHERE day=? AND active=0 AND retired_at IS NULL AND user_id IN (SELECT id FROM users WHERE disabled=0)",
                (str(today),),
            ).fetchall():
                if json.loads(payload).get("state") != "ready":
                    continue
                conn.execute(
                    "UPDATE mix_editions SET active=0,retired_at=? WHERE user_id=? AND kind=? AND active=1",
                    (time.time(), user, kind),
                )
                conn.execute("UPDATE mix_editions SET active=1 WHERE id=?", (identity,))

    async def prepare_pass(self, client):
        today = self.day()
        await asyncio.to_thread(self.activate, today)
        # Reclaim retired audio before checking capacity for new editions.
        await asyncio.to_thread(self.cache.cleanup)
        for user in await asyncio.to_thread(self.people):
            if self.stopping.is_set():
                return
            try:
                await asyncio.wait_for(
                    self.prepare_person(client, user, today), timeout=PASS_SECONDS
                )
            except TimeoutError:
                log.info(
                    "Mix pass time budget reached; resuming persisted work next pass"
                )
            except Exception:
                log.exception(
                    "Preparing one person's mixes failed; other members continue"
                )
        await asyncio.to_thread(self.cache.cleanup)

    async def prepare_person(self, client, user, today):
        deadline = time.monotonic() + PASS_SECONDS
        current = await asyncio.to_thread(self.edition, user, "daily", today)
        upcoming = await asyncio.to_thread(
            self.edition, user, "daily", today + timedelta(days=1)
        )
        if (
            current
            and upcoming
            and all(
                json.loads(row[1])["state"] == "ready" for row in (current, upcoming)
            )
        ):
            # Readiness belongs to each family, not just the lead Daily blend.
            for day in (today, today + timedelta(days=1)):
                await self.prepare_staged(user, day, today, deadline)
            return
        projection = await asyncio.to_thread(self.store.user_libraries.projection, user)
        owned = [t for t in projection["tracks"] if t.get("available", True)]
        hidden = await asyncio.to_thread(self.hidden, user)
        owned = [t for t in owned if song_key(t) not in hidden]
        if not owned:
            # An imported inventory is still a taste signal even before its
            # files arrive. With no taste at all, label regional charts honestly.
            public = None
            for day in (today, today + timedelta(days=1)):
                kind = "daily" if projection["tracks"] else "popular"
                if not await asyncio.to_thread(self.edition, user, kind, day):
                    if projection["tracks"]:
                        pool, _ = await self.candidates(
                            client, {**projection, "mix_day": str(day)}
                        )
                        title, reason = (
                            KINDS["daily"],
                            "Discoveries inspired by your library",
                        )
                    else:
                        if public is None:
                            public = await self.home.popular(client)
                        pool = [
                            {
                                "title": t["name"],
                                "artist": t["artist"],
                                "album": t.get("album", ""),
                                "musicbrainz_recording_id": t["id"],
                                "musicbrainz_release_id": t["release_id"],
                            }
                            for t in public.get("songs", [])
                            if t.get("release_id")
                        ]
                        title = public.get("title") or (
                            "Popular in " + chart_region(settings(self.store)).upper()
                        )
                        reason = "Regional chart music. Add music to your library for personalised mixes."
                    tracks = choose(
                        [t for t in pool if song_key(t) not in hidden],
                        30,
                        f"{user}:{day}",
                        previous=await asyncio.to_thread(self.exposure, user, day),
                    )
                    if tracks:
                        await asyncio.to_thread(
                            self.stage, user, kind, day, title, reason, tracks
                        )
                await self.prepare_staged(user, day, today, deadline)
            return
        history = await asyncio.to_thread(self.history, user, owned)
        weights = await asyncio.to_thread(self.favourite_weights, user)
        # Give a new person a playable library mix before any external lookup.
        if not await asyncio.to_thread(self.edition, user, "back", today):
            tracks = choose(owned, 30, f"{user}:{today}:back", history)
            identity = await asyncio.to_thread(
                self.stage,
                user,
                "back",
                today,
                KINDS["back"],
                "Saved music worth another listen",
                tracks,
            )
            await asyncio.to_thread(self.publish, identity, tracks, today)
        for day in (today, today + timedelta(days=1)):
            if self.stopping.is_set():
                return
            if not await asyncio.to_thread(self.edition, user, "daily", day):
                candidates, genre = await self.candidates(
                    client, {**projection, "mix_day": str(day)}
                )
                candidates = [t for t in candidates if song_key(t) not in hidden]
                owned_keys = {
                    t.get("musicbrainz_recording_id") or song_key(t) for t in owned
                }
                discoveries = [
                    t
                    for t in candidates
                    if (t.get("musicbrainz_recording_id") or song_key(t))
                    not in owned_keys
                ]
                salt = f"{user}:{day}"
                previous = await asyncio.to_thread(self.exposure, user, day)
                related = choose(
                    [t for t in discoveries if t["bucket"] != "popular"],
                    9,
                    salt,
                    history,
                    previous=previous,
                )
                popular_tracks = choose(
                    [t for t in discoveries if t["bucket"] == "popular"],
                    30,
                    salt + ":popular",
                    history,
                )
                chart = choose(popular_tracks, 3, salt, history, previous=previous)
                familiar = choose(
                    owned,
                    max(18, 30 - len(related) - len(chart)),
                    salt,
                    history,
                    weights,
                    previous,
                )
                daily = choose(
                    familiar + related + chart, 30, salt, history, previous=previous
                )
                await asyncio.to_thread(
                    self.stage,
                    user,
                    "daily",
                    day,
                    KINDS["daily"],
                    (
                        "Your favourites, fresh discoveries and a little of what's current"
                        if related and chart
                        else (
                            "Your library and fresh discoveries"
                            if related
                            else (
                                "Your library and current chart discoveries"
                                if chart
                                else "A fresh selection from your library"
                            )
                        )
                    ),
                    daily,
                )
                await asyncio.to_thread(
                    self.stage,
                    user,
                    "back",
                    day,
                    KINDS["back"],
                    "Saved music worth another listen",
                    choose(owned, 30, salt + ":back", history),
                )
                seeded = [
                    t
                    for t in owned
                    if any(
                        c.get("reason") == "Similar to " + t["artist"]
                        for c in candidates
                    )
                ]
                artist = choose(seeded or owned, 1, salt)[0]["artist"]
                neighbourhood = [
                    t
                    for t in candidates
                    if ("Similar to " + artist).casefold()
                    == t.get("reason", "").casefold()
                ]
                artist_tracks = choose(
                    [t for t in owned if t["artist"] == artist] + neighbourhood,
                    25,
                    salt,
                    history,
                )
                if len({t["artist"].casefold() for t in artist_tracks}) > 1:
                    await asyncio.to_thread(
                        self.stage,
                        user,
                        "artist",
                        day,
                        "Around " + artist,
                        "An artist you saved and their musical neighbourhood",
                        artist_tracks,
                    )
                if genre:
                    await asyncio.to_thread(
                        self.stage,
                        user,
                        "genre",
                        day,
                        genre + " rotation",
                        "A genre from your library",
                        choose(
                            [
                                t
                                for t in owned + candidates
                                if (t.get("genre") or "").casefold() == genre.casefold()
                            ],
                            30,
                            salt,
                            history,
                        ),
                    )
                if popular_tracks:
                    await asyncio.to_thread(
                        self.stage,
                        user,
                        "popular",
                        day,
                        KINDS["popular"],
                        "Current chart music close to your taste",
                        popular_tracks,
                    )
            await self.prepare_staged(user, day, today, deadline)

    async def prepare_staged(self, user, day, today, deadline=None):
        deadline = deadline if deadline is not None else time.monotonic() + PASS_SECONDS
        rows = await asyncio.to_thread(self.pending, user, day)
        for identity, raw, kind in rows:
            payload = json.loads(raw)
            if payload["state"] == "ready" or payload.get("retry_at", 0) > time.time():
                continue
            if self.stopping.is_set() or time.monotonic() >= deadline:
                return
            payload["worked_at"] = time.time()
            payload.pop("blocked", None)
            hidden = (
                await asyncio.to_thread(self.hidden, user)
                if not kind.startswith("saved:")
                else set()
            )
            payload["tracks"] = [
                t for t in payload["tracks"] if song_key(t) not in hidden
            ]
            await asyncio.to_thread(self.update, identity, payload)
            deferred = False
            # Resume across passes/restarts. A repeatedly failing early song
            # cannot prevent later songs from ever getting a download attempt.
            cursor = payload.get("cursor", 0)
            for position in range(cursor, len(payload["tracks"])):
                track = payload["tracks"][position]
                if self.stopping.is_set() or time.monotonic() >= deadline:
                    return
                try:
                    await asyncio.to_thread(self.cache.available, track)
                except FileNotFoundError:
                    blocked = await asyncio.to_thread(self.blocked)
                    if blocked:
                        deferred = True
                        payload["blocked"] = blocked
                        continue
                    downloader = await asyncio.to_thread(
                        MixDownloader,
                        self.cache,
                        self.runtime,
                        lambda: self.stopping.is_set() or time.monotonic() >= deadline,
                    )
                    if not await asyncio.to_thread(downloader.fetch, track):
                        deferred |= downloader.result != "failed"
                        if downloader.result == "failed":
                            payload.setdefault("failures", {})[song_key(track)] = (
                                downloader.error or "No matching recording available"
                            )
                            log.info(
                                "Mixes: %s by %s unavailable for %s: %s",
                                track.get("title"),
                                track.get("artist"),
                                payload["title"],
                                payload["failures"][song_key(track)],
                            )
                        else:
                            payload["blocked"] = (
                                downloader.error
                                or "Preparation deferred: downloads paused or cache space reserved"
                            )
                        if time.monotonic() >= deadline:
                            await asyncio.to_thread(self.update, identity, payload)
                            return
                        payload["cursor"] = position + 1
                        await asyncio.to_thread(self.update, identity, payload)
                        continue
                payload.get("failures", {}).pop(song_key(track), None)
                payload["cursor"] = position + 1
                await asyncio.to_thread(self.update, identity, payload)
            # Successful audio is durable; rebuild readiness after a resumed pass.
            prepared = []
            for track in payload["tracks"]:
                try:
                    await asyncio.to_thread(self.cache.available, track)
                    prepared.append(track)
                except FileNotFoundError:
                    pass
            payload["cursor"] = 0
            if deferred:
                payload["retry_at"] = time.time() + 60
                await asyncio.to_thread(self.update, identity, payload)
                continue
            if (
                len(prepared) == len(payload["tracks"])
                or payload.get("attempts", 0) >= 2
            ):
                if prepared:
                    await asyncio.to_thread(self.publish, identity, prepared, today)
                else:
                    payload["retry_at"] = time.time() + 3600
                    await asyncio.to_thread(self.update, identity, payload)
            else:
                payload.update(
                    attempts=payload.get("attempts", 0) + 1, retry_at=time.time() + 300
                )
                await asyncio.to_thread(self.update, identity, payload)

    def pending(self, user, day):
        with self.store.connect() as conn:
            return conn.execute(
                "SELECT id,payload,kind FROM mix_editions WHERE user_id=? AND day=? AND (retired_at IS NULL OR lease_until>?) ORDER BY kind LIKE 'saved:%' DESC,COALESCE(json_extract(payload,'$.worked_at'),0),id",
                (user, str(day), time.time()),
            ).fetchall()

    def blocked(self):
        """Why automatic preparation must wait, or None when it may download."""
        # Explicit library requests always get first use of sources.
        with self.store.connect() as conn:
            busy = conn.execute(
                "SELECT 1 FROM queue WHERE status IN ('queued','searching','downloading','validating') LIMIT 1"
            ).fetchone()
        if busy:
            return "Explicit library downloads take priority"
        if not self.store.download_settings()["enabled"]:
            return "Downloads are paused"
        if not self.cache.room():
            return "Cache budget or disk reserve reached"
        return None

    def update(self, identity, payload):
        with self.store.connect() as conn:
            conn.execute(
                "UPDATE mix_editions SET payload=? WHERE id=?",
                (json.dumps(payload), identity),
            )

    def entry(self, user, track_id, playback=False):
        try:
            prefix, identity, position = track_id.split(":")
            if prefix != "mix":
                raise ValueError()
            with self.store.connect() as conn:
                row = conn.execute(
                    "SELECT payload,active,retired_at,lease_until FROM mix_editions WHERE id=? AND user_id=?",
                    (identity, user),
                ).fetchone()
            if not row:
                raise ValueError()
            payload = json.loads(row[0])
            # Old queues get a bounded lease across a rotation; old metadata alone
            # never grants access to another person's files or an arbitrary path.
            if playback and (
                payload["state"] != "ready"
                or (
                    not row[1]
                    and (row[2] is None or row[2] < time.time() - 6 * 3600)
                    and row[3] < time.time()
                )
            ):
                raise ValueError()
            index = int(position)
            if index < 0:
                raise ValueError()
            return payload["tracks"][index]
        except (ValueError, IndexError, TypeError):
            raise LookupError("Mix song not found") from None

    def playback(self, user, track_id):
        track = self.entry(user, track_id, playback=True)
        identity = track_id.split(":")[1]
        with self.store.lifecycle_lock, self.store.connect() as conn:
            until = time.time() + 6 * 3600
            conn.execute(
                "UPDATE mix_editions SET lease_until=? WHERE id=?", (until, identity)
            )
            payload = json.loads(
                conn.execute(
                    "SELECT payload FROM mix_editions WHERE id=?", (identity,)
                ).fetchone()[0]
            )
            for item in payload["tracks"]:
                conn.execute(
                    "UPDATE mix_audio SET lease_until=MAX(lease_until,?) WHERE key=?",
                    (until, song_key(item)),
                )
            return self.cache.available(track)

    def reference(self, user, track):
        """A saved playlist can reuse audio from this person's rotating edition."""
        key = song_key(track)
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT id,payload FROM mix_editions WHERE user_id=? AND (active=1 OR lease_until>?)",
                (user, time.time()),
            ).fetchall()
        for identity, raw in rows:
            for index, item in enumerate(json.loads(raw)["tracks"]):
                if song_key(item) == key:
                    return f"mix:{identity}:{index}"
        return None

    def list(self, user):
        with self.store.connect() as conn:
            members = {
                r[0]
                for r in conn.execute(
                    "SELECT track_id FROM library_members WHERE user_id=?", (user,)
                )
            }
            rows = conn.execute(
                "SELECT id,kind,day,payload FROM mix_editions WHERE user_id=? AND active=1 ORDER BY CASE kind WHEN 'daily' THEN 0 WHEN 'back' THEN 4 ELSE 2 END,kind",
                (user,),
            ).fetchall()
            preparing = bool(
                conn.execute(
                    "SELECT 1 FROM mix_editions WHERE user_id=? AND day=? AND active=0 AND retired_at IS NULL AND json_extract(payload,'$.state')='preparing' LIMIT 1",
                    (user, str(self.day())),
                ).fetchone()
            )
        hidden = self.hidden(user)
        result = []
        for identity, kind, day, raw in rows:
            if "edition:" + identity in hidden:
                continue
            payload = json.loads(raw)
            tracks = []
            for index, track in enumerate(payload["tracks"]):
                if song_key(track) in hidden:
                    continue
                try:
                    self.cache.available(track)
                except FileNotFoundError:
                    continue
                library_id = None
                match = self.store.index.match(track).track
                if match:
                    try:
                        track_file(self.store, match["id"])
                        library_id = match["id"]
                    except FileNotFoundError:
                        pass
                tracks.append(
                    TrackDTO(
                        **{
                            **track,
                            "id": f"mix:{identity}:{index}",
                            "server_state": (
                                "in_library"
                                if library_id in members
                                else (
                                    "household_available"
                                    if library_id
                                    else "not_in_library"
                                )
                            ),
                            "library_track_id": library_id,
                            "available": True,
                            "cover_url": (
                                f"/api/catalogue/artwork/release/{track['musicbrainz_release_id']}"
                                if track.get("musicbrainz_release_id")
                                else track.get("cover_url")
                            ),
                        }
                    )
                )
            if tracks:
                result.append(
                    {
                        "id": identity,
                        "kind": kind,
                        "day": day,
                        "title": payload["title"],
                        "reason": payload["reason"],
                        "tracks": tracks,
                    }
                )
        return {"mixes": result, "preparing": preparing}

    def inspect(self, user):
        """Owner diagnostics: every live edition with each intended song's state."""
        with self.store.connect() as conn:
            person = conn.execute(
                "SELECT display_name FROM users WHERE id=?", (user,)
            ).fetchone()
            if not person:
                raise LookupError("Person not found")
            rows = conn.execute(
                "SELECT id,kind,day,active,payload FROM mix_editions WHERE user_id=? AND (retired_at IS NULL OR active=1) ORDER BY day,CASE kind WHEN 'daily' THEN 0 WHEN 'back' THEN 4 ELSE 2 END,kind",
                (user,),
            ).fetchall()
        hidden = self.hidden(user)
        now = time.time()
        editions = []
        for identity, kind, day, active, raw in rows:
            payload = json.loads(raw)
            published = {song_key(t) for t in payload["tracks"]}
            failures = payload.get("failures", {})
            preparing = payload["state"] != "ready"
            cursor = payload.get("cursor", 0)
            songs = []
            for position, track in enumerate(
                payload.get("planned") or payload["tracks"]
            ):
                key = song_key(track)
                status, detail = "waiting", None
                match = self.store.index.match(track).track
                try:
                    if not match:
                        raise FileNotFoundError()
                    track_file(self.store, match["id"])
                    status = "library"
                except (FileNotFoundError, ValueError, OSError):
                    try:
                        self.cache.file(key)
                        status = "cached"
                    except FileNotFoundError:
                        pass
                if key in hidden:
                    status = "hidden"
                elif status == "waiting" and key in failures:
                    status, detail = "failed", failures[key]
                elif status == "waiting" and not preparing and key not in published:
                    status = "dropped"
                elif status == "waiting" and preparing and position == cursor:
                    status = "next"
                songs.append(
                    {
                        "title": track.get("title"),
                        "artist": track.get("artist"),
                        "album": track.get("album"),
                        "reason": track.get("reason"),
                        "status": status,
                        "detail": detail,
                    }
                )
            retry = payload.get("retry_at", 0)
            editions.append(
                {
                    "id": identity,
                    "kind": kind,
                    "day": day,
                    "title": payload["title"],
                    "reason": payload.get("reason"),
                    "state": payload["state"],
                    "active": bool(active),
                    "attempts": payload.get("attempts", 0),
                    "retry_at": retry if preparing and retry > now else None,
                    "worked_at": payload.get("worked_at"),
                    "blocked": payload.get("blocked") if preparing else None,
                    "published": len(payload["tracks"]) if not preparing else None,
                    "songs": songs,
                }
            )
        return {"person": person[0], "editions": editions}

    def hide_edition(self, user, identity):
        with self.store.lifecycle_lock, self.store.connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM mix_editions WHERE id=? AND user_id=?", (identity, user)
            ).fetchone():
                raise LookupError("Mix not found")
            conn.execute(
                "INSERT OR IGNORE INTO mix_feedback VALUES (?,?)",
                (user, "edition:" + identity),
            )
            conn.execute(
                "UPDATE mix_editions SET active=0,retired_at=COALESCE(retired_at,?) WHERE id=?",
                (time.time(), identity),
            )

    def queue_saved(self, user, requested):
        """Explicit playback of saved mix metadata grants temporary preparation.

        The canonical song must still belong to this person's saved edition;
        arbitrary catalogue requests never gain a cache-download entitlement.
        """
        wanted = song_key(requested)
        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM playlists WHERE owner_id=? AND json_extract(payload,'$.source')='mix'",
                (user,),
            ).fetchall()
        song = next(
            (
                t
                for (raw,) in rows
                for t in json.loads(raw)["tracks"]
                if song_key(t) == wanted
            ),
            None,
        )
        if song is None:
            return None
        identity = self.stage(
            user,
            "saved:" + wanted,
            self.day(),
            "Saved mix playback",
            "Prepared from your saved edition",
            [song],
        )
        with self.store.lifecycle_lock, self.store.connect() as conn:
            payload = json.loads(
                conn.execute(
                    "SELECT payload FROM mix_editions WHERE id=?", (identity,)
                ).fetchone()[0]
            )
            try:
                self.cache.available(song)
                payload["state"] = "ready"
            except FileNotFoundError:
                payload["state"] = "preparing"
            conn.execute(
                "UPDATE mix_editions SET active=0,retired_at=COALESCE(retired_at,?),lease_until=?,payload=? WHERE id=?",
                (time.time(), time.time() + 6 * 3600, json.dumps(payload), identity),
            )
        return f"mix:{identity}:0"

    async def restore(self, user, track):
        identity = await asyncio.to_thread(self.queue_saved, user, track)
        if not identity:
            return None
        song = self.entry(user, identity)
        try:
            await asyncio.to_thread(self.cache.available, song)
        except FileNotFoundError:
            deadline = time.monotonic() + 180
            worker = await asyncio.to_thread(
                MixDownloader,
                self.cache,
                self.runtime,
                lambda: self.stopping.is_set() or time.monotonic() >= deadline,
            )
            if not await asyncio.to_thread(worker.fetch, song):
                await asyncio.to_thread(
                    self.saved_failure, identity, song, worker.result, worker.error
                )
                raise ValueError(
                    "This saved mix song is waiting for a download. Check that downloads are enabled and cache space is available, then try again."
                )
        await asyncio.to_thread(
            self.publish, identity.split(":")[1], [song], self.day()
        )
        return identity

    def saved_failure(self, identity, song, result, error):
        edition = identity.split(":")[1]
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM mix_editions WHERE id=?", (edition,)
            ).fetchone()
        if not row:
            return
        payload = json.loads(row[0])
        if result == "failed":
            payload.setdefault("failures", {})[song_key(song)] = (
                error or "No matching full recording available"
            )
            payload["attempts"] = payload.get("attempts", 0) + 1
        else:
            payload["blocked"] = (
                error
                or "Preparation deferred: downloads paused or cache space reserved"
            )
        payload["retry_at"] = time.time() + (300 if result == "failed" else 60)
        self.update(edition, payload)

    def hide(self, user, track_id):
        track = self.entry(user, track_id)
        with self.store.connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO mix_feedback VALUES (?,?)",
                (user, song_key(track)),
            )

    def save(self, user, identity):
        with self.store.lifecycle_lock, self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload,day FROM mix_editions WHERE id=? AND user_id=?",
                (identity, user),
            ).fetchone()
            if not row or json.loads(row[0])["state"] != "ready":
                raise LookupError("Mix not found")
            payload = json.loads(row[0])
            hidden = {
                r[0]
                for r in conn.execute(
                    "SELECT key FROM mix_feedback WHERE user_id=?", (user,)
                )
            }
            playlist_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "saved-mix:" + identity))
            tracks = [
                {
                    k: v
                    for k, v in t.items()
                    if k not in {"id", "reason", "bucket", "relative_path"}
                }
                for t in payload["tracks"]
                if song_key(t) not in hidden
            ]
            conn.execute(
                "INSERT OR IGNORE INTO playlists(id,payload,owner_id) VALUES (?,?,?)",
                (
                    playlist_id,
                    json.dumps(
                        {
                            "id": playlist_id,
                            "name": payload["title"] + " · " + row[1],
                            "tracks": tracks,
                            "revision": 0,
                            "source": "mix",
                            "imported_at": datetime.now().isoformat(),
                        }
                    ),
                    user,
                ),
            )
            from .user_library import bump

            bump(conn, user)
        return Playlists(self.store, user).detail(playlist_id)
