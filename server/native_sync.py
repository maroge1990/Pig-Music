"""Durable final-state deltas and user/revision-bound pagination.

A checkpoint is materialised at a sync read, not on every individual mutation.
It records the diff since that user's previous observed state, allowing offline
clients to converge without storing a full snapshot for each edit.
"""

import base64
import json
import time
import uuid
from .api_models import ArtistDTO, AlbumDTO, TrackDTO, PlaylistDTO
from .user_library import stored_cover_sha

MODELS = {
    "artists": ArtistDTO,
    "albums": AlbumDTO,
    "tracks": TrackDTO,
    "playlists": PlaylistDTO,
}


class ResyncRequired(ValueError):
    pass


class NativeSync:
    def __init__(self, store):
        self.store = store

    def dto(self, kind, raw):
        if kind == "tracks":
            from .user_library import track_dto

            album_id = self.store.index.album_by_track.get(raw["id"])
            album = self.store.albums_by_id.get(album_id, {})
            raw = {
                **track_dto(raw),
                "album_id": album_id,
                "cover_url": album.get("cover_url"),
                "cover_sha": stored_cover_sha(album),
            }
        elif kind == "albums":
            raw = {**raw, "cover_sha": stored_cover_sha(raw)}
        return MODELS[kind].model_validate(raw).model_dump(mode="json")

    def capture(self, user_id):
        with self.store.lifecycle_lock, self.store.library_lock:
            projection = self.store.user_libraries.projection(user_id)
            signature = projection["revision"]
            revision = uuid.uuid4().hex
            with self.store.connect() as conn:
                previous = conn.execute(
                    "SELECT revision,signature,captured_at FROM sync_revisions WHERE user_id=? ORDER BY sequence DESC LIMIT 1",
                    (user_id,),
                ).fetchone()
                if (
                    previous
                    and previous[1] == signature
                    and previous[2] >= int(time.time()) - 30 * 86400
                ):
                    return {**projection, "revision": previous[0]}
                from .playlists import Playlists
                from .routes.personal import playlist_dto

                playlists = Playlists(self.store, user_id)
                projection = {
                    **projection,
                    "playlists": [
                        playlist_dto(playlists.detail(p["id"]))
                        for p in playlists.list()
                    ],
                }
                conn.execute("BEGIN IMMEDIATE")
                upserts = {kind: [] for kind in MODELS}
                deletes = {kind: [] for kind in MODELS}
                for kind, model in MODELS.items():
                    before = dict(
                        conn.execute(
                            "SELECT entity_id,payload FROM sync_entities WHERE user_id=? AND entity=?",
                            (user_id, kind),
                        )
                    )
                    for raw in projection[kind]:
                        item = self.dto(kind, raw)
                        payload = json.dumps(
                            item, sort_keys=True, separators=(",", ":")
                        )
                        if before.pop(item["id"], None) != payload:
                            upserts[kind].append(item)
                            conn.execute(
                                "INSERT INTO sync_entities VALUES (?,?,?,?) ON CONFLICT(user_id,entity,entity_id) DO UPDATE SET payload=excluded.payload",
                                (user_id, kind, item["id"], payload),
                            )
                    deletes[kind] = list(before)
                    conn.executemany(
                        "DELETE FROM sync_entities WHERE user_id=? AND entity=? AND entity_id=?",
                        [(user_id, kind, key) for key in before],
                    )
                conn.execute(
                    "INSERT INTO sync_revisions(user_id,revision,signature,captured_at,payload) VALUES (?,?,?,?,?)",
                    (
                        user_id,
                        revision,
                        signature,
                        int(time.time()),
                        json.dumps({"upserts": upserts, "deletes": deletes}),
                    ),
                )
                conn.execute(
                    "DELETE FROM sync_revisions WHERE captured_at<?",
                    (int(time.time()) - 30 * 86400,),
                )
            return {**projection, "revision": revision}

    def page(self, user_id, kind, cursor=None, limit=200):
        if not 1 <= limit <= 200:
            raise ValueError("Page limit must be between 1 and 200")
        data = self.capture(user_id)
        offset = 0
        if cursor:
            try:
                encoded = json.loads(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
                identity, collection, revision, offset = encoded
                if (
                    identity != user_id
                    or collection != kind
                    or revision != data["revision"]
                ):
                    raise ResyncRequired("Pagination changed. Restart this collection.")
                if not isinstance(offset, int) or offset < 0:
                    raise ValueError()
            except ResyncRequired:
                raise
            except (ValueError, TypeError):
                raise ValueError("Invalid cursor")
        values = data[kind]
        following = offset + limit
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps([user_id, kind, data["revision"], following]).encode()
            )
            .decode()
            .rstrip("=")
            if following < len(values)
            else None
        )
        return {
            "items": [self.dto(kind, v) for v in values[offset:following]],
            "total": len(values),
            "revision": data["revision"],
            "next_cursor": next_cursor,
        }

    def changes(self, user_id, since):
        current = self.capture(user_id)
        with self.store.connect() as conn:
            start = conn.execute(
                "SELECT sequence FROM sync_revisions WHERE user_id=? AND revision=? AND captured_at>=?",
                (user_id, since, int(time.time()) - 30 * 86400),
            ).fetchone()
            if not start:
                raise ResyncRequired(
                    "Sync history expired. Download the library again."
                )
            upserts, deletes = {k: {} for k in MODELS}, {k: set() for k in MODELS}
            for (raw,) in conn.execute(
                "SELECT payload FROM sync_revisions WHERE user_id=? AND sequence>? ORDER BY sequence",
                (user_id, start[0]),
            ):
                batch = json.loads(raw)
                for kind in MODELS:
                    for value in batch["upserts"][kind]:
                        upserts[kind][value["id"]] = value
                        deletes[kind].discard(value["id"])
                    for key in batch["deletes"][kind]:
                        upserts[kind].pop(key, None)
                        deletes[kind].add(key)
            return {
                "revision": current["revision"],
                "upserts": {k: list(v.values()) for k, v in upserts.items()},
                "deletes": {k: sorted(v) for k, v in deletes.items()},
            }
