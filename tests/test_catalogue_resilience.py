"""MusicBrainz rate limits, merged entries and catalogue outages during
acquisition."""

import asyncio
import json
import time

import httpx
import pytest

from server.artwork import Artwork
from server.catalogue import Catalogue
from server.downloader import Downloader
from server.editions import Deferred, EditionResolver, RESOLUTION_ATTEMPTS
from server.matching import album_title
from server.store import Store

OLD = "11111111-1111-4111-8111-111111111111"
NEW = "22222222-2222-4222-8222-222222222222"


def fetch(store, handler, path, **params):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await Catalogue(store).get(client, path, **params)

    return asyncio.run(run())


def test_rate_limited_answers_are_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"id": OLD})

    assert fetch(Store(tmp_path), handler, "artist/" + OLD) == {"id": OLD}
    assert len(calls) == 3


def test_a_persistent_outage_still_fails(tmp_path):
    def handler(request):
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        fetch(Store(tmp_path), handler, "artist/" + OLD)


def test_a_merged_entry_follows_musicbrainz_redirect_and_is_cached(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if OLD in request.url.path:
            return httpx.Response(
                301,
                headers={
                    "location": f"https://musicbrainz.org/ws/2/release-group/{NEW}?fmt=json"
                },
            )
        return httpx.Response(200, json={"id": NEW, "title": "Merged"})

    store = Store(tmp_path)
    assert fetch(store, handler, "release-group/" + OLD)["id"] == NEW
    # The answer is cached under the requested ID: no repeat every minute.
    assert fetch(store, handler, "release-group/" + OLD)["id"] == NEW
    assert len(calls) == 2


def test_redirects_off_musicbrainz_are_not_followed(tmp_path):
    def handler(request):
        return httpx.Response(
            302, headers={"location": "https://example.com/elsewhere"}
        )

    with pytest.raises(httpx.HTTPStatusError):
        fetch(Store(tmp_path), handler, "release-group/" + OLD)


class Unavailable:
    async def get(self, client, path, **params):
        request = httpx.Request("GET", "https://musicbrainz.org/ws/2/" + path)
        raise httpx.HTTPStatusError(
            "unavailable",
            request=request,
            response=httpx.Response(503, request=request),
        )


def song(**extra):
    return {
        "title": "Dreams",
        "artist": "Fleetwood Mac",
        "album": "Greatest Hits",
        "album_artist": "Fleetwood Mac",
        "duration": 257,
        "year": "",
        "disc_number": 1,
        "track_number": 1,
        **extra,
    }


def test_an_outage_defers_resolution_instead_of_filing_as_requested(tmp_path):
    resolver = EditionResolver(Store(tmp_path), Unavailable(), None, None)
    with pytest.raises(Deferred) as later:
        asyncio.run(resolver.prepare(song()))
    assert later.value.attempts == 1 and later.value.seconds > 0
    # After enough tries it is filed as requested rather than blocked forever.
    changes = asyncio.run(
        resolver.prepare(song(resolution_attempts=RESOLUTION_ATTEMPTS - 1))
    )
    assert changes == {"edition_resolved": True}


def test_a_missing_entry_is_not_retried(tmp_path):
    class Missing(Unavailable):
        async def get(self, client, path, **params):
            request = httpx.Request("GET", "https://musicbrainz.org/ws/2/" + path)
            raise httpx.HTTPStatusError(
                "missing",
                request=request,
                response=httpx.Response(404, request=request),
            )

    resolver = EditionResolver(Store(tmp_path), Missing(), None, None)
    assert asyncio.run(resolver.prepare(song())) == {"edition_resolved": True}


def test_the_worker_puts_a_deferred_request_back_until_its_time(tmp_path):
    store = Store(tmp_path)
    store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    store.submit_catalogue([{**song(), "status": "missing"}])
    job = store.claim_request()
    worker = Downloader(
        store,
        providers={},
        resolver=EditionResolver(store, Unavailable(), None, None),
    )
    worker.process = lambda job: (_ for _ in ()).throw(AssertionError("searched"))
    asyncio.run(worker.handle(job))
    (item,) = store.queue()["items"]
    assert item["status"] == "waiting_for_sources"
    assert item["resolution_attempts"] == 1 and item["retry_after"] > time.time()
    assert not item.get("edition_resolved")
    # Not claimed again until the pause is over.
    assert store.claim_request() is None
    with store.connect() as conn:
        payload = json.loads(conn.execute("SELECT payload FROM queue").fetchone()[0])
        payload["retry_after"] = time.time() - 1
        conn.execute("UPDATE queue SET payload=?", (json.dumps(payload),))
    assert store.claim_request()["id"] == job["id"]


def test_catalogue_album_titles_drop_apple_suffixes_and_artist_prefixes():
    assert album_title("Paper Planes (Homeland Security Remixes) - EP", "M.I.A.") == (
        "Paper Planes (Homeland Security Remixes)"
    )
    assert album_title("Folds in Your Hands - Single", "Passion Pit") == (
        "Folds in Your Hands"
    )
    assert (
        album_title("The Church - The Best of the Radio Songs", "The Church")
        == "The Best of the Radio Songs"
    )
    # Only the album's own artist is a prefix; other dashes stay.
    assert album_title("Hits - Volume 2", "Other") == "Hits - Volume 2"


def test_cover_search_uses_the_catalogue_album_title(tmp_path):
    queries = []

    class Recording:
        async def get(self, client, path, **params):
            queries.append(params.get("query", ""))
            return {"count": 0, "release-groups": [], "recordings": []}

    album = {
        "id": "album",
        "title": "The Church - The Best of the Radio Songs - EP",
        "artist": "The Church",
        "tracks": [{"title": "Under the Milky Way", "artist": "The Church"}],
    }
    asyncio.run(Artwork(Store(tmp_path), Recording()).cover(None, album))
    assert queries[0].startswith('releasegroup:"The Best of the Radio Songs"')
