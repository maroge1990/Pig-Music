import asyncio
import hashlib
import json
import shutil
import wave

import pytest
from fastapi.testclient import TestClient

from server.device_copies import DeviceCopies, checksum
from server.store import Store
from test_personal_libraries import household


def test_original_copy_checks_membership_and_supports_ranges(tmp_path, monkeypatch):
    app, owner, member, token, track = household(tmp_path, monkeypatch)
    root = tmp_path / "nas"
    (root / "private").mkdir(parents=True)
    payload = b"original-media-unchanged"
    (root / "private/song.mp3").write_bytes(payload)
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(root))
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        assert client.get("/api/v1/tracks/song/copy").status_code == 404
        assert client.get("/api/v1/tracks/song/copy/file").status_code == 404
        app.state.store.user_libraries.add(member, ["song"])
        response = client.post("/api/v1/tracks/song/copy").json()
        assert response["state"] == "ready"
        assert response["sha256"] == hashlib.sha256(payload).hexdigest()
        assert response["bytes"] == len(payload)
        assert "private" not in json.dumps(response)
        response = client.get(
            "/api/v1/tracks/song/copy/file", headers={"Range": "bytes=0-7"}
        )
        assert response.status_code == 206 and response.content == payload[:8]
        assert not app.state.device_copies.leases
        with app.state.store.connect() as conn:
            conn.execute(
                "DELETE FROM library_members WHERE user_id=? AND track_id=?",
                (member, "song"),
            )
        assert client.get("/api/v1/tracks/song/copy/file").status_code == 404


def audio_fixture(tmp_path, monkeypatch):
    root = tmp_path / "nas"
    root.mkdir()
    source = root / "song.wav"
    with wave.open(str(source), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(44100)
        stream.writeframes(b"\0" * 44100 * 4)
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(root))
    (tmp_path / "library-snapshot.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": "song",
                        "title": "Song",
                        "artist": "Artist",
                        "relative_path": "song.wav",
                    }
                ]
            }
        )
    )
    return source, DeviceCopies(Store(tmp_path))


def test_aac_is_deduplicated_validated_and_original_is_unchanged(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is required for AAC validation")
    source, copies = audio_fixture(tmp_path, monkeypatch)
    original = checksum(source)

    async def exercise():
        first = copies.manifest("song", "aac", True)
        assert first["key"] == copies.manifest("song", "aac", True)["key"]
        copies.kick()
        await copies.worker
        ready = copies.manifest("song", "aac")
        assert ready["state"] == "ready" and ready["bytes"] > 0
        output, receipt = copies.acquire("song", "aac")
        assert checksum(output) == ready["sha256"]
        copies.quota = 1
        with pytest.raises(ValueError, match="full"):
            copies.prune(1)
        assert output.exists()
        copies.release(receipt["key"])
        copies.prune(1)
        assert not output.exists()
        assert checksum(source) == original
        assert copies.manifest("song", "aac")["state"] == "not_requested"
        await copies.close()

    asyncio.run(exercise())


def test_restart_requeues_work_and_source_changes_invalidate_original_key(
    tmp_path, monkeypatch
):
    source, copies = audio_fixture(tmp_path, monkeypatch)
    first = copies.manifest("song", "original")
    job = {
        "id": "fixture",
        "state": "preparing",
        "source": str(source),
        "source_sha256": first["sha256"],
    }
    copies.save(job)
    (copies.root / "fixture.partial.m4a").write_bytes(b"incomplete")
    restarted = DeviceCopies(copies.store)
    assert restarted.read("fixture")["state"] == "queued"
    assert not (copies.root / "fixture.partial.m4a").exists()
    source.write_bytes(b"replaced-source")
    assert restarted.manifest("song", "original")["key"] != first["key"]


def test_disconnected_download_releases_cache_lease(tmp_path, monkeypatch):
    from server.routes.device_copies import LeasedFileResponse

    source, copies = audio_fixture(tmp_path, monkeypatch)
    path, value = copies.acquire("song", "original")
    response = LeasedFileResponse(path, release=lambda: copies.release(value["key"]))

    async def send(message):
        raise OSError("client disconnected")

    async def receive():
        return {"type": "http.disconnect"}

    async def exercise():
        with pytest.raises(OSError, match="disconnected"):
            await response(
                {"type": "http", "method": "GET", "headers": [], "extensions": {}},
                receive,
                send,
            )
        assert not copies.leases

    asyncio.run(exercise())
