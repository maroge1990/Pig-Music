import asyncio
from datetime import timedelta
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from server.home import HomeDiscovery
from server.mix_cache import song_key, MixDownloader
from server.mixes import choose
from test_security import PASSWORD, protected
from test_downloader import audio  # Shared real MP3 fixture, not provider traffic.


def track(n=1, **extra):
    return {
        "title": f"Song {n}",
        "artist": f"Artist {n}",
        "album": "Album",
        "album_artist": f"Artist {n}",
        "duration": 3,
        "track_number": 1,
        "disc_number": 1,
        "year": "",
        **extra,
    }


def cached(mixes, song, now=None):
    key = song_key(song)
    filename = key + ".mp3"
    path = mixes.cache.directory / filename
    path.write_bytes(b"fixture audio")
    with mixes.store.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mix_audio VALUES (?,?,?,?,?,?)",
            (
                key,
                filename,
                json.dumps({"codec": "mp3", "bitrate_kbps": 320}),
                path.stat().st_size,
                0,
                now or time.time() - 7200,
            ),
        )
    return path


def ready(mixes, user, songs, day=None, kind="daily"):
    day = day or mixes.day()
    identity = mixes.stage(
        user, kind, day, "Fixture blend", "Because you saved music", songs
    )
    mixes.publish(identity, songs, mixes.day())
    return identity


def member(app, owner):
    setup = app.state.auth.setup_code(owner, "member", "Member")
    app.state.auth.activate(setup["code"], PASSWORD, "fixture")
    token = app.state.auth.login(
        "member", PASSWORD, "device", "phone", "ios", "fixture"
    )["token"]
    with app.state.store.connect() as conn:
        user = conn.execute("SELECT id FROM users WHERE username='member'").fetchone()[
            0
        ]
    return user, token


def test_daily_selection_changes_without_losing_identity_or_artist_diversity():
    songs = [track(n, artist=f"Artist {n % 25}") for n in range(100)]
    left = choose(songs, 30, "today")
    assert left == choose(list(reversed(songs)), 30, "today")
    right = choose(songs, 30, "tomorrow")
    assert len({song_key(t) for t in left} - {song_key(t) for t in right}) >= 15
    assert all(a["artist"] != b["artist"] for a, b in zip(left, left[1:]))
    recent = {song_key(t): int(time.time()) for t in left}
    assert not {song_key(t) for t in choose(songs, 30, "today", recent)} & set(recent)
    a = track(musicbrainz_release_id="release", musicbrainz_recording_id="recording")
    assert song_key(a) == song_key({**a, "title": "Spelling difference"})
    assert song_key(a) != song_key({**a, "musicbrainz_release_id": "live-edition"})
    assert len(choose([a, {**a, "musicbrainz_release_id": "other"}], 5, "day")) == 1


