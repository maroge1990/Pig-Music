"""Which album a requested song is filed under, and its cover.

A song asked for without an explicit edition (a playlist import, a search
result without a release) is filed under the artist's own studio album that
contains it, on that album's recommended edition, whatever album the request
named. Only `explicit_edition` requests keep the release they name.
"""

import asyncio
import logging

import httpx
from PIL import Image

from .artwork import quoted
from .catalogue import RELEASE_INC, credit, edition_rank, mbid, release_tracks
from .matching import (
    flavour,
    lead_artist,
    primary_artist,
    same_length,
    strip_edition,
    title_key,
)

logger = logging.getLogger(__name__)

# Secondary release-group types that name other recordings or other contexts.
DISTINCT_TYPES = {
    "Live": "live",
    "Remix": "remix",
    "DJ-mix": "remix",
    "Demo": "demo",
}
SKIPPED_TYPES = {
    "Interview",
    "Audiobook",
    "Audio drama",
    "Spokenword",
    "Field recording",
}


def tier(group, wanted):
    """Lower is better: studio album, EP, single, compilation/soundtrack."""
    secondary = set(group.get("secondary-types") or [])
    if secondary & SKIPPED_TYPES:
        return None
    kinds = {DISTINCT_TYPES[t] for t in secondary if t in DISTINCT_TYPES}
    if kinds - wanted:
        return None
    base = {"Album": 0, "EP": 1, "Single": 2}.get(group.get("primary-type"), 4)
    if secondary - set(DISTINCT_TYPES):
        base = max(base, 3)
    # A live/remix request prefers a release of that kind when there is one.
    return base + (0 if wanted <= kinds else 5)


def choose(recordings, job):
    """(release, recording id) of the best edition for this song, or None.

    `recordings` is a MusicBrainz recording search answer."""
    artist = primary_artist(job.get("artist"))
    title = title_key(job.get("title"))
    wanted = flavour(job.get("album")) | flavour(job.get("title"))
    album = title_key(job.get("album"))
    options = []
    for recording in recordings:
        if title_key(recording.get("title")) != title:
            continue
        if primary_artist(credit(recording.get("artist-credit", []))) != artist:
            continue
        if flavour(recording.get("disambiguation")) - wanted:
            continue
        length = (recording.get("length") or 0) / 1000
        if not same_length({"duration": length}, job):
            continue
        for release in recording.get("releases") or []:
            if release.get("status") not in {None, "Official"}:
                continue
            group = release.get("release-group") or {}
            rank = tier(group, wanted)
            if rank is None or not group.get("id"):
                continue
            options.append((rank, group, release, recording["id"]))
    if not options:
        return None
    groups = {}
    for rank, group, release, recording in options:
        date = release.get("date") or "9999"
        best = groups.get(group["id"])
        groups[group["id"]] = (
            min(rank, best[0]) if best else rank,
            min(date, best[1]) if best else date,
            group,
        )
    rank, _, group = min(
        groups.values(),
        key=lambda g: (
            g[0],
            title_key(g[2].get("title")) != album,
            g[1],
            g[2]["id"],
        ),
    )
    release, recording = min(
        (
            (release, recording)
            for _, g, release, recording in options
            if g["id"] == group["id"]
        ),
        key=lambda pair: edition_rank(pair[0]),
    )
    return release, recording


class EditionResolver:
    def __init__(self, store, catalogue, artwork, client):
        self.store, self.catalogue, self.artwork = store, catalogue, artwork
        self.client = client

    async def prepare(self, job):
        """Fields to merge into the job before it is searched: the resolved
        edition (album, numbers, IDs) and a stored cover hash."""
        changes = {}
        if not job.get("explicit_edition") and not job.get("edition_resolved"):
            try:
                changes.update(await self.resolve(job) or {})
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
                logger.info("Edition lookup failed (%s)", type(error).__name__)
            changes["edition_resolved"] = True
        release = changes.get("musicbrainz_release_id") or job.get(
            "musicbrainz_release_id"
        )
        if release and not job.get("cover_sha"):
            sha = await self.cover(release)
            if sha:
                changes["cover_sha"] = sha
        return changes

    async def resolve(self, job):
        query = (
            "recording:"
            + quoted(strip_edition(job["title"]))
            + " AND artist:"
            + quoted(lead_artist(job["artist"]))
        )
        found = await self.catalogue.get(
            self.client, "recording/", query=query, limit=50
        )
        chosen = choose(found.get("recordings", []), job)
        if not chosen:
            return None
        release, recording = chosen
        detail = await self.catalogue.get(
            self.client, "release/" + mbid(release["id"]), inc=RELEASE_INC
        )
        track = next(
            (
                t
                for t in release_tracks(detail)
                if t.get("musicbrainz_recording_id") == recording
            ),
            None,
        )
        if not track:
            return None
        return {
            "requested_album": job.get("album") or "",
            "album": track["album"],
            "album_artist": track["album_artist"] or job["album_artist"],
            "year": str(track["year"] or job.get("year") or ""),
            "disc_number": track["disc_number"] or 1,
            "track_number": track["track_number"] or 1,
            "musicbrainz_release_id": track["musicbrainz_release_id"],
            "musicbrainz_recording_id": recording,
            **({"isrcs": track["isrcs"]} if track.get("isrcs") else {}),
        }

    async def cover(self, release_id):
        """The release's front cover (or its release group's) in the cover
        store, by hash; None when the Cover Art Archive has none."""
        try:
            path = await self.artwork.catalogue_cover(
                self.client, "release", mbid(release_id)
            )
            if not path:
                return None
            content = await asyncio.to_thread(path.read_bytes)
            return await asyncio.to_thread(self.store.covers.save, content)
        except (ValueError, TypeError, OSError, Image.DecompressionBombError):
            return None
