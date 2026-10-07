import json
import pytest
from server.auth import Auth
from server.store import Store
from server.native_sync import NativeSync, ResyncRequired


def fixture(tmp_path):
    (tmp_path / "library-snapshot.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": str(i),
                        "title": f"Song {i}",
                        "artist": "Artist",
                        "album_artist": "Artist",
                        "album": "Album",
                        "duration": 100,
                        "path": f"/private/song{i}.mp3",
                        "available": True,
                    }
                    for i in range(3)
                ]
            }
        )
    )
    store = Store(tmp_path)
    auth = Auth(store)
    owner = auth.create_owner("mark", "native fixture password")
    member_code = auth.setup_code(owner, "member", "Member")
    member = auth.activate(member_code["code"], "native fixture password", "fixture")[
        "id"
    ]
    return store, owner, member


def test_cursor_scoped_revision_and_durable_deletes(tmp_path):
    store, owner, member = fixture(tmp_path)
    sync = NativeSync(store)
    first = sync.page(owner, "tracks", limit=1)
    assert first["total"] == 3
    assert "/private/" not in json.dumps(first)
    assert first["items"][0]["server_state"] == "in_library"
    assert sync.page(owner, "tracks", first["next_cursor"], 1)["items"][0]["id"] == "1"
    with pytest.raises(ResyncRequired):
        sync.page(member, "tracks", first["next_cursor"], 1)
    with store.connect() as conn:
        conn.execute(
            "DELETE FROM library_members WHERE user_id=? AND track_id='1'", (owner,)
        )
        conn.execute(
            "UPDATE membership_versions SET revision=revision+1 WHERE user_id=?",
            (owner,),
        )
    changed = sync.changes(owner, first["revision"])
    assert changed["deletes"]["tracks"] == ["1"]
    assert NativeSync(Store(tmp_path)).changes(owner, first["revision"]) == changed
    with pytest.raises(ResyncRequired):
        sync.page(owner, "tracks", first["next_cursor"], 1)
    with pytest.raises(ResyncRequired):
        sync.changes(member, first["revision"])


def test_member_grants_retention_and_invalid_cursor(tmp_path):
    store, owner, member = fixture(tmp_path)
    sync = NativeSync(store)
    first = sync.page(member, "tracks")
    store.user_libraries.add(member, ["0"])
    changes = sync.changes(member, first["revision"])
    assert [t["id"] for t in changes["upserts"]["tracks"]] == ["0"]
    assert len(changes["upserts"]["albums"]) == 1
    with store.connect() as conn:
        conn.execute(
            "UPDATE sync_revisions SET captured_at=0 WHERE user_id=?", (member,)
        )
    with pytest.raises(ResyncRequired):
        sync.changes(member, first["revision"])
    with pytest.raises(ValueError):
        sync.page(owner, "tracks", "bad!", 100)


def test_private_playlist_delta_and_return_to_previous_file_state(tmp_path):
    from server.playlists import Playlists

    store, owner, member = fixture(tmp_path)
    sync = NativeSync(store)
    first = sync.page(owner, "tracks")
    playlist = Playlists(store, owner).create("Private fixture")
    delta = sync.changes(owner, first["revision"])
    assert delta["upserts"]["playlists"][0]["name"] == "Private fixture"
    assert (
        sync.changes(member, sync.page(member, "tracks")["revision"])["upserts"][
            "playlists"
        ]
        == []
    )
    Playlists(store, owner).edit(playlist["id"], 0, delete=True)
    removed = sync.changes(owner, delta["revision"])
    assert removed["deletes"]["playlists"] == [playlist["id"]]
    original_revision = store.library_revision
    store.library_revision = "changed-household"
    sync.page(owner, "tracks")
    store.library_revision = original_revision
    again = sync.page(owner, "tracks")
    assert again["revision"] != first["revision"]
    assert all(t["album_id"] for t in again["items"])
