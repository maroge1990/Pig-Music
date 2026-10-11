"""Personal original/AAC download manifests and revocable Range delivery."""

import asyncio
import subprocess
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel


class LeasedFileResponse(FileResponse):
    def __init__(self, *args, release, **kwargs):
        super().__init__(*args, **kwargs)
        self.release = release

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            await asyncio.to_thread(self.release)


class DeviceCopyDTO(BaseModel):
    state: Literal["not_requested", "queued", "preparing", "ready", "failed"]
    quality: Literal["original", "aac"]
    sha256: str | None = None
    source_sha256: str
    bytes: int
    extension: str
    key: str


def device_copy_router(copies):
    router = APIRouter(prefix="/api/v1/tracks", tags=["personal-library"])

    async def manifest(track_id, quality, create):
        try:
            result = await asyncio.to_thread(copies.manifest, track_id, quality, create)
            if result["state"] in ("queued", "preparing"):
                copies.kick()
            return result
        except FileNotFoundError:
            raise HTTPException(404, "File unavailable")
        except (ValueError, OSError, subprocess.SubprocessError):
            raise HTTPException(
                503, "Device copy unavailable. Retry or ask the administrator."
            )

    @router.post("/{track_id}/copy", response_model=DeviceCopyDTO)
    async def request_copy(
        track_id: str, quality: Literal["original", "aac"] = "original"
    ):
        return await manifest(track_id, quality, True)

    @router.get("/{track_id}/copy", response_model=DeviceCopyDTO)
    async def copy_status(
        track_id: str, quality: Literal["original", "aac"] = "original"
    ):
        return await manifest(track_id, quality, False)

    @router.get(
        "/{track_id}/copy/file",
        response_class=FileResponse,
        responses={
            200: {
                "content": {
                    "application/octet-stream": {
                        "schema": {"type": "string", "format": "binary"}
                    }
                }
            }
        },
    )
    async def copy_file(
        track_id: str, quality: Literal["original", "aac"] = "original"
    ):
        try:
            path, value = await asyncio.to_thread(copies.acquire, track_id, quality)
        except LookupError:
            raise HTTPException(409, "Device copy not ready")
        except (ValueError, OSError, subprocess.SubprocessError):
            raise HTTPException(404, "Device copy unavailable")
        return LeasedFileResponse(
            path,
            release=lambda: copies.release(value["key"]),
            media_type="application/octet-stream",
            headers={
                "ETag": '"' + value["sha256"] + '"',
                "Cache-Control": "private, no-store",
            },
        )

    return router
