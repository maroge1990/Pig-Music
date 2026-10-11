"""Opt-in local Apple codec/transition probe using generated tones only.

Requires a built PigAudioProbe and FFmpeg; never reads household music or providers.
Reports decode/render observations separately from exact source-duration preservation.
"""

import argparse
import hashlib
import json
import math
import platform
import re
import shutil
import struct
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path


FORMATS = {
    "wav": ("wav", ["-c:a", "pcm_s16le"]),
    "aiff": ("aiff", ["-c:a", "pcm_s16be"]),
    "aac": ("m4a", ["-c:a", "aac", "-b:a", "192k"]),
    "alac": ("m4a", ["-c:a", "alac"]),
    "mp3": ("mp3", ["-c:a", "libmp3lame", "-b:a", "192k"]),
    "flac": ("flac", ["-c:a", "flac"]),
    "opus": ("opus", ["-c:a", "libopus", "-b:a", "128k"]),
    "vorbis": ("ogg", ["-c:a", "vorbis", "-strict", "experimental", "-q:a", "5"]),
}


def run(arguments, timeout=30):
    return subprocess.run(
        arguments, capture_output=True, text=True, timeout=timeout, check=False
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe", default="swift/build/PigKit/out/Products/Debug/PigAudioProbe"
    )
    parser.add_argument("--output", default="swift/build/AudioMatrix")
    args = parser.parse_args()
    probe = Path(args.probe).resolve()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not probe.is_file() or not ffmpeg or not ffprobe:
        parser.error(
            "Build PigAudioProbe and provide FFmpeg/ffprobe before running this probe"
        )
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source = root / "generated-source.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(
            b"".join(
                struct.pack("<hh", value, value)
                for index in range(44100)
                for value in [
                    round(0.2 * 32767 * math.sin(2 * math.pi * 440 * index / 44100))
                ]
            )
        )
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "ffmpeg": run([ffmpeg, "-version"]).stdout.splitlines()[0],
        "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
        "fixture": "Generated 1-second 44.1kHz stereo 440Hz tone at 0.2 amplitude",
        "scope": "Local-file decoding and offline engine capture on this Mac only",
        "duration_note": "Comparison is to the original generated source, not automatically a decoder defect: inspect encoded input duration/padding separately.",
        "formats": {},
    }
    expression = re.compile(
        r"Engine rendered (\d+) frames at 48000 Hz stereo; overlap (\d+), peak held (\d+), peak scheduled (\d+) frames"
    )
    for name, (extension, options) in FORMATS.items():
        fixture = root / (name + "." + extension)
        encoded = run(
            [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                *options,
                str(fixture),
            ]
        )
        observation = {"fixture_encoder_arguments": options}
        report["formats"][name] = observation
        if encoded.returncode:
            observation["fixture_error"] = encoded.stderr[-1000:].replace(
                str(root), "<fixture-root>"
            )
            continue
        metadata = run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,sample_rate,duration_ts,time_base,duration:format=duration",
                "-of",
                "json",
                str(fixture),
            ]
        )
        if metadata.returncode == 0:
            observation["encoded_input_metadata"] = json.loads(metadata.stdout)
        for label, seconds in [("gapless", "0"), ("crossfade", "0.25")]:
            output = root / (name + "-" + label + ".wav")
            result = run(
                [
                    str(probe),
                    "--bounded",
                    str(fixture),
                    str(fixture),
                    str(output),
                    seconds,
                ]
            )
            match = expression.search(result.stdout)
            if result.returncode or not match:
                observation[label] = {
                    "rendered": False,
                    "reason": (result.stderr or result.stdout)[-1000:].replace(
                        str(root), "<fixture-root>"
                    ),
                }
                continue
            frames, overlap, held, scheduled = map(int, match.groups())
            expected = 96000 - round(float(seconds) * 48000)
            observation[label] = {
                "rendered": True,
                "output_frames": frames,
                "expected_source_frames": expected,
                "matches_generated_source_duration": frames == expected,
                "overlap_frames": overlap,
                "peak_held_frames": held,
                "peak_scheduled_frames": scheduled,
            }
        print(name, json.dumps(observation))
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
