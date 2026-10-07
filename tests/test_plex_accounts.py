import asyncio
import json
import pytest
from server.plex_accounts import PlexAccounts
from server.plex import Plex
from server.playlists import Playlists
from test_personal_removal import household


def test_encrypted_tokens_are_bound_to_account_and_legacy_migration_is_idempotent(
    tmp_path, monkeypatch
):
    store, _, _, _, owner, member, _ = household(tmp_path, monkeypatch)
    config = {
        "url": "http://plex",
        "section_id": "1",
        "machine_id": "machine",
        "token": "legacy-private-token",
    }
    path = store.directory / "plex-connection.json"
    path.write_text(json.dumps(config))
    accounts = PlexAccounts(store)
    accounts.migrate_owner()
    assert "token" not in json.loads(path.read_text())
    assert accounts.token(owner) == "legacy-private-token"
    accounts.set(member, "member-private-token", "Member Plex")
    with store.connect() as conn:
        payloads = list(
            conn.execute("SELECT user_id,token_encrypted FROM plex_accounts")
        )
    assert all("private-token" not in raw for _, raw in payloads)
    accounts.migrate_owner()
    assert accounts.token(owner) == "legacy-private-token"
    assert accounts.token(member) == "member-private-token"
    with store.connect() as conn:
        encrypted = conn.execute(
            "SELECT token_encrypted FROM plex_accounts WHERE user_id=?", (owner,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE plex_accounts SET token_encrypted=? WHERE user_id=?",
            (encrypted, member),
        )
    with pytest.raises(ValueError):
        accounts.token(member)


def test_each_plex_account_receives_only_its_private_playlists(tmp_path, monkeypatch):
    store, _, _, track, owner, member, _ = household(tmp_path, monkeypatch)
    (store.directory / "plex-connection.json").write_text(
        json.dumps(
            {
                "url": "http://plex",
                "section_id": "1",
                "machine_id": "machine",
                "library_root": "/Audio",
            }
        )
    )
    accounts = PlexAccounts(store)
    accounts.set(owner, "owner-token", "Owner")
    accounts.set(member, "member-token", "Member")
    owner_playlist = Playlists(store, owner).create("Owner playlist")
    member_playlist = Playlists(store, member).create("Member playlist")
    observed = []

    async def index(self, client, config):
        return {}

    async def reconcile(self, client, config, detail, desired):
        observed.append((client.headers["X-Plex-Token"], detail["id"]))

    monkeypatch.setattr(Plex, "index", index)
    monkeypatch.setattr(Plex, "reconcile", reconcile)
    root = Plex(store, Playlists(store))
    asyncio.run(root.sync())
    assert set(observed) == {
        ("owner-token", owner_playlist["id"]),
        ("member-token", member_playlist["id"]),
    }
