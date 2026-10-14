"""System callbacks in the Apple apps never inherit main-actor isolation.

A closure formed inside main-actor code is isolated to it, and Swift 6 traps
when the system calls it from another queue (the W3 crash hazard). Remote
commands and audio completions must be explicitly @Sendable.
"""

import re
from pathlib import Path

SWIFT = Path(__file__).resolve().parents[1] / "swift"
SOURCES = [
    path
    for folder in ("PigMusic", "PigMusicWatch", "Shared", "PigKit/Sources")
    for path in (SWIFT / folder).rglob("*.swift")
]


def test_remote_command_handlers_are_sendable():
    offenders = [
        f"{path.relative_to(SWIFT)}:{text[: match.start()].count(chr(10)) + 1}"
        for path in SOURCES
        for text in [path.read_text()]
        for match in re.finditer(r"\.addTarget\s*\{(?!\s*@Sendable)", text)
    ]
    assert offenders == []


def test_audio_buffer_completions_are_sendable():
    offenders = [
        f"{path.relative_to(SWIFT)}:{text[: match.start()].count(chr(10)) + 1}"
        for path in SOURCES
        for text in [path.read_text()]
        for match in re.finditer(r"scheduleBuffer\([^{}]*\)\s*\{(?!\s*@Sendable)", text)
    ]
    assert offenders == []
