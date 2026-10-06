"""Run through `docker exec -i music-grabber python -` to read its library.

Only opens the existing index and music files for reading. Prints a portable
snapshot to stdout; the invoking Windows process stores it in local appdata.
"""

import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from mutagen import File


def value(tags, *keys, default=""):
    for key in keys:
        item = tags.get(key)
        if item is not None:
            if hasattr(item, "text"):
                item = item.text
            if isinstance(item, (list, tuple)):
                item = item[0] if item else ""
            if str(item).strip():
                return str(item).strip()
    return default


def number(raw):
    try:
        return int(str(raw).split("/")[0])
    except (TypeError, ValueError):
        return 0


def export():
    conn = sqlite3.connect(
        "file:/data/music_grabber_library_index.db?mode=ro", uri=True
    )
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM library_files ORDER BY relative_path").fetchall()
    conn.close()
    tracks, covers, failures = [], {}, []
    for row in rows:
        relative = Path(row["relative_path"])
        if any(
            p.casefold() in {"#recycle", ".trash", "trash", ".staging"}
            for p in relative.parts
        ):
            continue
        root = Path(row["root_path"])
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()):
            continue
        try:
            audio = File(path)
            tags = audio.tags if audio is not None and audio.tags is not None else {}
            artist = value(
                tags, "TPE1", "artist", default=row["artist"] or "Unknown artist"
            )
            album = value(tags, "TALB", "album", default=row["album"] or "Singles")
            album_artist = value(
                tags, "TPE2", "albumartist", "album artist", default=artist
            )
            track = {
                "id": hashlib.sha256(str(relative).encode()).hexdigest()[:24],
                "title": value(
                    tags, "TIT2", "title", default=row["title"] or path.stem
                ),
                "artist": artist,
                "album": album,
                "album_artist": album_artist,
                "genre": value(tags, "TCON", "genre"),
                "compilation": value(tags, "TCMP", "compilation")
                in {"1", "true", "True"},
                "year": number(value(tags, "TDRC", "date", "year")),
                "track_number": number(value(tags, "TRCK", "tracknumber")),
                "disc_number": number(value(tags, "TPOS", "discnumber", default="1"))
                or 1,
                "duration": round(row["duration"] or 0, 3),
                "codec": row["codec"] or path.suffix.lstrip("."),
                "bitrate": row["bitrate_kbps"] or 0,
                "relative_path": relative.as_posix(),
                "size_bytes": row["size_bytes"],
            }
            tracks.append(track)
            cover_key = album_artist + "\x1f" + album
            if cover_key not in covers:
                pictures = getattr(audio, "pictures", []) if audio is not None else []
                if not pictures and hasattr(tags, "getall"):
                    pictures = tags.getall("APIC")
                picture = next(
                    (p for p in pictures if getattr(p, "type", 3) == 3), None
                )
                if picture is None and pictures:
                    picture = pictures[0]
                if picture is not None and 0 < len(picture.data) <= 5_000_000:
                    covers[cover_key] = {
                        "data": base64.b64encode(picture.data).decode("ascii"),
                        "mime": picture.mime,
                    }
        except Exception as exc:
            failures.append({"path": relative.as_posix(), "error": str(exc)[:200]})
    print(
        json.dumps(
            {
                "schema_version": 1,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "source": "Synology · SERVER01 / Audio",
                "tracks": tracks,
                "covers": covers,
                "read_failures": failures,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    export()
