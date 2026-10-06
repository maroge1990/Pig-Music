from server.organisation import Organisation
from server.recovery import Recovery
from test_recovery import setup


def test_review_has_no_mutations_and_applied_rename_can_be_undone(
    tmp_path, monkeypatch
):
    store, root, path, track = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "server.organisation.inspect_file",
        lambda p, r: (
            {
                **track,
                "relative_path": r,
                "size_bytes": p.stat().st_size,
                "mtime_ns": p.stat().st_mtime_ns,
            },
            None,
        ),
    )
    manager = Organisation(store, Recovery(store))
    plan = manager.plan()
    assert path.exists() and plan["items"][0]["rename"]
    result = manager.apply(["saved"])
    assert result["applied"] == 1 and not path.exists()
    manager.undo(result["operations"][0])
    assert path.read_bytes() == b"original music"


import json, shutil, subprocess
import pytest
from server.scanner import inspect_file
from server.store import Store


@pytest.mark.parametrize("tags", [False, True])
def test_real_audio_organisation_and_undo_preserve_original(
    tmp_path, monkeypatch, tags
):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg required for real audio integration")
    root = tmp_path / "music"
    root.mkdir()
    monkeypatch.setenv("PIG_MUSIC_LIBRARY", str(root))
    path = root / "old.mp3"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=3",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "320k",
            "-metadata",
            "artist=Artist",
            "-metadata",
            "album=Album",
            "-metadata",
            "title=Song",
            str(path),
        ],
        check=True,
        timeout=20,
    )
    original = path.read_bytes()
    track, _ = inspect_file(path, "old.mp3")
    data = tmp_path / "data"
    data.mkdir()
    (data / "library-snapshot.json").write_text(json.dumps({"tracks": [track]}))
    store = Store(data)
    manager = Organisation(store, Recovery(store))
    result = manager.apply([track["id"]], tags)
    assert result["applied"] == 1 and not path.exists()
    target = root / manager.history()[0]["destination"]
    checked, _ = inspect_file(target, target.name)
    assert (
        checked["title"] == "Song"
        and checked["codec"] == "mp3"
        and checked["bitrate"] >= 319
    )
    manager.undo(result["operations"][0])
    assert path.read_bytes() == original and not target.exists()
