"""Optional remote listening; matching never removes version descriptions."""

import asyncio
import time
from urllib.parse import urlsplit

import httpx

from .library import normalise
from .downloader import matches
from .vendor.jiosaavn import search_jiosaavn


class RemoteAudio:
    """Short-lived source resolution cache; remote listening never queues a download."""

    def __init__(self, search=None):
        self.search = search or search_jiosaavn
        self.cache = {}
        self.slots = asyncio.Semaphore(3)

    async def resolve(self, client, track):
        key = (
            track.get("musicbrainz_release_id"),
            track.get("musicbrainz_recording_id"),
            track["artist"],
            track["title"],
            track["album"],
            track.get("duration"),
        )
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
