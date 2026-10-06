"""Display-only, bounded Fanart artist backdrops."""

import asyncio, hashlib, io, time
from urllib.parse import urlsplit
from PIL import Image, ImageOps
from .library import identifier
from .catalogue import mbid
from .media import settings
from .fanart import Fanart


class Backgrounds:
    def __init__(self, store, artwork, fanart=None):
        self.store, self.artwork = store, artwork
        self.locks = {}
        self.slots = asyncio.Semaphore(3)
        self.fanart = fanart or Fanart(store)

    async def get(self, client, artist_id):
        config = settings(self.store)
        token = config.get("fanart_key")
        if not token or not config["portraits"]:
            return None
        artist_id = mbid(artist_id)
        target = background_target(self.store, artist_id)
        key = target.stem
        if target.exists():
            return target
        async with self.locks.setdefault(key, asyncio.Lock()), self.slots:
            if target.exists():
                return target
            if self.store.read_document(key).get("retry_after", 0) > time.time():
                return None
            try:
                data = await self.fanart.get(client, artist_id, token)
                photos = sorted(
                    data.get("artistbackground", []),
                    key=lambda p: int(p.get("likes") or 0),
                    reverse=True,
                )
                if not photos:
                    self.artwork.remember_missing(key, 86400)
                    return None
                parts = urlsplit(photos[0]["url"])
                if (
                    parts.scheme != "https"
                    or parts.hostname != "assets.fanart.tv"
                    or parts.port not in (None, 443)
                    or parts.username
                    or parts.password
                ):
                    raise ValueError("Untrusted artwork")
                async with client.stream(
                    "GET", photos[0]["url"], timeout=12, follow_redirects=False
                ) as response:
                    response.raise_for_status()
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 5_000_000:
                            raise ValueError("Artwork too large")
                await asyncio.to_thread(self.save, bytes(content), target)
                return target
            except Exception:
                self.artwork.remember_missing(key, 300)
                return None

    @staticmethod
    def save(content, target):
        with Image.open(io.BytesIO(content)) as picture:
            if picture.width * picture.height > 20_000_000:
                raise ValueError("Artwork too large")
            picture = ImageOps.exif_transpose(picture).convert("RGB")
            picture.thumbnail((1600, 900))
            temporary = target.with_suffix(".tmp")
            try:
                picture.save(temporary, "JPEG", quality=86)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)


def background_target(store, artist_id):
    token = settings(store).get("fanart_key", "")
    key = identifier(
        "artist-background",
        mbid(artist_id),
        hashlib.sha256(token.encode()).hexdigest()[:12],
    )
    return store.cover_dir / (key + ".jpg")
