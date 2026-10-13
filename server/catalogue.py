"""Cached MusicBrainz browsing; queue payloads are built from server metadata."""

import asyncio
from contextvars import ContextVar
import time
from uuid import UUID

from .library import normalise


def mbid(value):
    return str(UUID(value))


def credit(items):
    return (
        "".join(
            item.get("name", item.get("artist", {}).get("name", ""))
            + item.get("joinphrase", "")
            for item in items
            if isinstance(item, dict)
        )
        or "Unknown artist"
    )


def release_tracks(release):
    album_artist = credit(release.get("artist-credit", []))
    year = (
        int(release.get("date", "")[:4]) if release.get("date", "")[:4].isdigit() else 0
    )
    tracks = []
    for medium in release.get("media", []):
        for track in medium.get("tracks", []):
            recording = track.get("recording", {})
            tracks.append(
                {
                    "id": track["id"],
                    "title": track.get("title") or recording.get("title", ""),
                    "artist": credit(
                        track.get("artist-credit")
                        or recording.get("artist-credit")
                        or release.get("artist-credit", [])
                    ),
                    "album": release["title"],
                    "album_artist": album_artist,
                    "year": year,
                    "disc_number": medium.get("position", 1),
                    "track_number": track.get("position", 0),
                    "duration": (track.get("length") or recording.get("length") or 0)
                    / 1000,
                    "musicbrainz_release_id": release["id"],
                    "musicbrainz_recording_id": recording.get("id"),
                    "isrcs": recording.get("isrcs", []),
                }
            )
    return tracks


background_metadata = ContextVar("background_metadata", default=False)
# Set by the server warmer: cached answers this close to expiry are renewed
# now, so nobody ever waits on an expired cache.
warming = ContextVar("warming", default=False)
RENEW = 4 * 3600


def still_fresh(age, lifetime, margin=RENEW):
    return age < lifetime - (margin if warming.get() else 0)


class Catalogue:
    # MusicBrainz allows one request per second per client.
    min_interval = 1.05

    def __init__(self, store):
        self.store = store
        self.lock = asyncio.Lock()
        self.last_request = 0.0
        self.foreground_waiters = 0

    async def get(self, client, path, **params):
        key = "catalogue:" + path + repr(sorted(params.items()))
        cached = self.store.read_document(key)
        if cached and still_fresh(time.time() - cached["time"], 86400):
            return cached["data"]
        background = background_metadata.get()
        if not background:
            self.foreground_waiters += 1
        try:
            while background and self.foreground_waiters:
                await asyncio.sleep(0.05)
            async with self.lock:
                cached = self.store.read_document(key)
                if cached and still_fresh(time.time() - cached["time"], 86400):
                    return cached["data"]
                delay = max(
                    0, self.min_interval - (time.monotonic() - self.last_request)
                )
                if delay:
                    await asyncio.sleep(delay)
                self.last_request = time.monotonic()
                response = await client.get(
                    "https://musicbrainz.org/ws/2/" + path,
                    params={"fmt": "json", **params},
                )
                response.raise_for_status()
                data = response.json()
                import json

                with self.store.connect() as conn:
                    conn.execute(
                        "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                        (key, json.dumps({"time": time.time(), "data": data})),
                    )
                return data
        finally:
            if not background:
                self.foreground_waiters -= 1

    def presence(self, tracks):
        for track in tracks:
            match = self.store.index.match(track)
            track["status"] = match.status
            track["saved_id"] = match.track["id"] if match.track else None
            track["match_kind"] = match.kind
            track["presence_note"] = (
                "Matched local tags" if match.kind == "probable" else ""
            )

        return tracks


def edition_rank(release):
    text = normalise(release.get("disambiguation", "") + " " + release.get("title", ""))
    special = any(
        word in text.split()
        for word in (
            "deluxe",
            "expanded",
            "anniversary",
            "remastered",
            "remaster",
            "bonus",
            "atmos",
            "surround",
            "spatial",
        )
    )
    formats = {m.get("format", "") for m in release.get("media", [])}
    return (
        release.get("status") != "Official",
        special,
        0 if "Digital Media" in formats else 1 if "CD" in formats else 2,
        not bool(release.get("date")),
        release.get("date", "9999"),
        release.get("id", ""),
    )
