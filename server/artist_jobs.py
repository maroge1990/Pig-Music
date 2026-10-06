"""Durable artist acquisition with generation-guarded cancellation/progress."""

import asyncio
import json
import threading
import time
import uuid

from .catalogue import (
    Catalogue,
    edition_rank,
    release_tracks,
    mbid,
    background_metadata,
)
from .releases import release_query


class ArtistJobs:
    def __init__(self, store, catalogue):
        self.store, self.catalogue = store, catalogue
        self.stopping = asyncio.Event()
        self.lock = threading.RLock()

    def save(self, key, value):
        with self.lock, self.store.connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (key, json.dumps(value)),
            )

    def state(self, identity):
        return self.store.read_document("artist-job:" + mbid(identity)) or {
            "status": "idle",
            "monitor": False,
            "kinds": ["album"],
        }

    def configure(self, identity, kinds, monitor, request=False):
        identity = mbid(identity)
        if not kinds or not set(kinds) <= {"album", "single", "ep"}:
            raise ValueError("Choose albums, singles or EPs.")
        with self.lock:
            state = self.state(identity)
            if state.get("status") in {"queued", "running"} and request:
                raise ValueError("This artist already has a request running.")
            state.update(id=identity, kinds=kinds, monitor=monitor)
            if request:
                state.update(
                    status="queued",
                    done=[],
                    created=0,
                    error=None,
                    generation=uuid.uuid4().hex,
                )
            self.save("artist-job:" + identity, state)
            return state

    def cancel(self, identity):
        with self.lock:
            state = self.state(identity)
            state.update(status="cancelled", monitor=False, generation=uuid.uuid4().hex)
            self.save("artist-job:" + identity, state)
            return state

    def current(self, identity, generation):
        state = self.state(identity)
        return (
            state
            if state.get("status") in {"queued", "running"}
            and state.get("generation") == generation
            else None
        )

    def progress(self, identity, generation, **changes):
        with self.lock:
            state = self.current(identity, generation)
            if state is None:
                return None
            state.update(changes)
            self.save("artist-job:" + identity, state)
            return state

    async def acquire(self, client, identity, state):
        with self.lock:
            current = self.state(identity)
            if current.get("status") not in {"queued", "running"}:
                return
            generation = current.get("generation") or uuid.uuid4().hex
            current.update(generation=generation, status="running", error=None)
            self.save("artist-job:" + identity, current)
            state["generation"] = generation
            state = current
        groups = []
        for kind in state["kinds"]:
            offset = 0
            while not self.stopping.is_set() and self.current(identity, generation):
                data = await self.catalogue.get(
                    client,
                    "release-group/",
                    query=release_query(identity, kind),
                    limit=100,
                    offset=offset,
                )
                rows = data.get("release-groups", [])
                groups.extend(rows)
                offset += len(rows)
                if not rows or offset >= data.get("count", 0):
                    break
        if not self.progress(identity, generation, total=len(groups)):
            return
        for group in groups:
            current = self.current(identity, generation)
            if self.stopping.is_set() or current is None:
                return
            if group["id"] in current.get("done", []):
                continue
            editions = await self.catalogue.get(
                client,
                "release/",
                **{"release-group": group["id"], "inc": "media", "limit": 100},
            )
            ranked = sorted(editions.get("releases", []), key=edition_rank)
            tracks = []
            if ranked:
                release = await self.catalogue.get(
                    client,
                    "release/" + ranked[0]["id"],
                    inc="recordings+artist-credits+isrcs",
                )
                tracks = Catalogue(self.store).presence(release_tracks(release))
            # No await between generation validation and queue submission.
            with self.lock:
                current = self.current(identity, generation)
                if current is None:
                    return
                result = self.store.submit_catalogue(tracks)
                self.progress(
                    identity,
                    generation,
                    created=current.get("created", 0) + result["created"],
                    done=[*current.get("done", []), group["id"]],
                )
        self.progress(identity, generation, status="completed", checked_at=time.time())

    async def run(self, client):
        background_metadata.set(True)
        while not self.stopping.is_set():
            with self.store.connect() as conn:
                rows = [
                    (key, json.loads(value))
                    for key, value in conn.execute(
                        "SELECT name,payload FROM documents WHERE name LIKE 'artist-job:%'"
                    )
                ]
            for key, state in rows:
                if self.stopping.is_set():
                    return
                identity = key.split(":", 1)[1]
                if (
                    state.get("monitor")
                    and time.time() - state.get("checked_at", 0) > 86400
                    and state.get("status") not in {"queued", "running"}
                ):
                    state = self.configure(identity, state["kinds"], True, request=True)
                if state.get("status") in {"queued", "running"}:
                    try:
                        await self.acquire(client, identity, state)
                    except Exception:
                        self.progress(
                            identity,
                            state.get("generation"),
                            status="failed",
                            error="Artist lookup unavailable. Retry this request.",
                            checked_at=time.time(),
                        )
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=15)
            except TimeoutError:
                pass
