from scripts.export_openapi import TARGET, encoded


def test_native_contract_is_current_and_core_responses_are_typed():
    assert TARGET.read_text() == encoded()
    import json

    value = json.loads(TARGET.read_text())
    for path in [
        "/api/v1/library/tracks",
        "/api/v1/library/artists",
        "/api/v1/library/albums",
        "/api/v1/library/changes",
        "/api/v1/me",
        "/api/v1/albums/{album_id}",
        "/api/v1/artists/{artist_id}",
    ]:
        assert (
            "$ref"
            in value["paths"][path]["get"]["responses"]["200"]["content"][
                "application/json"
            ]["schema"]
        )
