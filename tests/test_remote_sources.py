import asyncio
import httpx
import pytest
from server.remote import RemoteAudio


def test_fast_remote_requires_release_context_and_caches_verified_urls():
    calls = []
    target = {
        "artist": "Artist",
        "title": "Song",
        "album": "Album",
        "duration": 180,
        "isrcs": ["ABC"],
    }
    candidate = {
        "channel": "Artist",
        "title": "Song",
        "album": "Album",
        "duration": 180,
        "source_url": "https://aac.saavncdn.com/music.m4a",
    }

    async def run():
        def search(*args):
            calls.append("search")
            return [candidate, candidate]

        def transport(req):
            calls.append("probe")
            return httpx.Response(206, headers={"content-type": "audio/mp4"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(transport)
        ) as client:
            resolver = RemoteAudio(search)
            assert await resolver.resolve(client, target) == candidate["source_url"]
            assert await resolver.resolve(client, target) == candidate["source_url"]
            resolver.cache.clear()
            for change in [
                {"album": "Different album"},
                {"isrc": "WRONG"},
                {"source_url": "https://127.0.0.1/private"},
            ]:
                resolver.search = lambda *_: [{**candidate, **change}]
                with pytest.raises(ValueError):
                    await resolver.resolve(client, target)

    asyncio.run(run())
    assert calls == ["search", "probe"]


def test_remote_falls_back_in_order_to_a_relayed_lossy_source(tmp_path, monkeypatch):
    import shutil
    import subprocess
    from server.providers import network

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is required for the relay probe")
    fixture = tmp_path / "fixture.mp3"
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=duration=3", str(fixture)],
        check=True,
    )
    target = {"artist": "Artist", "title": "Song", "album": "Album", "duration": 3}
    candidate = {
        "channel": "Artist",
        "title": "Song",
        "duration": 3,
        "source_url": "https://zvu4it.org/song.mp3",
    }
    searched = []

    def relay_search(source, track):
        searched.append(source)
        if source == "zvu4no":
            # A live version is not the requested recording; the next source is tried.
            return [{**candidate, "title": "Song (Live)"}]
        # Several copies of one recording: the 320 kbps one is relayed.
        return [
            {
                **candidate,
                "source_url": "https://meln.top/low.mp3",
                "quality": "128kbps",
            },
            {
                **candidate,
                "source_url": "https://meln.top/song.mp3",
                "quality": "320kbps",
            },
        ]

    def transfer(url, hosts, path, context):
        assert url == "https://meln.top/song.mp3" and "meln.top" in hosts
        shutil.copyfile(fixture, path)

    monkeypatch.setattr(network, "transfer", transfer)
    resolver = RemoteAudio(
        lambda *_: [], directory=tmp_path / "relay", relay_search=relay_search
    )

    async def run():
        async with httpx.AsyncClient() as client:
            return await resolver.stream(client, target, "member")

    found = asyncio.run(run())
    assert found["source"] == "freemp3cloud" and searched == ["zvu4no", "freemp3cloud"]
    path, media_type = resolver.relay(found["relay"], "member")
    assert media_type == "audio/mpeg" and path.read_bytes() == fixture.read_bytes()
    # A relay belongs to the person who asked for it.
    assert resolver.relay(found["relay"], "someone-else") is None
    # The fetched file is reused for the same recording.
    assert asyncio.run(run())["source"] == "freemp3cloud"
    assert searched == ["zvu4no", "freemp3cloud"]


def test_relay_cache_survives_restarts_expires_and_keeps_recent_plays(
    tmp_path, monkeypatch
):
    import os
    import time
    from server import remote

    target = {"artist": "Artist", "title": "Song", "album": "Album", "duration": 3}
    directory = tmp_path / "relay"
    directory.mkdir()
    resolver = RemoteAudio(directory=directory)
    path = directory / f"{resolver.name(target)}.zvu4no.mp3"
    path.write_bytes(b"x" * 10)
    # A new resolver (a restarted server) finds the copy by recording.
    assert RemoteAudio(directory=directory).cached(target) == (path, "zvu4no")
    old = time.time() - remote.RELAY_SECONDS - 60
    os.utime(path, (old, old))
    assert resolver.cached(target) is None
    resolver.prune()
    assert not path.exists()
    # Over budget, the least recently played copy goes first.
    monkeypatch.setattr(remote, "RELAY_BYTES", 15)
    for name, age in (("a", 300), ("b", 200), ("c", 100)):
        stale = directory / f"{name * 32}.youtube.m4a"
        stale.write_bytes(b"x" * 10)
        os.utime(stale, (time.time() - age, time.time() - age))
    resolver.prune()
    assert sorted(p.name[0] for p in directory.iterdir()) == ["c"]