def test_private_editions_signed_cache_playback_history_and_save(
    tmp_path, monkeypatch, audio
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    user, token = member(app, owner)
    cached(mixes, track()).write_bytes(audio.read_bytes())
    identity = ready(mixes, user, [track()])
    other = ready(mixes, owner, [track(2)])
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        feed = client.get("/api/v1/home/mixes")
        assert feed.status_code == 200, feed.text
        assert "relative_path" not in feed.text and "filename" not in feed.text
        song = feed.json()["mixes"][0]["tracks"][0]
        assert song["id"] == f"mix:{identity}:0"
        assert client.post(f"/api/v1/playback/mix:{other}:0/url").status_code == 404
        assert client.get("/api/v1/admin/mixes").status_code == 403
        assert client.put("/api/v1/admin/mixes", json={}).status_code == 403
        assert client.get(f"/api/v1/admin/mixes/people/{user}").status_code == 403
        playback = client.post(f"/api/v1/playback/{song['id']}/url")
        assert playback.status_code == 200, playback.text
        assert client.get(playback.json()["url"]).content == audio.read_bytes()
        partial = client.get(playback.json()["url"], headers={"Range": "bytes=10-99"})
        assert (
            partial.status_code == 206 and partial.content == audio.read_bytes()[10:100]
        )
        # The audio element can use the session-bound signature without its bearer.
        audio_client = TestClient(app, base_url="https://private.ts.net")
        assert audio_client.get(playback.json()["url"]).status_code == 200
        events = {
            "events": [
                {
                    "track_id": song["id"],
                    "seconds": 30,
                    "played_at": int(time.time()),
                    "event_id": "mix-listen",
                }
            ]
        }
        assert client.post("/api/v1/play-events", json=events).status_code == 200
        assert client.post("/api/v1/play-events", json=events).status_code == 200
        assert mixes.history(user, [])[song_key(track())] > 0
        with app.state.store.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM mix_listens").fetchone()[0] == 1
        saved = client.post(f"/api/v1/mixes/{identity}/save")
        assert saved.status_code == 200, saved.text
        assert (
            client.post(f"/api/v1/mixes/{identity}/save").json()["id"]
            == saved.json()["id"]
        )
        assert app.state.store.queue()["items"] == []
        from server.media import save_settings

        save_settings(app.state.store, portraits=True, remote_playback=False)
        # Saved editions reuse the prepared file even when experimental streams are off.
        reused = client.post("/api/v1/remote-playback", json=track())
        assert reused.status_code == 200 and reused.json()["source"] == "Prepared mix"
        assert not app.state.store.user_libraries.contains(user, song["id"])
        assert (
            client.post("/api/v1/mixes/hide", json={"track_id": song["id"]}).status_code
            == 200
        )
        assert client.get("/api/v1/home/mixes").json()["mixes"] == []


def test_rotation_respects_shared_references_queue_leases_and_restart(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    user, _ = member(app, owner)
    song = track()
    path = cached(mixes, song)
    today = mixes.day()
    first = ready(mixes, owner, [song])
    second = ready(mixes, user, [song])
    mixes.playback(owner, f"mix:{first}:0")  # Protect the complete playing edition.
    ready(mixes, owner, [track(2)], day=today + timedelta(days=1))
    mixes.activate(today + timedelta(days=1))
    mixes.cache.cleanup(time.time() + 7200)
    assert path.exists()  # Other person's active edition still needs the file.
    ready(mixes, user, [track(3)], day=today + timedelta(days=1))
    mixes.activate(today + timedelta(days=1))
    mixes.cache.cleanup(time.time() + 7200)
    assert path.exists()  # No active mix, but the durable playback lease remains.
    mixes.cache.cleanup(time.time() + 7 * 3600)
    assert not path.exists()
    # Playlist metadata, including delayed-listen identity, outlives audio retention.
    assert mixes.entry(owner, f"mix:{first}:0")["title"] == song["title"]
    with pytest.raises(LookupError):
        mixes.entry(owner, f"mix:{second}:0")


def test_future_editions_do_not_replace_today_until_rotation(tmp_path, monkeypatch):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    for song in (track(), track(2)):
        cached(mixes, song)
    first = ready(mixes, owner, [track()])
    tomorrow = mixes.day() + timedelta(days=1)
    second = ready(mixes, owner, [track(2)], day=tomorrow)
    assert mixes.list(owner)["mixes"][0]["id"] == first
    mixes.activate(tomorrow)
    assert mixes.list(owner)["mixes"][0]["id"] == second


def test_failed_preparation_retains_last_ready_and_publishes_shorter_complete_mix(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    cached(mixes, track())
    first = ready(mixes, owner, [track()], day=mixes.day() - timedelta(days=1))
    second = mixes.stage(
        owner, "daily", mixes.day(), "New", "Reason", [track(), track(2)]
    )
    asyncio.run(mixes.prepare_staged(owner, mixes.day(), mixes.day()))
    assert mixes.list(owner)["mixes"][0]["id"] == first
    with mixes.store.connect() as conn:
        payload = json.loads(
            conn.execute(
                "SELECT payload FROM mix_editions WHERE id=?", (second,)
            ).fetchone()[0]
        )
    payload.update(attempts=2, retry_at=0)
    mixes.update(second, payload)
    mixes.store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})

    def fail(downloader, song):
        downloader.result = "failed"
        downloader.error = "No matching candidate"
        return False

    monkeypatch.setattr(MixDownloader, "fetch", fail)
    asyncio.run(mixes.prepare_staged(owner, mixes.day(), mixes.day()))
    feed = mixes.list(owner)["mixes"][0]
    assert feed["id"] == second and len(feed["tracks"]) == 1
    # Admin still sees both intended songs and why the second was left out.
    detail = mixes.inspect(owner)
    edition = next(e for e in detail["editions"] if e["id"] == second)
    assert edition["state"] == "ready" and edition["published"] == 1
    assert [(s["title"], s["status"], s["detail"]) for s in edition["songs"]] == [
        ("Song 1", "cached", None),
        ("Song 2", "failed", "No matching candidate"),
    ]
    status = mixes.cache.status()
    assert status["people"] == [
        {"id": owner, "name": "mark", "ready": 1, "preparing": 0}
    ]


def test_owned_mix_rows_keep_library_actions_separate_from_private_playback(
    tmp_path, monkeypatch
):
    nas = tmp_path / "nas"
    nas.mkdir()
    (nas / "song.mp3").write_bytes(b"fixture audio")
    song = track(id="owned", relative_path="song.mp3")
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [song]}))
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    identity = ready(mixes, owner, [song])
    row = mixes.list(owner)["mixes"][0]["tracks"][0]
    assert row.id == f"mix:{identity}:0"
    assert row.library_track_id == "owned" and row.server_state == "in_library"
    assert mixes.playback(owner, row.id).read_bytes() == b"fixture audio"


