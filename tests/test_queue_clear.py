import hashlib, json
from server.store import Store


def test_clear_queue_invalidates_claim_and_preserves_music_and_playlists(tmp_path):
    store = Store(tmp_path / "data")
    song = {
        "id": "track",
        "artist": "Artist",
        "album_artist": "Artist",
        "album": "Album",
        "title": "Song",
        "year": 2020,
        "duration": 200,
        "disc_number": 1,
        "track_number": 1,
        "status": "missing",
    }
    store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    store.submit_catalogue([song])
    old = store.claim_request()
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO playlists(id,payload) VALUES (?,?)",
            ("kept", json.dumps({"id": "kept", "name": "Playlist", "entries": []})),
        )
    store.clear_queue()
    assert (
        not store.request_active(old["id"], old["claim_token"])
        and not store.queue()["items"]
    )
    store.submit_catalogue([song])
    new = store.claim_request()
    assert new["id"] == old["id"] and new["claim_token"] != old["claim_token"]
    store.request_state(new["id"], "validating", _claim_token=new["claim_token"])
    store.request_state(old["id"], "failed", _claim_token=old["claim_token"])
    assert store.queue()["items"][0]["status"] == "validating"
    stage = store.directory / "downloads" / "staging"
    stage.mkdir(parents=True)
    source = stage / "song.mp3"
    source.write_bytes(b"validated")
    target = store.directory / "downloads" / "library" / "song.mp3"
    probe = {"codec": "mp3", "bitrate_kbps": 320, "duration": 200}
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    store.publish_request(old, source, target, probe, sha)
    assert not target.exists() and source.exists()
    store.publish_request(new, source, target, probe, sha)
    assert target.read_bytes() == b"validated"
    store.clear_queue()
    assert target.exists() and store.library["stats"]["tracks"] == 1
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM playlists").fetchone()[0] == 1
