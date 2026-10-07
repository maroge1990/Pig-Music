"""Disposable two-person, 100k-unique-track gate; run through container stdin."""

import tempfile, time, json, resource, sys
from pathlib import Path
from server.store import Store
from server.auth import Auth
from server.native_sync import NativeSync

size = 50000
with tempfile.TemporaryDirectory(prefix="pig-disjoint-scale-") as temporary:
    root = Path(temporary)
    (root / "library-snapshot.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "tracks": [
                    {
                        "id": str(i),
                        "title": f"Song {i}",
                        "artist": f"Artist {i//100}",
                        "album_artist": f"Artist {i//100}",
                        "album": f"Album {i//10}",
                        "duration": 120,
                        "available": True,
                    }
                    for i in range(size * 2)
                ],
            }
        )
    )
    store = Store(root)
    auth = Auth(store)
    owner = auth.create_owner("mark", "disjoint scale fixture password")
    code = auth.setup_code(owner, "member", "Member")
    member = auth.activate(code["code"], "disjoint scale fixture password", "fixture")[
        "id"
    ]
    store.user_libraries.add(member, [str(i) for i in range(size, size * 2)])
    with store.connect() as conn:
        conn.execute(
            "DELETE FROM library_members WHERE user_id=? AND track_id IN (SELECT value FROM json_each(?))",
            (owner, json.dumps([str(i) for i in range(size, size * 2)])),
        )
        conn.execute(
            "UPDATE membership_versions SET revision=revision+1 WHERE user_id=?",
            (owner,),
        )
    start = time.monotonic()
    store.refresh_library()
    refresh = time.monotonic() - start
    sync = NativeSync(store)
    start = time.monotonic()
    for user in (owner, member):
        page = sync.page(user, "tracks", limit=200)
        assert page["total"] == size and len(page["items"]) == 200
        assert (
            sync.page(user, "tracks", page["next_cursor"], 200)["revision"]
            == page["revision"]
        )
        assert not sync.changes(user, page["revision"])["upserts"]["tracks"]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
        1024 * 1024 if sys.platform == "darwin" else 1024
    )
    assert rss < 900, f"Disjoint collections exceeded 900 MB: {rss:.2f}"
    print(
        json.dumps(
            {
                "users": 2,
                "tracks_per_user": size,
                "unique_tracks": size * 2,
                "refresh_seconds": round(refresh, 3),
                "cold_sync_seconds": round(time.monotonic() - start, 3),
                "peak_rss_mb": round(rss, 2),
                "database_bytes": store.database.stat().st_size,
            }
        ),
        flush=True,
    )
