import json

import httpx
from fastapi.testclient import TestClient

from server.app import create_app
from server.catalogue import Catalogue, release_tracks
from server.store import Store

ARTIST = "11111111-1111-4111-8111-111111111111"
GROUP = "22222222-2222-4222-8222-222222222222"
RELEASE = "33333333-3333-4333-8333-333333333333"
OTHER = "55555555-5555-4555-8555-555555555555"
TRACK = "44444444-4444-4444-8444-444444444444"


def test_discography_filters_studio_albums_and_sorts_dates(tmp_path):
    queries = []

    def transport(request):
        queries.append(request.url.params["query"])
        return httpx.Response(
            200,
            json={
                "count": 3,
                "release-groups": [
                    {
                        "id": RELEASE,
                        "title": "Newest",
                        "first-release-date": "2024",
                        "primary-type": "Album",
                    },
                    {"id": GROUP, "title": "Unknown date", "primary-type": "Album"},
                    {
                        "id": OTHER,
                        "title": "Oldest",
                        "first-release-date": "2010",
                        "primary-type": "Album",
                    },
                ],
            },
        )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        result = client.get(
            f"/api/catalogue/artists/{ARTIST}/releases?kind=album"
        ).json()
        assert [r["title"] for r in result["releases"]] == [
            "Newest",
            "Oldest",
            "Unknown date",
        ]
        assert "NOT secondarytype:demo" in queries[-1]
        assert "NOT secondarytype:live" in queries[-1]
        assert "NOT secondarytype:compilation" in queries[-1]
        assert client.get(
            f"/api/catalogue/artists/{ARTIST}/releases?kind=other"
        ).is_success
        assert (
            "NOT (primarytype:album" in queries[-1]
            and "NOT secondarytype:demo" in queries[-1]
        )
        assert (
            "NOT secondarytype:soundtrack" in queries[-1]
            and "NOT secondarytype:interview" in queries[-1]
        )
        app.state.http = original


def fixture_release():
    return {
        "id": RELEASE,
        "title": "Live at Home",
        "date": "2020-01-01",
        "artist-credit": [{"name": "Example"}],
        "media": [
            {
                "position": 2,
                "tracks": [
                    {
                        "id": TRACK,
                        "position": 3,
                        "title": "Song (Live)",
                        "length": 120000,
                        "recording": {"id": OTHER, "isrcs": ["USAAA2000001"]},
                    }
                ],
            }
        ],
    }


def test_catalogue_edition_requests_cached_validated_and_persistent(tmp_path):
    calls = []

    def transport(request):
        calls.append(request)
        if request.url.path.endswith("release-group"):
            return httpx.Response(
                200,
                json={
                    "release-group-count": 51,
                    "release-groups": [
                        {
                            "id": GROUP,
                            "title": "Live at Home",
                            "primary-type": "Album",
                            "secondary-types": ["Live"],
                        }
                    ],
                },
            )
        if request.url.path.endswith("release"):
            return httpx.Response(
                200,
                json={
                    "release-count": 1,
                    "releases": [
                        {
                            "id": RELEASE,
                            "title": "Live at Home",
                            "media": [{"format": "CD", "track-count": 1}],
                        }
                    ],
                },
            )
        return httpx.Response(200, json=fixture_release())

    app = create_app(tmp_path)
    with TestClient(app) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        assert (
            client.get(f"/api/catalogue/artists/{ARTIST}/releases?offset=50").json()[
                "total"
            ]
            == 51
        )
        assert calls[-1].url.params["offset"] == "50"
        assert client.get(f"/api/catalogue/groups/{GROUP}/editions").json()["editions"][
            0
        ]["formats"] == ["CD"]
        detail = client.get(f"/api/catalogue/releases/{RELEASE}").json()
        assert detail["tracks"][0]["disc_number"] == 2
        path = f"/api/catalogue/releases/{RELEASE}/request"
        assert (
            client.post(path, json={"track_ids": ["not-this-edition"]}).status_code
            == 400
        )
        assert client.post(path, json={"track_ids": []}).status_code == 400
        assert client.post(path, json={"track_ids": [TRACK]}).json()["created"] == 1
        assert client.post(path, json={}).json()["existing"] == 1
        assert len(calls) == 3  # release lookup reused by detail and submissions
        assert client.get("/api/catalogue/releases/not-a-uuid").status_code == 400
        app.state.http = original
    queued = Store(tmp_path).queue()["items"][0]
    assert queued["musicbrainz_release_id"] == RELEASE
    assert queued["isrcs"] == ["USAAA2000001"]
    assert queued["album"] == "Live at Home" and queued["duration"] == 120


