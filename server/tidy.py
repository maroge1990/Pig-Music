"""Albums the household has on two editions, tidied to the fullest one.

Editions are albums by one album artist whose titles agree once edition
qualifiers go ("Hot Fuss" and "Hot Fuss (Deluxe Edition)"), sharing at least
half their songs. Singles and EPs, live albums, greatest hits and
compilations are albums of their own. The fullest edition is kept. Each song
on another edition that the kept album also has either goes to Trash (the
kept copy is as good), or replaces the kept copy (it is better: the file
moves into the kept album's folder, retagged to it, and the kept copy goes to
Trash). Songs only another edition has stay where they are, listed for
review. Nothing changes until the owner applies an album from a plan whose
files are unchanged since it was made, and every step can be undone.
"""

import hashlib
import json
import os
import re
import time
import uuid
from collections import defaultdict
from pathlib import Path

from .library import normalise, year_order
from .lifecycle import coordinated
from .matching import compatible, primary_artist, strip_edition
from .organisation import ALBUM_FIELDS, TAG_SUFFIXES, file_name
from .quality import canonical_codec

CATEGORIES = {"album", "soundtrack", "musical"}
LOSSLESS = {"flac", "alac", "wav", "aiff"}
# Share of an edition's songs the kept album must also have.
OVERLAP = 0.5
# A lossy copy replaces another only when clearly better, not by noise.
BITRATE_MARGIN = 1.15


def edition_title(album):
    """ "The Killers - Hot Fuss (Deluxe Edition)" is "hot fuss"; " - EP" and
    " - Single" stay, so a single is never an edition of its album."""
    text = album.get("title") or ""
    prefix = re.match(r"\s*(.+?)\s+-\s+(.+)$", text)
    if prefix and normalise(prefix[1]) == normalise(album.get("artist")):
        text = prefix[2]
    return normalise(strip_edition(text))


def quality(track):
    codec = canonical_codec(track.get("codec"))
    bitrate = track.get("bitrate") or 0
    if codec in LOSSLESS:
        return 2, bitrate
    return (1 if codec and codec != "unknown" else 0), bitrate


def better(new, old):
    """Whether `new` is clearly the better file; unknown quality never is,
    and never loses its file to a guess."""
    a, b = quality(new), quality(old)
    if not a[0] or not b[0]:
        return False
    if a[0] != b[0]:
        return a[0] > b[0]
    return a[0] == 1 and b[1] > 0 and a[1] >= b[1] * BITRATE_MARGIN


def label(track):
    codec = canonical_codec(track.get("codec")).upper() or "Unknown"
    bitrate = track.get("bitrate")
    return codec if codec in {"FLAC", "ALAC"} or not bitrate else f"{codec} {bitrate}"


def summary(track, album):
    return {
        "id": track["id"],
        "title": track["title"],
        "artist": track["artist"],
        "album": album["title"],
        "quality": label(track),
    }


