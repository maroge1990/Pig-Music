"""Review-first organisation with preserved originals and restart recovery."""

from .lifecycle import coordinated

import json, os, shutil, uuid
from pathlib import Path
from .library import load_json
from .media import saved_track, track_file
from .exporter import Exporter, contained
from .downloader import Downloader, safe_name
from .scanner import inspect_file


class Organisation:
    def __init__(self, store, recovery):
        self.store = store
        self.recovery = recovery

    def plan(self):
        rows = []
        root = Path(os.environ.get("PIG_MUSIC_LIBRARY", "/library"))
        snapshot = load_json(self.store.directory / "library-snapshot.json")
        originals = {t["id"]: t for t in snapshot.get("tracks", [])}
        with self.store.connect() as c:
            acquired = {
                identity: json.loads(payload)
                for identity, payload in c.execute("SELECT id,payload FROM acquired")
            }
        for album in self.store.library["albums"]:
            for track in album["tracks"]:
                raw = acquired.get(track["id"]) or originals.get(track["id"])
                if not raw or raw.get("available") is False:
                    continue
                if track["id"] in acquired and not raw.get("export_relative_path"):
                    continue
                old = raw.get("export_relative_path") or raw.get("relative_path")
                if not old:
                    continue
                suffix = Path(old).suffix.lower()
                number = (
                    f"{raw.get('disc_number',1):02}-{raw.get('track_number',0):02}"
                    if raw.get("disc_number", 1) > 1
                    else f"{raw.get('track_number',0):02}"
                )
                label = " - ".join(
                    [
                        safe_name(raw["artist"]),
                        safe_name(raw["album"]),
                        number,
                        safe_name(raw["title"]),
                    ]
                )
                target = (
                    Path(old).parent
                    / (label.encode("utf-8")[:200].decode("utf-8", "ignore") + suffix)
                ).as_posix()
                rows.append(
                    {
                        "id": raw["id"],
                        "title": raw["title"],
                        "artist": raw["artist"],
                        "from": old,
                        "to": target,
                        "rename": old != target,
                        "tag_supported": suffix in {".mp3", ".flac", ".m4a"},
                        "conflict": old != target and contained(root, target).exists(),
                    }
                )
        targets = {}
        for row in rows:
            targets.setdefault(row["to"], []).append(row)
        for matches in targets.values():
            if len(matches) > 1:
                for row in matches:
                    row["conflict"] = True
        return {
            "items": rows,
            "note": "Existing album folders and release identities are retained. Tags use the current library metadata. Originals are preserved for recovery.",
        }

    @coordinated
    def apply(self, ids, tags=False):
        rows = {r["id"]: r for r in self.plan()["items"]}
        results = []
        for identity in ids:
            row = rows.get(identity)
            if not row or row["conflict"]:
                raise ValueError("A selected destination needs review.")
            if tags and not row["tag_supported"]:
                raise ValueError("This audio format needs a separate tag review.")
            if not row["rename"] and not tags:
                continue
            with self.recovery.lock:
                track, root = saved_track(self.store, identity)
                self.recovery.check_mount(root)
                source = track_file(self.store, identity)
                destination = contained(root, row["to"])
                operation = str(uuid.uuid4())
                backup = contained(
                    root,
                    ".pig-music-trash/organisation/" + operation + "/" + row["from"],
                )
                backup.parent.mkdir(parents=True, exist_ok=True)
                contained(root, ".pig-music-trash/.plexignore").write_text(
                    "*\n", encoding="utf-8"
                )
                before = self.recovery.digest(source)
                stage = source.parent / (
                    ".pig-music-organise-" + operation + source.suffix
                )
                record = {
                    "id": operation,
                    "track_id": identity,
                    "track": track,
                    "root": str(root.resolve()),
                    "source": row["from"],
                    "destination": row["to"],
                    "backup": backup.relative_to(root).as_posix(),
                    "stage": stage.relative_to(root).as_posix(),
                    "before": before,
                    "status": "preparing",
                }
                self.recovery.save("organisation:" + operation, record)
                os.link(source, backup)
                shutil.copyfile(source, stage)
                if tags:
                    Downloader(self.store).tag(stage, track, "existing-library")
                checked, _ = inspect_file(stage, row["to"])
                if abs(checked.get("duration", 0) - track.get("duration", 0)) > 1:
                    raise ValueError("Audio duration changed; original retained.")
                record.update(after=self.recovery.digest(stage), status="publishing")
                self.recovery.save("organisation:" + operation, record)
                self.finish(record, root)
                results.append(operation)
        self.store.refresh_library()
        self.recovery.save("plex-refresh-required", True)
        return {"applied": len(results), "operations": results}

    def finish(self, record, root):
        source = contained(root, record["source"])
        target = contained(root, record["destination"])
        stage = contained(root, record["stage"])
        backup = contained(root, record["backup"])
        if not backup.is_file() or self.recovery.digest(backup) != record["before"]:
            raise ValueError("Original backup changed; publication stopped.")
        if record["status"] == "preparing":
            if stage.exists():
                stage.unlink()
            record["status"] = "cancelled"
            self.recovery.save("organisation:" + record["id"], record)
            return
        if record["source"] == record["destination"]:
            if target.exists() and self.recovery.digest(target) == record["before"]:
                if (
                    not stage.is_file()
                    or self.recovery.digest(stage) != record["after"]
                ):
                    raise ValueError("Prepared file unavailable.")
                os.replace(stage, target)
            elif (
                not target.is_file() or self.recovery.digest(target) != record["after"]
            ):
                raise ValueError("Destination changed.")
        else:
            if target.exists() and self.recovery.digest(target) != record["after"]:
                raise ValueError("Destination collision; original retained.")
            if not target.exists():
                if (
                    not stage.is_file()
                    or self.recovery.digest(stage) != record["after"]
                ):
                    raise ValueError("Prepared file unavailable.")
                os.link(stage, target)
            if source.exists():
                if self.recovery.digest(source) != record["before"]:
                    raise ValueError("Original changed; both files retained.")
                source.unlink()
            if stage.exists():
                stage.unlink()
        checked, _ = inspect_file(target, record["destination"])
        updated = {
            **record["track"],
            **checked,
            "id": record["track_id"],
            "sha256": record["after"],
        }
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT payload FROM acquired WHERE id=?", (record["track_id"],)
            ).fetchone()
            if row:
                acquired = json.loads(row[0])
                acquired.update(
                    export_relative_path=record["destination"],
                    sha256=record["after"],
                    size_bytes=target.stat().st_size,
                    mtime_ns=target.stat().st_mtime_ns,
                )
                conn.execute(
                    "UPDATE acquired SET payload=? WHERE id=?",
                    (json.dumps(acquired), record["track_id"]),
                )
        snapshot = load_json(self.store.directory / "library-snapshot.json")
        snapshot["tracks"] = [
            updated if t["id"] == record["track_id"] else t
            for t in snapshot.get("tracks", [])
        ]
        temporary = self.store.directory / "organisation-snapshot.tmp"
        temporary.write_text(json.dumps(snapshot), encoding="utf-8")
        temporary.replace(self.store.directory / "library-snapshot.json")
        record["status"] = "completed"
        self.recovery.save("organisation:" + record["id"], record)

    @coordinated
    def recover(self):
        with self.store.connect() as c:
            records = [
                json.loads(v)
                for (v,) in c.execute(
                    "SELECT payload FROM documents WHERE name LIKE 'organisation:%'"
                )
            ]
        for record in records:
            if record["status"] == "undoing":
                try:
                    self.undo(record["id"])
                except (OSError, ValueError):
                    pass
                continue
            if record["status"] not in {"preparing", "publishing"}:
                continue
            try:
                _, root = saved_track(self.store, record["track_id"])
                self.recovery.check_mount(root)
                if str(root.resolve()) != record["root"]:
                    continue
                with self.recovery.lock:
                    self.finish(record, root)
            except (OSError, ValueError):
                pass
        self.store.refresh_library()

    def history(self):
        with self.store.connect() as c:
            return [
                json.loads(v)
                for (v,) in c.execute(
                    "SELECT payload FROM documents WHERE name LIKE 'organisation:%'"
                )
            ]

    @coordinated
    def undo(self, identity):
        with self.recovery.lock:
            record = self.store.read_document("organisation:" + identity)
            if record.get("status") not in {"completed", "undoing"}:
                raise ValueError("Organisation record not found.")
            _, root = saved_track(self.store, record["track_id"])
            self.recovery.check_mount(root)
            if str(root.resolve()) != record["root"]:
                raise ValueError("Library mount changed.")
            source = contained(root, record["source"])
            target = contained(root, record["destination"])
            backup = contained(root, record["backup"])
            if not backup.is_file() or self.recovery.digest(backup) != record["before"]:
                raise ValueError("Original backup unavailable.")
            if target.exists() and self.recovery.digest(target) not in {
                record["after"],
                record["before"],
            }:
                raise ValueError("Organised file changed; undo stopped.")
            if (
                source.exists()
                and record["source"] != record["destination"]
                and self.recovery.digest(source) != record["before"]
            ):
                raise ValueError("Original location contains another file.")
            record["status"] = "undoing"
            self.recovery.save("organisation:" + identity, record)
            if record["source"] == record["destination"]:
                restore = source.parent / (
                    ".pig-music-restore-" + identity + source.suffix
                )
                shutil.copyfile(backup, restore)
                os.replace(restore, source)
            else:
                if not source.exists():
                    os.link(backup, source)
                if target.exists():
                    target.unlink()
            checked, _ = inspect_file(source, record["source"])
            updated = {
                **record["track"],
                **checked,
                "id": record["track_id"],
                "sha256": record["before"],
            }
            with self.store.connect() as c:
                row = c.execute(
                    "SELECT payload FROM acquired WHERE id=?", (record["track_id"],)
                ).fetchone()
                if row:
                    acquired = json.loads(row[0])
                    acquired.update(
                        export_relative_path=record["source"],
                        sha256=record["before"],
                        size_bytes=source.stat().st_size,
                        mtime_ns=source.stat().st_mtime_ns,
                    )
                    c.execute(
                        "UPDATE acquired SET payload=? WHERE id=?",
                        (json.dumps(acquired), record["track_id"]),
                    )
            snapshot = load_json(self.store.directory / "library-snapshot.json")
            snapshot["tracks"] = [
                updated if t["id"] == record["track_id"] else t
                for t in snapshot.get("tracks", [])
            ]
            temp = self.store.directory / "organisation-snapshot.tmp"
            temp.write_text(json.dumps(snapshot), encoding="utf-8")
            temp.replace(self.store.directory / "library-snapshot.json")
            record["status"] = "undone"
            self.recovery.save("organisation:" + identity, record)
            self.store.refresh_library()
            self.recovery.save("plex-refresh-required", True)
            return {"status": "undone"}
