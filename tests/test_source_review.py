"""SC1: SoundCloud uploads credited only by the uploader's name wait for the
owner's review instead of downloading or being silently dropped."""

import json

import pytest

from server.downloader import Downloader
from server.mix_cache import MixDownloader
from server.providers.extractor import recording
from server.store import Store
from test_artist_identity import client_for, prepared
from test_downloader import queued

UPLOAD = {
    "title": "Test Track",
    "channel": "Test Artist",
    "album": "",
    "duration": 3,
    "provider_track_id": "testartist/test-track",
    "identity_evidence": "uploader_name",
    "quality": "160kbps",
    "extension": ".m4a",
    "url": "https://cf-media.sndcdn.com/stream?Policy=expiring",
}


def engine(store, monkeypatch, found, sources=("soundcloud",)):
    """A worker whose sources answer `found[source]` and whose transfers are
    recorded instead of performed."""
    store.save_download_settings(
        {"enabled": True, "profile": "mp3_320", "sources": list(sources)}
    )
    worker = Downloader(
        store,
        providers={
            source: (lambda query, limit, found=found, source=source: found[source])
            for source in found
            if source != "soundcloud"
        },
    )
    transfers = []
    monkeypatch.setattr(
        worker.runtime,
        "search",
        lambda source, job, context: [dict(c) for c in found.get(source, [])],
    )

    def transfer(job_id, candidate, path):
        transfers.append(candidate)
        return {"identity_evidence": candidate.get("identity_evidence")}

    monkeypatch.setattr(worker, "transfer", transfer)
    monkeypatch.setattr(
        worker,
        "complete",
        lambda job, *a, **k: store.request_state(job["id"], "completed"),
    )
    return worker, transfers


def item(store):
    return store.queue()["items"][0]


def claimed(store):
    job = store.claim_request()
    assert job, store.queue()
    return job


def test_soundcloud_title_only_uploads_are_credited_by_uploader_for_review():
    upload = {"title": "Song", "uploader": "Artist", "duration": 200}
    assert recording(upload, "soundcloud")["identity_evidence"] == "uploader_name"
    assert recording(upload, "soundcloud")["channel"] == "Artist"
    explicit = recording({**upload, "title": "Artist - Song"}, "soundcloud")
    assert explicit["identity_evidence"] == "explicit_credit"
    assert recording(upload, "youtube") is None


def test_an_uploader_named_like_the_artist_is_held_not_downloaded(
    tmp_path, monkeypatch
):
    store = Store(tmp_path)
    job = queued(store)
    worker, transfers = engine(store, monkeypatch, {"soundcloud": [UPLOAD]})
    worker.process(job)
    assert transfers == []
    held = item(store)
    assert held["status"] == "failed"
    assert "waiting for review" in held["error"]
    review = held["source_review"]
    assert review["uploader"] == "Test Artist"
    assert review["provider_track_id"] == UPLOAD["provider_track_id"]
    # The public page only; a stream URL expires and must never be stored.
    assert review["url"] == "https://soundcloud.com/testartist/test-track"
    assert "sndcdn" not in json.dumps(held)


@pytest.mark.parametrize("uploader", ["Test Artist & Friends", "Test Artist Fans"])
def test_only_an_exact_uploader_name_is_worth_reviewing(
    tmp_path, monkeypatch, uploader
):
    store = Store(tmp_path)
    job = queued(store)
    worker, transfers = engine(
        store, monkeypatch, {"soundcloud": [{**UPLOAD, "channel": uploader}]}
    )
    worker.process(job)
    assert transfers == []
    assert not item(store).get("source_review")


