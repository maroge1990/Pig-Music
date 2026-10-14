"""Configured transfer storage; appdata remains the default for previews/tests."""

import hashlib
import os
from pathlib import Path


def require_library_mount(
    directory, root, marker_path=".pig-music-library.json", required=False
):
    from .library import load_json

    config = load_json(Path(directory) / "library-export.json")
    if required or config.get("library_id"):
        marker = load_json(Path(root) / marker_path)
        if (
            not config.get("library_id")
            or marker.get("library_id") != config["library_id"]
        ):
            raise ValueError("The expected SMB library mount is unavailable.")


def download_root(store):
    value = os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT")
    if value:
        root = Path(os.environ.get("PIG_MUSIC_LIBRARY", "/library"))
        require_library_mount(store.directory, root, required=True)
    return Path(value or store.directory / "downloads")


def library_root(store):
    return download_root(store) / "library"


def file_sha256(path):
    """Hash a file in chunks, so large lossless files never load whole into memory."""
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
