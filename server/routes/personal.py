"""Versioned personal-library API, with no household/private path disclosure."""

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr

from ..library import identifier, normalise
from ..api_models import (
    AlbumDetail,
    ArtistDetail,
    PlaylistDTO,
    PlaylistList,
    SearchResults,
    RequestList,
)
from ..playlists import Playlists, PlaylistConflict
from ..user_library import track_dto
from ..personal_removal import PersonalRemoval, RemovalChanged
from ..household_policy import HouseholdPolicy
from ..plex_accounts import PlexAccounts


class TrackInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=500)
    album: str = Field(default="", max_length=500)
    album_artist: str = Field(default="", max_length=500)
    year: str = Field(default="", max_length=10)
    disc_number: int = Field(default=1, ge=1, le=999)
    track_number: int = Field(default=1, ge=0, le=9999)
    duration: float = Field(default=0, ge=0, le=86400)
    musicbrainz_release_id: str | None = Field(default=None, max_length=36)
    musicbrainz_recording_id: str | None = Field(default=None, max_length=36)


class Tracks(BaseModel):
    tracks: list[TrackInput] = Field(min_length=1, max_length=500)


class LookupSong(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=500)
    musicbrainz_recording_id: str | None = Field(default=None, max_length=36)


class Lookup(BaseModel):
    songs: list[LookupSong] = Field(min_length=1, max_length=200)


class Membership(BaseModel):
    track_ids: list[str] = Field(min_length=1, max_length=500)


class Removal(Membership):
    confirmation: str = Field(min_length=64, max_length=64)


class QualityPreference(BaseModel):
    scope: Literal["system", "artist", "album"]
    item_id: str = Field(default="*", max_length=128)
    preferred: Literal["mp3_128", "mp3_320", "aac_256", "lossless"] | None = None


class PlexAccount(BaseModel):
    token: SecretStr = Field(min_length=1, max_length=512)
    label: str = Field(default="My Plex account", max_length=128)


class PlaylistName(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class PlaylistEdit(BaseModel):
    revision: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    order: list[int] | None = Field(default=None, max_length=10000)


class Favourite(BaseModel):
    track: TrackInput
    favourite: bool | None = None


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
                "server_state": (
                    "in_library"
                    if t.get("saved_track")
                    else (
                        "household_available"
                        if t.get("household_available")
                        else "not_in_library"
                    )
                ),
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


def personal_router(store, artist_jobs, recovery):
    router = APIRouter(prefix="/api/v1", tags=["personal-library"])
    users = store.user_libraries
    removal = PersonalRemoval(store, recovery)

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
        data = await run(users.summary, identity(request))
        etag = '"' + data["revision"] + '"'
        headers = {
            "ETag": etag,
            "Cache-Control": "private, no-cache",
            "Vary": "Accept-Encoding",
        }
        if any(
            value.strip().removeprefix("W/") in {etag, "*"}
            for value in request.headers.get("if-none-match", "").split(",")
        ):
            return Response(status_code=304, headers=headers)
        return JSONResponse(data, headers=headers)

    @router.get("/library-pages/{kind}")
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

    @router.get("/albums/{album_id}", response_model=AlbumDetail)
    async def album(album_id: str, request: Request):
        data = await run(users.projection, identity(request))
        found = next((a for a in data["albums"] if a["id"] == album_id), None)
        if not found:
            raise HTTPException(404, "Album not found")
        return {
            **{k: v for k, v in found.items() if k not in {"tracks", "cover_key"}},
            "tracks": [track_dto(t) for t in found["tracks"]],
        }

    @router.get("/artists/{artist_id}", response_model=ArtistDetail)
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
        owned_track_ids = {
            t["id"]
            for a in data["albums"]
            if a["id"] in found["album_ids"]
            for t in a["tracks"]
        }
        return {
            **found,
            "albums": albums,
            "compilation_tracks": [
                track_dto(t)
                for t in data["tracks"]
                if identifier("artist", normalise(t.get("artist", ""))) == artist_id
                and t["id"] not in owned_track_ids
            ],
        }

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

    @router.get("/search", response_model=SearchResults)
    async def search(request: Request, q: str = ""):
        return await run(users.search, identity(request), q)

    @router.post("/library/lookup")
    async def lookup(body: Lookup, request: Request):
        songs = [s.model_dump() for s in body.songs]
        return {"tracks": await run(users.lookup, identity(request), songs)}

    @router.post("/library/membership")
    async def add(body: Membership, request: Request):
        return await run(users.add, identity(request), body.track_ids)

    async def remove_call(fn, *args):
        try:
            return await asyncio.to_thread(fn, *args)
        except LookupError as exc:
            raise HTTPException(404, str(exc))
        except RemovalChanged as exc:
            raise HTTPException(409, str(exc))
        except (ValueError, OSError):
            raise HTTPException(
                400,
                "Removal or restore unavailable. Refresh or ask the administrator to check Recovery.",
            )

    @router.post("/library/removal-preview")
    async def preview_removal(body: Membership, request: Request):
        return await remove_call(removal.preview, identity(request), body.track_ids)

    @router.post("/library/remove")
    async def remove_music(body: Removal, request: Request):
        return await remove_call(
            removal.remove, identity(request), body.track_ids, body.confirmation
        )

    @router.post("/library/removals/{operation_id}/undo")
    async def undo_removal(operation_id: str, request: Request):
        return await remove_call(removal.undo, identity(request), operation_id)

    @router.get("/playlists", response_model=PlaylistList)
    async def playlists(request: Request):
        return {"playlists": await run(Playlists(store, identity(request)).list)}

    @router.post("/playlists")
    async def create(body: PlaylistName, request: Request):
        return playlist_dto(
            await run(Playlists(store, identity(request)).create, body.name)
        )

    @router.get("/playlists/{playlist_id}", response_model=PlaylistDTO)
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

    @router.get("/requests", response_model=RequestList)
    async def requests(request: Request, offset: int = 0, limit: int = 200):
        return await run(users.queue, identity(request), offset, limit)

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

    @router.get("/plex")
    async def plex_status(request: Request):
        return await run(PlexAccounts(store).status, identity(request))

    @router.put("/plex")
    async def plex_account(body: PlexAccount, request: Request):
        return await run(
            PlexAccounts(store).set,
            identity(request),
            body.token.get_secret_value(),
            body.label,
        )

    @router.get("/quality")
    async def quality(request: Request):
        return await run(HouseholdPolicy(store).quality, identity(request))

    @router.put("/quality")
    async def save_quality(body: QualityPreference, request: Request):
        try:
            return await run(
                HouseholdPolicy(store).set_quality,
                identity(request),
                body.scope,
                body.item_id,
                body.preferred,
            )
        except LookupError:
            raise HTTPException(404, "Library item not found")

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
