import json

from test_request_groups import member_store, song


def test_match_index_is_built_once_per_projection_revision(tmp_path, monkeypatch):
    import server.matching as matching

    tracks = [
        {**song("Foreword", 1), "id": "t1", "path": "/private/a.mp3", "available": True}
    ]
    (tmp_path / "library-snapshot.json").write_text(json.dumps({"tracks": tracks}))
    store, member = member_store(tmp_path)
    built = []
    real = matching.LibraryIndex

    class Counting(real):
        def __init__(self, library):
            built.append(1)
            super().__init__(library)

    monkeypatch.setattr(matching, "LibraryIndex", Counting)
    users = store.user_libraries
    first = users.match_index(member)
    assert users.match_index(member) is first and len(built) == 1
    users.add(member, ["t1"])
    assert users.match_index(member) is not first and len(built) == 2
