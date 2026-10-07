"""Shared provider metadata with personal availability and acquisition controls."""

import asyncio
from uuid import UUID
import httpx
from fastapi import APIRouter, HTTPException, Request
from ..catalogue import release_tracks, credit
from ..releases import release_query
from ..library import normalise
from ..api_models import TrackDTO


def discover_router(store, catalogue, popularity=None):
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
                    "date": r.get("first-release-date", ""),
                    "type": r.get("primary-type", "Release"),
                }
                for r in result.get("release-groups", [])
            ],
        }

    @router.get("/artists/{artist_id}/popularity")
    async def popular_artist(artist_id: str, request: Request):
        return await popularity.get(request.app.state.http, valid(artist_id))

    @router.get("/library-artists/{artist_id}")
    async def saved_identity(artist_id: str, request: Request):
        projection = await asyncio.to_thread(
            store.user_libraries.projection, request.state.user["id"]
        )
        artist = next((a for a in projection["artists"] if a["id"] == artist_id), None)
        if artist is None:
            raise HTTPException(404, "Artist not found")
        result = await metadata(
            request,
            "artist/",
            query='artist:"' + artist["name"].replace('"', '"') + '"',
            limit=100,
        )
        matches = [
            a
            for a in result.get("artists", [])
            if normalise(a["name"]) == normalise(artist["name"])
        ]
        if len(matches) != 1 or result.get("count", 0) > 100:
            raise HTTPException(
                409,
                "Choose this artist in catalogue search to distinguish matching names.",
            )
        return {"id": matches[0]["id"], "name": matches[0]["name"]}

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
                    "status": r.get("status", ""),
                    "formats": [m.get("format", "") for m in r.get("media", [])],
                    "track_count": sum(
                        m.get("track-count", 0) for m in r.get("media", [])
                    ),
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
