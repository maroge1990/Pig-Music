import json
import shutil
import subprocess

import pytest

from server.auth import Auth
from server.organisation import Organisation
from server.recovery import Recovery
from server.scanner import inspect_file
from server.store import Store
from server.tidy import Tidy, better, edition_title

STANDARD = "Hot Fuss"
DELUXE = "Hot Fuss (Deluxe Edition)"


def song(title, album, number, codec="mp3", bitrate=320, **extra):
    return {
        "id": f"{album}/{title}",
        "title": title,
        "artist": "The Killers",
        "album_artist": "The Killers",
        "album": album,
        "duration": 3,
        "year": 2004,
        "disc_number": 1,
        "track_number": number,
        "codec": codec,
        "bitrate": bitrate,
        "relative_path": f"The Killers/{album}/{number:02} {title}.mp3",
        **extra,
    }


def planned(tmp_path, tracks, monkeypatch):
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(tmp_path / "music"))
    data = tmp_path / "data"
    data.mkdir()
    (data / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    store = Store(data)
    recovery = Recovery(store)
    return Tidy(store, recovery, Organisation(store, recovery)).plan()["albums"]


def test_titles_and_quality():
    assert edition_title({"title": DELUXE, "artist": "The Killers"}) == "hot fuss"
    assert edition_title(
        {"title": "The Killers - Hot Fuss", "artist": "The Killers"}
    ) == ("hot fuss")
    # A single or EP is an album of its own.
    assert edition_title({"title": "Hot Fuss - EP", "artist": "x"}) != "hot fuss"
    flac, mp3, low = (
        {"codec": "flac", "bitrate": 900},
        {"codec": "mp3", "bitrate": 320},
        {"codec": "mp3", "bitrate": 128},
    )
    assert better(flac, mp3) and better(mp3, low)
    assert not better(mp3, flac) and not better(mp3, {"codec": "mp3", "bitrate": 300})
    # Unknown quality is never replaced on a guess, nor replaces anything.
    assert not better(flac, {"codec": "unknown"}) and not better({}, low)


def test_plan_keeps_the_fullest_edition_and_lists_what_only_others_have(
    tmp_path, monkeypatch
):
    tracks = [
        song("Jenny", STANDARD, 1),
        song("Mr. Brightside", STANDARD, 2, codec="flac", bitrate=900),
        song("Glamorous Indie Rock & Roll", STANDARD, 3),
        song("Jenny", DELUXE, 1),
        song("Mr. Brightside", DELUXE, 2),
        song("Smile Like You Mean It", DELUXE, 3),
        song("Somebody Told Me", DELUXE, 4),
        # Neither a single nor a live album is an edition.
        song("Mr. Brightside", "Hot Fuss - EP", 1),
        song("Jenny", "Live from the Royal Albert Hall", 1),
        # The same title by the same artist with other songs is another album.
        song("Buddy Holly", "Weezer", 1, artist="Weezer", album_artist="Weezer"),
        song("Island in the Sun", "Weezer", 1, artist="Weezer", album_artist="Weezer")
        | {"id": "green", "relative_path": "Weezer/Green/01.mp3"},
    ]
    (item,) = planned(tmp_path, tracks, monkeypatch)
    assert item["keep"] == {
        "album_id": item["id"],
        "title": DELUXE,
        "year": 2004,
        "songs": 4,
    }
    assert [e["title"] for e in item["editions"]] == [STANDARD]
    assert [(r["title"], r["kept"]["album"]) for r in item["remove"]] == [
        ("Jenny", DELUXE)
    ]
    # The better copy moves into the kept album, replacing its own.
    (replace,) = item["replace"]
    assert replace["id"] == f"{STANDARD}/Mr. Brightside"
    assert replace["replaces"]["id"] == f"{DELUXE}/Mr. Brightside"
    assert (replace["quality"], replace["replaces"]["quality"]) == ("FLAC", "MP3 320")
    assert [(r["title"], r["album"]) for r in item["leftovers"]] == [
        ("Glamorous Indie Rock & Roll", STANDARD)
    ]


def test_explicit_editions_are_never_tidied(tmp_path, monkeypatch):
    tracks = [song("Jenny", STANDARD, 1), song("Jenny", DELUXE, 1)]
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(tmp_path / "music"))
    data = tmp_path / "data"
    data.mkdir()
    (data / "library-snapshot.json").write_text(json.dumps({"tracks": tracks[:1]}))
    store = Store(data)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO acquired VALUES (?,?)",
            (tracks[1]["id"], json.dumps({**tracks[1], "explicit_edition": True})),
        )
    store.refresh_library()
    recovery = Recovery(store)
    assert Tidy(store, recovery, Organisation(store, recovery)).plan()["albums"] == []


