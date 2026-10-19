import json

from fastapi.testclient import TestClient

from server.app import create_app
from server.auth import Auth
from server.store import Store


def song(title, number, album="Meteora", duration=200):
    return {
        "artist": "Linkin Park",
        "album_artist": "Linkin Park",
        "album": album,
        "title": title,
        "year": 2003,
        "duration": duration,
        "disc_number": 1,
        "track_number": number,
        "status": "missing",
        "musicbrainz_release_id": "33333333-3333-4333-8333-333333333333",
    }


def test_downloads_group_by_request_and_collapse_repeats(tmp_path, monkeypatch):
    monkeypatch.delenv("PIG_MUSIC_TEST_LEGACY_API", raising=False)
    store = Store(tmp_path)
    auth = Auth(store)
    owner = auth.create_owner("mark", "groups fixture password")
    code = auth.setup_code(owner, "member", "Member")
    member = auth.activate(code["code"], "groups fixture password", "f")["id"]
    token = auth.login(
        "member", "groups fixture password", "device", "phone", "ios", "f"
    )["token"]
    app = create_app(tmp_path)
    with TestClient(
        app,
        base_url="https://private.ts.net",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        live = app.state.store
        live.save_download_settings({"enabled": True, "sources": ["freemp3cloud"]})
        live.submit_catalogue(
            [song("Foreword", 1), song("Don't Stay", 2), song("Somewhere", 3)],
            user_id=member,
        )
        # The same song asked for again (slightly different tags): one row.
        live.submit_catalogue([song("Foreword", 1, duration=201)], user_id=member)
        live.submit_catalogue(
            [{**song("Numb", 1, album=""), "album_artist": ""}], user_id=member
        )
        with live.connect() as conn:
            rows = conn.execute("SELECT id,payload FROM queue").fetchall()
            for key, raw in rows:
                payload = json.loads(raw)
                if payload["title"] == "Don't Stay":
                    payload.update(source="soulseek", codec="flac")
                    conn.execute(
                        "UPDATE queue SET status='completed',payload=? WHERE id=?",
                        (json.dumps(payload), key),
                    )
                if payload["title"] == "Foreword" and payload["duration"] == 200:
                    conn.execute(
                        "UPDATE queue SET status='failed',payload=? WHERE id=?",
                        (json.dumps({**payload, "error": "secret detail"}), key),
                    )
        assert client.get("/api/v1/requests").json()["total"] == 5
        page = client.get("/api/v1/requests/groups")
        assert page.status_code == 200, page.text
        groups = page.json()["groups"]
        assert sorted(g["kind"] for g in groups) == ["album", "song"]
        album = next(g for g in groups if g["kind"] == "album")
        single = next(g for g in groups if g["kind"] == "song")
        assert album["title"] == "Meteora" and album["artist"] == "Linkin Park"
        assert album["songs"] == 3 and album["done"] == 1 and album["failed"] == 0
        assert album["state"] == "waiting"
        assert album["release_id"]
        assert 0 < album["progress"] < 1
        foreword = [i for i in album["items"] if i["title"] == "Foreword"]
        assert len(foreword) == 1 and foreword[0]["status"] == "waiting_for_sources"
        done = next(i for i in album["items"] if i["title"] == "Don't Stay")
        assert done["source"] == "soulseek" and done["quality"] == "FLAC"
        assert single["title"] == "Numb" and single["songs"] == 1
        assert "secret detail" not in page.text and "/private" not in page.text
        assert client.get("/api/v1/requests/groups?limit=1").json()["next_offset"] == 1