def test_tag_candidates_accept_the_providers_list_response(tmp_path, monkeypatch):
    app, _ = protected(tmp_path, monkeypatch)
    home = HomeDiscovery(app.state.store, None)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=[{"recording_mbid": "one"}])
            )
        ) as client:
            value, failed = await home.feed(client, "lb-radio/tags", tag="rock")
            assert value == {"recordings": [{"recording_mbid": "one"}]} and not failed

    asyncio.run(run())


def test_cache_download_uses_validation_without_nas_or_membership(
    tmp_path, monkeypatch, audio
):
    app, _ = protected(tmp_path, monkeypatch)
    store = app.state.store
    store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    song = {"title": "Test", "artist": "Test", "album": "Studio", "duration": 3}
    candidate = {
        "title": "Test",
        "channel": "Test",
        "duration": 3,
        "quality": "320kbps",
        "source_url": "https://meln.top/mix-fixture.mp3",
    }
    downloader = MixDownloader(
        store.mix_cache,
        app.state.source_runtime,
        lambda: False,
        providers={"freemp3cloud": lambda q, n: [candidate]},
    )
    from server.providers import network

    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=audio.read_bytes())

    monkeypatch.setattr(
        network,
        "client",
        lambda: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    assert downloader.fetch(song)
    assert len(requests) == 1 and requests[0].url.host == "meln.top"
    assert store.mix_cache.file(song_key(song)).is_file()
    assert store.queue()["items"] == []
    assert not (tmp_path / "nas").exists()
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM acquired").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM library_members").fetchone()[0] == 0
        probe = json.loads(conn.execute("SELECT probe FROM mix_audio").fetchone()[0])
        assert probe["codec"] == "mp3" and probe["duration"] == pytest.approx(
            3, abs=0.1
        )
    store.write_document("mix-settings", {"budget_bytes": 1})
    assert not downloader.fetch(track(3))


