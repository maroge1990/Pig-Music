"""Adopt the existing verified live image into Docker Manager without upgrading it.

Retains a stopped rollback container and appdata backup. Account releases must
use their own fresh-state migration procedure, not this management conversion.

HISTORICAL: calls unversioned /api/... routes that U01-4 (R17) retired, so it
fails against images built from c62a8ac onward. Kept for migration history;
do not reuse without migrating it to /api/v1 and re-reviewing it.
"""

import argparse
import json
import shlex
import subprocess
import time
from pathlib import Path
import httpx

LIVE = "sha256:17f42b85b47f4404988f849c26005a66a2c3051b85671c821dffcb3f01e7a439"
IMAGE = "ghcr.io/maroge1990/pig-music:sha-1f21118b0448f7dce0cedb694a3067da132fd7ab"
ROOT = "/mnt/user/appdata/pig-music-preview"
BACKUP = ROOT + "/backups/pre-dockerman-20261007-v1"
PREVIOUS = "pig-music-preview-before-dockerman-20261007-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    ssh = [
        "ssh",
        "-i",
        str(Path.home() / ".ssh/pig_music_unraid"),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "root@192.168.1.235",
    ]

    def remote(command):
        return subprocess.check_output([*ssh, command], text=True).strip()

    def inspect(name):
        return json.loads(remote("docker inspect " + shlex.quote(name)))[0]

    existing = inspect("pig-music-preview")
    candidate = json.loads(remote("docker image inspect " + shlex.quote(IMAGE)))[0]
    assert existing["Image"] == candidate["Id"]
    assert any(d.endswith("@" + LIVE) for d in candidate["RepoDigests"])
    generator = '$docroot="/usr/local/emhttp"; $var=["timeZone"=>"Australia/Melbourne","NAME"=>"Passyflix"]; $subnet=["pig-music-preview"=>"172.25.0.0/16"]; $driver=["pig-music-preview"=>"bridge"]; require "/usr/local/emhttp/plugins/dynamix.docker.manager/include/Helpers.php"; echo json_encode(xmlToCommand(file_get_contents("/tmp/PigMusic-reviewed.xml")));'
    command, name, repository = json.loads(
        remote("php -d short_open_tag=1 -r " + shlex.quote(generator))
    )
    assert name == "PigMusic" and repository == IMAGE
    print(
        "Verified template and exact existing image; no application upgrade.",
        flush=True,
    )
    if not args.apply:
        return
    remote(
        "set -e; test ! -e "
        + shlex.quote(BACKUP)
        + "; ! docker inspect PigMusic >/dev/null 2>&1"
    )
    with httpx.Client(
        base_url="http://192.168.1.203:8765", timeout=20, headers={"X-Pig-Request": "1"}
    ) as client:
        settings = client.get("/api/settings/downloads").raise_for_status().json()
        health = client.get("/api/health").raise_for_status().json()
        assert health["storage_available"]

        def active():
            return any(
                i["status"] in {"searching", "downloading", "validating", "importing"}
                for i in client.get("/api/queue").raise_for_status().json()["items"]
            )

        if active():
            raise RuntimeError("Active transfers: conversion deferred")
        client.put(
            "/api/settings/downloads", json={**settings, "enabled": False}
        ).raise_for_status()
        stopped = renamed = created = False
        try:
            if active():
                raise RuntimeError("Transfer started: conversion deferred")
            remote("docker stop --timeout 30 pig-music-preview")
            stopped = True
            remote(
                "set -e; mkdir -m 700 "
                + shlex.quote(BACKUP)
                + "; cp -a "
                + ROOT
                + "/data "
                + shlex.quote(BACKUP + "/data")
                + "; cp "
                + ROOT
                + "/compose.yaml "
                + shlex.quote(BACKUP + "/compose.yaml")
            )
            remote("docker rename pig-music-preview " + PREVIOUS)
            renamed = True
            remote(
                "set -e; docker network disconnect br0 "
                + PREVIOUS
                + "; docker network disconnect pig-music-preview "
                + PREVIOUS
            )
            remote(command)
            created = True
            remote("docker start PigMusic")
            for _ in range(30):
                try:
                    after = client.get("/api/health").raise_for_status().json()
                    if (
                        after["storage_available"]
                        and after["library_stats"]["tracks"]
                        == health["library_stats"]["tracks"]
                    ):
                        break
                except (httpx.HTTPError, KeyError):
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Readiness/library acceptance failed")
            for path in ("/api/library", "/api/playlists", "/api/queue"):
                client.get(path).raise_for_status()
            live = inspect("PigMusic")
            assert live["Config"]["Labels"]["net.unraid.docker.managed"] == "dockerman"
            assert (
                live["HostConfig"]["ReadonlyRootfs"]
                and live["HostConfig"]["Memory"] == 1073741824
            )
            assert live["Config"]["User"] == "99:100"
            assert (
                live["NetworkSettings"]["Networks"]["br0"]["IPAddress"]
                == "192.168.1.203"
            )
            assert (
                live["NetworkSettings"]["Networks"]["pig-music-preview"]["IPAddress"]
                == "172.25.0.2"
            )
            client.put("/api/settings/downloads", json=settings).raise_for_status()
            remote(
                "set -e; cp /tmp/PigMusic-reviewed.xml /boot/config/plugins/dockerMan/templates-user/my-PigMusic.xml; cp "
                + ROOT
                + "/compose.yaml "
                + ROOT
                + "/compose.before-dockerman.yaml; mv "
                + ROOT
                + "/compose.yaml "
                + ROOT
                + "/compose.retired-dockerman.yaml; cp /var/lib/docker/unraid-autostart "
                + shlex.quote(BACKUP + "/unraid-autostart")
                + "; grep -v '^pig-music-preview$' /var/lib/docker/unraid-autostart > /tmp/pig-autostart-reviewed; printf 'PigMusic\\n' >> /tmp/pig-autostart-reviewed; cp /tmp/pig-autostart-reviewed /var/lib/docker/unraid-autostart"
            )
            print(
                "PigMusic is managed by Unraid; same image, library and private addresses. Rollback: "
                + PREVIOUS,
                flush=True,
            )
        except Exception:
            if created:
                remote(
                    "docker stop --timeout 30 PigMusic; docker network disconnect br0 PigMusic; docker network disconnect pig-music-preview PigMusic; docker rename PigMusic PigMusic-failed-dockerman-20261007-v1"
                )
            if renamed:
                remote(
                    "docker rename "
                    + PREVIOUS
                    + " pig-music-preview; docker network connect --ip 192.168.1.203 --gw-priority -1 br0 pig-music-preview; docker network connect --ip 172.25.0.2 pig-music-preview pig-music-preview"
                )
            if stopped:
                remote("docker start pig-music-preview")
            for _ in range(30):
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
