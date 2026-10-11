import json
from server.household_policy import HouseholdPolicy
from test_personal_removal import household


def test_shared_quality_precedence_and_claim_invalidation(tmp_path, monkeypatch):
    store, _, _, track, owner, member, _ = household(tmp_path, monkeypatch)
    track.update(codec="mp3", bitrate=128)
    (store.directory / "library-snapshot.json").write_text(
        json.dumps({"tracks": [track]})
    )
    store.refresh_library()
    policy = HouseholdPolicy(store)
    store.user_libraries.add(member, ["saved"])
    policy.set_quality(owner, "system", "*", "lossless")
    policy.set_quality(member, "system", "*", "mp3_128")
    assert store.quality_policy(track)["preferred"] == "lossless"
    album = store.library["albums"][0]["id"]
    policy.set_quality(owner, "album", album, "mp3_128")
    assert store.quality_policy(track)["preferred"] == "mp3_128"
    policy.set_quality(member, "system", "*", "lossless")
    assert store.quality_policy(track)["preferred"] == "lossless"
    job = store.queue()["items"][0]
    with store.connect() as conn:
        conn.execute("UPDATE queue SET status='validating' WHERE id=?", (job["id"],))
    policy.set_quality(member, "system", "*", "mp3_320")
    updated = next(j for j in store.queue()["items"] if j["id"] == job["id"])
    assert updated["status"] == "waiting_for_sources"
    assert updated["quality_profile"] == "mp3_320"
    assert updated.get("claim_token") != job.get("claim_token")
    assert len(policy.quality(owner)["preferences"]) == 2
    assert len(policy.quality(member)["preferences"]) == 1


def test_external_scan_assignment_and_restart_retains_memberships(
    tmp_path, monkeypatch
):
    store, _, _, track, owner, member, _ = household(tmp_path, monkeypatch)
    external = {
        **track,
        "id": "external",
        "title": "External",
        "album": "New",
        "relative_path": "external.mp3",
    }
    (store.directory / "library-snapshot.json").write_text(
        json.dumps({"tracks": [track, external]})
    )
    store.refresh_library()
    policy = HouseholdPolicy(store)
    assert policy.inbox()["albums"][0]["tracks"][0]["id"] == "external"
    assert policy.assign(["external"], [owner, member]) == {"assigned": 1, "people": 2}
    assert policy.inbox()["total"] == 0
    from server.store import Store

    restarted = Store(store.directory)
    assert restarted.user_libraries.contains(owner, "external")
    assert restarted.user_libraries.contains(member, "external")


def test_downgrade_requires_sole_membership_and_pending_users_resolve_quality(
    tmp_path, monkeypatch
):
    store, _, _, track, owner, member, _ = household(tmp_path, monkeypatch)
    track.update(codec="mp3", bitrate=320)
    (store.directory / "library-snapshot.json").write_text(
        json.dumps({"tracks": [track]})
    )
    store.refresh_library()
    store.user_libraries.add(member, ["saved"])
    policy = HouseholdPolicy(store)
    policy.set_quality(owner, "system", "*", "mp3_128")
    policy.set_quality(member, "system", "*", "mp3_128")
    assert store.queue()["items"] == []  # Sharing prevents a downgrade.
    with store.connect() as conn:
        conn.execute("DELETE FROM library_members WHERE user_id=?", (member,))
    policy.set_quality(owner, "system", "*", "mp3_128")
    assert store.queue()["items"][0]["quality_profile"] == "mp3_128"
    policy.set_quality(member, "system", "*", "lossless")
    missing = {**track, "title": "New", "album": "Other", "status": "missing"}
    store.submit_catalogue([missing], user_id=owner)
    store.submit_catalogue([missing], user_id=member)
    shared = next(j for j in store.queue()["items"] if j["title"] == "New")
    assert shared["quality_profile"] == "lossless"
    assert set(shared["requested_by"]) == {owner, member}


def test_rescan_after_rename_and_metadata_refresh_keeps_membership(
    tmp_path, monkeypatch
):
    from server.scanner import LibraryScanner

    store, root, path, track, owner, member, _ = household(tmp_path, monkeypatch)
    store.user_libraries.add(member, ["saved"])
    renamed = root / "renamed.mp3"
    path.rename(renamed)
    known = {**track, "relative_path": "renamed.mp3"}
    (store.directory / "library-snapshot.json").write_text(
        json.dumps({"tracks": [known]})
    )
    monkeypatch.setattr(
        "server.scanner.inspect_file",
        lambda p, relative: (
            {
                **known,
                "id": "new-path-derived-id",
                "size_bytes": p.stat().st_size,
                "mtime_ns": p.stat().st_mtime_ns,
            },
            None,
        ),
    )
    LibraryScanner(store, root).run()
    assert store.user_libraries.contains(owner, "saved")
    assert store.user_libraries.contains(member, "saved")
    assert store.library["albums"][0]["tracks"][0]["id"] == "saved"


def test_quality_listing_offers_shared_options_and_household_default(
    tmp_path, monkeypatch
):
    store, _, _, _, owner, _, _ = household(tmp_path, monkeypatch)
    listing = HouseholdPolicy(store).quality(owner)
    assert [(o["value"], o["label"], o["rank"]) for o in listing["options"]] == [
        ("lossless", "Lossless (FLAC)", 4),
        ("mp3_320", "MP3 320 kbps", 3),
        ("mp3_128", "MP3 128 kbps", 2),
        ("aac_256", "AAC 256 kbps", 1),
        ("native_standard", "Native audio (standard or better)", 0.5),
    ]
    assert listing["household_default"] == store.download_settings()["profile"]