@pytest.mark.parametrize("failure", ["invalid_audio", "incomplete_transfer"])
def test_cache_rejects_invalid_or_incomplete_transfers(
    tmp_path, monkeypatch, audio, failure
):
    from server.providers import network

    app, _ = protected(tmp_path, monkeypatch)
    store = app.state.store
    store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    candidate = {
        "title": "Song 1",
        "channel": "Artist 1",
        "duration": 3,
        "quality": "320kbps",
        "source_url": "https://meln.top/mix-fixture.mp3",
    }
    body = b"not audio" if failure == "invalid_audio" else audio.read_bytes()
    headers = (
        {"content-length": str(len(body) + 1)}
        if failure == "incomplete_transfer"
        else {}
    )
    monkeypatch.setattr(
        network,
        "client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=body, headers=headers)
            )
        ),
    )
    worker = MixDownloader(
        store.mix_cache,
        app.state.source_runtime,
        lambda: False,
        providers={"freemp3cloud": lambda q, n: [candidate]},
    )
    assert not worker.fetch(track()) and worker.result == "failed"
    assert not list(store.mix_cache.staging.iterdir())
    with store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM mix_audio").fetchone()[0] == 0
    assert not (tmp_path / "nas").exists()


def test_explicit_library_add_copies_cache_and_survives_cache_cleanup(
    tmp_path, monkeypatch, audio
):
    from server.downloader import Downloader
    from server.media import track_file

    app, owner = protected(tmp_path, monkeypatch)
    store = app.state.store
    store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    song = track()
    path = cached(store.mixes, song)
    path.write_bytes(audio.read_bytes())
    store.submit_catalogue([{**song, "status": "missing"}], user_id=owner)
    store.mix_cache.cleanup(time.time() + 7200)
    assert path.is_file()  # The queued library intent protects audio before processing.
    job = store.claim_request()
    worker = Downloader(
        store, providers={}
    )  # No provider search can rescue a broken promotion.
    worker.process(job)
    assert store.queue()["items"][0]["status"] == "completed", store.queue()["items"]
    published = store.library["albums"][0]["tracks"][0]
    durable = track_file(store, published["id"])
    assert store.user_libraries.contains(owner, published["id"])
    assert durable != path and durable.is_file() and path.is_file()
    store.mix_cache.cleanup(time.time() + 7 * 3600)
    assert not path.exists() and durable.is_file()


def test_background_pass_prepares_all_families_and_tomorrow_without_duplicate_work(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    store = app.state.store
    mixes = store.mixes
    owned = [track(n, id=f"owned-{n}", genre="Rock") for n in range(45)]
    discoveries = [
        track(n, genre="Rock", reason="Similar to Artist 0", bucket="related")
        for n in range(100, 120)
    ]
    discoveries += [track(120, bucket="popular")]
    for song in owned + discoveries:
        cached(mixes, song, now=time.time())
    monkeypatch.setattr(
        store.user_libraries,
        "projection",
        lambda user: {"tracks": owned, "artists": [], "albums": []},
    )
    calls = []

    async def candidates(client, projection):
        calls.append(projection)
        return discoveries, "Rock"

    monkeypatch.setattr(mixes, "candidates", candidates)

    async def run():
        await mixes.prepare_pass(None)
        first = mixes.list(owner)
        await mixes.prepare_pass(None)
        assert mixes.list(owner) == first
        assert (
            len(calls) == 2
        )  # Current and next day; revisiting Home never prepares again.
        assert {m["kind"] for m in first["mixes"]} == {
            "daily",
            "back",
            "artist",
            "genre",
            "popular",
        }
        for mix in first["mixes"]:
            assert mix["day"] == str(mixes.day())
            assert all(mixes.playback(owner, t.id).is_file() for t in mix["tracks"])
        with store.connect() as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM mix_editions WHERE active=0 AND retired_at IS NULL"
                ).fetchone()[0]
                == 5
            )
        assert store.queue()["items"] == []

    asyncio.run(run())


