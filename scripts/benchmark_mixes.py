"""Disposable two-person mix generation and rotation memory gate.

Synthetic metadata and one shared WAV fixture exercise prepared household-file
reuse. This measures ranking, persistence and feed assembly, not provider/audio
quality or perceived listening quality. CI runs it with networking off and 1 GB.
"""

import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import resource
import secrets
import sys
import tempfile
import time
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server.auth import Auth
from server.mixes import Mixes
from server.store import Store


async def measure(size):
    with tempfile.TemporaryDirectory(prefix="pig-mix-scale-") as temporary:
        root = Path(temporary)
        os.environ["PIG_MUSIC_LIBRARY"] = str(root)
        with wave.open(str(root / "fixture.wav"), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\0\0" * 8000)
        (root / "library-snapshot.json").write_text(
            json.dumps(
                {
                    "tracks": [
                        {
                            "id": str(i),
                            "title": f"Song {i}",
                            "artist": f"Artist {i//100}",
                            "album_artist": f"Artist {i//100}",
                            "album": f"Album {i//10}",
                            "duration": 1,
                            "available": True,
                            "relative_path": "fixture.wav",
                        }
                        for i in range(size)
                    ]
                }
            )
        )
        store = Store(root)
        auth = Auth(store)
        password = secrets.token_urlsafe(32)
        owner = auth.create_owner("owner", password)
        setup = auth.setup_code(owner, "member", "Member")
        member = auth.activate(setup["code"], password, "fixture")["id"]
        with store.connect() as conn:
            conn.execute("DELETE FROM library_members WHERE user_id=?", (owner,))
        for person, parity in ((owner, 0), (member, 1)):
            store.user_libraries.add(person, [str(i) for i in range(parity, size, 2)])
        mixes = Mixes(store, None, None)

        async def candidates(client, projection):
            return [], None

        mixes.candidates = candidates
        started = time.monotonic()
        first = {}
        for person, parity in ((owner, 0), (member, 1)):
            await mixes.prepare_person(None, person, mixes.day())
            feed = mixes.list(person)
            daily = next(m for m in feed["mixes"] if m["kind"] == "daily")
            assert len(daily["tracks"]) == 30
            first[person] = daily
            assert all(int(t.library_track_id) % 2 == parity for t in daily["tracks"])
        mixes.activate(mixes.day() + timedelta(days=1))
        minimum_change = 30
        for person in (owner, member):
            daily = next(m for m in mixes.list(person)["mixes"] if m["kind"] == "daily")
            previous = {t.library_track_id for t in first[person]["tracks"]}
            changed = len({t.library_track_id for t in daily["tracks"]} - previous)
            assert changed >= 15
            minimum_change = min(minimum_change, changed)
            assert mixes.playback(person, first[person]["tracks"][0].id).is_file()
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_mb = peak / (1024 * 1024 if sys.platform == "darwin" else 1024)
        assert (
            peak_mb < 900
        ), f"Mix generation exceeded its memory guard: {peak_mb:.1f} MiB"
        return {
            "household_tracks": size,
            "people": 2,
            "editions": 8,
            "seconds": round(time.monotonic() - started, 3),
            "minimum_daily_songs_changed": minimum_change,
            "peak_rss_mib": round(peak_mb, 2),
            "provider_calls": 0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=50000)
    args = parser.parse_args()
    if args.size < 6000:
        parser.error("Use at least 6000 synthetic tracks for the diversity gate")
    print(json.dumps(asyncio.run(measure(args.size)), indent=2))
