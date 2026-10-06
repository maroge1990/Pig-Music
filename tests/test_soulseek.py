import json
import shutil
import subprocess

import httpx
import pytest
from mutagen.flac import FLAC

from server.downloader import Cancelled, Downloader
from server.soulseek import Soulseek, candidate_for
from server.store import Store


def song(title="Song", number=1):
    return {
        "title": title,
        "artist": "Example",
        "album": "Studio",
        "album_artist": "Example",
        "year": 2020,
        "disc_number": 1,
        "track_number": number,
        "duration": 3,
        "quality_profile": "mp3_320",
        "status": "missing",
    }


def file(title="Song", codec="mp3"):
    return {
        "filename": f"Music\\Example\\Studio\\01 {title}.{codec}",
        "size": 10000,
        "length": 3,
        "bitRate": 320,
    }


def configured(tmp_path):
    store = Store(tmp_path)
    (tmp_path / "slskd-connection.json").write_text(
        json.dumps(
            {
                "url": "http://localhost:5031",
                "api_key": "test-only",
                "download_root": str(tmp_path / "engine"),
            }
        )
    )
    return store


def test_filename_recording_album_and_quality_gates():
    response = {"username": "peer"}
    assert candidate_for(song(), response, file())
    for bad in (
        file("Song Two"),
        file("Song (Live)"),
        {**file(), "bitRate": 128},
        {**file(), "length": 10},
        {**file(), "filename": "Other\\Other Album\\Song.mp3"},
        file(codec="flac"),
    ):
        assert candidate_for(song(), response, bad) is None
    assert candidate_for(
        {**song(), "quality_profile": "lossless"}, response, file(codec="flac")
    )


def test_album_search_prefers_folder_coverage_and_reuses_results(tmp_path):
    store = configured(tmp_path)
    store.submit_catalogue([song(), song("Second", 2)])
    calls = []
    responses = [
        {"username": "partial", "queueLength": 0, "files": [file()]},
        {"username": "complete", "queueLength": 1, "files": [file(), file("Second")]},
    ]

    def handler(request):
        calls.append(request)
        if request.method == "POST":
            assert json.loads(request.content)["searchText"] == "Example Studio"
            return httpx.Response(200, json={"id": "search-id"})
        if request.url.path.endswith("responses"):
            return httpx.Response(200, json=responses)
        return httpx.Response(200, json={"isComplete": True})

    adapter = Soulseek(store)
    adapter.client = lambda: httpx.Client(
        base_url="http://engine/api/v0/", transport=httpx.MockTransport(handler)
    )
    candidates = adapter.search(song(), lambda: None)
    assert (
        candidates[0]["username"] == "complete" and candidates[0]["album_coverage"] == 2
    )
    assert adapter.search(song("Second", 2), lambda: None)[0]["username"] == "complete"
    assert sum(r.method == "POST" for r in calls) == 1


def test_peer_failure_and_cancellation_do_not_read_uncompleted_files(tmp_path):
    adapter = Soulseek(configured(tmp_path))
    deletes = []

    def handler(request):
        if request.method == "DELETE":
            deletes.append(request.url.path)
            return httpx.Response(204)
        return httpx.Response(
            200,
            json={
                "directories": [
                    {
                        "files": [
                            {
                                **file(),
                                "id": "owned-id",
                                "stateDescription": "Completed, Errored",
                            }
                        ]
                    }
                ]
            },
        )

    adapter.client = lambda: httpx.Client(
        base_url="http://engine/api/v0/", transport=httpx.MockTransport(handler)
    )
    adapter.copy_completed = lambda *_: pytest.fail(
        "Failed peer data must not be imported"
    )
    candidate = candidate_for(song(), {"username": "peer"}, file())
    with pytest.raises(ValueError, match="peer transfer failed"):
        adapter.transfer(candidate, tmp_path / "bad.mp3", lambda: None, lambda *_: None)
    assert deletes == ["/api/v0/transfers/downloads/peer/owned-id"]
    with pytest.raises(Cancelled):
        adapter.transfer(
            candidate,
            tmp_path / "bad.mp3",
            lambda: (_ for _ in ()).throw(Cancelled()),
            lambda *_: None,
        )


def test_flac_complete_import_and_lossy_rejection(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg required")
    fixture = tmp_path / "fixture.flac"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=3",
            "-codec:a",
            "flac",
            str(fixture),
        ],
        check=True,
        timeout=20,
    )
    store = configured(tmp_path / "data")
    store.save_download_settings(
        {"enabled": True, "profile": "lossless", "sources": ["soulseek"]}
    )
    store.submit_catalogue([song()])
    job = store.claim_request()
    worker = Downloader(store)
    candidate = {
        "title": "Song",
        "channel": "Example",
        "album": "Studio",
        "duration": 3,
        "extension": ".flac",
    }
    worker.soulseek.search = lambda *_: [candidate]
    worker.soulseek.transfer = lambda candidate, path, *_: shutil.copyfile(
        fixture, path
    )
    worker.process(job)
    assert store.queue()["items"][0]["status"] == "completed"
    track = Store(store.directory).library["albums"][0]["tracks"][0]
    path = worker.library_root / track["relative_path"]
    assert track["codec"] == "flac" and path.suffix == ".flac"
    assert FLAC(path)["albumartist"] == ["Example"]
    with pytest.raises(ValueError, match="quality profile"):
        worker.validate(path, job, "mp3_320")


def test_completed_file_lookup_rejects_ambiguity_and_outside_files(tmp_path):
    adapter = Soulseek(configured(tmp_path / "data"))
    root = tmp_path / "data" / "engine"
    (root / "Studio").mkdir(parents=True)
    (root / "Studio" / "01 Song.mp3").write_bytes(b"1" * 10000)
    candidate = candidate_for(song(), {"username": "peer"}, file())
    adapter.copy_completed(candidate, tmp_path / "copy.mp3")
    (root / "other" / "Studio").mkdir(parents=True)
    (root / "other" / "Studio" / "01 Song.mp3").write_bytes(b"2" * 10000)
    with pytest.raises(ValueError, match="uniquely"):
        adapter.copy_completed(candidate, tmp_path / "copy.mp3")
