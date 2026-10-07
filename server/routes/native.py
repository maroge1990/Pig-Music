"""Typed native library and authenticated live updates."""

import asyncio
import json
import time
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from ..api_models import TrackPage, AlbumPage, ArtistPage, LibraryChanges
from ..native_sync import NativeSync, ResyncRequired
from ..auth import AuthError


def native_router(store, auth):
    router = APIRouter(prefix="/api/v1", tags=["personal-library"])
    sync = NativeSync(store)
    connections = {}

    async def page(request, kind, cursor, limit):
        try:
            return await asyncio.to_thread(
                sync.page, request.state.user["id"], kind, cursor, limit
            )
        except ResyncRequired as exc:
            raise HTTPException(409, str(exc))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @router.get("/library/tracks", response_model=TrackPage)
    async def tracks(request: Request, cursor: str | None = None, limit: int = 200):
        return await page(request, "tracks", cursor, limit)

    @router.get("/library/albums", response_model=AlbumPage)
    async def albums(request: Request, cursor: str | None = None, limit: int = 200):
        return await page(request, "albums", cursor, limit)

    @router.get("/library/artists", response_model=ArtistPage)
    async def artists(request: Request, cursor: str | None = None, limit: int = 200):
        return await page(request, "artists", cursor, limit)

    @router.get("/library/changes", response_model=LibraryChanges)
    async def changes(request: Request, since: str):
        try:
            return await asyncio.to_thread(
                sync.changes, request.state.user["id"], since
            )
        except ResyncRequired as exc:
            raise HTTPException(410, str(exc))

    @router.get("/events")
    async def events(request: Request):
        session = request.state.session
        key, user_id = session["public_id"], request.state.user["id"]
        if connections.get(key, 0) >= 4:
            raise HTTPException(429, "event_connection_limit")
        # Reserve before returning the response; release even if the generator is cancelled.
        connections[key] = connections.get(key, 0) + 1

        async def stream():
            previous = {}
            heartbeat = time.monotonic()
            try:
                while not await request.is_disconnected():
                    # Revoked sessions cannot keep receiving events indefinitely.
                    with store.connect() as conn:
                        valid = conn.execute(
                            "SELECT 1 FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.public_id=? AND s.revoked_at IS NULL AND s.expires_at>? AND u.disabled=0",
                            (key, auth.now()),
                        ).fetchone()
                    if not valid:
                        yield "event: revoked\ndata: {}\n\n"
                        return
                    summary = await asyncio.to_thread(
                        store.user_libraries.projection, user_id
                    )
                    queue = await asyncio.to_thread(store.user_libraries.queue, user_id)
                    state = {
                        "revision": {"revision": summary["revision"]},
                        "queue": queue,
                        "health": {"status": "ok"},
                    }
                    for kind, value in state.items():
                        if previous.get(kind) != value:
                            yield f'event: {kind}\ndata: {json.dumps(value,separators=(",", ":"))}\n\n'
                            previous[kind] = value
                    if time.monotonic() - heartbeat >= 25:
                        yield ": keepalive\n\n"
                        heartbeat = time.monotonic()
                    await asyncio.sleep(2)
            finally:
                connections[key] -= 1
                if not connections[key]:
                    del connections[key]

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
