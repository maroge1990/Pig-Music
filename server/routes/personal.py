"""Versioned personal-library API, with no household/private path disclosure."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..playlists import Playlists, PlaylistConflict
from ..user_library import track_dto


class TrackInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=500)
    album: str = Field(default="", max_length=500)
    album_artist: str = Field(default="", max_length=500)
    year: str = Field(default="", max_length=10)
    disc_number: int = Field(default=1, ge=1, le=999)
    track_number: int = Field(default=1, ge=0, le=9999)
    duration: int = Field(default=0, ge=0, le=86400)
    musicbrainz_release_id: str | None = Field(default=None, max_length=36)
    musicbrainz_recording_id: str | None = Field(default=None, max_length=36)


class Tracks(BaseModel):
    tracks: list[TrackInput] = Field(min_length=1, max_length=500)


class Membership(BaseModel):
    track_ids: list[str] = Field(min_length=1, max_length=500)


class PlaylistName(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PlaylistEdit(BaseModel):
    revision: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    order: list[int] | None = Field(default=None, max_length=10000)


class Favourite(BaseModel):
    track: TrackInput
    favourite: bool


class PlayEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)
    track_id: str = Field(min_length=1, max_length=128)
    played_at: int
    seconds: int = Field(ge=0, le=86400)


class PlayEvents(BaseModel):
    events: list[PlayEvent] = Field(min_length=1, max_length=200)


class Preferences(BaseModel):
    appearance: Literal["system", "light", "dark"] = "system"
    default_tab: Literal["artists", "albums", "playlists", "favourites"] = "artists"


def playlist_dto(value):
    return {
        **{k: v for k, v in value.items() if k not in {"tracks", "entries"}},
        "entries": [
            {
                **track_dto(t),
                **{
                    k: t.get(k)
                    for k in (
                        "entry_id",
                        "position",
                        "status",
                        "match_kind",
                        "saved_id",
                        "household_available",
                    )
                },
                "saved_track": (
                    track_dto(t["saved_track"]) if t.get("saved_track") else None
                ),
            }
            for t in value["entries"]
        ],
    }


class ArtistRequest(BaseModel):
    kinds: list[Literal["album", "single", "ep"]] = Field(
        default=["album"], min_length=1, max_length=3
    )
    monitor: bool = False
    request: bool = False


def personal_router(store, artist_jobs):
    router = APIRouter(prefix="/api/v1", tags=["personal-library"])
    users = store.user_libraries

    def identity(request):
        return request.state.user["id"]

    def projection(request):
        return users.projection(identity(request))

    async def run(fn, *args):
        try:
            return await asyncio.to_thread(fn, *args)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.get("/library")
    async def library(request: Request):
        return await run(users.summary, identity(request))

    @router.get("/library/{kind}")
    async def page(
        kind: Literal["artists", "albums", "tracks"],
        request: Request,
        offset: int = 0,
        limit: int = 100,
    ):
        if offset < 0 or not 1 <= limit <= 200:
            raise HTTPException(422, "Invalid page bounds")
        data = await run(users.projection, identity(request))
        selected = data[kind][offset : offset + limit]
        if kind == "tracks":
            selected = [track_dto(t) for t in selected]
        elif kind == "albums":
            selected = [
                {k: v for k, v in a.items() if k not in {"tracks", "cover_key"}}
                for a in selected
            ]
        return {
            "items": selected,
            "total": len(data[kind]),
            "offset": offset,
            "next_offset": offset + limit if offset + limit < len(data[kind]) else None,
            "revision": data["revision"],
        }

    @router.get("/albums/{album_id}")
    async def album(album_id: str, request: Request):
        data = await run(users.projection, identity(request))
        found = next((a for a in data["albums"] if a["id"] == album_id), None)
        if not found:
            raise HTTPException(404, "Album not found")
        return {
            **{k: v for k, v in found.items() if k not in {"tracks", "cover_key"}},
            "tracks": [track_dto(t) for t in found["tracks"]],
        }

    @router.get("/artists/{artist_id}")
    async def artist(artist_id: str, request: Request):
        data = await run(users.projection, identity(request))
        found = next((a for a in data["artists"] if a["id"] == artist_id), None)
        if not found:
            raise HTTPException(404, "Artist not found")
        albums = [
            {k: v for k, v in a.items() if k not in {"tracks", "cover_key"}}
            for a in data["albums"]
            if a["id"] in found["album_ids"]
        ]
        return {**found, "albums": albums}

    @router.get("/artists/{artist_id}/acquisition")
    async def artist_acquisition(artist_id: str, request: Request):
        return await run(artist_jobs.scoped(identity(request)).state, artist_id)

    @router.put("/artists/{artist_id}/acquisition")
    async def configure_artist(artist_id: str, body: ArtistRequest, request: Request):
        return await run(
            artist_jobs.scoped(identity(request)).configure,
            artist_id,
            body.kinds,
            body.monitor,
            body.request,
        )

    @router.delete("/artists/{artist_id}/acquisition")
    async def cancel_artist(artist_id: str, request: Request):
        return await run(artist_jobs.scoped(identity(request)).cancel, artist_id)

    @router.get("/search")
    async def search(request: Request, q: str = ""):
        return await run(users.search, identity(request), q)

    @router.post("/library/membership")
    async def add(body: Membership, request: Request):
        return await run(users.add, identity(request), body.track_ids)

    @router.get("/playlists")
    async def playlists(request: Request):
        return {"playlists": await run(Playlists(store, identity(request)).list)}

    @router.post("/playlists")
    async def create(body: PlaylistName, request: Request):
        return playlist_dto(
            await run(Playlists(store, identity(request)).create, body.name)
        )

    @router.get("/playlists/{playlist_id}")
    async def playlist(playlist_id: str, request: Request):
        try:
            value = await asyncio.to_thread(
                Playlists(store, identity(request)).detail, playlist_id
            )
        except ValueError:
            raise HTTPException(404, "Playlist not found")
        return playlist_dto(value)

    @router.post("/playlists/{playlist_id}/songs")
    async def add_song(playlist_id: str, body: TrackInput, request: Request):
        try:
            return playlist_dto(
                await asyncio.to_thread(
                    Playlists(store, identity(request)).add,
                    playlist_id,
                    body.model_dump(exclude_none=True),
                )
            )
        except ValueError:
            raise HTTPException(404, "Playlist not found")

    async def edit_playlist(request, playlist_id, revision, **changes):
        try:
            value = await asyncio.to_thread(
                Playlists(store, identity(request)).edit,
                playlist_id,
                revision,
                **changes,
            )
            return value if changes.get("delete") else playlist_dto(value)
        except LookupError:
            raise HTTPException(404, "Playlist not found")
        except PlaylistConflict as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.patch("/playlists/{playlist_id}")
    async def edit(playlist_id: str, body: PlaylistEdit, request: Request):
        return await edit_playlist(
            request, playlist_id, body.revision, name=body.name, order=body.order
        )

    @router.delete("/playlists/{playlist_id}/songs/{position}")
    async def remove_song(
        playlist_id: str, position: int, revision: int, request: Request
    ):
        return await edit_playlist(request, playlist_id, revision, remove=position)

    @router.delete("/playlists/{playlist_id}")
    async def delete(playlist_id: str, revision: int, request: Request):
        return await edit_playlist(request, playlist_id, revision, delete=True)

    @router.post("/favourites")
    async def favourite(body: Favourite, request: Request):
        return await run(
            Playlists(store, identity(request)).favourite,
            body.track.model_dump(exclude_none=True),
            body.favourite,
        )

    @router.post("/imports/apple")
    async def import_apple(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 20 * 1024 * 1024:
                raise HTTPException(413, "Import is larger than 20MB")
        return await run(users.import_playlists, identity(request), bytes(body))

    @router.post("/requests")
    async def request_tracks(body: Tracks, request: Request):
        return await run(
            users.request,
            identity(request),
            [t.model_dump(exclude_none=True) for t in body.tracks],
        )

    @router.get("/requests")
    async def requests(request: Request):
        return await run(users.queue, identity(request))

    @router.post("/play-events")
    async def play_events(body: PlayEvents, request: Request):
        return await run(
            users.history,
            identity(request),
            [t.model_dump() for t in body.events],
            request.state.session["public_id"],
        )

    @router.get("/play-events")
    async def history(request: Request):
        from ..auth import records

        with store.connect() as conn:
            return {
                "events": records(
                    conn.execute(
                        "SELECT event_id,track_id,played_at,seconds FROM play_events WHERE user_id=? ORDER BY played_at DESC LIMIT 200",
                        (identity(request),),
                    )
                )
            }

    @router.get("/preferences")
    async def preferences(request: Request):
        import json

        with store.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM user_preferences WHERE user_id=?",
                (identity(request),),
            ).fetchone()
        return json.loads(row[0]) if row else Preferences().model_dump()

    @router.put("/preferences")
    async def save_preferences(body: Preferences, request: Request):
        import json

        with store.connect() as conn:
            conn.execute(
                "INSERT INTO user_preferences VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload",
                (identity(request), json.dumps(body.model_dump())),
            )
        return body

    return router
