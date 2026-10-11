"""Monochrome tracks API adapter. Provider numeric IDs are never MB UUIDs."""

import os
import re
from urllib.parse import urlencode, urlsplit

from .contracts import ProviderError
from .deezer import identify
from .network import get_json, transfer, validate_url


class Monochrome:
    source = "monochrome"

    def __init__(self):
        self.base = os.environ.get(
            "PIG_MUSIC_MONOCHROME_API", "https://tracks.monochrome.st"
        ).rstrip("/")
        host = urlsplit(self.base).hostname or ""
        self.hosts = (host,)
        validate_url(self.base, self.hosts)
        if urlsplit(self.base).query or urlsplit(self.base).fragment:
            raise ProviderError("network_policy")
        # CDN additions are explicit operator configuration, never learned from
        # a response. Every address must still resolve exclusively to public IPs.
        extra = os.environ.get("PIG_MUSIC_MONOCHROME_CDN_HOSTS", "")
        self.hosts += tuple(h.strip().lower() for h in extra.split(",") if h.strip())

    def search(self, target, context, limit=8):
        from ..downloader import matches, folded

        body = get_json(
            self.base
            + "/search/tracks?"
            + urlencode(
                {"q": f"{target['artist']} {target['title']}", "limit": min(limit, 25)}
            ),
            self.hosts,
            context,
        )
        if not isinstance(body, dict) or not isinstance(body.get("tracks"), list):
            raise ProviderError("invalid_response")
        requested = {str(v).strip().upper() for v in target.get("isrcs", []) if v}
        if target.get("isrc"):
            requested.add(str(target["isrc"]).strip().upper())
        if not requested:
            requested = identify(target, context)
        results, releases = [], {}
        for raw in body["tracks"][:25]:
            context.remaining()
            if not isinstance(raw, dict):
                continue
            identity = str(raw.get("trackId") or raw.get("id") or "")
            if not re.fullmatch(r"\d{1,30}", identity) or raw.get("playable") is False:
                continue
            isrc = str(raw.get("isrc") or "").upper()
            if requested and isrc not in requested:
                continue
            names = raw.get("artistNames") or []
            if not isinstance(names, list) or not all(
                isinstance(n, str) for n in names
            ):
                continue
            try:
                seconds = float(raw.get("duration", 0)) / 1000
            except (ValueError, TypeError):
                continue
            candidate = {
                "title": raw.get("title") or "",
                "channel": ", ".join(names),
                "album": "",
                "duration": seconds,
                "isrc": isrc,
                "provider_track_id": identity,
                "provider_recording_id": str(raw.get("recordingId") or ""),
                "extension": ".flac",
                "quality": "FLAC",
                "source": self.source,
            }
            if not matches(target, candidate):
                continue
            release = str(raw.get("releaseId") or "")
            if not re.fullmatch(r"\d{1,30}", release):
                continue
            if release not in releases:
                releases[release] = get_json(
                    self.base + "/releases/" + release, self.hosts, context
                )
            metadata = releases[release]
            if not isinstance(metadata, dict):
                raise ProviderError("invalid_response")
            candidate["album"] = metadata.get("title") or ""
            candidate["provider_release_id"] = release
            # Matching ISRC proves recording, but never erases a requested edition
            # conflict. With no ISRC, the exact release is mandatory evidence.
            if target.get("album") and folded(candidate["album"]) != folded(
                target["album"]
            ):
                continue
            if not requested and not target.get("album"):
                continue
            if matches(target, candidate):
                results.append(candidate)
        return results[:limit]

    def transfer(self, candidate, path, context):
        identity = candidate.get("provider_track_id", "")
        if not re.fullmatch(r"\d{1,30}", identity):
            raise ProviderError("invalid_response")
        transfer(self.base + "/track/" + identity, self.hosts, path, context)
        return {
            "format_id": "flac",
            "original_codec": "flac",
            "original_container": "flac",
            "remuxed": False,
        }

    def check(self, context):
        body = get_json(
            self.base + "/search/tracks?q=music&limit=1", self.hosts, context
        )
        if not isinstance(body, dict) or not isinstance(body.get("tracks"), list):
            raise ProviderError("invalid_response")
