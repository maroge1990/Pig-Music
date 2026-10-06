"""Disposable A01 migration/refresh benchmark with embedded legacy covers.

Each size runs in a fresh child process so peak RSS is measured independently.
Use --sizes 10000 inside docker run --memory=1g for the Linux release gate.
"""

import argparse
import base64
import io
import json
import resource
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from server.store import Store


def fixture(path, size):
    # Deterministic noisy 512px covers, roughly 274 KB as high-quality JPEG.
    pixels = bytearray(random.Random(0).randbytes(512 * 512 * 3))
    with path.open("w") as stream:
        stream.write('{"schema_version":2,"tracks":[')
        for i in range(size):
            if i:
                stream.write(",")
            json.dump(
                {
                    "id": str(i),
                    "title": "Song " + str(i),
                    "artist": "Artist " + str(i // 100),
                    "album_artist": "Artist " + str(i // 100),
                    "album": "Album " + str(i // 10),
                    "relative_path": str(i) + ".mp3",
                    "duration": 180,
                    "musicbrainz_release_id": "edition-" + str(i // 10),
                },
                stream,
            )
        stream.write('],"covers":{')
        for album in range((size + 9) // 10):
            if album:
                stream.write(",")
            # Distinct artwork for each album, not just one deduplicated cover.
            pixels[:4096] = random.Random(album + 1).randbytes(4096)
            output = io.BytesIO()
            Image.frombytes("RGB", (512, 512), bytes(pixels)).save(
                output, "JPEG", quality=97
            )
            json.dump("Artist " + str(album // 10) + "\x1fAlbum " + str(album), stream)
            stream.write(":")
            json.dump({"data": base64.b64encode(output.getvalue()).decode()}, stream)
        stream.write("}}")


def measure(size):
    with tempfile.TemporaryDirectory(prefix="pig-cover-benchmark-") as temporary:
        root = Path(temporary)
        snapshot = root / "library-snapshot.json"
        fixture(snapshot, size)
        old_bytes = snapshot.stat().st_size
        start = time.perf_counter()
        store = Store(root)
        first = time.perf_counter() - start
        start = time.perf_counter()
        store.refresh_library()
        warm = time.perf_counter() - start
        new_bytes = snapshot.stat().st_size
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = peak if sys.platform == "darwin" else peak * 1024
        payload = json.loads(snapshot.read_text())
        assert "covers" not in payload
        assert len(payload["tracks"]) == size
        assert store.library["stats"]["tracks"] == size
        assert all(store.covers.path(a["cover_sha"]) for a in store.library["albums"])
        assert len(list(store.cover_dir.glob("*.jpg"))) == (size + 9) // 10
        if size == 10000:
            assert new_bytes < 25_000_000, "Snapshot exceeds 25 MB gate"
            assert peak_bytes < 400_000_000, "Peak RSS exceeds 400 MB gate"
        return {
            "tracks": size,
            "legacy_snapshot_mb": round(old_bytes / 1e6, 2),
            "snapshot_mb": round(new_bytes / 1e6, 2),
            "migration_and_first_refresh_s": round(first, 3),
            "warm_refresh_s": round(warm, 3),
            "peak_rss_mb": round(peak_bytes / 1e6, 2),
            "cover_files": len(list(store.cover_dir.glob("*.jpg"))),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10000, 50000])
    parser.add_argument("--child", type=int)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(measure(args.child)))
        return
    results = []
    for size in args.sizes:
        child = subprocess.run(
            [sys.executable, __file__, "--child", str(size)],
            check=True,
            capture_output=True,
            text=True,
        )
        results.append(json.loads(child.stdout))
    print(
        json.dumps(
            {
                "method": "Disposable local legacy migration; 10 tracks/album; noisy 512px JPEG covers; independent peak RSS per size",
                "platform": sys.platform,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
