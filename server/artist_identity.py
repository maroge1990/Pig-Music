"""One resolver maps a library artist to its MusicBrainz artist, or asks for a choice."""

from .artwork import quoted
from .catalogue import mbid
from .library import normalise


class Ambiguous(Exception):
    """No single catalogue artist fits; candidates lists the exact-name matches."""

    def __init__(self, candidates=()):
        super().__init__("Ambiguous artist identity")
        self.candidates = list(candidates)


def cached_identity(store, artist):
    known = store.read_document("library-artist:" + artist["id"])
    if known and normalise(known.get("name", "")) == normalise(artist["name"]):
        try:
            return {"id": mbid(known["id"]), "name": artist["name"]}
        except (ValueError, TypeError, KeyError, AttributeError):
            return None
    return None


async def resolve_artist(store, catalogue, client, artist, albums):
    """Return {"id","name"} for a library artist; raise Ambiguous when unsure.

    Provider failures (httpx errors) propagate to the caller.
    """
    known = cached_identity(store, artist)
    if known:
        return known
    wanted = normalise(artist["name"])
    identities = {}

    def credits(items):
        for item in items:
            candidate = item.get("artist", {})
            if candidate.get("id") and normalise(candidate.get("name", "")) == wanted:
                identities[candidate["id"]] = {
                    "id": candidate["id"],
                    "name": candidate["name"],
                }

    # Release credits distinguish namesakes without guessing from popularity.
    release_ids = list(
        dict.fromkeys(
            a.get("musicbrainz_release_id")
            for a in albums
            if a.get("musicbrainz_release_id")
        )
    )
    for release_id in release_ids[:3]:
        try:
            release_id = mbid(release_id)
        except (ValueError, TypeError):
            continue
        release = await catalogue.get(
            client, "release/" + release_id, inc="artist-credits"
        )
        credits(release.get("artist-credit", []))
    matches = []
    if not identities:
        result = await catalogue.get(
            client, "artist/", query="artist:" + quoted(artist["name"]), limit=100
        )
        matches = [
            a for a in result.get("artists", []) if normalise(a["name"]) == wanted
        ]
        if len(matches) == 1 and result.get("count", len(matches)) <= 100:
            identities[matches[0]["id"]] = {
                "id": matches[0]["id"],
                "name": matches[0]["name"],
            }
        elif len(matches) > 1:
            candidates = {a["id"] for a in matches}
            for album in albums[:3]:
                found = await catalogue.get(
                    client,
                    "release-group/",
                    query="releasegroup:"
                    + quoted(album["title"])
                    + " AND artist:"
                    + quoted(artist["name"]),
                    limit=100,
                )
                if found.get("count", 0) > 100:
                    continue
                for group in found.get("release-groups", []):
                    if normalise(group.get("title", "")) == normalise(album["title"]):
                        credits(
                            [
                                c
                                for c in group.get("artist-credit", [])
                                if c.get("artist", {}).get("id") in candidates
                            ]
                        )
    if len(identities) != 1:
        options = matches or list(identities.values())
        raise Ambiguous(
            {
                "id": a["id"],
                "name": a["name"],
                "disambiguation": a.get("disambiguation", ""),
            }
            for a in options
        )
    identity = next(iter(identities.values()))
    store.write_document("library-artist:" + artist["id"], identity)
    return identity
