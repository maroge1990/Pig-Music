"""Library artwork projection and safe maintenance, separate from durable state."""

import json
import time
from .library import normalise, identifier, load_json
from .image_cache import public_image
from .media import settings as media_settings


def cache_covers(store, snapshot_tracks):
    # Quality replacements can supersede every scanned track in an album.
    # Retain its display artwork without moving the old file membership.
    scanned_art = {}
    for track in snapshot_tracks:
        if track.get("cover_sha"):
            key = (
                normalise(
                    track.get("album_artist", track.get("artist", "Unknown artist"))
                ),
                normalise(track.get("album", "Singles")),
            )
            scanned_art.setdefault(key, []).append(track)
    for album in store.library["albums"]:
        if not album.get("cover_sha"):
            candidates = scanned_art.get(
                (normalise(album["artist"]), normalise(album["title"])), []
            )
            release = album.get("musicbrainz_release_id")
            hashes = {
                t["cover_sha"]
                for t in candidates
                if not release or t.get("musicbrainz_release_id") == release
            }
            if len(hashes) == 1:
                album["cover_sha"] = next(iter(hashes))
        target = store.covers.path(album.get("cover_sha"))
        album["cover_url"] = "/api/artwork/" + target.name if target else None
    albums = {a["id"]: a for a in store.library["albums"]}
    # Prefer any available own-album cover, rather than only the first album.
    for artist in store.library["artists"]:
        candidates = artist["album_ids"] or [artist["cover_album_id"]]
        artist["cover_url"] = next(
            (
                albums[a]["cover_url"]
                for a in candidates
                if a in albums and albums[a].get("cover_url")
            ),
            None,
        )
    for album in store.library["albums"]:
        if not album["cover_url"]:
            cached = public_image(
                store,
                store.cover_dir / (identifier("catalogue-cover", album["id"]) + ".jpg"),
            )
            album["cover_url"] = (
                "/api/artwork/" + cached.name
                if cached
                else "/api/library-artwork/albums/" + album["id"]
            )
    config = media_settings(store)
    from .portraits import portrait_target

    for artist in store.library["artists"]:
        if not artist["cover_url"]:
            artist["cover_url"] = next(
                (
                    albums[a]["cover_url"]
                    for a in (artist["album_ids"] or [artist["cover_album_id"]])
                    if a in albums
                    and (albums[a].get("cover_url") or "").startswith("/api/artwork/")
                ),
                None,
            )
        known = store.read_document("library-artist:" + artist["id"])
        portrait = (
            public_image(store, portrait_target(store, artist["name"], known.get("id")))
            if config["portraits"]
            else None
        )
        artist["fallback_cover_url"] = artist["cover_url"]
        if portrait:
            artist["cover_url"] = "/api/artwork/" + portrait.name
        elif config["portraits"] or not artist["cover_url"]:
            artist["cover_url"] = (
                "/api/library-artwork/artists/" + artist["id"] + "?portraits=1"
            )
    # Optional image metadata is read from a small sidecar, never decoded here.
    for item in [*store.library["albums"], *store.library["artists"]]:
        url = item.get("cover_url", "") or ""
        if url.startswith("/api/artwork/"):
            sha = url.removeprefix("/api/artwork/").removesuffix(".jpg")
            metadata = store.covers.presentation(sha)
            if metadata:
                item["artwork_metadata"] = metadata


def prune_artwork(store, now=None):
    now = time.time() if now is None else now
    with store.covers.lock, store.library_lock:
        snapshot = load_json(store.directory / "library-snapshot.json")
        references = {t.get("cover_sha") for t in snapshot.get("tracks", [])}
        references.update(a.get("cover_sha") for a in store.library["albums"])
        with store.connect() as conn:
            references.update(
                json.loads(payload).get("sha")
                for (payload,) in conn.execute(
                    "SELECT payload FROM documents WHERE name LIKE 'image-public:%'"
                )
            )
        with store.connect() as conn:
            for (payload,) in conn.execute("SELECT payload FROM acquired"):
                references.add(json.loads(payload).get("cover_sha"))
            expired = []
            for name, payload in conn.execute(
                "SELECT name,payload FROM documents WHERE name LIKE 'missing-artwork:%' OR name LIKE 'catalogue:%'"
            ):
                value = json.loads(payload)
                expiry = (
                    value.get("retry_after")
                    if name.startswith("missing-artwork:")
                    else value.get("time", now) + 86400
                )
                if isinstance(expiry, (int, float)) and expiry < now:
                    expired.append((name, payload))
            # Compare payload as well so a concurrently refreshed cache wins.
            conn.executemany(
                "DELETE FROM documents WHERE name=? AND payload=?", expired
            )
        return {
            "covers_removed": store.covers.prune(references, now),
            "documents_removed": len(expired),
        }
