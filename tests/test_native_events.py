from types import SimpleNamespace
import pytest
import asyncio
from fastapi import HTTPException
from server.routes.native import native_router
from test_native_sync import fixture
from server.auth import Auth


def test_scoped_events_bound_connections_and_revoke(tmp_path):
    asyncio.run(events_journey(tmp_path))


async def events_journey(tmp_path):
    store, owner, member = fixture(tmp_path)
    auth = Auth(store)
    token = auth.login(
        "member", "native fixture password", "device", "fixture", "ios", "fixture"
    )["token"]
    user, session = auth.authenticate(token)
    router = native_router(store, auth)
    endpoint = next(
        route.endpoint for route in router.routes if route.path == "/api/v1/events"
    )

    async def connected():
        return False

    request = SimpleNamespace(
        state=SimpleNamespace(user=user, session=session), is_disconnected=connected
    )
    responses = [await endpoint(request) for _ in range(4)]
    with pytest.raises(HTTPException) as failure:
        await endpoint(request)
    assert failure.value.status_code == 429
    for response in responses:
        message = await anext(response.body_iterator)
        assert message.startswith("event: revision")
    response = responses[0]
    queue = await anext(response.body_iterator)
    assert '"items":[]' in queue and "event: queue" in queue
    await anext(response.body_iterator)
    auth.revoke(member, session["public_id"])
    assert "event: revoked" in await anext(response.body_iterator)
    for response in responses:
        await response.body_iterator.aclose()
    # Closing a stream releases its reserved connection slot.
    final = await endpoint(request)
    assert "event: revoked" in await anext(final.body_iterator)
    await final.body_iterator.aclose()
