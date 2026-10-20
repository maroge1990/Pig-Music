import asyncio
import io
import json

from PIL import Image

from server.downloader import Downloader
from server.editions import EditionResolver, choose
from server.store import Store

STUDIO = "11111111-1111-4111-8111-111111111111"
DELUXE = "22222222-2222-4222-8222-222222222222"
HITS = "33333333-3333-4333-8333-333333333333"
LIVE = "44444444-4444-4444-8444-444444444444"
RECORDING = "55555555-5555-4555-8555-555555555555"
WEMBLEY = "77777777-7777-4777-8777-777777777777"
DANCE = "88888888-8888-4888-8888-888888888888"


def release(release_id, title, group, primary="Album", secondary=(), date="1977"):
    return {
        "id": release_id,
        "title": title,
        "status": "Official",
        "date": date,
        "media": [{"format": "Digital Media"}],
        "release-group": {
            "id": group,
            "title": title,
            "primary-type": primary,
            "secondary-types": list(secondary),
        },
    }


def recording(releases, title="Dreams", length=257000, recording_id=RECORDING):
    return {
        "id": recording_id,
        "title": title,
        "length": length,
        "artist-credit": [{"name": "Fleetwood Mac", "joinphrase": ""}],
        "releases": releases,
    }


def requested(**extra):
    return {
        "title": "Dreams - 2004 Remaster",
        "artist": "Fleetwood Mac",
        "album": "Greatest Hits",
        "album_artist": "Fleetwood Mac",
        "duration": 258,
        "year": "",
        "disc_number": 1,
        "track_number": 1,
        **extra,
    }


def test_choose_files_a_song_under_the_studio_album_not_the_compilation():
    found = [
        recording(
            [
                release(HITS, "Greatest Hits", "g-hits", secondary=["Compilation"]),
                release(DELUXE, "Rumours (Deluxe)", "g-rumours", date="2013"),
                release(STUDIO, "Rumours", "g-rumours"),
                release(LIVE, "The Dance", DANCE, secondary=["Live"]),
            ]
        )
    ]
    chosen, recording_id = choose(found, requested())
    # The studio album's recommended (non-deluxe) edition.
    assert chosen["id"] == STUDIO and recording_id == RECORDING


def test_choose_keeps_live_and_other_lengths_apart():
    live = [recording([release(LIVE, "The Dance", DANCE, secondary=["Live"])])]
    assert choose(live, requested()) is None
    assert choose(live, requested(album="The Dance (Live)"))[0]["id"] == LIVE
    long = [recording([release(STUDIO, "Rumours", "g")], length=400000)]
    assert choose(long, requested()) is None
    other = [recording([release(STUDIO, "Rumours", "g")], title="Dreams (Live)")]
    assert choose(other, requested()) is None


def test_choose_uses_a_deluxe_edition_only_for_a_bonus_track():
    found = [recording([release(DELUXE, "Rumours (Deluxe)", "g-rumours")])]
    assert choose(found, requested())[0]["id"] == DELUXE


class FakeCatalogue:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    async def get(self, client, path, **params):
        self.calls.append(path)
        return self.answers[path]


class FakeArtwork:
    def __init__(self, path):
        self.path = path

    async def catalogue_cover(self, client, kind, item_id):
        return self.path


def jpeg(tmp_path):
    path = tmp_path / "front.jpg"
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, "JPEG")
    path.write_bytes(buffer.getvalue())
    return path


def resolver(tmp_path, store):
    detail = {
        "id": STUDIO,
        "title": "Rumours",
        "date": "1977-02-04",
        "artist-credit": [{"name": "Fleetwood Mac", "joinphrase": ""}],
        "media": [
            {
                "position": 1,
                "tracks": [
                    {
                        "id": "t2",
                        "position": 2,
                        "title": "Dreams",
                        "length": 257000,
                        "recording": {"id": RECORDING, "title": "Dreams"},
                    }
                ],
            }
        ],
    }
    catalogue = FakeCatalogue(
        {
            "recording/": {
                "recordings": [recording([release(STUDIO, "Rumours", "g")])]
            },
            "release/" + STUDIO: detail,
        }
    )
    return EditionResolver(store, catalogue, FakeArtwork(jpeg(tmp_path)), None)


def test_resolver_retags_to_the_chosen_edition_with_a_cover(tmp_path):
    store = Store(tmp_path)
    changes = asyncio.run(resolver(tmp_path, store).prepare(requested()))
    assert changes["album"] == "Rumours" and changes["track_number"] == 2
    assert changes["musicbrainz_release_id"] == STUDIO
    assert changes["requested"]["album"] == "Greatest Hits"
    assert changes["year"] == "1977" and changes["edition_resolved"]
    assert store.covers.path(changes["cover_sha"])