def test_letter_case_does_not_stop_an_exact_name_match(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = queued(store)
    worker, _ = engine(
        store, monkeypatch, {"soundcloud": [{**UPLOAD, "channel": "TEST ARTIST"}]}
    )
    worker.process(job)
    assert item(store)["source_review"]["uploader"] == "TEST ARTIST"


def test_approving_requeues_and_downloads_that_upload(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = queued(store)
    worker, transfers = engine(store, monkeypatch, {"soundcloud": [UPLOAD]})
    worker.process(job)
    store.review_source(job["id"], approve=True)
    approved = item(store)
    assert approved["status"] == "waiting_for_sources"
    assert approved["source_review"] is None
    worker.process(claimed(store))
    assert [t["provider_track_id"] for t in transfers] == [UPLOAD["provider_track_id"]]
    assert item(store)["status"] == "completed"


def test_rejecting_rules_that_upload_out_for_good(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = queued(store)
    worker, transfers = engine(store, monkeypatch, {"soundcloud": [UPLOAD]})
    worker.process(job)
    store.review_source(job["id"], approve=False)
    rejected = item(store)
    assert rejected["status"] == "failed"
    assert rejected["source_review"] is None
    store.retry_request(job["id"])
    worker.process(claimed(store))
    assert transfers == []
    assert not item(store).get("source_review")


def test_another_source_satisfying_the_request_clears_the_review(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = queued(store)
    official = {
        **UPLOAD,
        "identity_evidence": "structured",
        "provider_track_id": "x",
        "extension": ".mp3",
    }
    worker, transfers = engine(
        store,
        monkeypatch,
        {"soundcloud": [UPLOAD], "zvu4no": [official]},
        sources=("soundcloud", "zvu4no"),
    )
    worker.process(job)
    assert [t["provider_track_id"] for t in transfers] == ["x"]
    assert item(store)["status"] == "completed"
    with pytest.raises(ValueError):
        store.review_source(job["id"], approve=True)


def test_a_retry_that_no_longer_finds_the_upload_leaves_no_stale_review(
    tmp_path, monkeypatch
):
    store = Store(tmp_path)
    job = queued(store)
    found = {"soundcloud": [UPLOAD]}
    worker, _ = engine(store, monkeypatch, found)
    worker.process(job)
    found["soundcloud"] = []
    store.retry_request(job["id"])
    worker.process(claimed(store))
    assert not item(store).get("source_review")


def test_a_cancelled_or_running_request_cannot_be_decided(tmp_path, monkeypatch):
    store = Store(tmp_path)
    job = queued(store)
    worker, _ = engine(store, monkeypatch, {"soundcloud": [UPLOAD]})
    worker.process(job)
    store.retry_request(job["id"])
    running = claimed(store)
    store.request_state(running["id"], "searching", source_review=UPLOAD)
    with pytest.raises(ValueError):
        store.review_source(job["id"], approve=True)
    store.cancel_request(job["id"])
    with pytest.raises(ValueError):
        store.review_source(job["id"], approve=False)
    with pytest.raises(LookupError):
        store.review_source("missing", approve=True)


def test_mix_preparation_never_asks_the_owner():
    assert MixDownloader.hold(object(), {}, "soundcloud", UPLOAD) is None


def test_only_the_owner_can_decide_a_held_upload(tmp_path, monkeypatch):
    app, owner_token, member_token, _ = prepared(tmp_path, monkeypatch)
    store = app.state.store
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO queue(id,status,payload) VALUES (?,?,?)",
            (
                "held",
                "failed",
                json.dumps({"title": "Song", "source_review": UPLOAD}),
            ),
        )
    path = "/api/v1/admin/queue/held/source-review/"
    with client_for(app, member_token) as member:
        assert member.post(path + "approve").status_code in {401, 403, 404}
    with client_for(app, owner_token) as owner:
        assert owner.post(path + "maybe").status_code == 422
        assert (
            owner.post("/api/v1/admin/queue/nope/source-review/approve").status_code
            == 404
        )
        decided = owner.post(path + "reject")
        assert decided.status_code == 200
        entry = next(i for i in decided.json()["items"] if i["id"] == "held")
        assert entry["source_review_rejected"] == [UPLOAD["provider_track_id"]]
        assert owner.post(path + "reject").status_code == 409
