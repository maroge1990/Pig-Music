"""Historical initial-preview bootstrap; not the current deployment path.

Use deploy_unraid.py for releases. This older tool can include private bootstrap
state and is retained only for understanding the initial migration.

Create an allowlisted source bundle and consistent private preview state.

Does not deploy, expose credentials in logs, or copy SSH keys/test downloads.
Run with the local worker paused before handing live testing to Unraid.
"""

import argparse
import json
import sqlite3
import tarfile
from pathlib import Path


def add(archive, path, name, private=False):
    info = archive.gettarinfo(str(path), arcname=name)
    info.mode = 0o600 if private else 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    with path.open("rb") as file:
        archive.addfile(info, file)


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / ".localdata")
    parser.add_argument(
        "--output", type=Path, default=root / ".localdata" / "unraid-deploy"
    )
    parser.add_argument(
        "--source-only",
        action="store_true",
        help="Package an update without copying or replacing live state",
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tarfile.open(args.output / "source.tar.gz", "w:gz") as archive:
        for name in (
            "Dockerfile",
            ".dockerignore",
            "requirements.lock.txt",
            "README.md",
        ):
            add(archive, root / name, name)
        for folder in ("server", "client"):
            for file in sorted((root / folder).rglob("*")):
                if (
                    file.is_file()
                    and not file.is_symlink()
                    and not {"node_modules", "__pycache__", "dist"}.intersection(
                        file.parts
                    )
                    and not file.name.startswith(".env")
                    and file.suffix not in {".pem", ".key"}
                ):
                    add(archive, file, file.relative_to(root).as_posix())
    if args.source_only:
        print("Prepared allowlisted source archive only; live state is not included")
        return
    backup = args.output / "pig-music.sqlite3"
    with (
        sqlite3.connect(args.data / "pig-music.sqlite3") as source,
        sqlite3.connect(backup) as target,
    ):
        source.backup(target)
    config = json.loads(
        (args.data / "slskd-connection.json").read_text(encoding="utf-8-sig")
    )
    deployed = {
        "url": "http://pig-music-slskd-test:5030",
        "api_key": config["api_key"],
        "download_root": "/engine-downloads",
    }
    connection = args.output / "slskd-connection.json"
    connection.write_text(json.dumps(deployed), encoding="utf-8")
    with sqlite3.connect(backup) as database:
        acquired = [
            json.loads(row[0])
            for row in database.execute("SELECT payload FROM acquired")
        ]
    with tarfile.open(args.output / "state.tar.gz", "w:gz") as archive:
        add(archive, backup, "pig-music.sqlite3", private=True)
        add(archive, connection, "slskd-connection.json", private=True)
        add(archive, args.data / "library-snapshot.json", "library-snapshot.json")
        library = (args.data / "downloads" / "library").resolve()
        for track in acquired:
            file = (library / track["relative_path"]).resolve()
            if not file.is_relative_to(library) or not file.is_file():
                raise ValueError(
                    "An acquired file is unavailable; refuse to deploy stale downloaded badges"
                )
            add(
                archive,
                file,
                "downloads/library/" + file.relative_to(library).as_posix(),
            )
    print(
        "Prepared allowlisted source and private state archives; acquired files:",
        len(acquired),
    )


if __name__ == "__main__":
    main()
