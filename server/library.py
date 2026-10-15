"""Release-aware read-only library model and Apple export comparison."""

import hashlib
import io
import json
import plistlib
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

VARIOUS = {"various artists", "various", "va", "v a"}


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(re.findall(r"\w+", text))


def identifier(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()[:24]


def is_compilation(album_artist: str, tracks: list[dict]) -> bool:
    """A single artist's greatest hits must never hide that artist."""
    performers = {normalise(t["artist"]) for t in tracks}
    if normalise(album_artist) in VARIOUS:
        return True
    return len(performers) > 1 and any(t.get("compilation") for t in tracks)


SOUNDTRACK_TITLE = re.compile(
    r"\b(soundtracks?|ost|original score|film score|music from|motion picture"
    r"|video game|game music|original music|inspired by)\b"
)
# "Transformers: The Album" or "(The Score)" are tie-ins; "The Score" alone is not.
TIE_IN = re.compile(r"(?:[:(\[]|\s[-–]\s)\s*(?:the |original )?(?:score|album)\b")
SOUNDTRACK_GENRE = re.compile(
    r"\b(soundtracks?|score|video game|game music|vgm|anime)\b"
)
MUSICAL_TEXT = re.compile(
    r"\b(broadway|west end|cast recording|original cast|london cast|cast album"
    r"|musical theatre|musical theater)\b"
)
MUSICAL_TITLE = re.compile(r"\b(the|an?(?: \w+)?) musical\b")
MUSICAL_GENRE = re.compile(r"\b(musicals?|show tunes|cast recordings?)\b")
KNOWN_MUSICALS = {
    "hamilton",
    "hamilton an american musical",
    "the book of mormon",
    "book of mormon",
}


def classify(album: str, album_artist: str, genres: list[str], compilation: bool):
    """Automatic category; an owner's explicit choice always wins over this."""
    title = normalise(album)
    genre = normalise(" ".join(dict.fromkeys(genres)))
    if (
        MUSICAL_TEXT.search(title + " " + normalise(album_artist) + " " + genre)
        or MUSICAL_TITLE.search(title)
        or MUSICAL_GENRE.search(genre)
        or title in KNOWN_MUSICALS
    ):
        return "musical"
    if (
        SOUNDTRACK_TITLE.search(title)
        or TIE_IN.search((album or "").casefold())
        or SOUNDTRACK_GENRE.search(genre)
        or re.search(r"\bsound team\b", normalise(album_artist))
    ):
        return "soundtrack"
    return "compilation" if compilation else "album"


def build_library(
    snapshot: dict, categories: dict | None = None, anchors: dict | None = None
) -> dict:
    groups = defaultdict(list)
    anchors = anchors if anchors is not None else {}
    for raw in snapshot.get("tracks", []):
        track = dict(raw)
        track.setdefault("album_artist", track.get("artist", "Unknown artist"))
        track.setdefault("album", "Singles")
        track.setdefault("year", 0)
        track.setdefault("track_number", 0)
        track.setdefault("disc_number", 1)
        track.setdefault("duration", 0)
        track.setdefault("codec", "unknown")
        groups[(normalise(track["album_artist"]), normalise(track["album"]))].append(
            track
        )
    # Keep the original album ID for its first known edition. Persisted anchors
    # prevent a newly encountered edition from changing links or preferences.
    edition_groups = {}
    for key, tracks in groups.items():
        legacy_id = identifier("album", *key)
        releases = list(
            dict.fromkeys(
                t.get("musicbrainz_release_id")
                for t in tracks
                if t.get("musicbrainz_release_id")
            )
        )
        if releases and legacy_id not in anchors:
            anchors[legacy_id] = releases[0]
        anchor = anchors.get(legacy_id)
        for track in tracks:
            release = track.get("musicbrainz_release_id")
            # Unknown tags can join a sole known edition, but never choose among
            # multiple editions. Their own group remains reviewable.
            edition = release or (releases[0] if len(releases) == 1 else None)
            album_id = (
                legacy_id
                if not anchor or edition == anchor
                else identifier("album-edition", legacy_id, edition or "unknown")
            )
            edition_groups.setdefault((key, album_id), []).append(track)
    albums = []
    artist_names = {}
    artist_albums = defaultdict(list)
    artist_tracks = defaultdict(list)
    for (key, album_id), tracks in edition_groups.items():
        tracks.sort(key=lambda t: (t["disc_number"], t["track_number"], t["title"]))
        first = tracks[0]
        compilation = is_compilation(first["album_artist"], tracks)
        auto = classify(
            first["album"],
            first["album_artist"],
            [t.get("genre", "") for t in tracks],
            compilation,
        )
        category = (categories or {}).get(album_id) or auto
        compilation = category == "compilation"
        album = {
            "id": album_id,
            "title": first["album"],
            "artist": first["album_artist"],
            "artist_id": identifier("artist", key[0]),
            "year": next((t["year"] for t in tracks if t["year"]), 0),
            "compilation": compilation,
            "track_count": len(tracks),
            "category": category,
            "musicbrainz_release_id": next(
                (
                    t.get("musicbrainz_release_id")
                    for t in tracks
                    if t.get("musicbrainz_release_id")
                ),
                None,
            ),
            "tracks": tracks,
            "codecs": sorted({t["codec"].upper() for t in tracks}),
            "cover_key": first["album_artist"] + "\x1f" + first["album"],
            "cover_sha": next(
                (t.get("cover_sha") for t in tracks if t.get("cover_sha")), None
            ),
            "duration": sum(t["duration"] for t in tracks),
        }
        albums.append(album)
        if category == "album":
            artist_names[album["artist_id"]] = album["artist"]
            artist_albums[album["artist_id"]].append(album_id)
        for t in tracks:
            performer_id = identifier("artist", normalise(t["artist"]))
            artist_names.setdefault(performer_id, t["artist"])
            artist_tracks[performer_id].append(
                {**t, "album_id": album_id, "compilation": compilation}
            )
    artists = []
    for artist_id, name in artist_names.items():
        own_albums = artist_albums.get(artist_id, [])
        credited = artist_tracks.get(artist_id, [])
        representative = next((a for a in albums if a["id"] in own_albums), None)
        if representative is None and credited:
            representative = next(
                a for a in albums if a["id"] == credited[0]["album_id"]
            )
        associated_tracks = {t["id"] for t in credited}
        associated_tracks.update(
            t["id"] for a in albums if a["id"] in own_albums for t in a["tracks"]
        )
        artists.append(
            {
                "id": artist_id,
                "name": name,
                "album_ids": own_albums,
                "album_count": len(own_albums),
                "track_count": len(associated_tracks),
                "compilation_only": not bool(own_albums),
                "cover_album_id": representative["id"] if representative else None,
            }
        )
    artists.sort(key=lambda a: a["name"].casefold().removeprefix("the "))
    albums.sort(
        key=lambda a: (
            a["artist"].casefold().removeprefix("the "),
            a["year"],
            a["title"].casefold(),
        )
    )
    return {
        "artists": artists,
        "albums": albums,
        "snapshot": {
            k: snapshot.get(k) for k in ("source", "captured_at", "read_failures")
        },
        "stats": {
            "tracks": sum(a["track_count"] for a in albums),
            "artists": sum(not a["compilation_only"] for a in artists),
            "albums": sum(a["category"] == "album" for a in albums),
            "compilations": sum(a["category"] == "compilation" for a in albums),
            "soundtracks": sum(a["category"] == "soundtrack" for a in albums),
            "musicals": sum(a["category"] == "musical" for a in albums),
        },
    }


def parse_apple(raw: bytes) -> dict:
    if len(raw) > 20_000_000:
        raise ValueError("The export is too large (maximum 20 MB).")
    try:
        data = plistlib.load(io.BytesIO(raw))
    except Exception as exc:
        raise ValueError(
            "Choose a valid Apple Music XML library or playlist export."
        ) from exc
    if not isinstance(data, dict) or not isinstance(data.get("Tracks"), dict):
        raise ValueError("This file does not contain an Apple Music track inventory.")
    result, ignored = [], 0
    for key, track in data["Tracks"].items():
        if (
            not isinstance(track, dict)
            or not track.get("Name")
            or track.get("Video")
            or track.get("Movie")
        ):
            ignored += 1
            continue
        result.append(
            {
                "id": identifier(
                    "apple",
                    data.get("Library Persistent ID", ""),
                    track.get("Persistent ID", key),
                ),
                "source_track_id": str(key),
                "title": str(track["Name"]),
                "artist": str(track.get("Artist") or "Unknown artist"),
                "album_artist": str(
                    track.get("Album Artist") or track.get("Artist") or "Unknown artist"
                ),
                "album": str(track.get("Album") or "Unknown release"),
                "compilation": bool(track.get("Compilation", False)),
                "year": int(track.get("Year") or 0),
                "track_number": int(track.get("Track Number") or 0),
                "disc_number": int(track.get("Disc Number") or 1),
                "duration": int(track.get("Total Time") or 0) / 1000,
                "favourited": bool(track.get("Favorited") or track.get("Loved")),
                "play_count": int(track.get("Play Count") or 0),
            }
        )
    if not result:
        raise ValueError("This export contains no music tracks to review.")
    by_source = {t["source_track_id"]: t["id"] for t in result}
    for key, raw_track in data["Tracks"].items():
        if (
            str(key) in by_source
            and isinstance(raw_track, dict)
            and raw_track.get("Track ID") is not None
        ):
            by_source[str(raw_track["Track ID"])] = by_source[str(key)]
    playlists = []
    for item in data.get("Playlists", []):
        if (
            not isinstance(item, dict)
            or not item.get("Name")
            or item.get("Master")
            or item.get("Folder")
        ):
            continue
        members = [
            by_source[str(entry["Track ID"])]
            for entry in item.get("Playlist Items", [])
            if isinstance(entry, dict) and str(entry.get("Track ID")) in by_source
        ]
        playlists.append(
            {
                "id": identifier(
                    "apple-playlist",
                    data.get("Library Persistent ID", ""),
                    item.get("Playlist Persistent ID") or item["Name"],
                ),
                "name": str(item["Name"]),
                "track_ids": members,
            }
        )
    return {
        "tracks": result,
        "playlists": playlists,
        "source_name": ", ".join(p["name"] for p in playlists[:3])
        or "Apple Music library",
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "ignored_records": ignored,
    }


def build_migration(
    source: dict, library: dict, selected: set[str], index=None
) -> dict:
    from .matching import LibraryIndex

    index = index or LibraryIndex(library)
    groups = defaultdict(list)
    for raw in source.get("tracks", []):
        track = dict(raw)
        match = index.match(track)
        track["status"] = match.status
        track["saved_id"] = match.track["id"] if match.track else None
        track["match_kind"] = match.kind
        track["reason"] = (
            "Artist, track and release match a saved file."
            if match.track
            else (
                "A saved song has this name, but its edition, context or duration needs review."
                if match.kind == "conflict"
                else "No matching track was found in the library snapshot."
            )
        )
        track["selected"] = track["id"] in selected and track["status"] != "downloaded"
        groups[(normalise(track["album_artist"]), normalise(track["album"]))].append(
            track
        )
    albums = []
    for key, tracks in groups.items():
        tracks.sort(key=lambda t: (t["disc_number"], t["track_number"], t["title"]))
        first = tracks[0]
        albums.append(
            {
                "id": identifier("migration-album", *key),
                "title": first["album"],
                "artist": first["album_artist"],
                "year": first["year"],
                "compilation": is_compilation(first["album_artist"], tracks),
                "tracks": tracks,
                "track_count": len(tracks),
                "saved_count": sum(t["status"] == "downloaded" for t in tracks),
                "selected_count": sum(t["selected"] for t in tracks),
                "library_album_id": next(
                    (
                        a["id"]
                        for a in library["albums"]
                        if normalise(a["artist"]) == key[0]
                        and normalise(a["title"]) == key[1]
                    ),
                    None,
                ),
            }
        )
    albums.sort(
        key=lambda a: (
            a["compilation"],
            a["artist"].casefold(),
            a["year"],
            a["title"].casefold(),
        )
    )
    all_tracks = [t for a in albums for t in a["tracks"]]
    return {
        "source_name": source.get("source_name", "No export imported"),
        "imported_at": source.get("imported_at"),
        "albums": albums,
        "stats": {
            "tracks": len(all_tracks),
            "saved": sum(t["status"] == "downloaded" for t in all_tracks),
            "missing": sum(t["status"] == "missing" for t in all_tracks),
            "review": sum(t["status"] == "review" for t in all_tracks),
            "selected": sum(t["selected"] for t in all_tracks),
        },
    }


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))
