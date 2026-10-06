import json
from server.store import Store
from server.playlists import Playlists


def song(title="Song", album="Album"):
    return {
        "id": "one",
        "title": title,
        "artist": "Artist",
        "album_artist": "Artist",
        "album": album,
        "duration": 100,
    }


def test_created_playlist_survives_restart_and_add_is_idempotent(tmp_path):
    p = Playlists(Store(tmp_path))
    identity = p.create("Household")["id"]
    p.add(identity, song())
    p.add(identity, song())
    assert len(Playlists(Store(tmp_path)).raw(identity)["tracks"]) == 1
    assert not p.store.queue()["items"]


def test_favourites_do_not_download_and_preserve_release_context(tmp_path):
    p = Playlists(Store(tmp_path))
    p.favourite(song(), True)
    p.favourite(song(album="Live recording"), True)
    assert p.favourite(song())["favourited"]
    assert len(p.raw("pig-favourites")["tracks"]) == 2 and not p.store.queue()["items"]
    p.favourite(song(), False)
    assert (
        not p.favourite(song())["favourited"]
        and p.favourite(song(album="Live recording"))["favourited"]
    )


def test_tag_only_song_and_discovered_song_share_membership_without_merging_editions(
    tmp_path,
):
    p = Playlists(Store(tmp_path))
    identity = p.create("Listening")["id"]
    tagged = song()
    discovered = {
        **tagged,
        "musicbrainz_release_id": "edition-one",
        "musicbrainz_recording_id": "recording-one",
    }
    p.add(identity, tagged)
    p.add(identity, discovered)
    assert len(p.raw(identity)["tracks"]) == 1
    p.favourite(discovered, True)
    assert p.favourite(tagged)["favourited"]
    assert not p.favourite({**discovered, "musicbrainz_release_id": "edition-two"})[
        "favourited"
    ]
    p.favourite(tagged, False)
    assert not p.raw("pig-favourites")["tracks"]
