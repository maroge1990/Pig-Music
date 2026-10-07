import asyncio
import httpx
from server.home import HomeDiscovery
from server.store import Store

ARTIST = "83d91898-7763-47d7-b03b-b92132375c47"
RELATED = "83d91898-7763-47d7-b03b-b92132375c48"
GROUP = "83d91898-7763-47d7-b03b-b92132375c49"
RECORD = "83d91898-7763-47d7-b03b-b92132375c50"


def test_popular_weekly_feed_validates_ids_and_caches(tmp_path):
    calls = []

    def respond(request):
        calls.append(str(request.url))
        assert request.url.params["range"] == "week"
        kind = request.url.path.split("/")[-1]
        data = {
            "artists": {
                "artists": [
                    {"artist_mbid": ARTIST, "artist_name": "Artist"},
                    {"artist_mbid": "bad", "artist_name": "Bad"},
                ]
            },
            "release-groups": {
                "release_groups": [
                    {
                        "release_group_mbid": GROUP,
                        "release_group_name": "Album",
                        "artist_mbids": [ARTIST],
                        "artist_name": "Artist",
                    }
                ]
            },
            "recordings": {
                "recordings": [
                    {
                        "recording_mbid": RECORD,
                        "track_name": "Song",
                        "artist_mbids": [ARTIST],
                        "artist_name": "Artist",
                    }
                ]
            },
        }
        return httpx.Response(200, json={"payload": data[kind]})

    async def run():
        home = HomeDiscovery(Store(tmp_path), None)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await home.popular(client)
            assert [x["name"] for x in result["artists"]] == ["Artist"]
            assert result["albums"][0]["id"] == GROUP
            assert result["songs"][0]["id"] == RECORD
            assert result == await home.popular(client)
            assert len(calls) == 3

    asyncio.run(run())


def test_failed_feed_keeps_stale_data_and_throttles_retry(tmp_path):
    store = Store(tmp_path)
    home = HomeDiscovery(store, None)
    store.write_document(
        "home-feed:v1:stats/sitewide/artists[]",
        {"until": 0, "data": {"payload": {"artists": ["retained"]}}},
    )
    calls = []

    def unavailable(request):
        calls.append(request)
        return httpx.Response(503)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(unavailable)
        ) as client:
            data, failed = await home.feed(client, "stats/sitewide/artists")
            assert failed and data["payload"]["artists"] == ["retained"]
            await home.feed(client, "stats/sitewide/artists")
            assert len(calls) == 1

    asyncio.run(run())


def test_recommendations_use_only_personal_seeds_and_do_not_submit_listens(tmp_path):
    store = Store(tmp_path)
    store.write_document("library-artist:mine", {"id": ARTIST, "name": "My Artist"})
    store.write_document("library-artist:theirs", {"id": RELATED, "name": "Other User"})

    class Catalogue:
        async def get(self, client, path, **params):
            if path == "release-group/":
                return {
                    "release-groups": [
                        {
                            "id": GROUP,
                            "title": "Recommended Album",
                            "primary-type": "Album",
                            "secondary-types": [],
                        }
                    ]
                }
            return {
                "title": "Recommended Song",
                "releases": [],
                "artist-credit": [{"name": "Related"}],
            }

    calls = []

    def radio(request):
        calls.append(request)
        assert request.method == "GET" and request.url.path.endswith(ARTIST)
        return httpx.Response(
            200,
            json={
                ARTIST: [{"similar_artist_name": "My Artist"}],
                RELATED: [{"similar_artist_name": "Related", "recording_mbid": RECORD}],
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(radio)) as client:
            result = await HomeDiscovery(store, Catalogue()).recommended(
                client,
                {"artists": [{"id": "mine", "name": "My Artist", "track_count": 1}]},
            )
            assert len(calls) == 1
            assert result["artists"][0]["name"] == "Related"
            assert result["albums"][0]["name"] == "Recommended Album"
            assert result["songs"][0]["name"] == "Recommended Song"
            assert result["artists"][0]["reason"] == "Because you saved My Artist"

    asyncio.run(run())
