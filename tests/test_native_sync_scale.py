"""Small native changes must not re-serialise the whole library (two-week
review, finding 4), while revisions, deletes and pagination stay coherent."""

import json
import secrets
import threading
from collections import Counter

from server.auth import Auth
from server.native_sync import MODELS, NativeSync
from server.playlists import Playlists
from server.store import Store

SIZE = 5000


def household(tmp_path, size=SIZE):
    (tmp_path / "library-snapshot.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": str(i),
                        "title": f"Song {i}",
                        "artist": f"Artist {i // 100}",
                        "album_artist": f"Artist {i // 100}",
                        "album": f"Album {i // 10}",
                        "duration": 120,
                        "available": True,
                    }
                    for i in range(size)
                ]
            }
        )
    )
    store = Store(tmp_path)
    owner = Auth(store).create_owner("owner", secrets.token_urlsafe(32))
    return store, owner


def counting(sync, monkeypatch):
    built = Counter()
    original = sync.dto

    def dto(kind, raw):
        built[kind] += 1
        return original(kind, raw)

    monkeypatch.setattr(sync, "dto", dto)
    return built


def stored_matches_projection(store, sync, user):
    """Every stored row equals a fresh, full serialisation of the projection."""
    from server.routes.personal import playlist_dto

    data = sync.capture(user)
    playlists = Playlists(store, user)
    data["playlists"] = [
        playlist_dto(playlists.detail(p["id"])) for p in playlists.list()
    ]
    with store.connect() as conn:
        stored = {
            (kind, entity): payload
            for kind, entity, payload in conn.execute(
                "SELECT entity,entity_id,payload FROM sync_entities WHERE user_id=?",
                (user,),
            )
        }
    fresh = NativeSync(store)
    expected = {
        (kind, raw["id"]): json.dumps(
            fresh.dto(kind, raw), sort_keys=True, separators=(",", ":")
        )
        for kind in MODELS
        for raw in data[kind]
    }
    assert stored == expected


def test_a_playlist_edit_serialises_only_the_playlist(tmp_path, monkeypatch):
    store, owner = household(tmp_path)
    sync = NativeSync(store)
    first = sync.capture(owner)
    built = counting(sync, monkeypatch)
    Playlists(store, owner).create("One empty playlist")
    delta = sync.changes(owner, first["revision"])
    assert {k: len(v) for k, v in delta["upserts"].items()} == {
        "artists": 0,
        "albums": 0,
        "tracks": 0,
        "playlists": 1,
    }
    assert set(built) == {"playlists"}, built
    assert delta["revision"] != first["revision"]
    stored_matches_projection(store, sync, owner)


def test_an_unchanged_sync_does_no_work(tmp_path, monkeypatch):
    store, owner = household(tmp_path)
    sync = NativeSync(store)
    first = sync.capture(owner)
    built = counting(sync, monkeypatch)
    assert sync.capture(owner)["revision"] == first["revision"]
    assert not built


def test_music_changes_after_a_playlist_edit_are_still_complete(tmp_path):
    store, owner = household(tmp_path, 300)
    sync = NativeSync(store)
    first = sync.capture(owner)
    Playlists(store, owner).create("Road trip")
    sync.capture(owner)
    with store.connect() as conn:
        conn.execute(
            "DELETE FROM library_members WHERE user_id=? AND track_id IN ('1','2')",
            (owner,),
        )
        conn.execute(
            "UPDATE membership_versions SET revision=revision+1 WHERE user_id=?",
            (owner,),
        )
    delta = sync.changes(owner, first["revision"])
    assert {"1", "2"} <= set(delta["deletes"]["tracks"])
    assert [p["name"] for p in delta["upserts"]["playlists"]] == ["Road trip"]
    stored_matches_projection(store, sync, owner)
    # Pagination is bound to the new revision and still covers everything.
    page = sync.page(owner, "tracks", limit=200)
    assert page["total"] == len(sync.capture(owner)["tracks"])


def test_concurrent_playlist_edits_and_syncs_converge(tmp_path):
    store, owner = household(tmp_path, 2000)
    sync = NativeSync(store)
    first = sync.capture(owner)
    errors = []

    def edit(n):
        try:
            for i in range(5):
                Playlists(store, owner).create(f"List {n}-{i}")
                sync.capture(owner)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=edit, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors, errors
    delta = sync.changes(owner, first["revision"])
    assert len(delta["upserts"]["playlists"]) == 20
    assert not any(delta["upserts"][k] for k in ("artists", "albums", "tracks"))
    stored_matches_projection(store, sync, owner)


def test_first_sync_pages_hold_a_thousand_songs_and_stay_byte_bounded(
    tmp_path, monkeypatch
):
    import pytest

    import server.native_sync as native_sync

    store, owner = household(tmp_path, 2500)
    sync = NativeSync(store)
    first = sync.page(owner, "tracks", limit=1000)
    assert len(first["items"]) == 1000 and first["total"] == 2500
    with pytest.raises(ValueError):
        sync.page(owner, "tracks", limit=1001)
    # A tiny byte budget splits pages early; the cursor carries on exactly.
    monkeypatch.setattr(native_sync, "PAGE_BYTES", 20_000)
    seen, cursor, sizes = [], None, []
    while True:
        page = sync.page(owner, "tracks", cursor, 1000)
        sizes.append(len(page["items"]))
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert max(sizes) < 1000
    assert sorted(seen, key=int) == [str(i) for i in range(2500)]
    assert len(seen) == len(set(seen))
