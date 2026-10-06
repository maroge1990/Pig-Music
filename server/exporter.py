"""Publish validated managed downloads with a durable, restartable export record.

Unrelated NAS files are never overwritten. Managed quality replacements retain
guarded originals until validated publication. NAS mode requires explicit mount
identity/configuration; isolated previews remain the default.
"""

import asyncio
import hashlib
import json
import os
import shutil
import threading
import uuid
from pathlib import Path

from .downloader import safe_name
from .library import load_json, normalise
from .storage import library_root


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contained(root, relative):
    value = Path(relative)
    if value.is_absolute() or ".." in value.parts or ":" in str(value):
        raise ValueError("Invalid export path.")
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Export escaped the configured library.")
    cursor = root.resolve()
    for part in value.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("Export paths cannot contain symlinks.")
    return target


class Exporter:
    def __init__(self, store, root=None):
        self.store = store
        self.root = Path(root or os.environ.get("PIG_MUSIC_LIBRARY", "/library"))
        self.lock = threading.Lock()
        self.stopping = asyncio.Event()

    def config(self):
        return load_json(self.store.directory / "library-export.json")

    def records(self):
        with self.store.connect() as conn:
            return [
                json.loads(row[0])
                for row in conn.execute("SELECT payload FROM acquired")
            ]

    def relative(self, track):
        component = (
            lambda value: safe_name(value)
            .encode("utf-8")[:220]
            .decode("utf-8", "ignore")
        )
        album = component(track["album"]) + (
            f" ({track['year']})" if track.get("year") else ""
        )
        folder = Path(component(track["album_artist"])) / album
        # Preserve the existing folder spelling and edition context when tags
        # identify exactly one matching album folder.
        candidates = set()
        snapshot = load_json(self.store.directory / "library-snapshot.json")
        for saved in snapshot.get("tracks", []):
            if normalise(saved.get("album_artist", "")) != normalise(
                track["album_artist"]
            ):
                continue
            if normalise(saved.get("album", "")) != normalise(track["album"]):
                continue
            if (
                track.get("year")
                and saved.get("year")
                and str(track["year"])[:4] != str(saved["year"])[:4]
            ):
                continue
            if (
                track.get("musicbrainz_release_id")
                and saved.get("musicbrainz_release_id")
                and track["musicbrainz_release_id"] != saved["musicbrainz_release_id"]
            ):
                continue
            parent = Path(saved.get("relative_path", "")).parent
            if len(parent.parts) >= 2:
                candidates.add(parent.as_posix())
        if len(candidates) > 1:
            raise ValueError(
                "Multiple existing album folders need a destination decision."
            )
        if len(candidates) == 1:
            folder = Path(next(iter(candidates)))
        number = (
            f"{track['disc_number']:02}-{track['track_number']:02}"
            if track["disc_number"] > 1
            else f"{track['track_number']:02}"
        )
        label = f"{component(track['artist'])} - {component(track['album'])} - {number} - {component(track['title'])}"
        filename = (
            label.encode("utf-8")[:200].decode("utf-8", "ignore")
            + Path(track["relative_path"]).suffix
        )
        relative = (folder / filename).as_posix()
        # A same-extension quality replacement must coexist with the original
        # until publication succeeds. Unknown collisions remain review errors.
        target = contained(self.root, relative)
        if target.is_file() and digest(target) != track["sha256"]:
            with self.store.connect() as conn:
                old = [
                    json.loads(r[0])
                    for r in conn.execute(
                        "SELECT payload FROM quality_cleanup WHERE track_id=?",
                        (track["id"],),
                    )
                ]
            if any(
                (v.get("export_relative_path") or v.get("nas_relative_path"))
                == relative
                and v.get("sha256") == digest(target)
                for v in old
            ):
                relative = (
                    folder
                    / (
                        Path(filename).stem
                        + f" [{track['sha256'][:8]}]"
                        + Path(filename).suffix
                    )
                ).as_posix()
        return relative

    def plan(self):
        items = []
        for track in self.records():
            relative = track.get("export_relative_path") or self.relative(track)
            target = contained(self.root, relative)
            items.append(
                {
                    "id": track["id"],
                    "artist": track["artist"],
                    "album": track["album"],
                    "title": track["title"],
                    "destination": relative,
                    "exported": bool(track.get("export_relative_path")),
                    "collision": target.exists()
                    and not track.get("export_relative_path"),
                }
            )
        return {
            "enabled": self.config().get("enabled") is True,
            "destination": "Existing artist/album folders",
            "existing_files_unchanged": True,
            "items": items,
            "status": self.store.read_document("library-export-status"),
        }

    def report(self, **value):
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES ('library-export-status',?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (json.dumps(value),),
            )

    def publish(self, track):
        source_root = library_root(self.store)
        if not contained(source_root, track["relative_path"]).is_file():
            legacy = self.store.directory / "downloads" / "library"
            if contained(legacy, track["relative_path"]).is_file():
                source_root = legacy
        source = contained(source_root, track["relative_path"])
        relative = track.get("export_relative_path") or self.relative(track)
        target = contained(self.root, relative)
        expected = track["sha256"]
        if not source.is_file():
            if (
                track.get("export_relative_path")
                and target.is_file()
                and digest(target) == expected
            ):
                return
            raise ValueError("Validated download is unavailable; export deferred.")
        if digest(source) != expected:
            raise ValueError("Validated download changed; export refused.")
        if target.exists():
            if not target.is_file() or digest(target) != expected:
                raise ValueError(
                    "Destination contains different content; export refused."
                )
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            stage = contained(
                self.root,
                str(
                    Path(relative).parent
                    / (".pig-music-" + uuid.uuid4().hex + ".pig-part")
                ),
            )
            try:
                if source.stat().st_dev == target.parent.stat().st_dev:
                    os.link(
                        source, stage
                    )  # Same NAS: publish without a second audio copy.
                else:
                    with source.open("rb") as incoming, stage.open("wb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                        outgoing.flush()
                        os.fsync(outgoing.fileno())
                if digest(stage) != expected:
                    raise ValueError("Export verification failed.")
                # Hard-link publication is atomic and cannot replace a competing
                # file. Both files are on the same NAS filesystem.
                try:
                    os.link(stage, target)
                except FileExistsError:
                    if digest(target) != expected:
                        raise ValueError("Destination changed during export.")
            finally:
                stage.unlink(missing_ok=True)
        if digest(target) != expected:
            raise ValueError("Published file verification failed.")
        with self.store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT payload FROM acquired WHERE id=?", (track["id"],)
            ).fetchone()
            if not row or json.loads(row[0]).get("sha256") != expected:
                return
            value = {**json.loads(row[0]), "export_relative_path": relative}
            conn.execute(
                "UPDATE acquired SET payload=? WHERE id=?",
                (json.dumps(value), track["id"]),
            )
        # The NAS copy is verified and its location durably committed before
        # deleting the staging-library copy. Restart can finish this cleanup.
        if source.exists() and digest(source) == expected:
            source.unlink()

    def process(self):
        if self.config().get("enabled") is not True or not self.lock.acquire(
            blocking=False
        ):
            return
        try:
            if not self.root.is_dir():
                raise ValueError("Library mount unavailable; export deferred.")
            config = self.config()
            marker = load_json(
                contained(
                    self.root,
                    config.get("marker_path", "Pig Music/.pig-music-library.json"),
                )
            )
            if (
                not config.get("library_id")
                or marker.get("library_id") != config["library_id"]
            ):
                raise ValueError(
                    "The expected library marker is unavailable; export deferred."
                )
            completed = 0
            changed = False
            for track in self.records():
                self.publish(track)
                completed += 1
                changed = changed or not track.get("export_relative_path")
            if changed:
                self.store.refresh_library()
            self.store.cleanup_replacements()
            if changed:
                with self.store.connect() as conn:
                    conn.execute(
                        "INSERT INTO documents VALUES ('plex-refresh-required','true') ON CONFLICT(name) DO UPDATE SET payload='true'"
                    )
            self.report(status="completed", files=completed)
        except (OSError, ValueError, KeyError) as exc:
            self.report(status="deferred", error=str(exc)[:180])
        finally:
            self.lock.release()

    async def run(self):
        while not self.stopping.is_set():
            await asyncio.to_thread(self.process)
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=15)
            except TimeoutError:
                pass
