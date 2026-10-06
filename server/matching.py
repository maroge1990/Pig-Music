"""Indexed, conservative music matching shared by every library consumer.

Names alone never override conflicting release/recording IDs. Multiple candidates
are usable only when their hashes prove that they contain the same bytes.
"""

from collections import defaultdict
from dataclasses import dataclass

from .library import identifier, normalise

CONTEXT = ("artist", "title", "album", "album_artist")
IDENTITIES = ("musicbrainz_release_id", "musicbrainz_recording_id")


def context(track):
    return tuple(
        normalise(
            track.get(k) or (track.get("artist", "") if k == "album_artist" else "")
        )
        for k in CONTEXT
    )


def same_song(left, right):
    if context(left) != context(right):
        return False
    if any(left.get(k) and right.get(k) and left[k] != right[k] for k in IDENTITIES):
        return False
    return not (
        left.get("duration")
        and right.get("duration")
        and abs(left["duration"] - right["duration"]) > 5
    )


def exclusion_key(track):
    return identifier(
        "excluded-v2", *context(track), *(track.get(k) or "" for k in IDENTITIES)
    )


@dataclass(frozen=True)
class Match:
    kind: str
    track: dict | None = None

    @property
    def status(self):
        return (
            "downloaded"
            if self.track
            else "review" if self.kind == "conflict" else "missing"
        )


class LibraryIndex:
    def __init__(self, library):
        self.by_id = {}
        self.by_context = defaultdict(list)
        self.by_recording = defaultdict(list)
        self.album_by_track = {}
        self.search_tracks = []
        for album in library["albums"]:
            for raw in album["tracks"]:
                track = {
                    **raw,
                    "album_id": album["id"],
                    "cover_url": album.get("cover_url"),
                }
                self.by_id[track["id"]] = track
                self.album_by_track[track["id"]] = album["id"]
                self.search_tracks.append(
                    (normalise(track["title"] + " " + track["artist"]), track)
                )
                if track.get("available") is not False:
                    key = context(track)
                    self.by_context[key].append(track)
                    self.by_recording[key[:2]].append(track)

    def match(self, requested):
        key = context(requested)
        matches = [t for t in self.by_context.get(key, ()) if same_song(t, requested)]
        hashes = {t.get("sha256") for t in matches}
        if len(matches) == 1 or matches and len(hashes) == 1 and None not in hashes:
            track = matches[0]
            known = all(requested.get(k) and track.get(k) for k in IDENTITIES)
            return Match("exact" if known else "probable", track)
        return Match("conflict" if self.by_recording.get(key[:2]) else "absent")