class Tidy:
    def __init__(self, store, recovery, organisation):
        self.store = store
        self.recovery = recovery
        self.organisation = organisation

    def files(self):
        """Library-relative path, size and modification time of every song
        file as PigMusic last saw it."""
        with self.store.connect() as conn:
            acquired = {
                identity: json.loads(payload)
                for identity, payload in conn.execute("SELECT id,payload FROM acquired")
            }
        found = {}
        for album in self.store.library["albums"]:
            for track in album["tracks"]:
                raw = acquired.get(track["id"])
                if raw is not None:
                    path = raw.get("export_relative_path")
                    raw = {**raw, "nas": bool(path)}
                else:
                    raw = self.store.snapshot_tracks.get(track["id"]) or track
                    path = raw.get("relative_path")
                    raw = {**raw, "nas": bool(path)}
                found[track["id"]] = {
                    "path": path,
                    "nas": raw["nas"],
                    "size": raw.get("size_bytes"),
                    "mtime": raw.get("mtime_ns"),
                    "explicit": bool(raw.get("explicit_edition")),
                }
        return found

    def plan(self):
        files = self.files()
        groups = defaultdict(list)
        for album in self.store.library["albums"]:
            if album.get("category") not in CATEGORIES or album.get("compilation"):
                continue
            tracks = [t for t in album["tracks"] if t.get("available") is not False]
            # An edition chosen from Other versions is never tidied away.
            if not tracks or any(files[t["id"]]["explicit"] for t in tracks):
                continue
            key = (primary_artist(album["artist"]), edition_title(album))
            groups[key].append((album, tracks))
        items = []
        for editions in groups.values():
            if len(editions) > 1:
                item = self.review(editions, files)
                if item:
                    items.append(item)
        items.sort(key=lambda i: (i["artist"].casefold(), i["keep"]["title"]))
        return {"albums": items}

    def review(self, editions, files):
        editions.sort(
            key=lambda e: (-len(e[1]), year_order(e[0].get("year")) or 9999, e[0]["id"])
        )
        keeper, kept = editions[0]

        def filed(track, album):
            return {**track, "album": album["title"]}

        kept_paths = {files[k["id"]]["path"] for k in kept}
        matches, leftovers, others = defaultdict(list), [], []
        for album, tracks in editions[1:]:
            found = {
                t["id"]: [
                    k for k in kept if compatible(filed(k, keeper), filed(t, album))
                ]
                for t in tracks
            }
            if sum(len(f) == 1 for f in found.values()) < OVERLAP * len(tracks):
                continue  # Another album that happens to share the title.
            others.append(album)
            for track in tracks:
                if files[track["id"]]["path"] in kept_paths:
                    continue  # The kept album's own file under another name.
                if len(found[track["id"]]) == 1:
                    matches[found[track["id"]][0]["id"]].append((album, track))
                else:
                    leftovers.append(summary(track, album))
        if not others:
            return None
        remove, replace = [], []
        for k in kept:
            copies = matches.get(k["id"])
            if not copies:
                continue
            best = max(copies, key=lambda c: quality(c[1]))
            movable = (
                files[best[1]["id"]]["nas"]
                and files[k["id"]]["nas"]
                and Path(files[best[1]["id"]]["path"]).suffix.lower() in TAG_SUFFIXES
            )
            if better(best[1], k) and movable:
                replace.append(
                    {**summary(best[1], best[0]), "replaces": summary(k, keeper)}
                )
                copies = [c for c in copies if c is not best]
            elif better(best[1], k):
                # A better copy that cannot be retagged into place stays put.
                leftovers += [summary(t, a) for a, t in copies]
                continue
            remove += [{**summary(t, a), "kept": summary(k, keeper)} for a, t in copies]
        involved = [t["id"] for t in kept] + [
            t["id"] for album, tracks in editions[1:] if album in others for t in tracks
        ]
        fingerprint = hashlib.sha256(
            json.dumps(sorted([i, files[i]] for i in involved), sort_keys=True).encode()
        ).hexdigest()
        return {
            "id": keeper["id"],
            "artist": keeper["artist"],
            "keep": {
                "album_id": keeper["id"],
                "title": keeper["title"],
                "year": keeper.get("year") or None,
                "songs": len(kept),
            },
            "editions": [
                {
                    "album_id": a["id"],
                    "title": a["title"],
                    "year": a.get("year") or None,
                    "songs": len(
                        [t for t in a["tracks"] if t.get("available") is not False]
                    ),
                }
                for a in others
            ],
            "remove": remove,
            "replace": replace,
            "leftovers": leftovers,
            "fingerprint": fingerprint,
        }

    def unchanged(self, files, ids):
        """Every file still as PigMusic last saw it (else rescan first)."""
        root = Path(os.environ.get("PIG_MUSIC_LIBRARY", "/library"))
        for identity in ids:
            known = files[identity]
            path = root / known["path"]
            if known["size"] is not None and path.stat().st_size != known["size"]:
                return False
            if known["mtime"] is not None and path.stat().st_mtime_ns != known["mtime"]:
                return False
        return True

    @coordinated
    def apply(self, album_id, fingerprint):
        """Tidy one album's editions as planned; refused if anything changed."""
        item = next((i for i in self.plan()["albums"] if i["id"] == album_id), None)
        if not item or item["fingerprint"] != fingerprint:
            raise ValueError("These albums changed since the review.")
        files = self.files()
        moving = [r["id"] for r in item["remove"]] + [
            i for r in item["replace"] for i in (r["id"], r["replaces"]["id"])
        ]
        if not self.unchanged(files, [i for i in moving if files[i]["nas"]]):
            raise ValueError("Files changed since the last scan.")
        keeper = self.store.albums_by_id[album_id]
        tracks = {t["id"]: t for t in keeper["tracks"]}
        record = {
            "id": str(uuid.uuid4()),
            "album_id": album_id,
            "artist": item["artist"],
            "title": item["keep"]["title"],
            "time": int(time.time()),
            "status": "applying",
            "memberships": [],
            "removals": [],
            "moves": [],
        }
        self.save(record)
        try:
            for row in item["replace"]:
                old = tracks[row["replaces"]["id"]]
                # The better file's listeners and the kept copy's share it.
                self.share(record, row["replaces"]["id"], row["id"])
                self.trash(record, old["id"])
                placement = {k: keeper.get(k) for k in ("year",)}
                placement.update(
                    album=keeper["title"],
                    album_artist=keeper["artist"],
                    track_number=old.get("track_number"),
                    disc_number=old.get("disc_number", 1),
                    musicbrainz_release_id=keeper.get("musicbrainz_release_id"),
                )
                placement = {k: placement.get(k) for k in ALBUM_FIELDS}
                source = files[row["id"]]["path"]
                moved = self.store.index.by_id[row["id"]]
                destination = (
                    Path(files[old["id"]]["path"]).parent
                    / file_name({**moved, **placement}, Path(source).suffix.lower())
                ).as_posix()
                record["moves"].append(
                    self.organisation.move(
                        row["id"], source, destination, True, placement
                    )
                )
                self.save(record)
            for row in item["remove"]:
                kept = row["kept"]["id"]
                # A kept copy replaced above now lives on in the better file.
                kept = next(
                    (r["id"] for r in item["replace"] if r["replaces"]["id"] == kept),
                    kept,
                )
                self.share(record, row["id"], kept)
                self.trash(record, row["id"])
            record["status"] = "applied"
        except (ValueError, OSError):
            record["status"] = "stopped"
            raise
        finally:
            self.save(record)
            self.store.refresh_library()
        return record

    def share(self, record, track_id, keeper):
        from .user_library import bump

        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for (user_id,) in conn.execute(
                "SELECT user_id FROM library_members WHERE track_id=?", (track_id,)
            ).fetchall():
                if conn.execute(
                    "INSERT OR IGNORE INTO library_members VALUES (?,?,?,'household-add')",
                    (user_id, keeper, int(time.time())),
                ).rowcount:
                    record["memberships"].append([user_id, keeper])
                    bump(conn, user_id)
        self.save(record)

    def trash(self, record, track_id):
        removal = self.recovery.remove(track_id, exclude=False, refresh=False)
        record["removals"].append(removal["id"])
        self.save(record)

    @coordinated
    def undo(self, identity):
        """Put an album's editions back as they were before the tidy-up."""
        from .user_library import bump

        record = self.store.read_document("tidy:" + identity)
        # "applying" is a tidy-up a restart interrupted.
        if record.get("status") not in {"applying", "applied", "stopped"}:
            raise ValueError("Tidy-up not found.")
        for operation in reversed(record["moves"]):
            if self.store.read_document("organisation:" + operation).get("status") in {
                "completed",
                "undoing",
            }:
                self.organisation.undo(operation)
        for removal in reversed(record["removals"]):
            if self.store.read_document("removed:" + removal).get("status") in {
                "removed",
                "removing",
            }:
                self.recovery.restore(removal)
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for user_id, track_id in record["memberships"]:
                if conn.execute(
                    "DELETE FROM library_members WHERE user_id=? AND track_id=? AND source='household-add'",
                    (user_id, track_id),
                ).rowcount:
                    bump(conn, user_id)
        record["status"] = "undone"
        self.save(record)
        self.store.refresh_library()
        return record

    def history(self):
        with self.store.connect() as conn:
            records = [
                json.loads(v)
                for (v,) in conn.execute(
                    "SELECT payload FROM documents WHERE name LIKE 'tidy:%'"
                )
            ]
        return sorted(
            (r for r in records if r["status"] in {"applying", "applied", "stopped"}),
            key=lambda r: -r["time"],
        )

    def save(self, record):
        self.recovery.save("tidy:" + record["id"], record)
