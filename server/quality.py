"""Source quality policy; remove superseded downloads after validated replacement."""

PROFILES = {"mp3_128", "mp3_320", "aac_256", "lossless"}


def rank(profile):
    return {"aac_256": 1, "mp3_128": 2, "mp3_320": 3, "lossless": 4}.get(profile, 0)


def actual_profile(track):
    codec = track.get("codec", "").lower()
    if codec == "flac":
        return "lossless"
    if codec == "aac":
        return "aac_256" if track.get("bitrate", 0) >= 240 else "unknown"
    if codec == "mp3":
        bitrate = track.get("bitrate", 0)
        return (
            "mp3_320"
            if bitrate >= 300
            else "mp3_128" if 112 <= bitrate <= 144 else "unknown"
        )
    return "unknown"


def policy(settings, preferred=None):
    return {
        "preferred": preferred or settings["profile"],
        "fallback": settings.get("fallback_profile", "mp3_320"),
        # Marks requests made since AAC became the last resort; older
        # queued requests keep their original fallback behaviour.
        "aac_fallback": True,
        "fallback_minutes": settings.get("fallback_minutes", 10),
        "recheck_hours": settings.get("recheck_hours", 24),
    }
