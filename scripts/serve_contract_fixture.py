"""Disposable loopback-only server for generated native-client contract tests."""

import json
import os
import tempfile
import wave
from pathlib import Path
import uvicorn
from server.store import Store
from server.auth import Auth


def main():
    os.environ.pop("PIG_MUSIC_TEST_LEGACY_API", None)
    os.environ["PIG_MUSIC_PRELOAD"] = "false"
    os.environ["PIG_MUSIC_EMBEDDED_ENGINE"] = "false"
    with tempfile.TemporaryDirectory(prefix="pig-swift-contract-") as temporary:
        root = Path(temporary)
        os.environ["PIG_MUSIC_LIBRARY"] = str(root)
        for i in range(3):
            with wave.open(str(root / f"song-{i}.wav"), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(8000)
                audio.writeframes(b"\0\0" * 8000 * 120)
        (root / "library-snapshot.json").write_text(
            json.dumps(
                {
                    "tracks": [
                        {
                            "id": f"track-{i}",
                            "title": f"Song {i+1}",
                            "artist": "Fixture Artist",
                            "album_artist": "Fixture Artist",
                            "album": "Fixture Album",
                            "duration": 120,
                            "available": True,
                            "relative_path": f"song-{i}.wav",
                        }
                        for i in range(3)
                    ]
                }
            )
        )
        store = Store(root)
        auth = Auth(store)
        owner = auth.create_owner("mark", "browser fixture password", "Mark fixture")
        code = auth.setup_code(owner, "member", "Member fixture")
        member = auth.activate(code["code"], "browser fixture password", "fixture")[
            "id"
        ]
        store.user_libraries.add(member, ["track-0", "track-1"])
        from server.app import create_app

        uvicorn.run(
            create_app(root),
            host="127.0.0.1",
            port=8781,
            proxy_headers=True,
            forwarded_allow_ips="127.0.0.1",
            access_log=False,
        )


if __name__ == "__main__":
    main()
