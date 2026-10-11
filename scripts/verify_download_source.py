"""Opt-in metadata/transfer acceptance in a newly created, isolated directory.

Run as a module from the repository root. Use recordings you control or have
permission to download. No production appdata, mount, source settings or cookies
are read. A successful transfer is fully validated/tagged/published by Downloader.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from server.downloader import Downloader, matches
from server.providers.contracts import Context, ProviderError
from server.routes.personal import TrackInput
from server.store import Store


def verify(source, target, output, metadata_only=False):
    output = Path(output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    # The normal download root validates NAS identity when explicitly set. This
    # process uses fresh appdata's local staging/library and never that mount.
    os.environ.pop("PIG_MUSIC_DOWNLOAD_ROOT", None)
    store = Store(output / "state")
    profile = "lossless" if source == "monochrome" else "native_standard"
    store.save_download_settings(
        {"enabled": True, "profile": profile, "sources": [source]}
    )
    worker = Downloader(store)
    report = {
        "source": source,
        "profile": profile,
        "metadata_only": metadata_only,
        "audio_verified": False,
        "recording": {
            key: target.get(key) for key in ("artist", "title", "album", "duration")
        },
    }
    if metadata_only:
        try:
            candidates = worker.runtime.search(source, target, Context(profile))
            report.update(
                metadata_reachable=True,
                matching_candidates=len([c for c in candidates if matches(target, c)]),
            )
        except ProviderError as exc:
            report.update(metadata_reachable=False, error=str(exc))
    else:
        store.submit_catalogue([{**target, "status": "missing"}])
        worker.process(store.claim_request())
        request = store.queue()["items"][0]
        report["status"] = request["status"]
        if request["status"] == "completed":
            with store.connect() as conn:
                saved = json.loads(
                    conn.execute("SELECT payload FROM acquired").fetchone()[0]
                )
            path = worker.library_root / saved["relative_path"]
            # Re-open durable state, preserving both publication and queue evidence.
            restarted = Store(store.directory)
            if restarted.queue()["items"][0]["status"] != "completed":
                raise ValueError("Published request did not survive restart")
            report.update(
                audio_verified=True,
                acquisition=saved["acquisition"],
                relative_path=saved["relative_path"],
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        else:
            report["error"] = request.get("error", "Recording did not complete")
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, choices=("youtube", "soundcloud", "monochrome")
    )
    parser.add_argument(
        "--track",
        required=True,
        type=Path,
        help="JSON recording with artist, title, album and duration; optional ISRCs",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New isolated directory; existing directories are refused",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Search/hydrate without downloading audio",
    )
    args = parser.parse_args()
    target = TrackInput.model_validate(json.loads(args.track.read_text())).model_dump(
        exclude_none=True
    )
    target["album_artist"] = target["album_artist"] or target["artist"]
    if target["duration"] <= 0 or not target["album"]:
        parser.error("Acceptance needs an expected album and full recording duration")
    report = verify(args.source, target, args.output, args.metadata_only)
    print(json.dumps(report, indent=2))
    success = (
        report.get("metadata_reachable")
        if args.metadata_only
        else report.get("audio_verified")
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
