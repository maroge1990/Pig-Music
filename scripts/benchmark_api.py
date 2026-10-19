"""Measure warm read-only LAN endpoints; never submits library/queue changes."""

import argparse
import json
import math
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://192.168.1.203:8765")
    parser.add_argument("--artist", default="3e241a6f0ea7ef0dd71d085f")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples < 30:
        parser.error("Use at least thirty samples for p95")
    results = []
    with httpx.Client(base_url=args.url, timeout=30) as client:
        library = client.get("/api/v1/admin/library").raise_for_status().json()
        artist = next(a for a in library["artists"] if a["id"] == args.artist)
        album = next(a for a in library["albums"] if a["artist_id"] == artist["id"])
        paths = [
            ("Health", "/api/health"),
            ("Library summary", "/api/v1/admin/library"),
            ("Artist detail", "/api/artists/" + artist["id"]),
            ("Album detail", "/api/albums/" + album["id"]),
            ("Queue", "/api/v1/admin/queue"),
            ("Playlists", "/api/playlists"),
            ("Local search", "/api/search?q=" + artist["name"].split()[0]),
            ("Migration inventory", "/api/v1/admin/migration"),
            ("Organisation review", "/api/v1/admin/library/organisation"),
        ]
        for name, path in paths:
            client.get(path).raise_for_status()
            timings = []
            for _ in range(args.samples):
                start = time.perf_counter()
                response = client.get(path).raise_for_status()
                timings.append((time.perf_counter() - start) * 1000)
            result = {
                "endpoint": name,
                "path": path,
                "median_ms": round(statistics.median(timings), 2),
                "p95_ms": round(sorted(timings)[math.ceil(args.samples * 0.95) - 1], 2),
                "max_ms": round(max(timings), 2),
                "bytes": len(response.content),
                "samples_ms": [round(t, 2) for t in timings],
            }
            results.append(result)
            print(
                name,
                result["median_ms"],
                "ms median;",
                result["p95_ms"],
                "ms p95",
                flush=True,
            )
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "Warm read-only Windows LAN requests; one warmup, thirty or more sequential samples per endpoint; nearest-rank p95",
        "tracks": library["stats"]["tracks"],
        "samples": args.samples,
        "results": results,
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