def test_explicit_editions_are_never_resolved(tmp_path):
    store = Store(tmp_path)
    resolve = resolver(tmp_path, store)
    job = requested(explicit_edition=True, musicbrainz_release_id=DELUXE)
    changes = asyncio.run(resolve.prepare(job))
    assert "album" not in changes and "recording/" not in resolve.catalogue.calls
    # Its own release still gets a cover.
    assert changes["cover_sha"]


def claimed(store, track):
    store.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
    store.submit_catalogue([{**track, "status": "missing", "requested_by": []}])
    return store.claim_request()


def test_worker_completes_a_request_from_another_edition_without_downloading(
    tmp_path,
):
    saved = {
        "id": "saved",
        "title": "Dreams",
        "artist": "Fleetwood Mac",
        "album": "Rumours",
        "album_artist": "Fleetwood Mac",
        "duration": 257,
        "disc_number": 1,
        "track_number": 2,
    }
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": []}))
    store = Store(tmp_path)
    job = claimed(store, requested(album="Rumours (Super Deluxe)"))
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [saved]}))
    store.refresh_library()

    class Resolver:
        async def prepare(self, job):
            return {"edition_resolved": True}

    worker = Downloader(store, providers={}, resolver=Resolver())
    worker.process = lambda job: (_ for _ in ()).throw(AssertionError("searched"))
    asyncio.run(worker.handle(job))
    (item,) = store.queue()["items"]
    assert item["status"] == "completed" and item["fulfilled_by"] == "saved"


def test_worker_persists_the_resolved_edition_before_searching(tmp_path):
    store = Store(tmp_path)
    job = claimed(store, requested())
    searched = []

    class Resolver:
        async def prepare(self, job):
            return {"album": "Rumours", "edition_resolved": True}

    worker = Downloader(store, providers={}, resolver=Resolver())
    worker.process = searched.append
    asyncio.run(worker.handle(job))
    assert searched[0]["album"] == "Rumours"
    (item,) = store.queue()["items"]
    assert item["album"] == "Rumours" and item["edition_resolved"]


def test_one_request_per_song_whichever_edition_asked(tmp_path):
    store = Store(tmp_path)
    first = store.submit_catalogue([{**requested(), "status": "missing"}])
    again = store.submit_catalogue(
        [{**requested(album="Rumours (Deluxe)", duration=257), "status": "missing"}]
    )
    assert first["created"] == 1 and again["existing"] == 1
    explicit = store.submit_catalogue(
        [
            {
                **requested(album="Rumours (Deluxe)"),
                "status": "missing",
                "explicit_edition": True,
            }
        ]
    )
    assert explicit["created"] == 1


def test_downloads_carry_the_edition_cover(tmp_path):
    import shutil
    import subprocess

    import pytest
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is required")
    store = Store(tmp_path)
    sha = store.covers.save(jpeg(tmp_path).read_bytes())
    worker = Downloader(store, providers={})
    for suffix in (".mp3", ".flac"):
        path = tmp_path / ("song" + suffix)
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc"]
            + ["-t", "1", str(path)],
            check=True,
        )
        worker.tag(path, {**requested(), "album": "Rumours"}, "test")
        worker.embed_cover(path, sha)
        data = store.covers.path(sha).read_bytes()
        if suffix == ".flac":
            assert FLAC(path).pictures[0].data == data
        else:
            assert ID3(path).getall("APIC")[0].data == data


def test_album_cover_falls_back_to_the_release_holding_its_songs(tmp_path):
    from server.artwork import Artwork

    found = [
        recording(
            [
                release(HITS, "Greatest Hits", "g-hits", secondary=["Compilation"]),
                release(DELUXE, "Rumours (Deluxe)", "g-rumours", date="2013"),
                release(STUDIO, "Rumours", "g-rumours"),
            ]
        )
    ]
    artwork = Artwork(
        Store(tmp_path), FakeCatalogue({"recording/": {"recordings": found}})
    )
    album = {
        "title": "Rumours (Remastered)",
        "artist": "Fleetwood Mac",
        "tracks": [{"title": "Dreams", "artist": "Fleetwood Mac", "duration": 257}],
    }
    assert asyncio.run(artwork.from_songs(None, album)) == STUDIO


