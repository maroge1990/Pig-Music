"""Source quality policy; remove superseded downloads after validated replacement."""

PROFILES = {"mp3_128", "mp3_320", "aac_256", "lossless"}


def rank(profile):
    return {"mp3_128": 1, "mp3_320": 2, "aac_256": 2, "lossless": 3}.get(profile, 0)


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
        "fallback_minutes": settings.get("fallback_minutes", 10),
        "recheck_hours": settings.get("recheck_hours", 24),
    }
