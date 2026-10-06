import asyncio
import httpx
from server.store import Store
from server.playlists import Playlists
from server.plex import Plex

CONFIG = {"machine_id": "machine", "library_root": "/Audio", "section_id": "1"}


def test_plex_exact_paths_do_not_match_ambiguous_or_unpublished_downloads(tmp_path):
    store = Store(tmp_path)
    plex = Plex(store, Playlists(store))
    detail = {
        "entries": [
            {"saved_track": {"id": "a", "relative_path": "Album/song.mp3"}},
            {"saved_track": {"id": "b", "relative_path": "Other/song.mp3"}},
            {"saved_track": {"id": "c", "relative_path": "../outside.mp3"}},
            {"saved_track": None},
        ]
    }
    assert plex.desired(
        detail,
        {"/Audio/Album/song.mp3": {"11"}, "/Audio/Other/song.mp3": {"12", "13"}},
        CONFIG,
    ) == ["11"]


def test_plex_reconciles_order_and_counts_repeats_without_treating_them_as_missing(
    tmp_path,
):
    store = Store(tmp_path)
    plex = Plex(store, Playlists(store))
    plex.save("plex-playlist:playlist", {"remote_id": "99"})
    current = [("1", "101"), ("3", "103")]
    next_id = 104
    mutations = []

    def transport(request):
        nonlocal next_id
        path = request.url.path
        mutations.append((request.method, path))
        if path == "/playlists/99":
            return httpx.Response(
                200,
                text='<MediaContainer><Playlist summary="Managed by Pig Music: playlist"/></MediaContainer>',
            )
        if path == "/playlists/99/items" and request.method == "GET":
            return httpx.Response(
                200,
                text="<MediaContainer>"
                + "".join(
                    f'<Track ratingKey="{key}" playlistItemID="{item}"/>'
                    for key, item in current
                )
                + "</MediaContainer>",
            )
        if request.method == "PUT" and path.endswith("/items"):
            current.append((request.url.params["uri"].rsplit("/", 1)[-1], str(next_id)))
            next_id += 1
        elif path.endswith("/move"):
            item_id = path.split("/")[-2]
            item = next(t for t in current if t[1] == item_id)
            current.remove(item)
            after = request.url.params.get("after")
            position = (
                next(i + 1 for i, t in enumerate(current) if t[1] == after)
                if after
                else 0
            )
            current.insert(position, item)
        elif request.method == "DELETE":
            current[:] = [t for t in current if t[1] != path.rsplit("/", 1)[-1]]
        return httpx.Response(200, text="<MediaContainer/>")

    async def run():
        async with httpx.AsyncClient(
            base_url="http://plex", transport=httpx.MockTransport(transport)
        ) as client:
            await plex.reconcile(
                client,
                CONFIG,
                {"id": "playlist", "name": "Test", "track_count": 4},
                ["2", "1", "2"],
            )

    asyncio.run(run())
    assert [t[0] for t in current] == ["2", "1"]
    state = store.read_document("plex-playlist:playlist")
    assert (
        state["available_count"] == 2
        and state["pending_count"] == 1
        and state["repeated_count"] == 1
    )
    assert any(
        method == "DELETE" and path.endswith("103") for method, path in mutations
    )


def test_plex_does_not_edit_playlist_after_ownership_changes(tmp_path):
    store = Store(tmp_path)
    plex = Plex(store, Playlists(store))
    plex.save("plex-playlist:playlist", {"remote_id": "99"})
    calls = []

    def transport(request):
        calls.append(request.method)
        return httpx.Response(
            200,
            text='<MediaContainer><Playlist summary="Personal playlist"/></MediaContainer>',
        )

    async def run():
        async with httpx.AsyncClient(
            base_url="http://plex", transport=httpx.MockTransport(transport)
        ) as client:
            try:
                await plex.reconcile(
                    client,
                    CONFIG,
                    {"id": "playlist", "name": "Test", "track_count": 1},
                    ["1"],
                )
            except ValueError:
                pass
            else:
                raise AssertionError("Changed ownership must stop automatic editing")

    asyncio.run(run())
    assert calls == ["GET"]
