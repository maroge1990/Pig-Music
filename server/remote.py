"""Optional remote listening; matching never removes version descriptions."""

import asyncio
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .library import normalise
from .downloader import FREEMP3CLOUD_RETRY_PAUSE, matches
from .vendor.jiosaavn import search_jiosaavn

# After JioSaavn's direct stream, in coverage order (14 October 2026 test).
# Lossless sources are never streamed.
RELAYED = ("zvu4no", "freemp3cloud", "youtube")
LABELS = {
    "jiosaavn": "JioSaavn",
    "zvu4no": "zvu4no",
    "freemp3cloud": "FreeMp3Cloud",
    "youtube": "YouTube",
}
MEDIA_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".opus": "audio/ogg"}
RELAY_SECONDS = 3600
RELAY_BYTES = 500_000_000


class RemoteAudio:
    """Short-lived source resolution cache; remote listening never queues a download."""

    def __init__(self, search=None, directory=None, runtime=None, relay_search=None):
        self.search = search or search_jiosaavn
        self.cache = {}
        self.slots = asyncio.Semaphore(3)
        # Other sources are fetched by the server into a short-lived cache and
        # served from this origin; without a directory only JioSaavn is used.
        self.directory = Path(directory) if directory else None
        self.runtime = runtime
        self.relay_search = relay_search
        self.relayed = {}
        self.fetched = {}

    @staticmethod
    def key(track):
        return (
            track.get("musicbrainz_release_id"),
            track.get("musicbrainz_recording_id"),
            track["artist"],
            track["title"],
            track["album"],
            track.get("duration"),
        )

    async def stream(self, client, track, user_id):
        """The first source with one confident match: JioSaavn's address, or
        a relay token for audio the server fetched from another source."""
        try:
            return {"url": await self.resolve(client, track), "source": "jiosaavn"}
        except (ValueError, KeyError, TypeError) as exc:
            failure = exc
        except (httpx.HTTPError, TimeoutError) as exc:
            failure = exc
        if self.directory is None:
            raise failure
        key = self.key(track)
        found = self.fetched.get(key)
        if not found or found[0] <= time.monotonic() or not found[1].is_file():
            found = None
            async with self.slots:
                for source in RELAYED:
                    try:
                        path = await asyncio.to_thread(self.fetch, source, track)
                    except Exception:  # One broken source must not stop the next.
                        continue
                    found = (time.monotonic() + RELAY_SECONDS, path, source)
                    self.fetched[key] = found
                    break
        if not found:
            raise failure
        token = secrets.token_urlsafe(24)
        self.relayed[token] = (found[0], found[1], user_id)
        return {"relay": token, "source": found[2]}

    def relay(self, token, user_id):
        """The cached file behind a token, only for the person it was made for."""
        entry = self.relayed.get(token)
        if not entry or entry[0] <= time.monotonic() or entry[2] != user_id:
            return None
        path = entry[1]
        return (path, MEDIA_TYPES[path.suffix]) if path.is_file() else None

    def fetch(self, source, track):
        from .audio import probe_file
        from .providers import REGISTRY
        from .providers.contracts import Context
        from .providers.legacy import search as legacy_search
        from .providers.network import transfer

        context = Context(
            "native_standard",
            deadline=time.monotonic() + (90 if source == "youtube" else 30),
        )
        context.max_bytes = 40_000_000
        if self.relay_search:
            candidates = self.relay_search(source, track)
        elif REGISTRY[source].adapter:
            candidates = self.runtime.search(source, track, context)
        else:
            query = track["artist"] + " " + track["title"]
            candidates = legacy_search(source, query, context)
            if not candidates and source == "freemp3cloud":
                # It silently answers empty when busy; acquisition retries once too.
                time.sleep(FREEMP3CLOUD_RETRY_PAUSE)
                candidates = legacy_search(source, query, context)
        # Acquisition's identity rules decide the match. These sites list one
        # recording several times, so take the best copy as downloads do:
        # formats every Apple player opens first, then the higher bitrate.
        found = [c for c in candidates if matches(track, c)]
        found = [c for c in found if REGISTRY[source].extension(c) in MEDIA_TYPES]
        if not found:
            raise ValueError("No recording matched.")
        candidate = min(
            found,
            key=lambda c: (
                REGISTRY[source].extension(c) == ".opus",
                c.get("quality") != "320kbps",
            ),
        )
        extension = REGISTRY[source].extension(candidate)
        self.prune()
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (secrets.token_hex(16) + extension)
        try:
            if REGISTRY[source].adapter:
                self.runtime.transfer(source, candidate, path, context)
            else:
                transfer(
                    candidate["source_url"],
                    REGISTRY[source].download_hosts,
                    path,
                    context,
                )
            probe = probe_file(path)
            expected = float(track.get("duration") or 0)
            if not probe or (expected and abs(probe["duration"] - expected) > 5):
                raise ValueError("The remote file was not the expected recording.")
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path

    def prune(self):
        """Keep the relay cache under an hour old and within its size budget."""
        if not self.directory or not self.directory.is_dir():
            return
        now = time.time()
        files = sorted(
            (p for p in self.directory.iterdir() if p.is_file()),
            key=lambda p: p.stat().st_mtime,
        )
        total = sum(p.stat().st_size for p in files)
        for path in files:
            if now - path.stat().st_mtime > RELAY_SECONDS or total > RELAY_BYTES:
                total -= path.stat().st_size
                path.unlink(missing_ok=True)
        live = time.monotonic()
        self.relayed = {k: v for k, v in self.relayed.items() if v[0] > live}
        self.fetched = {k: v for k, v in self.fetched.items() if v[0] > live}

    async def resolve(self, client, track):
        key = self.key(track)
        cached = self.cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        async with self.slots:
            results = await asyncio.wait_for(
                asyncio.to_thread(
                    self.search, track["artist"] + " " + track["title"], 40
                ),
                timeout=5,
            )
            candidates = [
                c
                for c in results
                if matches(track, c)
                and normalise(c.get("album", "")) == normalise(track["album"])
                and (
                    not track.get("isrcs")
                    or not c.get("isrc")
                    or c["isrc"] in track["isrcs"]
                )
            ]
            urls = {c.get("source_url"): c for c in candidates}
            if len(urls) != 1:
                raise ValueError(
                    "No unique remote recording matched this release. Downloading remains available."
                )
            url = next(iter(urls))
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or parsed.port not in {None, 443}
                or not (parsed.hostname or "").endswith(".saavncdn.com")
            ):
                raise ValueError("Remote source returned an unsupported audio address.")
            async with client.stream(
                "GET",
                url,
                headers={"Range": "bytes=0-31", "Accept": "audio/*"},
                timeout=3,
                follow_redirects=False,
            ) as stream:
                if stream.status_code not in {200, 206} or not stream.headers.get(
                    "content-type", ""
                ).split(";")[0].startswith(("audio/", "application/octet-stream")):
                    raise ValueError("Remote source did not return an audio stream.")
            if len(self.cache) > 200:
                self.cache.clear()
            self.cache[key] = (time.monotonic() + 90, url)
            return url
