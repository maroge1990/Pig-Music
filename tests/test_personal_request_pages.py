import json
from test_native_sync import fixture


def test_request_pages_filter_in_sql_and_redact_failure_details(tmp_path):
    store, owner, member = fixture(tmp_path)
    with store.connect() as conn:
        for i in range(205):
            payload = {
                "id": str(i),
                "title": f"Request {i}",
                "artist": "Artist",
                "album": "Album",
                "requested_by": [member],
                "received_bytes": 50,
                "total_bytes": 100,
                "error": "/nas/private/token=secret",
            }
            conn.execute(
                "INSERT INTO queue(id,payload,status) VALUES (?,?,'failed')",
                (str(i), json.dumps(payload)),
            )
        conn.execute(
            "INSERT INTO queue(id,payload,status) VALUES ('private',?,'downloading')",
            (json.dumps({"title": "Other private request", "requested_by": [owner]}),),
        )
    first = store.user_libraries.queue(member)
    assert (
        first["total"] == 205
        and len(first["items"]) == 200
        and first["next_offset"] == 200
    )
    assert "Other private request" not in json.dumps(first)
    assert "/nas/" not in json.dumps(first) and "token=secret" not in json.dumps(first)
    assert len(store.user_libraries.queue(member, 200)["items"]) == 5
    assert first["items"][0]["server_state"] == "failed"
    assert store.user_libraries.queue(owner)["items"][0]["request_progress"] is None