def test_queue_keeps_distinct_recordings_of_one_title_apart(tmp_path):
    store = Store(tmp_path)
    studio = store.submit_catalogue(
        [
            {
                **requested(album="Rumours", musicbrainz_recording_id=RECORDING),
                "status": "missing",
            }
        ]
    )
    live = store.submit_catalogue(
        [{**requested(album="Live at Home"), "status": "missing"}]
    )
    kind = store.submit_catalogue(
        [{**requested(album="Wembley", recording_kind=["live"]), "status": "missing"}]
    )
    other = store.submit_catalogue(
        [
            {
                **requested(album="Tusk", musicbrainz_recording_id="other-recording"),
                "status": "missing",
            }
        ]
    )
    assert studio["created"] == live["created"] == other["created"] == 1
    # A known live release type is the same kind as an album called "Live ...".
    assert kind["existing"] == 1
    assert len(store.queue()["items"]) == 3


def test_explicit_and_ordinary_requests_never_share_an_unconstrained_job(tmp_path):
    store = Store(tmp_path)
    same = {**requested(), "status": "missing", "musicbrainz_release_id": DELUXE}
    assert store.submit_catalogue([same])["created"] == 1
    explicit = store.submit_catalogue([{**same, "explicit_edition": True}])
    assert explicit["created"] == 1
    jobs = store.queue()["items"]
    assert sorted(bool(j.get("explicit_edition")) for j in jobs) == [False, True]
    # Asking again for either keeps to its own job.
    assert store.submit_catalogue([{**same, "explicit_edition": True}])["existing"] == 1
    assert store.submit_catalogue([same])["existing"] == 1
    assert len(store.queue()["items"]) == 2


def test_an_ordinary_request_is_satisfied_by_a_queued_explicit_one(tmp_path):
    store = Store(tmp_path)
    explicit = {**requested(), "status": "missing", "explicit_edition": True}
    store.submit_catalogue([explicit])
    assert (
        store.submit_catalogue([{**requested(), "status": "missing"}])["existing"] == 1
    )
    (job,) = store.queue()["items"]
    assert job["explicit_edition"]


def live_detail(release_id, title, group):
    return {
        "id": release_id,
        "title": title,
        "date": "1986-07-12",
        "artist-credit": [{"name": "Fleetwood Mac", "joinphrase": ""}],
        "release-group": {
            "id": group,
            "title": title,
            "primary-type": "Album",
            "secondary-types": ["Live"],
        },
        "media": [
            {
                "position": 1,
                "tracks": [
                    {
                        "id": "t9",
                        "position": 9,
                        "title": "Dreams",
                        "length": 300000,
                        "recording": {"id": LIVE, "title": "Dreams"},
                    }
                ],
            }
        ],
    }


def test_a_known_live_recording_stays_live_and_keeps_its_identity(tmp_path):
    store = Store(tmp_path)
    remaster = "66666666-6666-4666-8666-666666666666"
    catalogue = FakeCatalogue(
        {
            "release/" + HITS: live_detail(HITS, "Wembley 1986", WEMBLEY),
            "release/" + remaster: live_detail(remaster, "Wembley 1986", WEMBLEY),
            "recording/" + LIVE: {"releases": [{"id": HITS}, {"id": remaster}]},
            "release": {
                "releases": [
                    {**release(HITS, "Wembley 1986", WEMBLEY), "date": "1987"},
                    {**release(remaster, "Wembley 1986", WEMBLEY), "date": "1986"},
                    release(STUDIO, "Rumours", "g-rumours"),
                ]
            },
        }
    )
    resolve = EditionResolver(store, catalogue, FakeArtwork(jpeg(tmp_path)), None)
    job = requested(
        title="Dreams",
        album="Wembley 1986",
        duration=300,
        musicbrainz_release_id=HITS,
        musicbrainz_recording_id=LIVE,
    )
    changes = asyncio.run(resolve.prepare(job))
    # Same group, its recommended edition holding this recording; never a
    # title search, never the studio album.
    assert changes["musicbrainz_recording_id"] == LIVE
    assert changes["musicbrainz_release_id"] == remaster
    assert changes["recording_kind"] == ["live"]
    assert changes["requested"]["musicbrainz_release_id"] == HITS
    assert "recording/" not in catalogue.calls


def test_a_recording_only_released_live_is_filed_as_live(tmp_path):
    store = Store(tmp_path)
    lookup = recording(
        [release(LIVE, "The Dance", DANCE, secondary=["Live"])],
        recording_id=LIVE,
    )
    catalogue = FakeCatalogue(
        {
            "recording/" + LIVE: lookup,
            "release/"
            + LIVE: {
                **live_detail(LIVE, "The Dance", DANCE),
            },
        }
    )
    resolve = EditionResolver(store, catalogue, FakeArtwork(jpeg(tmp_path)), None)
    job = requested(
        title="Dreams", album="", duration=300, musicbrainz_recording_id=LIVE
    )
    changes = asyncio.run(resolve.prepare(job))
    assert changes["album"] == "The Dance" and changes["recording_kind"] == ["live"]
    assert changes["musicbrainz_recording_id"] == LIVE
