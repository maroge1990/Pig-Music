"""Owner catalogue, artwork aliases, quality and media administration routes."""

import json
import time
from pathlib import Path
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..library import normalise
from ..releases import release_query
from ..catalogue import mbid, credit, release_tracks, edition_rank
from ..artwork import quoted
from ..media import public_settings, save_settings
from ..portraits import portrait_target
from ..artist_backgrounds import background_target
from ..quality import PROFILES


def catalogue_router(
    store,
    music_catalogue,
    artist_jobs,
    popularity,
    backgrounds,
    portraits,
    artwork,
    enrichment,
    image_response,
    image_config,
    http_client,
):
    router = APIRouter()
    catalogue_cache = {}

    @router.get("/api/catalogue/artists")
    async def catalogue(q: str = ""):
        query = q.strip()[:150]
        if len(query) < 2:
            return {"artists": []}
        cache_key = normalise(query)
        if (
            cache_key in catalogue_cache
            and time.monotonic() - catalogue_cache[cache_key][0] < 3600
        ):
            return catalogue_cache[cache_key][1]
        try:
            data = await music_catalogue.get(
                http_client(), "artist/", query=query, limit=12
            )
            # Search already supplies identity needed by portrait requests.
            with store.connect() as conn:
                for identity in data.get("artists", []):
                    conn.execute(
                        "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                        (
                            "catalogue:artist/" + identity["id"] + "[]",
                            json.dumps({"time": time.time(), "data": identity}),
                        ),
                    )
            payload = {
                "artists": [
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "description": a.get("disambiguation")
                        or a.get("country")
                        or a.get("type", "Artist"),
                        "saved_artist_id": next(
                            (
                                s["id"]
                                for s in store.library["artists"]
                                if normalise(s["name"]) == normalise(a["name"])
                            ),
                            None,
                        ),
                    }
                    for a in data.get("artists", [])
                ]
            }
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(
                502,
                "The catalogue is unavailable. Your saved library is still accessible.",
            ) from exc
        catalogue_cache[cache_key] = (time.monotonic(), payload)
        if len(catalogue_cache) > 200:
            catalogue_cache.pop(next(iter(catalogue_cache)))
        return payload

    async def metadata(path, **params):
        try:
            return await music_catalogue.get(http_client(), path, **params)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(
                502, "The catalogue is unavailable. Try again shortly."
            ) from exc

    def valid_id(value):
        try:
            return mbid(value)
        except ValueError as exc:
            raise HTTPException(400, "Invalid catalogue identifier.") from exc

    @router.get("/api/catalogue/artists/{artist_id}/releases")
    async def artist_releases(artist_id: str, offset: int = 0, kind: str | None = None):
        if offset < 0 or offset > 10000:
            raise HTTPException(400, "Invalid page.")
        if kind is not None:
            if kind not in {"album", "single", "ep", "other"}:
                raise HTTPException(400, "Choose a supported release type.")
            query = release_query(valid_id(artist_id), kind)
            data = await metadata(
                "release-group/", query=query, limit=100, offset=offset
            )
        else:
            data = await metadata(
                "release-group", artist=valid_id(artist_id), limit=50, offset=offset
            )
        identity = store.read_document(
            "catalogue:artist/" + valid_id(artist_id) + "[]"
        ).get("data", {})
        albums = [
            a
            for a in store.library["albums"]
            if normalise(a["artist"]) == normalise(identity.get("name", ""))
        ]
        releases = sorted(
            {r["id"]: r for r in data.get("release-groups", [])}.values(),
            key=lambda r: (
                bool(r.get("first-release-date")),
                r.get("first-release-date", ""),
                r.get("title", ""),
            ),
            reverse=True,
        )
        return {
            "total": data.get("count", data.get("release-group-count", 0)),
            "offset": offset,
            "releases": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("first-release-date", ""),
                    "saved_album_id": next(
                        (
                            a["id"]
                            for a in albums
                            if normalise(a["title"]) == normalise(r["title"])
                        ),
                        None,
                    ),
                    "type": " · ".join(
                        [
                            r.get("primary-type", "Release"),
                            *r.get("secondary-types", []),
                        ]
                    ),
                }
                for r in releases
            ],
        }

    @router.get("/api/artists/{artist_id}/catalogue")
    async def library_artist_catalogue(artist_id: str):
        artist = store.artists_by_id.get(artist_id)
        if artist is None:
            raise HTTPException(404, "Artist not found.")
        known = store.read_document("library-artist:" + artist_id)
        if known and known.get("name") == artist["name"]:
            return known
        data = await metadata(
            "artist/", query="artist:" + quoted(artist["name"]), limit=100
        )
        matches = [
            a
            for a in data.get("artists", [])
            if normalise(a["name"]) == normalise(artist["name"])
        ]
        if len(matches) != 1 or data.get("count", len(matches)) > 100:
            raise HTTPException(
                409, "Choose this artist in Search to distinguish matching names."
            )
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (
                    "catalogue:artist/" + matches[0]["id"] + "[]",
                    json.dumps({"time": time.time(), "data": matches[0]}),
                ),
            )
        identity = {"id": matches[0]["id"], "name": matches[0]["name"]}
        store.write_document("library-artist:" + artist_id, identity)
        return identity

    class ArtistRequest(BaseModel):
        kinds: list[str] = Field(default=["album"], max_length=3)
        monitor: bool = False
        request: bool = False

    @router.get("/api/catalogue/artists/{artist_id}/acquisition")
    def artist_acquisition(artist_id: str):
        return artist_jobs.state(valid_id(artist_id))

    @router.put("/api/catalogue/artists/{artist_id}/acquisition")
    def artist_acquisition_update(artist_id: str, body: ArtistRequest):
        try:
            return artist_jobs.configure(
                valid_id(artist_id), body.kinds, body.monitor, body.request
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/api/catalogue/artists/{artist_id}/popularity")
    async def artist_popularity(artist_id: str):
        return await popularity.get(http_client(), valid_id(artist_id))

    @router.get(
        "/api/catalogue/artists/{artist_id}/background", tags=["personal-library"]
    )
    async def catalogue_artist_background(
        artist_id: str, w: int = 0, soft: bool = False
    ):
        artist_id = valid_id(artist_id)
        config = public_settings(store)
        if not config["portraits"] or not config["fanart_configured"]:
            raise HTTPException(404, "Artwork unavailable.")
        target = background_target(store, artist_id)
        if not target.is_file():
            enrichment.submit(
                "background:" + target.stem,
                lambda: backgrounds.get(http_client(), artist_id),
            )
        return await image_response(target, w, soft)

    async def enrich_background(artist_id):
        identity = await library_artist_catalogue(artist_id)
        return await backgrounds.get(http_client(), identity["id"])

    @router.get("/api/artists/{artist_id}/background")
    async def artist_background(artist_id: str, w: int = 0, soft: bool = False):
        if artist_id not in store.artists_by_id:
            raise HTTPException(404, "Artist not found.")
        config = public_settings(store)
        if not config["fanart_configured"] or not config["portraits"]:
            raise HTTPException(404, "Artwork unavailable.")
        identity = store.read_document("library-artist:" + artist_id)
        target = background_target(store, identity["id"]) if identity else None
        if not target or not target.is_file():
            enrichment.submit(
                "library-background:" + artist_id, lambda: enrich_background(artist_id)
            )
        return await image_response(target, w, soft)

    async def enrich_catalogue_artist(artist_id, cache_key):
        if public_settings(store)["portraits"]:
            identity = await metadata("artist/" + artist_id)
            target = await portraits.get(
                http_client(), identity.get("name", ""), artist_id
            )
            if target:
                store.write_document(cache_key, {"file": target.name})
                return target
        data = await metadata(
            "release", artist=artist_id, inc="release-groups", limit=50
        )
        releases = [
            r
            for r in data.get("releases", [])
            if r.get("cover-art-archive", {}).get("front")
        ]
        releases.sort(
            key=lambda r: (
                r.get("release-group", {}).get("primary-type") != "Album",
                bool(r.get("release-group", {}).get("secondary-types")),
            )
        )
        if releases:
            target = await artwork.catalogue_cover(
                http_client(), "release", valid_id(releases[0]["id"])
            )
            if target:
                store.write_document(cache_key, {"file": target.name})
                return target
        return None

    @router.get("/api/catalogue/artists/{artist_id}/artwork", tags=["personal-library"])
    async def artist_artwork(artist_id: str, w: int = 0):
        artist_id = valid_id(artist_id)
        cache_key = "catalogue-artist-image:" + artist_id + ":" + image_config()
        cached = store.read_document(cache_key).get("file", "")
        target = (
            store.cover_dir / cached if cached and Path(cached).name == cached else None
        )
        if not target or not target.is_file():
            enrichment.submit(
                cache_key, lambda: enrich_catalogue_artist(artist_id, cache_key)
            )
        return await image_response(target, w)

    @router.get("/api/catalogue/groups/{group_id}/editions")
    async def editions(group_id: str, offset: int = 0):
        if offset < 0 or offset > 10000:
            raise HTTPException(400, "Invalid page.")
        data = await metadata(
            "release",
            **{
                "release-group": valid_id(group_id),
                "inc": "media",
                "limit": 50,
                "offset": offset,
            },
        )
        ranked = sorted(data.get("releases", []), key=edition_rank)
        return {
            "total": data.get("release-count", 0),
            "offset": offset,
            "editions": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("date", ""),
                    "country": r.get("country", ""),
                    "description": r.get("disambiguation", ""),
                    "status": r.get("status", ""),
                    "formats": [
                        m.get("format", "Unknown format") for m in r.get("media", [])
                    ],
                    "track_count": sum(
                        m.get("track-count", 0) for m in r.get("media", [])
                    ),
                }
                for r in ranked
            ],
            "recommended_id": ranked[0]["id"] if ranked else None,
        }

    async def release_data(release_id):
        return await metadata(
            "release/" + valid_id(release_id), inc="recordings+artist-credits+isrcs"
        )

    @router.get("/api/catalogue/releases/{release_id}")
    async def catalogue_release(release_id: str):
        data = await release_data(release_id)
        tracks = music_catalogue.presence(release_tracks(data))
        jobs = store.queue()["items"]
        for track in tracks:
            job = next(
                (
                    j
                    for j in jobs
                    if j.get("musicbrainz_release_id") == data["id"]
                    and j.get("musicbrainz_recording_id")
                    == track.get("musicbrainz_recording_id")
                    and j.get("track_number") == track["track_number"]
                    and j.get("disc_number") == track["disc_number"]
                ),
                None,
            )
            if job and track["status"] != "downloaded":
                track.update(
                    download_status=job["status"],
                    received_bytes=job.get("received_bytes", 0),
                    total_bytes=job.get("total_bytes", 0),
                )
        return {
            "id": data["id"],
            "title": data["title"],
            "artist": credit(data.get("artist-credit", [])),
            "date": data.get("date", ""),
            "description": data.get("disambiguation", ""),
            "tracks": tracks,
        }

    class CatalogueRequest(BaseModel):
        track_ids: list[str] | None = Field(default=None, max_length=500)
        quality_profile: str | None = None

    @router.post("/api/catalogue/releases/{release_id}/request")
    async def request_release(release_id: str, body: CatalogueRequest):
        if body.quality_profile is not None and body.quality_profile not in PROFILES:
            raise HTTPException(400, "Choose a supported quality.")
        tracks = music_catalogue.presence(
            release_tracks(await release_data(release_id))
        )
        if body.track_ids is not None:
            if not set(body.track_ids).issubset({t["id"] for t in tracks}):
                raise HTTPException(400, "Unknown tracks in this edition.")
            tracks = [t for t in tracks if t["id"] in body.track_ids]
        if not tracks:
            raise HTTPException(400, "This edition has no selected tracks.")
        return store.submit_catalogue(tracks, body.quality_profile)

    class AlbumQuality(BaseModel):
        profile: str | None = None

    @router.post("/api/albums/{album_id}/quality")
    def album_quality(album_id: str, body: AlbumQuality):
        try:
            return store.quality_override("album", album_id, body.profile)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/api/albums/{album_id}/quality")
    def album_quality_status(album_id: str):
        try:
            return store.quality_status("album", album_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/api/artists/{artist_id}/quality")
    def artist_quality_status(artist_id: str):
        try:
            return store.quality_status("artist", artist_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/api/artists/{artist_id}/quality")
    def artist_quality(artist_id: str, body: AlbumQuality):
        try:
            return store.quality_override("artist", artist_id, body.profile)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    class MediaSettings(BaseModel):
        portraits: bool
        remote_playback: bool
        fanart_key: str | None = Field(default=None, max_length=128)
        listenbrainz_token: str | None = Field(default=None, max_length=128)

    @router.get("/api/settings/media")
    def media_settings():
        return public_settings(store)

    @router.put("/api/settings/media")
    def update_media_settings(body: MediaSettings):
        try:
            result = save_settings(store, **body.model_dump())
            store.refresh_library()
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    return router, library_artist_catalogue, valid_id, release_data
