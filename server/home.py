"""Bounded discovery feeds; only catalogue IDs are sent to providers, never listens."""

import asyncio
import json
import time
import httpx
from .catalogue import mbid, credit, warming
from .media import settings
from .releases import feature_album


def renew_margin():
    # Hour-long feeds are renewed by the warmer with 20 minutes to spare.
    return 1200 if warming.get() else 0


class HomeDiscovery:
    def __init__(self, store, catalogue):
        self.store, self.catalogue = store, catalogue
        self.locks = {}

    async def feed(self, client, path, **params):
        key = "home-feed:v1:" + path + repr(sorted(params.items()))
        cached = self.store.read_document(key)
        if cached and cached.get("until", 0) - renew_margin() > time.time():
            return cached["data"], cached.get("failed", False)
        async with self.locks.setdefault(key, asyncio.Lock()):
            cached = self.store.read_document(key)
            if cached and cached.get("until", 0) - renew_margin() > time.time():
                return cached["data"], cached.get("failed", False)
            try:
                headers = {
                    "User-Agent": "PigMusic/1.0 (https://github.com/maroge1990/Pig-Music)"
                }
                token = settings(self.store).get("listenbrainz_token")
                if token:
                    headers["Authorization"] = "Token " + token
                async with client.stream(
                    "GET",
                    "https://api.listenbrainz.org/1/" + path,
                    params=params,
                    headers=headers,
                    timeout=6,
                    follow_redirects=False,
                ) as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 2_000_000:
                            raise ValueError("Feed too large")
                data = json.loads(content)
                if not isinstance(data, dict):
                    raise ValueError("Invalid feed")
                self.store.write_document(
                    key, {"until": time.time() + 3600, "data": data}
                )
                return data, False
            except (httpx.HTTPError, ValueError):
                # A short retry window avoids hammering an unavailable service.
                data = cached.get("data", {}) if cached else {}
                self.store.write_document(
                    key, {"until": time.time() + 60, "data": data, "failed": True}
                )
                return data, True

    @staticmethod
    def identity(value):
        try:
            return mbid(value)
        except (ValueError, TypeError, AttributeError):
            return None

    async def popular(self, client):
        feeds = await asyncio.gather(
            *(
                self.feed(client, "stats/sitewide/" + kind, range="week", count=12)
                for kind in ("artists", "release-groups", "recordings")
            )
        )
        result = {
            "artists": [],
            "albums": [],
            "songs": [],
            "unavailable": any(failed for _, failed in feeds),
            "source": "ListenBrainz · this week",
        }
        for kind, field, identity, name in (
            ("artists", "artists", "artist_mbid", "artist_name"),
            ("albums", "release_groups", "release_group_mbid", "release_group_name"),
            ("songs", "recordings", "recording_mbid", "track_name"),
        ):
            data = feeds[("artists", "albums", "songs").index(kind)][0].get(
                "payload", {}
            )
            if not isinstance(data, dict) or not isinstance(data.get(field, []), list):
                result["unavailable"] = True
                continue
            seen = set()
            for item in data.get(field, [])[:12]:
                if not isinstance(item, dict):
                    continue
                item_id = self.identity(item.get(identity))
                artists = item.get("artist_mbids") or []
                artist_id = (
                    item_id
                    if kind == "artists"
                    else next(
                        (self.identity(i) for i in artists if self.identity(i)), None
                    )
                )
                if (
                    not item_id
                    or not artist_id
                    or not item.get(name)
                    or item_id in seen
                ):
                    continue
                seen.add(item_id)
                result[kind].append(
                    {
                        "id": item_id,
                        "name": item[name],
                        "artist": item.get("artist_name", ""),
                        "artist_id": artist_id,
                        "release_id": self.identity(
                            item.get("release_mbid") or item.get("caa_release_mbid")
                        ),
                        "album": (
                            item.get("release_name", "") if kind == "songs" else ""
                        ),
                        "kind": kind,
                    }
                )
        return result

    async def recommended(self, client, projection):
        result = {
            "artists": [],
            "albums": [],
            "songs": [],
            "source": "Similar to artists in your library",
            "unavailable": False,
        }
        seeds = []
        for artist in sorted(
            projection["artists"], key=lambda a: (-a.get("track_count", 0), a["id"])
        )[:3]:
            known = self.store.read_document("library-artist:" + artist["id"])
            identity = self.identity(known.get("id")) if known else None
            if not identity:
                try:
                    data = await self.catalogue.get(
                        client,
                        "artist/",
                        query='artist:"' + artist["name"].replace('"', "") + '"',
                        limit=12,
                    )
                    matches = [
                        a
                        for a in data.get("artists", [])
                        if a.get("name", "").casefold() == artist["name"].casefold()
                    ]
                    if len(matches) == 1:
                        identity = self.identity(matches[0]["id"])
                        self.store.write_document(
                            "library-artist:" + artist["id"],
                            {"id": identity, "name": artist["name"]},
                        )
                except (httpx.HTTPError, ValueError, KeyError):
                    result["unavailable"] = True
            if identity:
                seeds.append((identity, artist["name"]))
        owned = {a["name"].casefold() for a in projection["artists"]}
        seen = set()
        for identity, name in seeds:
            feed, failed = await self.feed(
                client,
                "lb-radio/artist/" + identity,
                mode="easy",
                max_similar_artists=5,
                max_recordings_per_artist=1,
                pop_begin=40,
                pop_end=100,
            )
            result["unavailable"] |= failed
            for artist_id, recordings in feed.items():
                candidate = self.identity(artist_id)
                if (
                    not candidate
                    or candidate == identity
                    or candidate in seen
                    or not isinstance(recordings, list)
                    or not recordings
                ):
                    continue
                record = recordings[0]
                if not isinstance(record, dict):
                    continue
                artist_name = record.get("similar_artist_name", "")
                if not artist_name or artist_name.casefold() in owned:
                    continue
                seen.add(candidate)
                reason = "Because you saved " + name
                result["artists"].append(
                    {
                        "id": candidate,
                        "artist_id": candidate,
                        "name": artist_name,
                        "artist": artist_name,
                        "reason": reason,
                        "kind": "artists",
                    }
                )
                try:
                    groups = await self.catalogue.get(
                        client,
                        "release-group/",
                        query="arid:" + candidate + " AND primarytype:album",
                        limit=6,
                    )
                    for group in groups.get("release-groups", []):
                        if feature_album(group):
                            result["albums"].append(
                                {
                                    "id": group["id"],
                                    "artist_id": candidate,
                                    "artist": artist_name,
                                    "name": group["title"],
                                    "reason": reason,
                                    "kind": "albums",
                                }
                            )
                            break
                    recording = self.identity(record.get("recording_mbid"))
                    if recording:
                        detail = await self.catalogue.get(
                            client,
                            "recording/" + recording,
                            inc="releases+artist-credits",
                        )
                        releases = detail.get("releases", [])
                        result["songs"].append(
                            {
                                "id": recording,
                                "artist_id": candidate,
                                "artist": credit(detail.get("artist-credit", [])),
                                "name": detail["title"],
                                "release_id": releases[0]["id"] if releases else None,
                                "album": (
                                    releases[0].get("title", "") if releases else ""
                                ),
                                "reason": reason,
                                "kind": "songs",
                            }
                        )
                except (httpx.HTTPError, ValueError, KeyError):
                    result["unavailable"] = True
                if len(result["artists"]) >= 4:
                    return result
        return result
