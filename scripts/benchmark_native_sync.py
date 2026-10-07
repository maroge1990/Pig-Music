"""Disposable, two-account 10k/50k native sync memory and pagination gate."""

import argparse
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.store import Store
from server.auth import Auth
from server.native_sync import NativeSync


def measure(size):
    with tempfile.TemporaryDirectory(prefix="pig-native-scale-") as temporary:
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
                        for i in range(size)
                    ],
                }
            )
        )
        store = Store(root)
        auth = Auth(store)
        owner = auth.create_owner("mark", "native scale fixture password")
        setup = auth.setup_code(owner, "member", "Member")
        member = auth.activate(
            setup["code"], "native scale fixture password", "fixture"
        )["id"]
        store.user_libraries.add(member, [str(i) for i in range(size)])
        sync = NativeSync(store)
        start = time.monotonic()
        for user in (owner, member):
            first = sync.page(user, "tracks", limit=200)
            assert first["total"] == size and len(first["items"]) == 200
            assert len(json.dumps(first).encode()) < 250000
            warm = sync.page(user, "tracks", first["next_cursor"], 200)
            assert first["revision"] == warm["revision"]
            assert not sync.changes(user, first["revision"])["upserts"]["tracks"]
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = rss / (1024 * 1024 if sys.platform == "darwin" else 1024)
        assert rss_mb < 900, f"Native sync exceeded its 900 MB guard: {rss_mb:.1f}"
        return {
            "tracks_per_user": size,
            "users": 2,
            "cold_sync_seconds": round(time.monotonic() - start, 3),
            "peak_rss_mb": round(rss_mb, 2),
            "page_bytes": len(json.dumps(first).encode()),
            "database_bytes": (root / "pig-music.sqlite3").stat().st_size,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int)
    args = parser.parse_args()
    if args.size:
        print(json.dumps(measure(args.size)))
    else:
        print(
            json.dumps(
                [
                    json.loads(
                        subprocess.check_output(
                            [sys.executable, __file__, "--size", str(size)]
                        )
                    )
                    for size in (10000, 50000)
                ],
                indent=2,
            )
        )