def test_ready_daily_editions_do_not_starve_an_unfinished_family(tmp_path, monkeypatch):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    today = mixes.day()
    cached(mixes, track())
    for day in (today, today + timedelta(days=1)):
        ready(mixes, owner, [track()], day=day)
    artist = mixes.stage(
        owner, "artist", today, "Around an artist", "Reason", [track()]
    )

    def unexpected_projection(user):
        pytest.fail("Retrying staged work must not repeat candidate generation")

    monkeypatch.setattr(mixes.store.user_libraries, "projection", unexpected_projection)
    asyncio.run(mixes.prepare_person(None, owner, today))
    assert artist in {m["id"] for m in mixes.list(owner)["mixes"]}


def test_disabled_members_upcoming_editions_never_reactivate(tmp_path, monkeypatch):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    user, _ = member(app, owner)
    tomorrow = mixes.day() + timedelta(days=1)
    ready(mixes, user, [track()], day=tomorrow)
    with mixes.store.connect() as conn:
        conn.execute("UPDATE users SET disabled=1 WHERE id=?", (user,))
    mixes.activate(tomorrow)
    assert mixes.list(user)["mixes"] == []


def test_reclaims_retired_audio_before_attempting_preparation(tmp_path, monkeypatch):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    path = cached(mixes, track())
    calls = []

    async def prepare(client, user, today):
        assert not path.exists()
        calls.append(user)

    monkeypatch.setattr(mixes, "prepare_person", prepare)
    asyncio.run(mixes.prepare_pass(None))
    assert calls == [owner]


def test_saved_edition_reacquires_expired_audio_without_experimental_streaming(
    tmp_path, monkeypatch
):
    from server.media import save_settings

    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    user, token = member(app, owner)
    song = track()
    path = cached(mixes, song)
    edition = ready(mixes, user, [song])
    playlist = mixes.save(user, edition)
    with mixes.store.connect() as conn:
        conn.execute(
            "UPDATE mix_editions SET active=0,retired_at=? WHERE id=?",
            (time.time() - 7200, edition),
        )
    mixes.cache.cleanup()
    assert not path.exists()
    save_settings(mixes.store, portraits=True, remote_playback=False)
    calls = []

    def fetch(worker, canonical):
        calls.append(canonical)
        if len(calls) == 1:
            worker.result, worker.error = "failed", "No matching full recording"
            return False
        cached(mixes, canonical, now=time.time())
        worker.result, worker.error = "ready", None
        return True

    monkeypatch.setattr(MixDownloader, "fetch", fetch)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        assert client.post("/api/v1/remote-playback", json=song).status_code == 503
        assert mixes.cache.status()["failed"] == 1
        response = client.post("/api/v1/remote-playback", json=song)
        assert response.status_code == 200, response.text
        restored = response.json()["history_track_id"]
        assert (
            restored.startswith("mix:") and response.json()["source"] == "Prepared mix"
        )
        assert client.get(response.json()["url"]).status_code == 200
        assert client.post("/api/v1/remote-playback", json=song).status_code == 200
        assert len(calls) == 2 and mixes.cache.status()["failed"] == 0
        assert client.post("/api/v1/remote-playback", json=track(2)).status_code == 409
    assert mixes.list(user)["mixes"] == []  # Playback leases are not Home cards.
    assert mixes.save(user, edition)["id"] == playlist["id"]
    with mixes.store.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM library_members").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM acquired").fetchone()[0] == 0
    assert (
        mixes.queue_saved(owner, song) is None
    )  # Another member's save grants nothing.
    mixes.cache.cleanup(time.time() + 7 * 3600)
    assert not path.exists()


