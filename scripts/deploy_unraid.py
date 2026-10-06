"""Build/test a source-only candidate; optionally deploy with state-preserving rollback.

Never bundles appdata or credentials. Existing images, backups and containers are
retained. Run from the repository with its virtual environment activated.
"""

import argparse
import json
import re
import shlex
import subprocess
import tarfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
REMOTE = "/mnt/user/appdata/pig-music-preview"


def bundle(target):
    with tarfile.open(target, "w:gz") as archive:
        files = [
            ROOT / name
            for name in (
                "Dockerfile",
                ".dockerignore",
                ".gitignore",
                "compose.yaml",
                "compose.unraid-preview.yaml",
                "requirements.txt",
                "requirements-dev.txt",
                "requirements.lock.txt",
                "pyproject.toml",
                "README.md",
                "blueprint.md",
            )
        ]
        for folder in ("server", "client", "tests", "docs", "scripts"):
            files.extend(
                p
                for p in (ROOT / folder).rglob("*")
                if p.is_file()
                and not p.is_symlink()
                and not {"node_modules", "__pycache__", "dist"}.intersection(p.parts)
                and not p.name.startswith(".env")
                and p.suffix not in {".pem", ".key"}
            )
        for path in sorted(files):
            info = archive.gettarinfo(str(path), path.relative_to(ROOT).as_posix())
            info.mode, info.uid, info.gid = 0o644, 0, 0
            info.uname = info.gname = ""
            with path.open("rb") as stream:
                archive.addfile(info, stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="root@192.168.1.235")
    parser.add_argument(
        "--key", type=Path, default=Path.home() / ".ssh/pig_music_unraid"
    )
    parser.add_argument("--url", default="http://192.168.1.203:8765")
    parser.add_argument(
        "--version",
        required=True,
        help="Unique lowercase candidate suffix; never overwrite a release",
    )
    parser.add_argument(
        "--image",
        help="Tested ghcr.io/maroge1990/pig-music@sha256:<digest>; pull instead of local build",
    )
    parser.add_argument(
        "--deploy",
        action="store_true",
        help="After passing candidate tests, update the live container",
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{3,70}", args.version):
        parser.error("Use a lowercase version suffix")
    if args.image and not re.fullmatch(
        r"ghcr\.io/maroge1990/pig-music@sha256:[0-9a-f]{64}", args.image
    ):
        parser.error(
            "Registry images must use the Pig Music repository and a full SHA-256 digest"
        )
    image = args.image or "pig-music:" + args.version
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    if (
        args.image
        and subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=ROOT,
            text=True,
        ).strip()
    ):
        parser.error(
            "Registry verification requires a clean tracked source tree at the image commit"
        )
    stage = REMOTE + "/releases/" + args.version
    ssh = ["ssh", "-i", str(args.key), "-o", "BatchMode=yes", args.host]

    def remote(command):
        subprocess.run(ssh + [command], check=True)

    output = ROOT / ".localdata" / "deploy"
    output.mkdir(parents=True, exist_ok=True)
    archive = output / (args.version + ".tar.gz")
    bundle(archive)
    remote(
        "set -e; test ! -e " + shlex.quote(stage) + "; mkdir -p " + shlex.quote(stage)
    )
    subprocess.run(
        [
            "scp",
            "-i",
            str(args.key),
            str(archive),
            args.host + ":" + stage + "/source.tar.gz",
        ],
        check=True,
    )
    remote("cd " + shlex.quote(stage) + "; tar -xzf source.tar.gz; chmod -R a+rX tests")
    if args.image:
        remote("docker pull " + shlex.quote(image))
        # Match the supplied source/tests to the image, without inspecting secrets.
        remote(
            "test $(docker image inspect --format '{{index .Config.Labels \"org.opencontainers.image.revision\"}}' "
            + shlex.quote(image)
            + ") = "
            + shlex.quote(revision)
        )
        remote(
            "test $(docker image inspect --format '{{index .Config.Labels \"org.opencontainers.image.source\"}}' "
            + shlex.quote(image)
            + ") = https://github.com/maroge1990/Pig-Music"
        )
    else:
        remote(
            "cd "
            + shlex.quote(stage)
            + "; docker build --build-arg VCS_REF="
            + shlex.quote(revision)
            + " --build-arg VERSION="
            + shlex.quote(args.version)
            + " -t "
            + shlex.quote(image)
            + " ."
        )
    remote(
        "docker run --rm --network none --memory=1g --user 99:100 --tmpfs /tmp:rw,uid=99,gid=100 --tmpfs /data:rw,uid=99,gid=100 -e PYTHONDONTWRITEBYTECODE=1 -e PIG_MUSIC_PRELOAD=false -e PIG_MUSIC_EMBEDDED_ENGINE=false -v "
        + shlex.quote(stage + "/tests:/tests:ro")
        + " --entrypoint python "
        + shlex.quote(image)
        + " -m pytest /tests -q -p no:cacheprovider --basetemp=/tmp/pig-tests"
    )
    remote(
        "docker run --rm --network none --memory=1g --entrypoint python "
        + shlex.quote(image)
        + " /app/scripts/benchmark_cover_store.py --sizes 10000 50000"
    )
    remote(
        "docker run --rm --network none --memory=1g --entrypoint python "
        + shlex.quote(image)
        + " /app/scripts/benchmark_delivery.py"
    )
    print(
        "Candidate passed isolated Linux tests, artwork and HTTP delivery scale gates:",
        image,
        flush=True,
    )
    if not args.deploy:
        return
    backup = REMOTE + "/backups/pre-" + args.version
    previous = "pig-music-preview-before-" + args.version
    active = {"searching", "downloading", "validating", "importing"}
    with httpx.Client(base_url=args.url, timeout=20) as client:
        settings = client.get("/api/settings/downloads").raise_for_status().json()
        library = client.get("/api/library").raise_for_status().json()
        expected = output / (args.version + "-expected.json")
        expected.write_text(
            json.dumps(
                {
                    "tracks": library["stats"]["tracks"],
                    "album_ids": [a["id"] for a in library["albums"]],
                }
            )
        )
        subprocess.run(
            [
                "scp",
                "-i",
                str(args.key),
                str(expected),
                args.host + ":" + stage + "/expected.json",
            ],
            check=True,
        )
        if any(
            t["status"] in active
            for t in client.get("/api/queue").raise_for_status().json()["items"]
        ):
            raise RuntimeError(
                "Active transfers detected; candidate is ready but deployment deferred."
            )
        client.put(
            "/api/settings/downloads", json={**settings, "enabled": False}
        ).raise_for_status()
        if any(
            t["status"] in active
            for t in client.get("/api/queue").raise_for_status().json()["items"]
        ):
            client.put("/api/settings/downloads", json=settings).raise_for_status()
            raise RuntimeError(
                "A transfer started during the check; original settings restored."
            )
        changed = False
        try:
            changed = True
            remote(
                "set -e; test ! -e "
                + shlex.quote(backup)
                + "; docker stop --timeout 30 pig-music-preview; mkdir -p "
                + shlex.quote(backup)
                + "; cp -a "
                + REMOTE
                + "/data "
                + shlex.quote(backup + "/data")
                + "; cp "
                + REMOTE
                + "/compose.yaml "
                + shlex.quote(backup + "/compose.yaml")
            )
            remote(
                "docker run --rm --network none --user 99:100 --tmpfs /data:rw,uid=99,gid=100 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app -v "
                + shlex.quote(backup + "/data:/backup:ro")
                + " -v "
                + shlex.quote(stage + ":/release:ro")
                + " --entrypoint python "
                + shlex.quote(image)
                + " /release/scripts/verify_state_migration.py --source /backup --destination /data/migration --expected /release/expected.json"
            )
            remote(
                "set -e; docker rename pig-music-preview "
                + shlex.quote(previous)
                + "; docker network disconnect br0 "
                + shlex.quote(previous)
            )
            # The reviewed compose keeps all existing resource/network protections.
            compose = (ROOT / "compose.unraid-preview.yaml").read_text()
            compose = re.sub(r"image: pig-music:[^\s]+", "image: " + image, compose)
            local = output / (args.version + "-compose.yaml")
            local.write_text(compose)
            subprocess.run(
                [
                    "scp",
                    "-i",
                    str(args.key),
                    str(local),
                    args.host + ":" + REMOTE + "/compose.yaml",
                ],
                check=True,
            )
            # A renamed Compose container still carries its original service
            # labels. A unique project prevents Compose deleting that rollback
            # container when it recreates the current service.
            remote(
                "cd "
                + REMOTE
                + "; docker compose -p "
                + shlex.quote("pig-music-" + args.version)
                + " -f compose.yaml up -d"
            )
            for attempt in range(30):
                try:
                    health = client.get("/api/health").raise_for_status().json()
                    if health["storage_available"]:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Candidate failed readiness/storage check")
            for path in (
                "/api/library",
                "/api/queue",
                "/api/playlists",
                "/api/settings/media",
            ):
                client.get(path).raise_for_status()
            client.put("/api/settings/downloads", json=settings).raise_for_status()
            print(
                "Deployed:",
                image,
                "; original download settings restored; backup:",
                backup,
                flush=True,
            )
        except Exception:
            if changed:
                remote(
                    "if docker inspect "
                    + shlex.quote(previous)
                    + " >/dev/null 2>&1; then docker stop --timeout 30 pig-music-preview >/dev/null 2>&1 || true; docker network disconnect br0 pig-music-preview >/dev/null 2>&1 || true; docker rename pig-music-preview pig-music-preview-failed-"
                    + args.version
                    + "; docker rename "
                    + shlex.quote(previous)
                    + " pig-music-preview; cp "
                    + shlex.quote(backup + "/compose.yaml")
                    + " "
                    + REMOTE
                    + "/compose.yaml; docker network connect --ip 192.168.1.203 --gw-priority -1 br0 pig-music-preview; docker start pig-music-preview; else docker start pig-music-preview; fi"
                )
            else:
                remote("docker start pig-music-preview")
            for attempt in range(30):
                try:
                    client.put(
                        "/api/settings/downloads", json=settings
                    ).raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(1)
            raise


if __name__ == "__main__":
    main()