def test_saved_presence_and_same_title_different_editions(tmp_path):
    track = release_tracks(fixture_release())[0]
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    store = Store(tmp_path)
    catalogue = Catalogue(store)
    assert catalogue.presence([dict(track)])[0]["status"] == "downloaded"
    other = {**track, "musicbrainz_release_id": OTHER}
    assert catalogue.presence([other])[0]["status"] == "review"
    first = {**track, "status": "missing"}
    assert store.submit_catalogue([first])["created"] == 1
    assert store.submit_catalogue([other])["created"] == 1
    assert store.submit_catalogue([other])["existing"] == 1
    assert len(store.queue()["items"]) == 2


def test_artist_artwork_uses_credited_album_and_cached_metadata(tmp_path):
    (tmp_path / "media-settings.json").write_text(json.dumps({"portraits": False}))
    calls = []

    def transport(request):
        calls.append(request)
        if request.url.host != "musicbrainz.org":
            import io
            from PIL import Image

            content = io.BytesIO()
            Image.new("RGB", (100, 100), "red").save(content, "PNG")
            assert "/release/" + RELEASE in request.url.path
            return httpx.Response(200, content=content.getvalue())
        return httpx.Response(
            200,
            json={
                "releases": [
                    {
                        "id": OTHER,
                        "release-group": {"primary-type": "Single"},
                        "cover-art-archive": {"front": True},
                    },
                    {
                        "id": GROUP,
                        "release-group": {"primary-type": "Album"},
                        "cover-art-archive": {"front": False},
                    },
                    {
                        "id": RELEASE,
                        "release-group": {"primary-type": "Album"},
                        "cover-art-archive": {"front": True},
                    },
                ]
            },
        )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        path = f"/api/catalogue/artists/{ARTIST}/artwork"
        result = client.get(path, follow_redirects=False)
        assert result.status_code == 404
        client.portal.call(app.state.enrichment.queue.join)
        result = client.get(path, follow_redirects=False)
        assert result.status_code == 307
        assert result.headers["location"].startswith("/api/artwork/")
        assert client.get(path).status_code == 200
        assert len(calls) == 2
        assert (
            client.get("/api/catalogue/artists/not-a-uuid/artwork").status_code == 400
        )
        assert len(calls) == 2
        app.state.http = original


def test_artist_without_artwork_returns_missing_without_redirect(tmp_path):
    (tmp_path / "media-settings.json").write_text(json.dumps({"portraits": False}))
    app = create_app(tmp_path)
    with TestClient(app) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"releases": []})
            )
        )
        result = client.get(
            f"/api/catalogue/artists/{ARTIST}/artwork", follow_redirects=False
        )
        assert result.status_code == 404
        assert "location" not in result.headers
        app.state.http = original


def test_default_edition_prefers_standard_mix_over_atmos():
    from server.catalogue import edition_rank

    regular = {
        "id": "regular",
        "status": "Official",
        "date": "2025-08-22",
        "media": [{"format": "Digital Media"}],
    }
    atmos = {**regular, "id": "atmos", "disambiguation": "Dolby Atmos mix"}
    assert edition_rank(regular) < edition_rank(atmos)


def test_native_artist_profile_accepts_missing_optional_metadata(tmp_path):
    def transport(request):
        return httpx.Response(
            200,
            json={
                "id": ARTIST,
                "name": "Example",
                "country": None,
                "type": None,
                "disambiguation": None,
                "life-span": None,
            },
        )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        original = app.state.http
        app.state.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        response = client.get(f"/api/v1/catalogue/artists/{ARTIST}/profile")
        assert response.status_code == 200
        assert response.json() == {
            "id": ARTIST,
            "name": "Example",
            "description": "",
            "country": "",
            "type": "",
            "begin": "",
            "end": "",
        }
        app.state.http = original
