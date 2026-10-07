import asyncio
from server.store import Store
from server.artist_jobs import ArtistJobs

A = "11111111-1111-4111-8111-111111111111"
G = "22222222-2222-4222-8222-222222222222"
R = "33333333-3333-4333-8333-333333333333"
T = "44444444-4444-4444-8444-444444444444"


class Catalogue:
    async def get(self, client, path, **params):
        if path == "release-group/":
            return {"count": 1, "release-groups": [{"id": G}]}
        if path == "release/":
            return {
                "releases": [
                    {
                        "id": R,
                        "status": "Official",
                        "media": [{"format": "CD", "track-count": 1}],
                    }
                ]
            }
        return {
            "id": R,
            "title": "Album",
            "date": "2020",
            "artist-credit": [{"name": "Artist"}],
            "media": [
                {
                    "position": 1,
                    "tracks": [
                        {
                            "id": T,
                            "position": 1,
                            "title": "Song",
                            "recording": {"id": T},
                            "length": 100000,
                        }
                    ],
                }
            ],
        }


def test_artist_request_is_durable_idempotent_and_monitoring_is_opt_in(tmp_path):
    store = Store(tmp_path)
    jobs = ArtistJobs(store, Catalogue())
    jobs.configure(A, ["album"], False, True)
    jobs = ArtistJobs(Store(tmp_path), Catalogue())
    asyncio.run(jobs.acquire(None, A, jobs.state(A)))
    assert (
        jobs.state(A)["status"] == "completed"
        and not jobs.state(A)["monitor"]
        and len(jobs.store.queue()["items"]) == 1
    )
    jobs.configure(A, ["album"], False, True)
    asyncio.run(jobs.acquire(None, A, jobs.state(A)))
    assert len(jobs.store.queue()["items"]) == 1


def test_cancellation_during_metadata_cannot_submit_or_overwrite_state(tmp_path):
    async def run():
        entered = asyncio.Event()
        release = asyncio.Event()

        class Delayed(Catalogue):
            async def get(self, client, path, **params):
                if path == "release/":
                    entered.set()
                    await release.wait()
                return await super().get(client, path, **params)

        store = Store(tmp_path)
        jobs = ArtistJobs(store, Delayed())
        jobs.configure(A, ["album"], False, True)
        task = asyncio.create_task(jobs.acquire(None, A, jobs.state(A)))
        await entered.wait()
        jobs.cancel(A)
        release.set()
        await task
        assert jobs.state(A)["status"] == "cancelled" and not store.queue()["items"]

    asyncio.run(run())


def test_following_records_existing_albums_and_acquires_only_new_ones(tmp_path):
    """'Follow new albums' must not download the back catalogue."""
    G2 = "55555555-5555-4555-8555-555555555555"
    groups = [{"id": G}]

    class Growing(Catalogue):
        async def get(self, client, path, **params):
            if path == "release-group/":
                return {"count": len(groups), "release-groups": list(groups)}
            return await super().get(client, path, **params)

    store = Store(tmp_path)
    jobs = ArtistJobs(store, Growing())
    jobs.configure(A, ["album"], True)  # follow, no request
    # The background loop treats a never-checked followed artist as due.
    state = jobs.configure(A, ["album"], True, request=True, periodic=True)
    asyncio.run(jobs.acquire(None, A, state))
    assert jobs.state(A)["done"] == [G] and not store.queue()["items"]
    # A release that appears after following is acquired on the next check.
    groups.append({"id": G2})
    state = jobs.configure(A, ["album"], True, request=True, periodic=True)
    asyncio.run(jobs.acquire(None, A, state))
    assert jobs.state(A)["done"] == [G, G2]
    assert len(store.queue()["items"]) == 1


def test_explicit_request_still_acquires_the_whole_catalogue(tmp_path):
    store = Store(tmp_path)
    jobs = ArtistJobs(store, Catalogue())
    jobs.configure(A, ["album"], True)
    state = jobs.configure(A, ["album"], True, request=True)
    asyncio.run(jobs.acquire(None, A, state))
    assert len(store.queue()["items"]) == 1
