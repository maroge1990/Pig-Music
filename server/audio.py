"""Read-only measured audio properties; no encoding or tag changes."""

import json
import math
import os
import shutil
import tempfile
from pathlib import Path

from .providers.process import run_checked
from .vendor.audio_probe import probe_file as vendor_probe


def measured_bitrate(path, duration, check=lambda: None):
    """Use audio packet bytes when the container exposes no reliable bitrate.

    File-size/container overhead is deliberately excluded. Unknown measurements
    stay unknown; a nominal encoder setting is not substituted for missing data.
    """
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not math.isfinite(duration) or duration <= 0:
        return 0
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "packet=size",
            "-of",
            "json",
            str(path),
        ],
        check,
        timeout=30,
        max_output_bytes=10_000_000,
    )
    if result.returncode:
        return 0
    try:
        sizes = [
            int(packet["size"])
            for packet in json.loads(result.stdout).get("packets", [])
        ]
        if not sizes or any(size <= 0 for size in sizes):
            return 0
        return int(sum(sizes) * 8 / duration / 1000)
    except (ValueError, KeyError, TypeError):
        return 0


def probe_file(path, check=lambda: None):
    probe = vendor_probe(path)
    if probe and probe["codec"] in {"opus", "vorbis"} and not probe["bitrate_kbps"]:
        probe["bitrate_kbps"] = measured_bitrate(path, probe["duration"], check)
    return probe


def remux_opus(source, destination, check=lambda: None):
    """Copy a single Opus stream into Ogg without encoding or overwriting.

    The acquisition worker supplies staging paths; mixed/video inputs are
    rejected. Temporary output is linked into place only after successful copy.
    """
    source, destination = Path(source), Path(destination)
    if destination.suffix != ".opus" or destination.exists():
        raise ValueError("Choose a new Opus staging destination")
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise ValueError("FFmpeg and FFprobe are required for native Opus")
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(source),
        ],
        check,
        timeout=30,
    )
    if result.returncode:
        raise ValueError("Source audio is not readable Opus")
    streams = json.loads(result.stdout).get("streams", [])
    if (
        len(streams) != 1
        or streams[0].get("codec_type") != "audio"
        or streams[0].get("codec_name") != "opus"
    ):
        raise ValueError("Native Opus requires one audio stream and no video")
    with tempfile.TemporaryDirectory(
        prefix=".remux-", dir=destination.parent
    ) as temporary:
        output = Path(temporary) / "audio.opus"
        result = run_checked(
            [
                ffmpeg,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-c:a",
                "copy",
                "-f",
                "opus",
                str(output),
            ],
            check,
            timeout=90,
        )
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise ValueError("Native Opus stream copy failed")
        check()
        os.link(output, destination)
    return destination


def _remux_native(source, destination, codec, check):
    """Retain one audio stream from native HLS in its supported container."""
    source, destination = Path(source), Path(destination)
    if (
        destination.suffix != {"aac": ".m4a", "mp3": ".mp3"}[codec]
        or destination.exists()
    ):
        raise ValueError("Choose a new AAC staging destination")
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise ValueError("FFmpeg and FFprobe are required for native AAC")
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(source),
        ],
        check,
        timeout=30,
    )
    streams = (
        json.loads(result.stdout).get("streams", []) if not result.returncode else []
    )
    if (
        len(streams) != 1
        or streams[0].get("codec_type") != "audio"
        or streams[0].get("codec_name") != codec
    ):
        raise ValueError("Native AAC requires one audio stream and no video")
    with tempfile.TemporaryDirectory(
        prefix=".remux-", dir=destination.parent
    ) as temporary:
        output = Path(temporary) / ("audio" + destination.suffix)
        result = run_checked(
            [
                ffmpeg,
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-c:a",
                "copy",
                str(output),
            ],
            check,
            timeout=90,
        )
        if result.returncode or not output.is_file() or not output.stat().st_size:
            raise ValueError("Native AAC stream copy failed")
        check()
        os.link(output, destination)


def remux_aac(source, destination, check=lambda: None):
    return _remux_native(source, destination, "aac", check)


def remux_mp3(source, destination, check=lambda: None):
    return _remux_native(source, destination, "mp3", check)


def validate_streams(path, check=lambda: None):
    """Reject video and extra audio streams before rewriting any metadata."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise ValueError("FFprobe is required to validate recording streams")
    result = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file,pipe",
            "-show_entries",
            "stream=codec_type:stream_disposition=attached_pic",
            "-of",
            "json",
            str(path),
        ],
        check,
        timeout=30,
    )
    streams = (
        json.loads(result.stdout).get("streams", []) if not result.returncode else []
    )
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    other = [
        s
        for s in streams
        if s.get("codec_type") != "audio"
        and not s.get("disposition", {}).get("attached_pic")
    ]
    if len(audio) != 1 or other:
        raise ValueError("Recording must contain one audio stream and no video")
