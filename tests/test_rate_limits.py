import asyncio, time
import httpx
import pytest
from server.store import Store
from server.media import save_settings
from server.popularity import Popularity
from server.catalogue import Catalogue

ARTIST = "70248960-cb53-4ea4-943a-edb18f7d336f"
TOKEN = "00000000-0000-4000-8000-000000000000"

pytestmark = pytest.mark.real_rate_limits


def spaced(times):
    return all(b - a >= 1.0 for a, b in zip(times, times[1:]))


def test_musicbrainz_requests_are_at_least_a_second_apart(tmp_path):
    times = []

    def transport(request):
        times.append(time.monotonic())
        return httpx.Response(200, json={"id": ARTIST})

    async def run():
        catalogue = Catalogue(Store(tmp_path))
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport)
        ) as client:
            await catalogue.get(client, "artist/" + ARTIST)
            await catalogue.get(client, "artist/" + ARTIST, inc="tags")
            await catalogue.get(client, "artist/" + ARTIST)  # cached, no request

    asyncio.run(run())
    assert len(times) == 2 and spaced(times)


def test_listenbrainz_requests_are_at_least_a_second_apart(tmp_path):
    store = Store(tmp_path)
    save_settings(store, True, True, listenbrainz_token=TOKEN)
    times = []

    def transport(request):
        times.append(time.monotonic())
        return httpx.Response(200, json=[])

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport)
        ) as client:
            await Popularity(store).get(client, ARTIST)

    asyncio.run(run())
    assert len(times) == 2 and spaced(times)
