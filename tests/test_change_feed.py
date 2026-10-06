import asyncio
import json

from server.change_feed import ChangeFeed


def data(message):
    return json.loads(
        next(line[6:] for line in message.splitlines() if line.startswith("data: "))
    )


def test_feed_reconnect_latest_state_bounded_slow_reader_and_cleanup():
    async def run():
        current = {"library_revision": "one", "items": []}
        feed = ChangeFeed(lambda: dict(current), lambda: {})
        stream = feed.stream()
        first = await anext(stream)
        assert data(first)["queue"]["library_revision"] == "one"
        assert len(feed.listeners) == 1
        for n in range(100):
            feed.publish("queue", {"library_revision": str(n), "items": []})
        listener = next(iter(feed.listeners))
        assert listener.qsize() == 1
        assert data(await anext(stream))["queue"]["library_revision"] == "99"
        feed.publish("health", {"storage_available": False})
        update = data(await anext(stream))
        assert update["queue"]["library_revision"] == "99"
        assert update["health"]["storage_available"] is False
        await stream.aclose()
        assert not feed.listeners
        current["library_revision"] = "reconnected"
        second = feed.stream()
        assert data(await anext(second))["queue"]["library_revision"] == "reconnected"
        await second.aclose()
        feed.start()
        await feed.close()
        assert feed.tasks == []

    asyncio.run(run())
