import json
import uuid
import pytest
from test_native_sync import fixture
from server.native_mutations import NativeMutations
from server.playlists import Playlists, PlaylistConflict


def edit(action, **values):
    return {"operation_id": str(uuid.uuid4()), "action": action, **values}


def test_retry_after_lost_response_does_not_duplicate_playlist_occurrences(tmp_path):
    store, owner, member = fixture(tmp_path)
    service = NativeMutations(store)
    create = edit("create", name="Offline")
    receipt = service.apply(member, create)
    assert service.apply(member, create) == receipt
    song = {"title": "Song", "artist": "Artist"}
    append = edit("append", playlist_id=receipt["playlist_id"], track=song)
    result = service.apply(member, append)
    assert service.apply(member, append) == result
    assert len(Playlists(store, member).detail(receipt["playlist_id"])["entries"]) == 1
    service.apply(
        member, edit("append", playlist_id=receipt["playlist_id"], track=song)
    )
    assert len(Playlists(store, member).detail(receipt["playlist_id"])["entries"]) == 2
    with pytest.raises(PlaylistConflict):
        service.apply(
            member, {**append, "track": {"title": "Different", "artist": "Artist"}}
        )
    with pytest.raises(LookupError):
        service.apply(
            owner, edit("append", playlist_id=receipt["playlist_id"], track=song)
        )


def test_stale_edits_leave_the_receipt_uncommitted_for_review(tmp_path):
    store, owner, member = fixture(tmp_path)
    service = NativeMutations(store)
    created = service.apply(member, edit("create", name="Original"))
    stale = edit("rename", playlist_id=created["playlist_id"], revision=0, name="Stale")
    with pytest.raises(PlaylistConflict):
        service.apply(member, stale)
    with store.connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM native_mutations WHERE operation_id=?",
            (stale["operation_id"],),
        ).fetchone()
    refreshed = {**stale, "revision": 1}
    service.apply(member, refreshed)
    assert Playlists(store, member).detail(created["playlist_id"])["name"] == "Stale"


def test_receipt_and_side_effect_rollback_together(tmp_path, monkeypatch):
    import server.native_mutations as module

    store, owner, member = fixture(tmp_path)
    service = NativeMutations(store)
    create = edit("create", name="Never committed")

    def fail(*args):
        raise RuntimeError("Simulated crash before receipt commit")

    monkeypatch.setattr(module, "bump", fail)
    with pytest.raises(RuntimeError):
        service.apply(member, create)
    with store.connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM playlists WHERE id=?", (create["operation_id"],)
        ).fetchone()
        assert not conn.execute(
            "SELECT 1 FROM native_mutations WHERE operation_id=?",
            (create["operation_id"],),
        ).fetchone()


def test_favourites_and_preferences_replay_without_repeating_changes(tmp_path):
    store, owner, member = fixture(tmp_path)
    service = NativeMutations(store)
    favourite = edit(
        "favourite", track={"title": "Cloud song", "artist": "Artist"}, favourite=True
    )
    service.apply(member, favourite)
    service.apply(member, favourite)
    detail = Playlists(store, member).detail("pig-favourites:" + member)
    assert len(detail["entries"]) == 1 and detail["revision"] == 1
    preferences = edit(
        "preferences", preferences={"appearance": "dark", "default_tab": "albums"}
    )
    service.apply(member, preferences)
    assert service.apply(member, preferences)["applied"]
    with store.connect() as conn:
        assert (
            json.loads(
                conn.execute(
                    "SELECT payload FROM user_preferences WHERE user_id=?", (member,)
                ).fetchone()[0]
            )["appearance"]
            == "dark"
        )
