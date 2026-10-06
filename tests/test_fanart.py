import asyncio

import httpx

from server.fanart import Fanart
from server.store import Store


def test_concurrent_portrait_and_background_share_metadata_but_key_rotation_refreshes(
    tmp_path,
):
    store = Store(tmp_path)
    cache = Fanart(store)
    calls = []

    async def handler(request):
        calls.append(request.headers["api-key"])
        await asyncio.sleep(0)
        return httpx.Response(200, json={"artistthumb": [], "artistbackground": []})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            first, second = await asyncio.gather(
                cache.get(client, "artist", "first-key"),
                cache.get(client, "artist", "first-key"),
            )
            assert first == second
            await Fanart(store).get(client, "artist", "first-key")
            assert calls == ["first-key"]
            await cache.get(client, "artist", "rotated-key")
            assert calls == ["first-key", "rotated-key"]

    asyncio.run(run())
    with store.connect() as conn:
        documents = str(conn.execute("SELECT * FROM documents").fetchall())
    assert "first-key" not in documents and "rotated-key" not in documents
