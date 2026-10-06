"""Disposable metadata scaling benchmark; never reads or writes live music."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.matching import LibraryIndex


def main():
    results = []
    for size in (1000, 10000, 50000):
        tracks = [
            {
                "id": str(i),
                "artist": "Fixture Artist",
                "album_artist": "Fixture Artist",
                "title": "Song " + str(i),
                "album": "Album " + str(i // 10),
                "duration": 180,
            }
            for i in range(size)
        ]
        start = time.perf_counter()
        index = LibraryIndex({"albums": [{"id": "fixture", "tracks": tracks}]})
        indexed = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        for track in tracks[:200]:
            assert index.match(track).track["id"] == track["id"]
        results.append(
            {
                "tracks": size,
                "index_ms": round(indexed, 2),
                "200_matches_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
    print(
        json.dumps(
            {
                "method": "Synthetic unique-context metadata, local process; includes no filesystem/provider work",
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
