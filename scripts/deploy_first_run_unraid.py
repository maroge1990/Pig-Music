"""One-time legacy-to-account switch under native Unraid Docker Manager.

Requires exact-image Unraid acceptance. Preserves a fresh stopped appdata backup,
old container and template; verifies attribution on a disposable copy only.
The real owner creates their password later in the private HTTPS WebUI.
"""

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

import httpx

ROOT = "/mnt/user/appdata/pig-music-preview"
TEMPLATE = "/boot/config/plugins/dockerMan/templates-user/my-PigMusic.xml"
LEGACY = "sha256:17f42b85b47f4404988f849c26005a66a2c3051b85671c821dffcb3f01e7a439"
ORIGIN = "https://passyflix.tail6d1471.ts.net:10000"
ACTIVE = {"searching", "downloading", "validating", "importing"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--verified-log", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(
        r"ghcr.io/maroge1990/pig-music@sha256:[0-9a-f]{64}", args.image
    ):
        parser.error("Use the immutable Pig Music registry digest")
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision) or not re.fullmatch(
        r"[a-z0-9-]{6,70}", args.version
    ):
        parser.error("Invalid revision/release name")
    evidence = args.verified_log.read_text()
    if (
        "Candidate passed isolated Linux tests, artwork and HTTP delivery scale gates: "
        + args.image
        not in evidence
    ):
        parser.error("Exact-image Unraid acceptance has not completed")
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

    def remote(command, payload=None):
        return subprocess.check_output(
            [*ssh, command], text=True, input=payload
        ).strip()

    def inspect(name):
        return json.loads(remote("docker inspect " + shlex.quote(name)))[0]

    def php(code):
        return remote("php -d short_open_tag=1 -r " + shlex.quote(code))

    def private(path):
        return json.loads(
            remote(
                "curl --max-time 15 --fail --silent --show-error --resolve passyflix.tail6d1471.ts.net:10000:100.99.233.14 "
                + shlex.quote(ORIGIN + path)
            )
        )

    live = inspect("PigMusic")
    candidate = json.loads(remote("docker image inspect " + shlex.quote(args.image)))[0]
    assert any(
        d.endswith("@" + LEGACY)
        for d in json.loads(
            remote("docker image inspect " + shlex.quote(live["Image"]))
        )[0]["RepoDigests"]
    )
    labels = candidate["Config"]["Labels"]
    assert labels["org.opencontainers.image.revision"] == args.revision
    assert (
        labels["org.opencontainers.image.source"]
        == "https://github.com/maroge1990/Pig-Music"
    )
    assert live["Config"]["Labels"]["net.unraid.docker.managed"] == "dockerman"
    assert (
        live["HostConfig"]["ReadonlyRootfs"]
        and live["HostConfig"]["Memory"] == 1073741824
    )
    assert live["Config"]["User"] == "99:100"
    networks = live["NetworkSettings"]["Networks"]
    assert networks["br0"]["IPAddress"] == "192.168.1.203"
    assert networks["pig-music-preview"]["IPAddress"] == "172.25.0.2"
    backup = ROOT + "/backups/pre-" + args.version
    previous = "PigMusic-before-" + args.version
    stage = ROOT + "/releases/" + args.version
    failed = "PigMusic-failed-" + args.version
    reviewed = "/tmp/PigMusic-" + args.version + ".xml"
    remote(
        "test ! -e "
        + shlex.quote(backup)
        + " && test -f "
        + shlex.quote(stage + "/source.tar.gz")
    )
    remote("! docker inspect " + shlex.quote(previous) + " >/dev/null 2>&1")
    with httpx.Client(
        base_url="http://192.168.1.203:8765", timeout=20, headers={"X-Pig-Request": "1"}
    ) as client:
        original = client.get("/api/settings/downloads").raise_for_status().json()
        library = client.get("/api/library").raise_for_status().json()
        expected = {
            "tracks": library["stats"]["tracks"],
            "album_ids": [a["id"] for a in library["albums"]],
        }
        assert private("/api/health")["storage_available"]

        def active():
            return any(
                q["status"] in ACTIVE
                for q in client.get("/api/queue").raise_for_status().json()["items"]
            )

        if active():
            raise RuntimeError("Active transfers; switch deferred")
        print(
            "Preflight passed: exact image, native manager, private HTTPS and",
            expected["tracks"],
            "tracks.",
            flush=True,
        )
        if not args.apply:
            return
        remote(
            "cat > " + shlex.quote(stage + "/expected-first-run.json"),
            json.dumps(expected),
        )
        settings_changed = stopped = backup_complete = renamed = created = (
            template_changed
        ) = data_changed = False
        try:
            settings_changed = True
            client.put(
                "/api/settings/downloads", json={**original, "enabled": False}
            ).raise_for_status()
            if active():
                raise RuntimeError("Transfer started; switch deferred")
            remote("docker stop --timeout 30 PigMusic >/dev/null")
            stopped = True
            remote(
                "set -e\nmkdir -m 700 "
                + shlex.quote(backup)
                + "\ncp -a "
                + ROOT
                + "/data "
                + shlex.quote(backup + "/data")
                + "\ncp "
                + TEMPLATE
                + " "
                + shlex.quote(backup + "/PigMusic.xml")
                + "\ncp /var/lib/docker/unraid-autostart "
                + shlex.quote(backup + "/unraid-autostart")
            )
            backup_complete = True
            print(
                "Fresh stopped backup saved; verifying migration and owner attribution on a disposable copy.",
                flush=True,
            )
            remote(
                "docker run --rm --network none --memory=1g --user 99:100 --tmpfs /data:rw,uid=99,gid=100 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/app -v "
                + shlex.quote(backup + "/data:/backup:ro")
                + " -v "
                + shlex.quote(stage + ":/release:ro")
                + " --entrypoint python "
                + shlex.quote(args.image)
                + " /app/scripts/verify_state_migration.py --source /backup --destination /data/migration --expected /release/expected-first-run.json --bootstrap-owner-fixture"
            )
            # The disposable owner above is never copied into live state.
            data_changed = True
            code = "import json,sys; from pathlib import Path; from server.store import Store; from server.auth import Auth; s=Store(Path('/data')); assert not Auth(s).has_owner(); s.save_download_settings(json.load(sys.stdin)); print(json.dumps({'tracks':s.summary()['stats']['tracks'],'owner_ready':Auth(s).ready()}))"
            result = json.loads(
                remote(
                    "docker run --rm -i --network none --memory=1g --user 99:100 --tmpfs /tmp:rw,uid=99,gid=100 -e PYTHONDONTWRITEBYTECODE=1 -v "
                    + ROOT
                    + "/data:/data --entrypoint python "
                    + shlex.quote(args.image)
                    + " -c "
                    + shlex.quote(code),
                    json.dumps(original),
                )
            )
            assert result == {"tracks": expected["tracks"], "owner_ready": False}
            tag = "ghcr.io/maroge1990/pig-music:sha-" + args.revision
            assert (
                json.loads(remote("docker image inspect " + shlex.quote(tag)))[0]["Id"]
                == candidate["Id"]
            )
            php(
                "$x=simplexml_load_file("
                + json.dumps(TEMPLATE)
                + "); $x->Repository="
                + json.dumps(tag)
                + '; $x->Overview="Pig Music: private household music, playlists and downloads. First open offers administrator setup; copy the installation code from PigMusic Logs and choose your password in the private HTTPS WebUI."; if ($x->asXML('
                + json.dumps(reviewed)
                + ")===false) exit(1);"
            )
            generator = (
                '$docroot="/usr/local/emhttp"; $var=["timeZone"=>"Australia/Melbourne","NAME"=>"Passyflix"]; $subnet=["pig-music-preview"=>"172.25.0.0/16"]; $driver=["pig-music-preview"=>"bridge"]; require "/usr/local/emhttp/plugins/dynamix.docker.manager/include/Helpers.php"; echo json_encode(xmlToCommand(file_get_contents('
                + json.dumps(reviewed)
                + ")));"
            )
            command, name, repository = json.loads(php(generator))
            assert name == "PigMusic" and repository == tag
            remote("docker rename PigMusic " + previous)
            renamed = True
            remote(
                "set -e\ndocker network disconnect br0 "
                + previous
                + "\ndocker network disconnect pig-music-preview "
                + previous
            )
            remote(command)
            created = True
            remote("cp " + shlex.quote(reviewed) + " " + TEMPLATE)
            template_changed = True
            remote("docker start PigMusic >/dev/null")
            for _ in range(40):
                try:
                    response = client.get("/api/health").raise_for_status().json()
                    if response.get("status") == "ok" and response.get(
                        "storage_available"
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError("Readiness/storage check failed")
            assert private("/api/health")["https"] is True
            assert private("/api/v1/setup/owner") == {"setup_required": True}
            assert client.get("/api/library").status_code == 503
            assert client.get("/api/v1/setup/owner").status_code == 400
            after = inspect("PigMusic")
            assert after["Image"] == candidate["Id"]
            assert after["Config"]["Labels"]["net.unraid.docker.managed"] == "dockerman"
            assert after["Config"]["User"] == "99:100"
            assert (
                after["HostConfig"]["ReadonlyRootfs"]
                and after["HostConfig"]["Memory"] == live["HostConfig"]["Memory"]
            )
            assert after["HostConfig"]["NanoCpus"] == live["HostConfig"]["NanoCpus"]
            assert after["HostConfig"]["CapDrop"] == live["HostConfig"]["CapDrop"]
            assert (
                after["HostConfig"]["SecurityOpt"] == live["HostConfig"]["SecurityOpt"]
            )
            assert {
                (m["Source"], m["Destination"], m["RW"]) for m in after["Mounts"]
            } == {(m["Source"], m["Destination"], m["RW"]) for m in live["Mounts"]}
            assert (
                after["NetworkSettings"]["Networks"]["br0"]["IPAddress"]
                == "192.168.1.203"
            )
            assert (
                after["NetworkSettings"]["Networks"]["pig-music-preview"]["IPAddress"]
                == "172.25.0.2"
            )
            print(
                "First-run release is live over verified private HTTPS. Owner creation is still required in the WebUI.",
                flush=True,
            )
            print("Backup:", backup, "; rollback:", previous, flush=True)
        except Exception:
            print(
                "Switch failed; restoring complete stopped state and prior native container.",
                flush=True,
            )
            if renamed and (
                created
                or remote(
                    "if docker inspect PigMusic >/dev/null 2>&1; then echo present; fi"
                )
                == "present"
            ):
                remote("docker stop --timeout 30 PigMusic >/dev/null 2>&1 || true")
                remote("docker network disconnect br0 PigMusic >/dev/null 2>&1 || true")
                remote(
                    "docker network disconnect pig-music-preview PigMusic >/dev/null 2>&1 || true"
                )
                remote("docker rename PigMusic " + failed)
            if data_changed and backup_complete:
                remote(
                    "set -e\nmv "
                    + ROOT
                    + "/data "
                    + ROOT
                    + "/data.failed-"
                    + args.version
                    + "\ncp -a "
                    + shlex.quote(backup + "/data")
                    + " "
                    + ROOT
                    + "/data"
                )
            if template_changed:
                remote("cp " + shlex.quote(backup + "/PigMusic.xml") + " " + TEMPLATE)
            if renamed:
                remote("docker rename " + previous + " PigMusic")
                for network, address, priority in [
                    ("br0", "192.168.1.203", "-1"),
                    ("pig-music-preview", "172.25.0.2", "0"),
                ]:
                    if (
                        network
                        not in inspect("PigMusic")["NetworkSettings"]["Networks"]
                    ):
                        remote(
                            "docker network connect --ip "
                            + address
                            + " --gw-priority "
                            + priority
                            + " "
                            + network
                            + " PigMusic"
                        )
            if stopped:
                remote("docker start PigMusic >/dev/null")
            if settings_changed:
                for _ in range(40):
                    try:
                        client.put(
                            "/api/settings/downloads", json=original
                        ).raise_for_status()
                        break
                    except httpx.HTTPError:
                        time.sleep(1)
                else:
                    raise RuntimeError(
                        "Rollback started but original download settings could not be restored"
                    )
            raise


if __name__ == "__main__":
    main()
