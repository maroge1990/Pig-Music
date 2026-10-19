"""Disposable 10k/50k HTTP payload and warm validator benchmark; no NAS/provider access."""

import gzip
import json
import os
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from server.app import create_app


def measure(size):
    os.environ["PIG_MUSIC_PRELOAD"] = "false"
    os.environ["PIG_MUSIC_EMBEDDED_ENGINE"] = "false"
    with tempfile.TemporaryDirectory(prefix="pig-delivery-") as folder:
        root = Path(folder)
        (root / "media-settings.json").write_text('{"portraits":false}')
        (root / "library-snapshot.json").write_text(
            json.dumps(
                {
                    "schema_version": 3,
                    "tracks": [
                        {
                            "id": str(i),
                            "artist": f"Artist {i // 100}",
                            "album": f"Album {i // 10}",
                            "title": f"Song {i}",
                        }
                        for i in range(size)
                    ],
                }
            )
        )
        startup = time.perf_counter()
        app = create_app(root)
        auth = app.state.auth
        auth.create_owner("deliveryfixture", "disposable delivery fixture password")
        token = auth.login(
            "deliveryfixture",
            "disposable delivery fixture password",
            "device",
            "benchmark",
            "ios",
            "fixture",
        )["token"]
        with TestClient(
            app,
            base_url="https://private.ts.net",
            headers={"Authorization": "Bearer " + token},
        ) as client:
            startup_seconds = time.perf_counter() - startup
            assert (
                startup_seconds < 30
            ), f"Metadata startup exceeded 30 seconds: {startup_seconds:.2f}"
            result = client.get(
                "/api/v1/admin/library", headers={"Accept-Encoding": "gzip"}
            )
            assert result.status_code == 200, result.text
            assert result.json()["stats"]["tracks"] == size
            assert result.headers["content-encoding"] == "gzip"
            etag = result.headers["etag"]
            times = []
            for _ in range(30):
                start = time.perf_counter()
                response = client.get(
                    "/api/v1/admin/library", headers={"If-None-Match": etag}
                )
                times.append((time.perf_counter() - start) * 1000)
                assert response.status_code == 304 and not response.content
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak = peak if sys.platform == "darwin" else peak * 1024
            return {
                "tracks": size,
                "startup_seconds": round(startup_seconds, 3),
                "albums": len(result.json()["albums"]),
                "json_bytes": len(result.content),
                "gzip_bytes": len(gzip.compress(result.content)),
                "conditional_median_ms": round(statistics.median(times), 3),
                "conditional_p95_ms": round(sorted(times)[28], 3),
                "process_peak_rss_mb": round(peak / 1e6, 2),
            }


if __name__ == "__main__":
    print(json.dumps([measure(size) for size in (10000, 50000)], indent=2))
