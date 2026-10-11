"""Home uses each signed-in person's projection, with shared public provider caches."""

import asyncio
from fastapi import APIRouter, Request
from ..home import HomeDiscovery
from ..api_models import HomeFeedDTO, RecentAlbums


def home_router(store, catalogue, home=None):
    router = APIRouter(tags=["personal-library"])
    home = home or HomeDiscovery(store, catalogue)

    @router.get("/api/v1/home/popular", response_model=HomeFeedDTO)
    async def popular(request: Request):
        return await home.popular(request.app.state.http)

    @router.get("/api/v1/home/recent", response_model=RecentAlbums)
    async def recent(request: Request):
        return await asyncio.to_thread(
            store.user_libraries.recently_added, request.state.user["id"]
        )

    @router.get("/api/v1/home/recommended", response_model=HomeFeedDTO)
    async def recommended(request: Request):
        user = getattr(request.state, "user", None)
        projection = (
            await asyncio.to_thread(store.user_libraries.projection, user["id"])
            if user
            else store.library
        )
        try:
            return await asyncio.wait_for(
                home.recommended(request.app.state.http, projection), 25
            )
        except asyncio.TimeoutError:
            return {
                "artists": [],
                "albums": [],
                "songs": [],
                "unavailable": True,
                "state": "unavailable",
                "source": "Similar to artists in your library",
            }

    return router