def test_saved_mix_prefetch_is_durable_and_works_without_a_library(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    from unittest.mock import AsyncMock

    monkeypatch.setattr(mixes.home, "popular", AsyncMock(return_value={"songs": []}))
    song = track()
    edition = ready(mixes, owner, [song])
    mixes.save(owner, edition)
    with mixes.store.connect() as conn:
        conn.execute(
            "UPDATE mix_editions SET active=0,retired_at=? WHERE id=?",
            (time.time() - 7200, edition),
        )
    identity = mixes.queue_saved(owner, song)
    assert identity and mixes.list(owner)["mixes"] == []
    mixes.store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})

    def fetch(worker, song):
        cached(mixes, song)
        worker.result = "ready"
        return True

    monkeypatch.setattr(MixDownloader, "fetch", fetch)
    asyncio.run(mixes.prepare_person(None, owner, mixes.day()))
    assert mixes.playback(owner, identity).is_file()
    assert not mixes.list(owner)["mixes"]


def test_hide_edition_is_private_does_not_break_queue_and_expires_with_rotation(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    user, token = member(app, owner)
    cached(mixes, track())
    edition = ready(mixes, user, [track()])
    other = ready(mixes, owner, [track()])
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        assert client.post(f"/api/v1/mixes/{other}/hide").status_code == 404
        assert client.post(f"/api/v1/mixes/{edition}/hide").status_code == 200
        assert client.get("/api/v1/home/mixes").json() == {
            "mixes": [],
            "preparing": False,
        }
        assert client.post(f"/api/v1/playback/mix:{edition}:0/url").status_code == 200
    tomorrow = mixes.day() + timedelta(days=1)
    next_edition = ready(mixes, user, [track()], day=tomorrow)
    mixes.activate(tomorrow)
    assert mixes.list(user)["mixes"][0]["id"] == next_edition


def test_daily_exposure_changes_at_least_half_the_mix_across_a_week(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    owned = [track(n, id=f"owned-{n}", genre="Rock") for n in range(100)]
    discoveries = [
        track(n, bucket="related", reason="Similar to Artist 0")
        for n in range(100, 130)
    ]
    for song in owned + discoveries:
        cached(mixes, song, now=time.time())
    monkeypatch.setattr(
        mixes.store.user_libraries,
        "projection",
        lambda user: {"tracks": owned, "artists": [], "albums": []},
    )

    async def candidates(client, projection):
        return discoveries, "Rock"

    monkeypatch.setattr(mixes, "candidates", candidates)
    day = mixes.day()
    previous = set()
    for offset in range(7):
        today = day + timedelta(days=offset)
        monkeypatch.setattr(mixes, "day", lambda: today)
        mixes.activate(today)
        asyncio.run(mixes.prepare_person(None, owner, today))
        row = mixes.edition(owner, "daily", today)
        songs = json.loads(row[1])["tracks"]
        current = {song_key(t) for t in songs}
        assert len(current) == len(songs) >= 25
        assert all(a["artist"] != b["artist"] for a, b in zip(songs, songs[1:]))
        if previous:
            assert len(current - previous) >= len(current) / 2
        previous = current


def test_preparation_cursor_survives_a_time_budget_and_resumes_later_songs(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    import server.mixes as implementation

    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    mixes.store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    edition = mixes.stage(
        owner, "daily", mixes.day(), "Daily", "Reason", [track(n) for n in range(1, 4)]
    )
    row = mixes.edition(owner, "daily", mixes.day())
    payload = json.loads(row[1])
    payload["attempts"] = 2
    mixes.update(edition, payload)
    clock, calls = [0], []
    monkeypatch.setattr(
        implementation,
        "time",
        SimpleNamespace(time=time.time, monotonic=lambda: clock[0]),
    )

    def fetch(worker, song):
        calls.append(song["title"])
        clock[0] += 1
        worker.result, worker.error = "failed", "No match"
        if song["title"] == "Song 1":
            return False
        cached(mixes, song)
        worker.result = "ready"
        return True

    monkeypatch.setattr(MixDownloader, "fetch", fetch)
    asyncio.run(mixes.prepare_staged(owner, mixes.day(), mixes.day(), deadline=2))
    assert json.loads(mixes.edition(owner, "daily", mixes.day())[1])["cursor"] == 2
    clock[0] = 0
    asyncio.run(mixes.prepare_staged(owner, mixes.day(), mixes.day(), deadline=2))
    assert calls == ["Song 1", "Song 2", "Song 3"]
    assert [
        t["title"]
        for t in json.loads(mixes.edition(owner, "daily", mixes.day())[1])["tracks"]
    ] == ["Song 2", "Song 3"]


def test_cache_status_reports_only_reclaimable_audio_and_real_failures(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    retained = cached(mixes, track())
    orphan = cached(mixes, track(2))
    ready(mixes, owner, [track()])
    identity = mixes.stage(
        owner, "artist", mixes.day(), "Around an artist", "Reason", [track(3)]
    )
    asyncio.run(mixes.prepare_staged(owner, mixes.day(), mixes.day()))
    status = mixes.cache.status()
    assert status["reclaimable_bytes"] == orphan.stat().st_size
    assert status["failed"] == 0
    assert status["issues"][0]["message"] == "Downloads are paused"
    mixes.cache.cleanup()
    assert retained.exists() and not orphan.exists()


def test_empty_library_is_not_reported_as_perpetually_preparing(tmp_path, monkeypatch):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    from unittest.mock import AsyncMock

    monkeypatch.setattr(mixes.home, "popular", AsyncMock(return_value={"songs": []}))
    asyncio.run(mixes.prepare_person(None, owner, mixes.day()))
    assert mixes.list(owner) == {"mixes": [], "preparing": False}


def test_automatic_and_on_demand_downloads_share_one_transfer(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    app, _ = protected(tmp_path, monkeypatch)
    cache = app.state.store.mix_cache
    entered, release = Event(), Event()
    calls = []

    def fetch(worker, song):
        calls.append(song)
        entered.set()
        assert release.wait(5)
        cached(app.state.store.mixes, song)
        worker.result, worker.error = "ready", None
        return True

    monkeypatch.setattr(MixDownloader, "_fetch", fetch)
    first = MixDownloader(cache, app.state.source_runtime, lambda: False)
    second = MixDownloader(cache, app.state.source_runtime, lambda: False)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(first.fetch, track())
        assert entered.wait(5)
        try:
            assert not second.fetch(track()) and second.result == "deferred"
        finally:
            release.set()
        assert pending.result(timeout=5)
    assert second.fetch(track()) and len(calls) == 1


@pytest.mark.parametrize("chart_count", [0, 12])
def test_local_fallback_fills_daily_and_chart_mix_has_its_own_size(
    tmp_path, monkeypatch, chart_count
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    owned = [track(n, id=f"own-{n}") for n in range(100)]
    chart = [track(n, bucket="popular") for n in range(100, 100 + chart_count)]
    for song in owned + chart:
        cached(mixes, song, now=time.time())
    monkeypatch.setattr(
        mixes.store.user_libraries,
        "projection",
        lambda user: {"tracks": owned, "artists": [], "albums": []},
    )

    async def candidates(client, projection):
        return chart, None

    monkeypatch.setattr(mixes, "candidates", candidates)
    asyncio.run(mixes.prepare_person(None, owner, mixes.day()))
    daily = json.loads(mixes.edition(owner, "daily", mixes.day())[1])
    assert len(daily["tracks"]) == 30
    assert sum(t.get("bucket") == "popular" for t in daily["tracks"]) == min(
        3, chart_count
    )
    assert mixes.edition(owner, "artist", mixes.day()) is None
    if chart_count:
        popular = json.loads(mixes.edition(owner, "popular", mixes.day())[1])
        assert len(popular["tracks"]) == chart_count
    else:
        assert daily["reason"] == "A fresh selection from your library"


def test_genre_themes_rotate_without_a_large_discography_dominating(
    tmp_path, monkeypatch
):
    app, _ = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    songs = [track(n, artist="One rock artist", genre="Rock") for n in range(500)]
    songs += [
        track(501, genre="Jazz"),
        track(502, genre="Jazz"),
        track(503, genre="K-pop"),
    ]

    async def seeds(*args):
        return []

    async def feed(*args, **kwargs):
        return {}, False

    async def popular(*args):
        return {"songs": []}

    monkeypatch.setattr(mixes.home, "seeds", seeds)
    monkeypatch.setattr(mixes.home, "feed", feed)
    monkeypatch.setattr(mixes.home, "popular", popular)
    genres = []
    for offset in range(3):
        day = mixes.day() + timedelta(days=offset)
        _, genre = asyncio.run(
            mixes.candidates(None, {"tracks": songs, "mix_day": str(day)})
        )
        genres.append(genre)
    assert set(genres) == {"Rock", "Jazz", "K-pop"}


def test_cold_start_chart_is_labelled_regional_and_does_not_use_another_library(
    tmp_path, monkeypatch
):
    from unittest.mock import AsyncMock

    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    song = track(musicbrainz_recording_id="recording", musicbrainz_release_id="release")
    cached(mixes, song, now=time.time())
    monkeypatch.setattr(
        mixes.home,
        "popular",
        AsyncMock(
            return_value={
                "title": "Popular in Australia",
                "songs": [
                    {
                        "id": "recording",
                        "release_id": "release",
                        "name": song["title"],
                        "artist": song["artist"],
                        "album": song["album"],
                    }
                ],
            }
        ),
    )
    asyncio.run(mixes.prepare_person(None, owner, mixes.day()))
    feed = mixes.list(owner)
    assert len(feed["mixes"]) == 1
    assert feed["mixes"][0]["title"] == "Popular in Australia"
    assert "Regional chart" in feed["mixes"][0]["reason"]
    assert mixes.edition(owner, "daily", mixes.day()) is None


def test_imported_taste_seeds_discoveries_before_its_files_are_available(
    tmp_path, monkeypatch
):
    app, owner = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes
    imported = track(10, id="imported", available=False)
    discovered = track(20, bucket="related")
    cached(mixes, discovered, now=time.time())
    monkeypatch.setattr(
        mixes.store.user_libraries,
        "projection",
        lambda user: {"tracks": [imported], "artists": [], "albums": []},
    )

    async def candidates(client, projection):
        assert projection["tracks"] == [imported]
        return [discovered], None

    monkeypatch.setattr(mixes, "candidates", candidates)
    asyncio.run(mixes.prepare_person(None, owner, mixes.day()))
    daily = mixes.list(owner)["mixes"][0]
    assert (
        daily["kind"] == "daily"
        and daily["reason"] == "Discoveries inspired by your library"
    )
    assert mixes.edition(owner, "back", mixes.day()) is None


def test_a_stalled_metadata_provider_cannot_starve_the_next_person(
    tmp_path, monkeypatch
):
    import server.mixes as implementation

    app, owner = protected(tmp_path, monkeypatch)
    user, _ = member(app, owner)
    mixes = app.state.store.mixes
    completed = []

    async def prepare(client, person, today):
        if person == owner:
            await asyncio.Event().wait()
        completed.append(person)

    monkeypatch.setattr(implementation, "PASS_SECONDS", 0.02)
    monkeypatch.setattr(mixes, "prepare_person", prepare)
    asyncio.run(mixes.prepare_pass(None))
    assert completed == [user]


def test_shutdown_cancels_a_pass_that_ignores_the_stop_flag(tmp_path, monkeypatch):
    import server.mixes as implementation

    app, _ = protected(tmp_path, monkeypatch)
    mixes = app.state.store.mixes

    async def stuck(client):
        await asyncio.Event().wait()

    monkeypatch.setattr(implementation, "SHUTDOWN_SECONDS", 0.05)
    monkeypatch.setattr(mixes, "prepare_pass", stuck)

    async def run():
        mixes.stopping = asyncio.Event()
        mixes.start(None)
        await asyncio.sleep(0)
        await asyncio.wait_for(mixes.close(), timeout=2)
        return mixes.task.cancelled()

    assert asyncio.run(run())
