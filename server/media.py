"""Private provider settings and read-only playback file resolution."""

import json
import os
import re
from pathlib import Path

from .library import load_json
from .storage import library_root


def settings(store):
    target = store.directory / "media-settings.json"
    try:
        stat = target.stat()
        signature = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    except FileNotFoundError:
        signature = None
    cached = getattr(store, "_media_settings_cache", None)
    if cached is None or cached[0] != signature:
        cached = (
            signature,
            {"portraits": True, "remote_playback": True, **load_json(target)},
        )
        store._media_settings_cache = cached
    return dict(cached[1])


def public_settings(store):
    value = settings(store)
    return {
        "portraits": value["portraits"],
        "remote_playback": value["remote_playback"],
        "fanart_configured": bool(value.get("fanart_key")),
        "listenbrainz_configured": bool(value.get("listenbrainz_token")),
    }


def save_settings(
    store, portraits, remote_playback, fanart_key=None, listenbrainz_token=None
):
    value = {
        **settings(store),
        "portraits": portraits,
        "remote_playback": remote_playback,
    }
    if fanart_key is not None:
        if fanart_key and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", fanart_key):
            raise ValueError("Enter a valid Fanart API key.")
        value["fanart_key"] = fanart_key
    if listenbrainz_token is not None:
        if listenbrainz_token and not re.fullmatch(
            r"[A-Za-z0-9_-]{16,128}", listenbrainz_token
        ):
            raise ValueError("Enter a valid ListenBrainz user token.")
        value["listenbrainz_token"] = listenbrainz_token
    target = store.directory / "media-settings.json"
    temporary = target.with_suffix(".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    store._media_settings_cache = None
    return public_settings(store)


def saved_track(store, track_id):
    # Acquired tracks may be staged or published; snapshot tracks use the NAS root.
    with store.connect() as conn:
        row = conn.execute(
            "SELECT payload FROM acquired WHERE id=?", (track_id,)
        ).fetchone()
    if row:
        track = json.loads(row[0])
        if track.get("export_relative_path"):
            return {**track, "relative_path": track["export_relative_path"]}, Path(
                os.environ.get("PIG_MUSIC_LIBRARY", "/library")
            )
        return track, library_root(store)
    track = store.snapshot_tracks.get(track_id)
    return track, Path(os.environ.get("PIG_MUSIC_LIBRARY", "/library"))


def track_file(store, track_id):
    track, root = saved_track(store, track_id)
    if track is None:
        raise FileNotFoundError
    relative = track.get("relative_path", "").replace("\\", "/")
    if (
        not relative
        or relative.startswith("/")
        or ":" in relative
        or ".." in relative.split("/")
    ):
        raise FileNotFoundError
    root = root.resolve()
    target = (root / relative).resolve()
    if (
        not target.is_relative_to(root)
        or not target.is_file()
        or target.suffix.lower()
        not in {".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"}
    ):
        raise FileNotFoundError
    return target