def audio(path, title, album, number, codec):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg required for real audio integration")
    path.parent.mkdir(parents=True, exist_ok=True)
    encode = (
        ["-c:a", "flac"]
        if codec == "flac"
        else ["-c:a", "libmp3lame", "-b:a", codec.removeprefix("mp3_") + "k"]
    )
    subprocess.run(
        [ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=duration=3", *encode]
        + [
            arg
            for key, value in (
                ("artist", "The Killers"),
                ("album_artist", "The Killers"),
                ("album", album),
                ("title", title),
                ("track", str(number)),
            )
            for arg in ("-metadata", f"{key}={value}")
        ]
        + [str(path)],
        check=True,
        timeout=20,
    )


def library(tmp_path, monkeypatch):
    root = tmp_path / "music"
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(root))
    files = [
        (STANDARD, "Jenny", 1, "flac"),
        (STANDARD, "Mr. Brightside", 2, "mp3_320"),
        (DELUXE, "Jenny", 1, "mp3_128"),
        (DELUXE, "Mr. Brightside", 2, "mp3_320"),
        (DELUXE, "Smile Like You Mean It", 3, "mp3_320"),
    ]
    tracks = []
    for album, title, number, codec in files:
        suffix = ".flac" if codec == "flac" else ".mp3"
        relative = f"The Killers/{album}/{number:02} {title}{suffix}"
        audio(root / relative, title, album, number, codec)
        tracks.append(inspect_file(root / relative, relative)[0])
    data = tmp_path / "data"
    data.mkdir()
    (data / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    store = Store(data)
    auth = Auth(store)
    owner = auth.create_owner("mark", "tidy fixture password")
    code = auth.setup_code(owner, "member", "Member")
    member = auth.activate(code["code"], "tidy fixture password", "f")["id"]
    ids = {(t["album"], t["title"]): t["id"] for t in tracks}
    store.user_libraries.add(
        member, [ids[STANDARD, "Jenny"], ids[STANDARD, "Mr. Brightside"]]
    )
    recovery = Recovery(store)
    return Tidy(store, recovery, Organisation(store, recovery)), root, member, ids


def songs(store, user_id=None):
    if user_id:
        tracks = store.user_libraries.projection(user_id)["tracks"]
        return sorted((t["album"], t["title"]) for t in tracks)
    return sorted(
        (a["title"], t["title"], t["codec"])
        for a in store.library["albums"]
        for t in a["tracks"]
    )


def test_apply_keeps_the_best_copies_in_the_fullest_edition_and_undo_restores(
    tmp_path, monkeypatch
):
    tidy, root, member, ids = library(tmp_path, monkeypatch)
    store = tidy.store
    before = songs(store)
    (item,) = tidy.plan()["albums"]
    with pytest.raises(ValueError):
        tidy.apply(item["id"], "0" * 64)
    record = tidy.apply(item["id"], item["fingerprint"])
    assert record["status"] == "applied"
    # One album, with the FLAC Jenny moved in and retagged to it.
    assert songs(store) == [
        (DELUXE, "Jenny", "flac"),
        (DELUXE, "Mr. Brightside", "mp3"),
        (DELUXE, "Smile Like You Mean It", "mp3"),
    ]
    moved = root / "The Killers" / DELUXE / f"The Killers - {DELUXE} - 01 - Jenny.flac"
    assert inspect_file(moved, "x")[0]["album"] == DELUXE
    assert not (root / "The Killers" / STANDARD / "01 Jenny.flac").exists()
    assert not (root / "The Killers" / DELUXE / "01 Jenny.mp3").exists()
    assert not (root / "The Killers" / STANDARD / "02 Mr. Brightside.mp3").exists()
    # The member's songs are now the kept album's.
    assert songs(store, member) == [(DELUXE, "Jenny"), (DELUXE, "Mr. Brightside")]
    # Nothing was excluded: the song can still be requested and found.
    with store.connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM documents WHERE name LIKE 'excluded:%'"
        ).fetchone()
    assert tidy.plan()["albums"] == []
    (entry,) = tidy.history()
    tidy.undo(entry["id"])
    assert songs(store) == before
    assert (root / "The Killers" / STANDARD / "01 Jenny.flac").exists()
    assert (root / "The Killers" / DELUXE / "01 Jenny.mp3").exists()
    assert not moved.exists()
    assert songs(store, member) == [(STANDARD, "Jenny"), (STANDARD, "Mr. Brightside")]
    assert tidy.history() == []


def test_a_file_changed_since_the_scan_stops_the_tidy_up(tmp_path, monkeypatch):
    tidy, root, _, _ = library(tmp_path, monkeypatch)
    (item,) = tidy.plan()["albums"]
    (root / "The Killers" / STANDARD / "02 Mr. Brightside.mp3").write_bytes(b"edited")
    with pytest.raises(ValueError):
        tidy.apply(item["id"], item["fingerprint"])
    assert (root / "The Killers" / STANDARD / "01 Jenny.flac").exists()
    assert len(tidy.store.library["albums"]) == 2
