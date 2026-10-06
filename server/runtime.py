"""Supervise the web service and its private Soulseek engine in one container."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .storage import require_library_mount


def start_engine(root):
    log = None
    try:
        engine = root / "engine"
        engine.mkdir(parents=True, exist_ok=True)
        if os.environ.get("PIG_MUSIC_EMBEDDED_ENGINE", "true").lower() == "true":
            if os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT"):
                require_library_mount(
                    root,
                    Path(os.environ.get("PIG_MUSIC_LIBRARY", "/library")),
                    required=True,
                )
                work = Path(os.environ["PIG_MUSIC_DOWNLOAD_ROOT"])
                for name in ("engine-downloads", "engine-incomplete"):
                    (work / name).mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            private = engine / "engine.env"
            if private.exists():
                for line in private.read_text().splitlines():
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        if key.startswith("SLSKD_"):
                            env[key] = value.strip().strip('"').strip("'")
            env.update(
                SLSKD_HTTP_IP_ADDRESS="127.0.0.1",
                SLSKD_HTTP_PORT="5030",
                SLSKD_NO_HTTPS="true",
                SLSKD_REMOTE_CONFIGURATION="false",
                SLSKD_APP_DIR=str(engine),
                SLSKD_DOWNLOADS_DIR=(
                    str(
                        Path(os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT", str(engine)))
                        / "engine-downloads"
                    )
                    if os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT")
                    else str(engine / "downloads")
                ),
                SLSKD_INCOMPLETE_DIR=(
                    str(
                        Path(os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT", str(engine)))
                        / "engine-incomplete"
                    )
                    if os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT")
                    else str(engine / "incomplete")
                ),
                DOTNET_BUNDLE_EXTRACT_BASE_DIR=str(engine / "bundle"),
                DOTNET_EnableDiagnostics="0",
                DOTNET_GCHeapHardLimit="0x10000000",
                SLSKD_UMASK="077",
            )
            command = [
                "/opt/slskd/slskd",
                "--app-dir",
                str(engine),
                "--no-logo",
                "--no-version-check",
                "--no-https",
                "--http-ip-address",
                "127.0.0.1",
                "--http-port",
                "5030",
                "--headless",
            ]
            config = engine / "slskd.yml"
            if config.exists():
                command += ["--config", str(config)]
            if (
                not env.get("SLSKD_SLSK_USERNAME")
                or os.environ.get("PIG_MUSIC_ENGINE_NO_CONNECT") == "true"
            ):
                command += ["--no-connect"]
            logfile = engine / "runtime.log"
            if logfile.exists() and logfile.stat().st_size > 10_000_000:
                logfile.replace(engine / "runtime.previous.log")
            log = logfile.open("ab")
            os.chmod(logfile, 0o600)
            return (
                subprocess.Popen(
                    command,
                    cwd="/opt/slskd",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                ),
                log,
            )
    except (OSError, ValueError):
        if log:
            log.close()
    return None, None


def main():
    children = []
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log = None
    try:
        root = Path(os.environ.get("PIG_MUSIC_DATA", "/data"))
        child, log = start_engine(root)
        if child:
            children.append(child)
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "server.app:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    "8765",
                ]
            )
        )
        next_engine_check = 0
        while not stopping and all(child.poll() is None for child in children):
            if (
                len(children) == 1
                and os.environ.get("PIG_MUSIC_EMBEDDED_ENGINE", "true").lower()
                == "true"
                and time.monotonic() >= next_engine_check
            ):
                child, log = start_engine(root)
                if child:
                    children.append(child)
                next_engine_check = time.monotonic() + 5
            time.sleep(0.25)
        failed = not stopping
        stop(None, None)
        deadline = time.monotonic() + 25
        for child in children:
            try:
                child.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        return 1 if failed else 0
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait()
        if log:
            log.close()


if __name__ == "__main__":
    sys.exit(main())
