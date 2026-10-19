"""Shared provider metadata with personal availability and acquisition controls."""

import asyncio
from uuid import UUID
import httpx
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ..artist_identity import Ambiguous, resolve_artist
from ..catalogue import release_tracks, credit, edition_rank
from ..releases import release_query
from ..api_models import (
    CatalogueGroupsDTO,
    CatalogueEditionsDTO,
    CatalogueReleaseDTO,
    CatalogueTrackDTO,
    CatalogueArtistsDTO,
    CataloguePopularityDTO,
    CatalogueProfileDTO,
    ArtistIdentityDTO,
)
from ..user_library import track_dto

ACTIVE = {"waiting_for_sources", "searching", "downloading", "validating", "importing"}


def discover_router(store, catalogue, popularity=None, warmer=None, http_client=None):
    router = APIRouter(prefix="/api/v1/catalogue", tags=["personal-library"])

    def valid(value):
        try:
            return str(UUID(value))
        except ValueError:
            raise HTTPException(400, "invalid_catalogue_id")

    async def metadata(request, path, **parameters):
        try:
            return await catalogue.get(request.app.state.http, path, **parameters)
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, "catalogue_unavailable")

    @router.get("/artists", response_model=CatalogueArtistsDTO)
    async def artists(
        request: Request,
        q: str = "",
        offset: int = Query(default=0, ge=0, le=10000),
        limit: int = Query(default=12, ge=1, le=100),
    ):
        if len(q.strip()) < 2:
            return {"artists": [], "offset": offset, "total": 0, "next_offset": None}
        result = await metadata(
            request, "artist/", query=q.strip()[:150], limit=limit, offset=offset
        )
        if warmer is not None:
            # Prepare the likely next tap on the server, for every device.
            warmer.search([a["id"] for a in result.get("artists", []) if "id" in a])
        found = result.get("artists", [])
        total = int(
            result.get("count") or result.get("artist-count") or (offset + len(found))
        )
        end = offset + len(found)
        return {
            "offset": offset,
            "total": total,
            "next_offset": end if found and end < min(total, 10000) else None,
            "artists": [
                {
                    "id": a["id"],
                    "name": a["name"],
                    "description": a.get("disambiguation") or "",
                }
                for a in result.get("artists", [])
            ],
        }

    @router.get("/artists/{artist_id}/releases", response_model=CatalogueGroupsDTO)
    async def groups(
        artist_id: str, request: Request, offset: int = 0, kind: str | None = None
    ):
        if not 0 <= offset <= 10000:
            raise HTTPException(422, "invalid_page")
        if kind:
            if kind not in {"album", "single", "ep", "other"}:
                raise HTTPException(422, "invalid_release_type")
            result = await metadata(
                request,
                "release-group/",
                query=release_query(valid(artist_id), kind),
                limit=100,
                offset=offset,
            )
        else:
            result = await metadata(
                request,
                "release-group",
                artist=valid(artist_id),
                limit=50,
                offset=offset,
            )
        return {
            "total": result.get("count", result.get("release-group-count", 0)),
            "offset": offset,
            "releases": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("first-release-date") or "",
                    "type": r.get("primary-type") or "Release",
                }
                for r in result.get("release-groups", [])
            ],
        }

    @router.get(
        "/artists/{artist_id}/popularity", response_model=CataloguePopularityDTO
    )
    async def popular_artist(artist_id: str, request: Request):
        return await popularity.get(request.app.state.http, valid(artist_id))

    @router.get("/artists/{artist_id}/profile", response_model=CatalogueProfileDTO)
    async def artist_profile(artist_id: str, request: Request):
        found = await metadata(request, "artist/" + valid(artist_id))
        return {
            "id": valid(artist_id),
            "name": found.get("name") or "",
            "description": found.get("disambiguation") or "",
            "type": found.get("type") or "",
            "country": found.get("country") or "",
            "begin": (found.get("life-span") or {}).get("begin") or "",
            "end": (found.get("life-span") or {}).get("end") or "",
        }

    @router.get("/library-artists/{artist_id}", response_model=ArtistIdentityDTO)
    async def saved_identity(artist_id: str, request: Request):
        projection = await asyncio.to_thread(
            store.user_libraries.projection, request.state.user["id"]
        )
        artist = next((a for a in projection["artists"] if a["id"] == artist_id), None)
        if artist is None:
            raise HTTPException(404, "Artist not found")
        albums = [a for a in projection["albums"] if a["id"] in artist["album_ids"]]
        try:
            return await resolve_artist(
                store, catalogue, request.app.state.http, artist, albums
            )
        except Ambiguous as exc:
            return JSONResponse(
                {
                    "detail": "Choose this artist in catalogue search to distinguish matching names.",
                    "code": "conflict",
                    "candidates": exc.candidates,
                },
                status_code=409,
            )
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, "catalogue_unavailable")

    class ArtistLink(BaseModel):
        id: str

    @router.put("/library-artists/{artist_id}")
    async def link_identity(artist_id: str, body: ArtistLink, request: Request):
        # The household owner chooses once; every member then shares the link.
        if request.state.user["role"] != "owner":
            raise HTTPException(403, "owner_only")
        projection = await asyncio.to_thread(
            store.user_libraries.projection, request.state.user["id"]
        )
        artist = next((a for a in projection["artists"] if a["id"] == artist_id), None)
        if artist is None:
            raise HTTPException(404, "Artist not found")
        chosen = valid(body.id)
        try:
            found = await catalogue.get(request.app.state.http, "artist/" + chosen)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {400, 404}:
                raise HTTPException(400, "invalid_catalogue_id")
            raise HTTPException(502, "catalogue_unavailable")
        except (httpx.HTTPError, ValueError, KeyError):
            raise HTTPException(502, "catalogue_unavailable")
        if found.get("id") != chosen or not found.get("name"):
            raise HTTPException(400, "invalid_catalogue_id")
        identity = {"id": chosen, "name": artist["name"]}
        store.write_document("library-artist:" + artist_id, identity)
        return identity

    def editions_query(group_id, offset):
        return {
            "release-group": group_id,
            "inc": "media",
            "limit": 50,
            "offset": offset,
        }

    RELEASE_INC = "recordings+artist-credits+isrcs"

    @router.get("/groups/{group_id}/editions", response_model=CatalogueEditionsDTO)
    async def editions(group_id: str, request: Request, offset: int = 0):
        if not 0 <= offset <= 10000:
            raise HTTPException(422, "invalid_page")
        result = await metadata(
            request, "release", **editions_query(valid(group_id), offset)
        )
        # Ranked like the web, so the first is the recommended edition.
        ranked = sorted(result.get("releases", []), key=edition_rank)
        return {
            "total": result.get("release-count", 0),
            "offset": offset,
            "editions": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("date") or "",
                    "country": r.get("country") or "",
                    "description": r.get("disambiguation") or "",
                    "status": r.get("status") or "",
                    "formats": [m.get("format") or "" for m in r.get("media", [])],
                    "track_count": sum(
                        m.get("track-count") or 0 for m in r.get("media", [])
                    ),
                }
                for r in ranked
            ],
        }

    @router.get("/releases/{release_id}", response_model=CatalogueReleaseDTO)
    async def release(release_id: str, request: Request):
        result = await metadata(
            request, "release/" + valid(release_id), inc=RELEASE_INC
        )
        user = request.state.user["id"]
        projection = await asyncio.to_thread(store.user_libraries.projection, user)
        personal = {t["id"] for t in projection["tracks"]}
        active = [
            j
            for j in store.queue()["items"]
            if j.get("status") in ACTIVE
            and user in j.get("requested_by", [])
            and j.get("musicbrainz_release_id") == result["id"]
        ]
        tracks = []
        for raw in release_tracks(result):
            matched = store.index.match(raw)
            state = "not_in_library"
            if matched.track and matched.status == "downloaded":
                state = (
                    "in_library"
                    if matched.track["id"] in personal
                    else "household_available"
                )
            elif any(
                j.get("musicbrainz_recording_id") == raw.get("musicbrainz_recording_id")
                and j.get("track_number") == raw["track_number"]
                and j.get("disc_number") == raw["disc_number"]
                for j in active
            ):
                state = "requested"
            tracks.append(
                CatalogueTrackDTO.model_validate(
                    {
                        **raw,
                        "server_state": state,
                        "saved_track": (
                            track_dto(matched.track) if state == "in_library" else None
                        ),
                        "household_track": (
                            {
                                **track_dto(matched.track),
                                "server_state": "household_available",
                            }
                            if state == "household_available"
                            else None
                        ),
                    }
                ).model_dump(mode="json")
            )
        return {
            "id": result["id"],
            "title": result["title"],
            "artist": credit(result.get("artist-credit", [])),
            "artist_id": next(
                (
                    item["artist"]["id"]
                    for item in result.get("artist-credit", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("artist"), dict)
                    and item["artist"].get("id")
                ),
                "",
            ),
            "tracks": tracks,
        }

    async def warm_album(group_id):
        """Cache an album's first editions page and its recommended edition."""
        http = http_client()
        found = await catalogue.get(http, "release", **editions_query(group_id, 0))
        ranked = sorted(found.get("releases", []), key=edition_rank)
        if not ranked:
            return None
        await catalogue.get(http, "release/" + ranked[0]["id"], inc=RELEASE_INC)
        return ranked[0]["id"]

    router.warm_album = warm_album
    return router
