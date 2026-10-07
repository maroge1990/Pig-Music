"""Shared provider metadata with personal availability and acquisition controls."""

import asyncio
from uuid import UUID
import httpx
from fastapi import APIRouter, HTTPException, Request
from ..catalogue import release_tracks, credit
from ..api_models import TrackDTO


def discover_router(store, catalogue):
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

    @router.get("/artists")
    async def artists(request: Request, q: str = ""):
        if len(q.strip()) < 2:
            return {"artists": []}
        result = await metadata(request, "artist/", query=q.strip()[:150], limit=12)
        return {
            "artists": [
                {
                    "id": a["id"],
                    "name": a["name"],
                    "description": a.get("disambiguation", ""),
                }
                for a in result.get("artists", [])
            ]
        }

    @router.get("/artists/{artist_id}/releases")
    async def groups(artist_id: str, request: Request, offset: int = 0):
        if not 0 <= offset <= 10000:
            raise HTTPException(422, "invalid_page")
        result = await metadata(
            request, "release-group", artist=valid(artist_id), limit=50, offset=offset
        )
        return {
            "total": result.get("release-group-count", 0),
            "offset": offset,
            "releases": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("first-release-date", ""),
                }
                for r in result.get("release-groups", [])
            ],
        }

    @router.get("/groups/{group_id}/editions")
    async def editions(group_id: str, request: Request, offset: int = 0):
        if not 0 <= offset <= 10000:
            raise HTTPException(422, "invalid_page")
        result = await metadata(
            request,
            "release",
            **{
                "release-group": valid(group_id),
                "inc": "media",
                "limit": 50,
                "offset": offset,
            },
        )
        return {
            "total": result.get("release-count", 0),
            "offset": offset,
            "editions": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("date", ""),
                    "country": r.get("country", ""),
                    "description": r.get("disambiguation", ""),
                }
                for r in result.get("releases", [])
            ],
        }

    @router.get("/releases/{release_id}")
    async def release(release_id: str, request: Request):
        result = await metadata(
            request,
            "release/" + valid(release_id),
            inc="recordings+artist-credits+isrcs",
        )
        user = request.state.user["id"]
        projection = await asyncio.to_thread(store.user_libraries.projection, user)
        personal = {t["id"] for t in projection["tracks"]}
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
            tracks.append(
                TrackDTO.model_validate({**raw, "server_state": state}).model_dump(
                    mode="json"
                )
            )
        return {
            "id": result["id"],
            "title": result["title"],
            "artist": credit(result.get("artist-credit", [])),
            "tracks": tracks,
        }

    return router
