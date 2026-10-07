import io
import json
import os
import time

from fastapi.testclient import TestClient

from server.app import create_app
from server.cover_store import CoverStore, WEEK
from PIL import Image


def image_bytes(colour="red"):
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), colour).save(stream, "PNG")
    return stream.getvalue()


def test_metadata_is_deterministic_hash_scoped_and_survives_restart(tmp_path):
    covers = CoverStore(tmp_path)
    sha = covers.save(image_bytes("red"))
    value = covers.presentation(sha)
    assert value["sha"] == sha and value["version"] == 1
    assert value["width"] == value["height"] == 64
    assert int(value["dominant_colour"][1:3], 16) > 240
    assert int(value["dominant_colour"][3:5], 16) < 10
    assert CoverStore(tmp_path).metadata(sha) == value
    assert covers.metadata("../secret") is None
    other = covers.save(image_bytes("blue"))
    assert covers.presentation(other)["dominant_colour"] != value["dominant_colour"]
    metadata = tmp_path / "metadata" / (sha + "-v1.json")
    metadata.write_text('{"version":99}')
    fresh = CoverStore(tmp_path)
    assert fresh.presentation(sha) is None
    assert fresh.metadata(sha) == value
    now = time.time()
    os.utime(covers.path(sha), (now - WEEK - 1, now - WEEK - 1))
    os.utime(metadata, (now - WEEK - 1, now - WEEK - 1))
    covers.prune({other}, now)
    assert not metadata.exists() and covers.presentation(sha) is None
    assert covers.presentation(other)


def test_metadata_projection_endpoint_and_conditional_cache(tmp_path):
    app = create_app(tmp_path)
    store = app.state.store
    sha = store.covers.save(image_bytes())
    (tmp_path / "library-snapshot.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "tracks": [
                    {
                        "id": "song",
                        "title": "Song",
                        "artist": "Artist",
                        "album": "Album",
                        "cover_sha": sha,
                    }
                ],
            }
        )
    )
    store.refresh_library()
    assert store.summary()["albums"][0]["artwork_metadata"]["sha"] == sha
    with TestClient(app) as client:
        result = client.get("/api/artwork/" + sha + ".jpg/metadata")
        assert result.status_code == 200
        assert result.json() == store.covers.presentation(sha)
        assert "immutable" in result.headers["cache-control"]
        assert (
            client.get(
                "/api/artwork/" + sha + ".jpg/metadata",
                headers={"If-None-Match": result.headers["etag"]},
            ).status_code
            == 304
        )
        assert (
            client.get("/api/artwork/" + "0" * 64 + ".jpg/metadata").status_code == 404
        )
