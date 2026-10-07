"""Administrator-only explicit assignment of newly scanned music."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..household_policy import HouseholdPolicy


class Assignment(BaseModel):
    track_ids: list[str] = Field(min_length=1, max_length=500)
    user_ids: list[str] = Field(min_length=1, max_length=20)


def household_router(store):
    router = APIRouter(prefix="/api/v1/admin", tags=["owner-library"])
    policy = HouseholdPolicy(store)

    @router.get("/unassigned")
    async def inbox(offset: int = 0, limit: int = 100):
        try:
            return await asyncio.to_thread(policy.inbox, offset, limit)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @router.post("/unassigned/assign")
    async def assign(body: Assignment):
        try:
            return await asyncio.to_thread(policy.assign, body.track_ids, body.user_ids)
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    return router
