import asyncio
import json
import time

import httpx

from server.catalogue import Catalogue, warming
from server.store import Store
from server.warmer import HOME, LIBRARY, SEARCH, Warmer

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
C = "33333333-3333-3333-3333-333333333333"
D = "44444444-4444-4444-4444-444444444444"


class Home:
    def __init__(self, feed):
        self.feed = feed

    async def popular(self, client):
        return self.feed

    async def recommended(self, client, projection):
        return {"artists": [], "albums": [], "songs": []}


def warmer(tmp_path, feed=None):
    store = Store(tmp_path)
    w = Warmer(store, Home(feed or {}), lambda: None)
    calls, covers = [], []

    async def artist(artist_id, full):
        calls.append((artist_id, full))
        return [("release-group", artist_id + "-album")] if full else []

    async def cover(kind, item_id):
        covers.append((kind, item_id))
        return True

    async def identity(library_id):
        return {"lib-a": A}.get(library_id)

    w.warm_artist, w.cover, w.library_identity = artist, cover, identity
    return w, calls, covers


async def drain(w):
    worker = asyncio.create_task(w.work())
    await w.queue.join()
    worker.cancel()


def test_search_prepares_three_artists_and_two_completely(tmp_path):
    w, calls, covers = warmer(tmp_path)

    async def run():
        w.search([A, B, C, D])
        await drain(w)

    asyncio.run(run())
    assert calls == [(A, True), (B, True), (C, False)]
    assert ("release-group", A + "-album") in covers
    assert w.status()["artists_ready"] == 3


def test_recently_prepared_artists_are_not_fetched_again(tmp_path):
    w, calls, _ = warmer(tmp_path)

    async def run():
        w.submit(A, full=True, priority=LIBRARY)
        await drain(w)
        assert not w.submit(A, full=False, priority=SEARCH)
        assert not w.submit(A, full=True, priority=HOME)
        await drain(w)

    asyncio.run(run())
    assert calls == [(A, True)]


def test_urgent_requests_run_before_library_work(tmp_path):
    w, calls, _ = warmer(tmp_path)

    async def run():
        w.submit(A, full=True, priority=LIBRARY)
        w.submit(B, full=True, priority=LIBRARY)
        w.search([C])
        await drain(w)

    asyncio.run(run())
    assert calls[0] == (C, True)


def test_pass_covers_home_and_library_artists(tmp_path):
    feed = {
        "artists": [{"id": B, "artist_id": B}],
        "albums": [{"id": "group", "artist_id": C}],
        "songs": [{"id": "rec", "artist_id": D, "release_id": "release"}],
    }
    w, calls, covers = warmer(tmp_path, feed)
    w.store.library = {
        "artists": [
            {"id": "lib-a", "compilation_only": False},
            {"id": "lib-x", "compilation_only": True},
        ]
    }

    async def run():
        await w.run_pass()
        await drain(w)

    asyncio.run(run())
    assert calls[:3] == [(B, True), (C, True), (D, False)]
    assert (A, True) in calls
    assert ("release-group", "group") in covers and ("release", "release") in covers


def test_warming_renews_catalogue_answers_before_they_expire(tmp_path):
    store = Store(tmp_path)
    key = "catalogue:artist/" + A + "[]"
    store.write_document(key, {"time": time.time() - 22 * 3600, "data": {"n": 1}})
    requests = []

    async def handler(request):
        requests.append(request.url.path)
        return httpx.Response(200, json={"n": 2})

    async def read(renew):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            if renew:
                warming.set(True)
            return await Catalogue(store).get(c, "artist/" + A)

    assert asyncio.run(read(False)) == {"n": 1}
    assert requests == []
    assert asyncio.run(read(True)) == {"n": 2}
    assert json.loads(json.dumps(store.read_document(key)))["data"] == {"n": 2}
