"""Shared, key-sensitive Fanart metadata cache for portraits and backdrops."""

import asyncio
import hashlib
import json
import time


class Fanart:
    def __init__(self, store):
        self.store = store
        self.locks = {}

    async def get(self, client, artist_id, token):
        key = (
            "fanart-metadata:"
            + artist_id
            + ":"
            + hashlib.sha256(token.encode()).hexdigest()[:12]
        )
        async with self.locks.setdefault(key, asyncio.Lock()):
            cached = self.store.read_document(key)
            if cached.get("expires", 0) > time.time():
                return cached["data"]
            response = await client.get(
                "https://webservice.fanart.tv/v3.2/music/" + artist_id,
                headers={"api-key": token},
                timeout=12,
                follow_redirects=False,
            )
            response.raise_for_status()
            if len(response.content) > 2_000_000:
                raise ValueError("Artwork metadata too large")
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Invalid artwork metadata")
            with self.store.connect() as conn:
                conn.execute(
                    "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                    (key, json.dumps({"expires": time.time() + 86400, "data": data})),
                )
            return data
