"""Historical acquisition probe; never run as a routine release check.

This submits a real external download into separate smoke state. Current release
checks use deploy_unraid.py and disposable tests without live providers.
"""

import json
import os
import shutil
from pathlib import Path

from server.downloader import Downloader
from server.store import Store

root = Path("/data/deployment-smoke")
root.mkdir(exist_ok=True)
shutil.copyfile("/data/slskd-connection.json", root / "slskd-connection.json")
store = Store(root)
store.save_download_settings(
    {"enabled": True, "profile": "lossless", "sources": ["soulseek"]}
)
track = {
    "title": "Pompeii",
    "artist": "Bastille",
    "album": "Bad Blood",
    "album_artist": "Bastille",
    "year": 2013,
    "disc_number": 1,
    "track_number": 1,
    "duration": 214.148,
    "status": "missing",
}
store.submit_catalogue([track])
job = store.claim_request()
if job:
    Downloader(store).process(job)
result = store.queue()["items"][0]
print(
    json.dumps(
        {
            "uid": os.getuid(),
            "status": result["status"],
            "error": result.get("error"),
            "tracks": [
                {k: t.get(k) for k in ("codec", "bitrate", "duration", "relative_path")}
                for a in store.library["albums"]
                for t in a["tracks"]
            ],
        }
    )
)
if result["status"] != "completed":
    raise SystemExit(1)
