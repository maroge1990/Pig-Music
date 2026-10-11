"""Exercise three private 50k libraries on new disposable metadata-only state."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from server.auth import Auth
from server.native_sync import NativeSync
from server.store import Store
from server.user_library import bump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--songs", type=int, default=50000)
    args = parser.parse_args()
    if args.output.exists() or not 5000 <= args.songs <= 50000:
        raise ValueError("Use a new disposable directory and 5,000–50,000 songs")
    args.output.mkdir(parents=True)
    tracks = [
        {
            "id": f"track-{i:05d}",
            "title": f"Song {i:05d}",
            "artist": f"Artist {i // 1000:02d}",
            "album_artist": f"Artist {i // 1000:02d}",
            "album": f"Album {i // 100:03d}",
            "track_number": i % 100 + 1,
            "relative_path": f"fixture/{i}.mp3",
            "duration": 180,
        }
        for i in range(args.songs)
    ]
    (args.output / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    store = Store(args.output)
    auth = Auth(store)
    owner = auth.create_owner("scalefixture", "disposable scale fixture password")
    users = [owner]
    for index in range(2):
        name = f"scalemember{index}"
        invitation = auth.setup_code(owner, name, name)
        auth.activate(
            invitation["code"], "disposable scale fixture password", "fixture"
        )
        with store.connect() as conn:
            users.append(
                conn.execute(
                    "SELECT id FROM users WHERE username=?", (name,)
                ).fetchone()[0]
            )
    with store.connect() as conn:
        for user in users:
            conn.executemany(
                "INSERT OR IGNORE INTO library_members VALUES (?,?,?,?)",
                [
                    (user, track["id"], int(time.time()), "household-add")
                    for track in tracks
                ],
            )
            bump(conn, user)
    sync = NativeSync(store)

    def exercise(user):
        start = time.perf_counter()
        page = sync.page(user, "tracks", limit=200)
        first = time.perf_counter() - start
        revision = page["revision"]
        seen, timings = set(), []
        while True:
            assert page["total"] == args.songs and page["revision"] == revision
            ids = {item["id"] for item in page["items"]}
            assert len(ids) == len(page["items"]) and seen.isdisjoint(ids)
            seen.update(ids)
            if not page["next_cursor"]:
                break
            before = time.perf_counter()
            page = sync.page(user, "tracks", cursor=page["next_cursor"], limit=200)
            timings.append(time.perf_counter() - before)
        assert len(seen) == args.songs
        return {
            "songs": len(seen),
            "first_page_seconds": round(first, 3),
            "full_sync_seconds": round(time.perf_counter() - start, 3),
            "warm_page_p95_seconds": round(
                sorted(timings)[int(len(timings) * 0.95)], 3
            ),
        }

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(exercise, users))
    report = {
        "users": results,
        "concurrent_elapsed_seconds": round(time.perf_counter() - start, 3),
        "database_bytes": (args.output / "pig-music.sqlite3").stat().st_size,
        "limitations": "Local metadata-only benchmark; excludes HTTP, NAS, audio, devices and provider traffic.",
    }
    (args.output / "scale-results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
