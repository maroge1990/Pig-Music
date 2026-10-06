"""Verify candidate projection against a stopped, read-only production backup.

Runs without NAS/network mounts. Only disposable state is modified; durable
rows must remain identical except for the additive album-edition anchor document.
"""

import argparse
import json
import shutil
import sqlite3
from pathlib import Path

from server.store import Store


def rows(database):
    with sqlite3.connect(database) as conn:
        tables = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return {
            table: sorted(
                conn.execute(
                    'SELECT * FROM "' + table.replace('"', '""') + '"'
                ).fetchall()
            )
            for table in tables
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    args = parser.parse_args()
    if args.destination.exists():
        raise ValueError("Migration fixture must be a new disposable directory")
    args.destination.mkdir(parents=True)
    for name in (
        "pig-music.sqlite3",
        "pig-music.sqlite3-wal",
        "pig-music.sqlite3-shm",
        "library-snapshot.json",
        "media-settings.json",
    ):
        source = args.source / name
        if source.exists():
            shutil.copyfile(source, args.destination / name)
    covers = args.source / "covers"
    if covers.is_dir():
        shutil.copytree(covers, args.destination / "covers")
    database = args.destination / "pig-music.sqlite3"
    before = rows(database)
    expected = json.loads(args.expected.read_text())
    snapshot_path = args.destination / "library-snapshot.json"
    # Metadata only: stream original tracks so large base64 maps are not loaded.
    import ijson

    with snapshot_path.open("rb") as stream:
        if stream.read(3) != b"\xef\xbb\xbf":
            stream.seek(0)
        original_tracks = list(ijson.items(stream, "tracks.item", use_float=True))
    store = Store(args.destination)
    migrated_tracks = json.loads(snapshot_path.read_text(encoding="utf-8-sig")).get(
        "tracks", []
    )
    image_fields = {"cover_sha", "cover_rescan"}
    assert [
        {k: v for k, v in t.items() if k not in image_fields} for t in original_tracks
    ] == [
        {k: v for k, v in t.items() if k not in image_fields} for t in migrated_tracks
    ], "Snapshot track metadata changed"
    assert all(
        store.covers.path(t["cover_sha"]) for t in migrated_tracks if t.get("cover_sha")
    ), "Migrated artwork missing"
    assert (
        store.summary()["stats"]["tracks"] == expected["tracks"]
    ), "Library count changed"
    assert set(expected["album_ids"]).issubset(
        {a["id"] for a in store.library["albums"]}
    ), "Existing album links changed"
    after = rows(database)
    for values in (before, after):
        values["documents"] = [
            r for r in values["documents"] if r[0] != "album-edition-anchors"
        ]
    assert before == after, "Existing durable preferences, queue or membership changed"
    print(
        "Stopped-state migration verified:",
        expected["tracks"],
        "tracks; existing links and durable rows retained",
    )


if __name__ == "__main__":
    main()
