"""Source quality policy; remove superseded downloads after validated replacement."""

import math

PROFILES = {"mp3_128", "mp3_320", "aac_256", "lossless", "native_standard"}
NATIVE_MINIMUMS = {"mp3": 120, "aac": 112, "opus": 96, "vorbis": 128}
CODEC_EXTENSIONS = {
    "mp3": ".mp3",
    "aac": ".m4a",
    "opus": ".opus",
    "vorbis": ".ogg",
    "flac": ".flac",
}


def canonical_codec(value):
    value = str(value or "").lower()
    return "vorbis" if value == "ogg" else value


def satisfies(profile, audio):
    """Check observed audio, never a provider's quality label or extension."""
    codec = canonical_codec(audio.get("codec"))
    if profile == "lossless":
        return codec == "flac"
    if profile == "native_standard":
        if codec == "flac":
            return True
        minimum = NATIVE_MINIMUMS.get(codec)
    else:
        expected, minimum = {
            "mp3_128": ("mp3", 120),
            "mp3_320": ("mp3", 300),
            "aac_256": ("aac", 240),
        }.get(profile, (None, None))
        if codec != expected:
            return False
    bitrate = audio.get("bitrate_kbps", audio.get("bitrate", 0))
    return (
        minimum is not None
        and isinstance(bitrate, (int, float))
        and not isinstance(bitrate, bool)
        and math.isfinite(bitrate)
        and bitrate >= minimum
    )


def rank(profile):
    return {
        "native_standard": 1,
        "mp3_128": 1,
        "mp3_320": 2,
        "aac_256": 2,
        "lossless": 3,
    }.get(profile, 0)


def actual_profile(track):
    codec = track.get("codec", "").lower()
    if codec == "flac":
        return "lossless"
    if codec == "aac":
        if track.get("bitrate", 0) >= 240:
            return "aac_256"
    if codec == "mp3":
        bitrate = track.get("bitrate", 0)
        profile = (
            "mp3_320"
            if bitrate >= 300
            else "mp3_128" if 112 <= bitrate <= 144 else "unknown"
        )
        if profile != "unknown":
            return profile
    # Existing scanned files of unknown quality remain protected. Only measured
    # native acquisitions gain a new classification for automatic improvements.
    if track.get("acquisition", {}).get(
        "quality_profile"
    ) == "native_standard" and satisfies("native_standard", track):
        return "native_standard"
    return "unknown"


def policy(settings, preferred=None):
    return {
        "preferred": preferred or settings["profile"],
        "fallback": settings.get("fallback_profile", "mp3_320"),
        "fallback_minutes": settings.get("fallback_minutes", 10),
        "recheck_hours": settings.get("recheck_hours", 24),
    }
