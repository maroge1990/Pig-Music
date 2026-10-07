import asyncio
import hashlib
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    Response,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from .auth import Auth
from .auth_logging import install_validation_redaction
from .routes.auth import auth_router, set_cookie
from .routes.personal import personal_router
from .security import Security, audit_routes
from .transport import public_origin
from .enrichment import Enrichment
from .change_feed import ChangeFeed
from .image_cache import public_image
from .routes.artwork import artwork_router
from .portraits import portrait_target
from .artist_backgrounds import background_target
from pydantic import BaseModel, Field

from .library import normalise, identifier
from .releases import release_query
from .fanart import Fanart
from .storage import download_root
from .store import Store
from .downloader import Downloader
from .catalogue import (
    Catalogue,
    mbid,
    credit,
    release_tracks,
    edition_rank,
    background_metadata,
)
from .artwork import quoted
from .quality import PROFILES
from .soulseek import Soulseek
from .artwork import Artwork
from .portraits import Portraits
from .popularity import Popularity
from .artist_backgrounds import Backgrounds
from .media import (
    public_settings,
    save_settings,
    track_file,
    saved_track,
    settings as private_media_settings,
)
from .remote import RemoteAudio
from .scanner import LibraryScanner
from .playlists import Playlists
from .plex import Plex
from .exporter import Exporter
from .artist_jobs import ArtistJobs
from .recovery import Recovery
from .organisation import Organisation

ROOT = Path(__file__).resolve().parent.parent


def create_app(data_dir: Path | None = None, client_dir: Path | None = None):
    https_origin = public_origin()
    store = Store(
        data_dir or Path(os.environ.get("PIG_MUSIC_DATA", ROOT / ".localdata"))
    )
    music_catalogue = Catalogue(store)
    artwork = Artwork(store, music_catalogue)
    fanart = Fanart(store)
    portraits = Portraits(store, music_catalogue, artwork, fanart)
    popularity = Popularity(store, music_catalogue)
    backgrounds = Backgrounds(store, artwork, fanart)
    catalogue_cache = {}
    remote_audio = RemoteAudio()
    scanner = LibraryScanner(store)
    playlists = Playlists(store)
    plex = Plex(store, playlists)
    exporter = Exporter(store)
    artist_jobs = ArtistJobs(store, music_catalogue)
    recovery = Recovery(store)
    organisation = Organisation(store, recovery)
    scan_task = None
    preload_stopping = asyncio.Event()
    image_revision = 0

    def images_changed():
        nonlocal image_revision
        image_revision += 1
        store.refresh_library()

    enrichment = Enrichment(images_changed)
    image_slots = asyncio.Semaphore(2)

    def feed_queue():
        return {
            **store.queue(),
            "artwork_revision": image_revision,
            "media": public_settings(store),
        }

    def feed_health():
        try:
            download_root(store)
            storage_available = True
        except (OSError, ValueError):
            storage_available = False
        return {
            "storage_available": storage_available,
            "soulseek": Soulseek(store).health(),
        }

    change_feed = ChangeFeed(feed_queue, feed_health)

    @asynccontextmanager
    async def lifespan(app):
        nonlocal scan_task
        async with httpx.AsyncClient(
            timeout=12,
            headers={
                "User-Agent": "PigMusic/0.1 (private household prototype)",
                "Accept": "application/json",
            },
        ) as client:
            app.state.http = client
            enrichment.start()
            change_feed.start()
            await asyncio.to_thread(recovery.recover)
            await asyncio.to_thread(organisation.recover)
            downloader = Downloader(store)
            task = asyncio.create_task(downloader.run())
            plex_task = asyncio.create_task(plex.run())
            export_task = asyncio.create_task(exporter.run())
            artist_task = asyncio.create_task(artist_jobs.run(client))
            preload_task = asyncio.create_task(preload_library())
            maintenance_task = asyncio.create_task(maintain_artwork())
            if (
                scanner.root.is_dir()
                and not (store.directory / "library-snapshot.json").exists()
            ):
                scan_task = asyncio.create_task(asyncio.to_thread(scanner.run))
            try:
                yield
            finally:
                downloader.stopping.set()
                scanner.stopping.set()
                plex.stopping.set()
                exporter.stopping.set()
                artist_jobs.stopping.set()
                await artist_task
                preload_stopping.set()
                preload_task.cancel()
                await enrichment.close()
                await change_feed.close()
                maintenance_task.cancel()
                await task
                await plex_task
                await export_task
                try:
                    await preload_task
                except asyncio.CancelledError:
                    pass
                try:
                    await maintenance_task
                except asyncio.CancelledError:
                    pass
                if scan_task:
                    await scan_task

    async def maintain_artwork():
        # Wait a week after startup; never prune during startup migration.
        while True:
            await asyncio.sleep(7 * 86400)
            await asyncio.to_thread(store.prune_artwork)

    auth = Auth(store)
    security = Security(
        auth, legacy_test=os.environ.get("PIG_MUSIC_TEST_LEGACY_API") == "1"
    )
    guard = security.current_user
    app = FastAPI(
        title="Pig Music",
        version="0.1.0",
        lifespan=lifespan,
        dependencies=[Depends(guard)],
    )
    app.state.auth = auth
    app.state.security = security
    app.include_router(auth_router(auth))
    app.include_router(personal_router(store, artist_jobs))
    install_validation_redaction(app)
    app.state.store = store
    app.state.enrichment = enrichment
    app.state.change_feed = change_feed
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    @app.middleware("http")
    async def headers(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in {
                https_origin,
                str(request.base_url).rstrip("/"),
            }:
                return Response("Cross-origin writes are not allowed.", status_code=403)
        response = await call_next(request)
        if getattr(request.state, "refresh_cookie", None):
            set_cookie(response, request.state.refresh_cookie)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/") and not request.url.path.startswith(
            ("/api/artwork/", "/api/library-artwork/")
        ):
            response.headers.setdefault("Cache-Control", "no-store")
        if request.url.path.startswith("/assets/") and response.status_code in {
            200,
            304,
        }:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    @app.get("/api/health")
    def health(request: Request):
        try:
            download_root(store)
            storage_available = True
        except (OSError, ValueError):
            storage_available = False
        if not security.legacy_test:
            return {
                "status": "ok",
                "https": request.url.scheme == "https",
                "storage_available": storage_available,
            }
        return {
            "status": "ok",
            "https": request.url.scheme == "https",
            "public_origin": https_origin,
            "mode": (
                "direct_library"
                if os.environ.get("PIG_MUSIC_DOWNLOAD_ROOT")
                else "isolated_library"
            ),
            "storage_available": storage_available,
            "downloads_enabled": store.download_settings()["enabled"]
            and storage_available,
            "library_snapshot": store.library["snapshot"],
            "library_stats": store.library["stats"],
        }

    @app.post("/api/albums/{album_id}/remove")
    async def remove_album(album_id: str):
        album = store.albums_by_id.get(album_id)
        if not album:
            raise HTTPException(404, "Album not found.")
        count = 0
        for track in list(album["tracks"]):
            try:
                await asyncio.to_thread(recovery.remove, track["id"])
                count += 1
            except (ValueError, OSError):
                raise HTTPException(
                    409,
                    f"Removed {count} songs; remaining files need review. All removed songs are recoverable.",
                )
        return {"removed": count}

    @app.post("/api/artists/{artist_id}/remove")
    async def remove_artist(artist_id: str):
        artist = store.artists_by_id.get(artist_id)
        if not artist:
            raise HTTPException(404, "Artist not found.")
        identity = await library_artist_catalogue(artist_id)
        artist_jobs.cancel(identity["id"])
        count = 0
        for album in [
            a for a in store.library["albums"] if a["artist_id"] == artist_id
        ]:
            for track in list(album["tracks"]):
                try:
                    await asyncio.to_thread(recovery.remove, track["id"])
                    count += 1
                except (ValueError, OSError):
                    raise HTTPException(
                        409,
                        f"Removed {count} songs; remaining files need review. All removed songs are recoverable.",
                    )
        return {"removed": count, "monitor": False}

    class OrganiseRequest(BaseModel):
        track_ids: list[str] = Field(max_length=5000)
        tags: bool = False

    @app.get("/api/library/organisation/history")
    def organisation_history():
        return [
            {"id": r["id"], "title": r["track"]["title"], "status": r["status"]}
            for r in organisation.history()
            if r["status"] in {"completed", "undoing"}
        ]

    @app.post("/api/library/organisation/{identity}/undo")
    async def undo_organisation(identity: str):
        if scan_task and not scan_task.done():
            raise HTTPException(
                409, "Wait for the library scan before undoing organisation."
            )
        if not scanner.lock.acquire(blocking=False):
            raise HTTPException(
                409, "Wait for the library scan before undoing organisation."
            )
        try:
            return await asyncio.to_thread(organisation.undo, identity)
        except (ValueError, OSError):
            raise HTTPException(
                409, "Undo stopped; original backup retained. Check the destination."
            )
        finally:
            scanner.lock.release()

    @app.get("/api/library/organisation")
    async def organisation_plan():
        return await asyncio.to_thread(organisation.plan)

    @app.post("/api/library/organisation")
    async def organisation_apply(body: OrganiseRequest):
        if scan_task and not scan_task.done():
            raise HTTPException(
                409, "Wait for the library scan before organising files."
            )
        if any(
            i["status"] in {"searching", "downloading", "validating", "importing"}
            for i in store.queue()["items"]
        ):
            raise HTTPException(
                409, "Wait for active downloads before organising files."
            )
        if not scanner.lock.acquire(blocking=False):
            raise HTTPException(
                409, "Wait for the library scan before organising files."
            )
        try:
            return await asyncio.to_thread(
                organisation.apply, body.track_ids, body.tags
            )
        except (ValueError, OSError):
            raise HTTPException(
                409,
                "Organisation stopped; originals and recovery records are retained. Review the selected files.",
            )
        finally:
            scanner.lock.release()

    @app.get("/api/library/trash")
    def removed_music():
        return [
            {
                k: v
                for k, v in record.items()
                if k not in {"root", "original", "trash", "sha256"}
            }
            for record in recovery.list()
            if record["status"] != "restored"
        ]

    @app.post("/api/tracks/{track_id}/remove")
    async def remove_song(track_id: str):
        try:
            record = await asyncio.to_thread(recovery.remove, track_id)
            return {"id": record["id"], "status": record["status"]}
        except (ValueError, OSError, FileNotFoundError):
            raise HTTPException(
                409,
                "Removal stopped; check the library mount and file. Existing recovery data is retained.",
            )

    @app.post("/api/library/trash/{identity}/restore")
    async def restore_song(identity: str):
        try:
            record = await asyncio.to_thread(recovery.restore, identity)
            return {"id": record["id"], "status": record["status"]}
        except (ValueError, OSError):
            raise HTTPException(
                409,
                "Restore stopped; check the library mount and destination. Recoverable music is retained.",
            )

    @app.get("/api/library")
    def library(request: Request):
        # Playlist count/settings are part of the response, so they enter the validator.
        with store.library_lock:
            with store.connect() as conn:
                playlist_count = conn.execute(
                    "SELECT COUNT(*) FROM playlists"
                ).fetchone()[0]
            signature = (
                store.library_revision,
                playlist_count,
                json.dumps(public_settings(store), sort_keys=True),
            )
            if not store.library_payload or store.library_payload[0] != signature:
                payload = json.dumps(
                    store.summary(),
                    separators=(",", ":"),
                ).encode()
                etag = 'W/"' + hashlib.sha256(payload).hexdigest() + '"'
                store.library_payload = (signature, payload, etag)
            _, payload, etag = store.library_payload
        headers = {
            "ETag": etag,
            "Cache-Control": "private, no-cache",
            "Vary": "Accept-Encoding",
        }
        candidates = request.headers.get("if-none-match", "").split(",")
        if any(
            value.strip().removeprefix("W/") in {etag.removeprefix("W/"), "*"}
            for value in candidates
        ):
            return Response(status_code=304, headers=headers)
        return Response(payload, media_type="application/json", headers=headers)

    @app.get("/api/events")
    async def events():
        if len(change_feed.listeners) >= 32:
            raise HTTPException(503, "Too many change-feed connections.")
        return StreamingResponse(
            change_feed.stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/library/scan")
    def scan_status():
        return scanner.status()

    @app.get("/api/library/export-plan")
    def export_plan():
        return exporter.plan()

    @app.post("/api/library/scan")
    async def scan_library():
        nonlocal scan_task
        if scan_task and not scan_task.done():
            raise HTTPException(409, "A library scan is already running.")
        if scanner.lock.locked():
            raise HTTPException(409, "Wait for library organisation before scanning.")
        scanner.report(status="scanning", files=0)
        scan_task = asyncio.create_task(asyncio.to_thread(scanner.run))
        return scanner.status()

    @app.get("/api/playlists")
    def playlist_list():
        return playlists.list()

    class PlaylistName(BaseModel):
        name: str = Field(min_length=1, max_length=100)

    class SongReference(BaseModel):
        playlist_id: str | None = None
        position: int | None = Field(default=None, ge=0)
        saved_id: str | None = None
        release_id: str | None = None
        track_id: str | None = None
        favourite: bool | None = None

    async def resolve_song(body):
        if body.saved_id:
            track, _ = saved_track(store, body.saved_id)
            if not track:
                raise HTTPException(404, "Song not found.")
        elif body.playlist_id and body.position is not None:
            try:
                track = playlists.raw(body.playlist_id)["tracks"][body.position]
            except (ValueError, IndexError):
                raise HTTPException(404, "Playlist song not found.")
        elif body.release_id and body.track_id:
            track = next(
                (
                    t
                    for t in release_tracks(await release_data(body.release_id))
                    if t["id"] == body.track_id
                ),
                None,
            )
            if not track:
                raise HTTPException(404, "Song not found in this release.")
        else:
            raise HTTPException(400, "Choose a saved song or a release track.")
        return {
            k: v
            for k, v in track.items()
            if k
            in {
                "id",
                "artist",
                "title",
                "album",
                "album_artist",
                "year",
                "duration",
                "disc_number",
                "track_number",
                "musicbrainz_release_id",
                "musicbrainz_recording_id",
            }
        }

    @app.post("/api/playlists")
    def create_playlist(body: PlaylistName):
        try:
            return playlists.create(body.name)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/playlists/{playlist_id}/songs")
    async def add_playlist_song(playlist_id: str, body: SongReference):
        track = await resolve_song(body)
        try:
            return playlists.add(playlist_id, track)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/favourites")
    async def favourite_song(body: SongReference):
        return playlists.favourite(await resolve_song(body), body.favourite)

    class MembershipBatch(BaseModel):
        songs: list[SongReference] = Field(max_length=200)

    @app.post("/api/membership")
    async def song_membership(body: MembershipBatch):
        # Resolve catalogue data through the shared provider cache and build the
        # favourite index once, rather than acquiring a transaction for each row.
        try:
            favourites = playlists.raw("pig-favourites")["tracks"]
        except ValueError:
            favourites = []
        from .matching import LibraryIndex, context, same_song

        index = LibraryIndex({"albums": [{"id": "favourites", "tracks": favourites}]})
        result = []
        for reference in body.songs:
            try:
                track = await resolve_song(reference)
                result.append(
                    {
                        "favourited": any(
                            same_song(t, track)
                            for t in index.by_context.get(context(track), ())
                        )
                    }
                )
            except HTTPException as exc:
                result.append({"favourited": False, "error": exc.detail})
        return {"songs": result}

    @app.get("/api/settings/plex")
    def plex_status():
        return plex.status()

    @app.get("/api/playlists/{playlist_id}")
    def playlist_detail(playlist_id: str):
        try:
            return playlists.detail(playlist_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/playlists/{playlist_id}/review")
    def playlist_review(playlist_id: str):
        try:
            return playlists.review(playlist_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    async def image_response(target, w=0, soft=False):
        if not target or not target.is_file():
            return Response(status_code=404, headers={"Cache-Control": "no-store"})
        async with image_slots:
            target = await asyncio.to_thread(public_image, store, target)
            if not target:
                return Response(status_code=404, headers={"Cache-Control": "no-store"})
            # Alias requests revalidate; redirect only to immutable local bytes.
            suffix = f"?w={w}&soft={int(soft)}" if w else ""
            return RedirectResponse(
                "/api/artwork/" + target.name + suffix,
                headers={"Cache-Control": "no-cache"},
            )

    def image_config():
        return hashlib.sha256(
            json.dumps(private_media_settings(store), sort_keys=True).encode()
        ).hexdigest()[:12]

    def library_image_key(kind, item):
        return "library:" + kind + ":" + item["id"] + ":" + image_config()

    async def enrich_library(kind, item):
        if kind == "albums":
            return await artwork.cover(app.state.http, item)
        identity = None
        if public_settings(store)["portraits"]:
            try:
                identity = await library_artist_catalogue(item["id"])
            except HTTPException:
                pass
            target = await portraits.get(
                app.state.http, item["name"], identity.get("id") if identity else None
            )
            if target:
                await asyncio.to_thread(public_image, store, target)
                return target
        return await artwork.artist(app.state.http, item)

    @app.get("/api/library-artwork/{kind}/{item_id}")
    async def library_artwork(kind: str, item_id: str, request: Request, w: int = 0):
        if kind not in {"albums", "artists"}:
            raise HTTPException(404, "Artwork not found.")
        item = (store.albums_by_id if kind == "albums" else store.artists_by_id).get(
            item_id
        )
        if item is None:
            raise HTTPException(404, "Library item not found.")
        person = getattr(request.state, "user", None)
        if person and person["role"] != "owner":
            item = next(
                (
                    i
                    for i in store.user_libraries.projection(person["id"])[kind]
                    if i["id"] == item_id
                ),
                None,
            )
            if item is None:
                raise HTTPException(404, "Library item not found.")
        target = artwork.target(item) if kind == "albums" else None
        if kind == "artists":
            identity = store.read_document("library-artist:" + item_id)
            portrait = portrait_target(store, item["name"], identity.get("id"))
            if public_settings(store)["portraits"] and portrait.is_file():
                target = portrait
            if not target:
                fallback = item.get("fallback_cover_url") or item.get("cover_url") or ""
                if fallback.startswith("/api/artwork/"):
                    target = store.cover_dir / fallback.split("/")[-1].split("?")[0]
        enrichment.submit(
            library_image_key(kind, item), lambda: enrich_library(kind, item)
        )
        return await image_response(target, w)

    @app.get("/api/albums/{album_id}")
    def album(album_id: str):
        match = store.albums_by_id.get(album_id)
        if match is None:
            raise HTTPException(404, "Album not found.")
        return match

    @app.get("/api/catalogue/artwork/{kind}/{item_id}")
    async def catalogue_artwork(kind: str, item_id: str, w: int = 0):
        if kind not in {"release", "release-group"}:
            raise HTTPException(404, "Artwork not found.")
        item_id = valid_id(item_id)
        key = "catalogue-artwork:" + kind + ":" + item_id
        target = store.cover_dir / (identifier(key) + ".jpg")
        if not target.is_file():
            enrichment.submit(
                key, lambda: artwork.catalogue_cover(app.state.http, kind, item_id)
            )
        return await image_response(target, w)

    @app.get("/api/artists/{artist_id}")
    def artist(artist_id: str):
        match = store.artists_by_id.get(artist_id)
        if match is None:
            raise HTTPException(404, "Artist not found.")
        return {
            **match,
            "albums": [
                store.albums_by_id[album_id]
                for album_id in match["album_ids"]
                if album_id in store.albums_by_id
            ],
            "compilation_tracks": [
                {**t, "album_id": a["id"]}
                for a in store.library["albums"]
                if a["category"] != "album"
                for t in a["tracks"]
                if normalise(t["artist"]) == normalise(match["name"])
            ],
        }

    class Category(BaseModel):
        category: str

    @app.put("/api/albums/{album_id}/category")
    def category(album_id: str, body: Category):
        try:
            return store.categorise(album_id, body.category)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/search")
    def search(q: str = ""):
        query = normalise(q)[:200]
        if not query:
            return {"artists": [], "albums": [], "tracks": [], "available": []}
        artists = [
            a for a in store.library["artists"] if query in normalise(a["name"])
        ][:12]
        albums = [
            a
            for a in store.summary()["albums"]
            if query in normalise(a["title"] + " " + a["artist"])
        ][:12]
        tracks = [track for text, track in store.index.search_tracks if query in text][
            :20
        ]
        available = [
            {**t, "migration_album_id": a["id"], "cover_url": a["cover_url"]}
            for a in store.migration()["albums"]
            for t in a["tracks"]
            if t["status"] != "downloaded"
            and query in normalise(t["title"] + " " + t["artist"])
        ][:20]
        return {
            "artists": artists,
            "albums": albums,
            "tracks": tracks,
            "available": available,
        }

    @app.get("/api/migration")
    def migration():
        return store.migration()

    @app.post("/api/migration/import")
    async def import_export(request: Request):
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > 20_000_000:
                raise HTTPException(413, "Choose an export smaller than 20 MB.")
            chunks.append(chunk)
        try:
            return await asyncio.to_thread(store.import_apple, b"".join(chunks))
        except (ValueError, TypeError, OverflowError) as exc:
            raise HTTPException(400, str(exc)) from exc

    class Selection(BaseModel):
        track_ids: list[str] = Field(max_length=5000)
        selected: bool

    @app.post("/api/migration/selection")
    def selection(body: Selection):
        try:
            return store.update_selection(body.track_ids, body.selected)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/migration/plan")
    def plan():
        return Response(
            json.dumps(store.plan(), indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="pig-music-migration-plan.json"'
            },
        )

    class Decision(BaseModel):
        track_id: str = Field(max_length=128)
        decision: str

    @app.post("/api/migration/decision")
    def decide(body: Decision):
        try:
            return store.decide(body.track_id, body.decision)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/migration/submit")
    def submit():
        try:
            return store.submit_migration()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/queue")
    def queue():
        return {
            **store.queue(),
            "artwork_revision": image_revision,
            "media": public_settings(store),
        }

    @app.post("/api/queue/clear")
    def clear_queue():
        return store.clear_queue()

    @app.get("/api/settings/downloads")
    def download_settings():
        return store.download_settings()

    @app.get("/api/settings/soulseek")
    async def soulseek_health():
        return await asyncio.to_thread(Soulseek(store).health)

    class DownloadSettings(BaseModel):
        enabled: bool
        profile: str
        sources: list[str]
        concurrent_downloads: int = Field(default=3, ge=1, le=6)
        fallback_profile: str = "mp3_320"
        fallback_minutes: int = Field(default=10, ge=1, le=60)
        recheck_hours: int = Field(default=24, ge=1, le=168)

    @app.put("/api/settings/downloads")
    def save_download_settings(body: DownloadSettings):
        try:
            return store.save_download_settings(body.model_dump())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/queue/{request_id}/retry")
    def retry(request_id: str):
        try:
            return store.retry_request(request_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/queue/{request_id}/cancel")
    def cancel(request_id: str):
        try:
            return store.cancel_request(request_id)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/catalogue/artists")
    async def catalogue(q: str = ""):
        query = q.strip()[:150]
        if len(query) < 2:
            return {"artists": []}
        cache_key = normalise(query)
        if (
            cache_key in catalogue_cache
            and time.monotonic() - catalogue_cache[cache_key][0] < 3600
        ):
            return catalogue_cache[cache_key][1]
        try:
            data = await music_catalogue.get(
                app.state.http, "artist/", query=query, limit=12
            )
            # Search already supplies identity needed by portrait requests.
            with store.connect() as conn:
                for identity in data.get("artists", []):
                    conn.execute(
                        "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                        (
                            "catalogue:artist/" + identity["id"] + "[]",
                            json.dumps({"time": time.time(), "data": identity}),
                        ),
                    )
            payload = {
                "artists": [
                    {
                        "id": a["id"],
                        "name": a["name"],
                        "description": a.get("disambiguation")
                        or a.get("country")
                        or a.get("type", "Artist"),
                        "saved_artist_id": next(
                            (
                                s["id"]
                                for s in store.library["artists"]
                                if normalise(s["name"]) == normalise(a["name"])
                            ),
                            None,
                        ),
                    }
                    for a in data.get("artists", [])
                ]
            }
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(
                502,
                "The catalogue is unavailable. Your saved library is still accessible.",
            ) from exc
        catalogue_cache[cache_key] = (time.monotonic(), payload)
        if len(catalogue_cache) > 200:
            catalogue_cache.pop(next(iter(catalogue_cache)))
        return payload

    async def metadata(path, **params):
        try:
            return await music_catalogue.get(app.state.http, path, **params)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(
                502, "The catalogue is unavailable. Try again shortly."
            ) from exc

    def valid_id(value):
        try:
            return mbid(value)
        except ValueError as exc:
            raise HTTPException(400, "Invalid catalogue identifier.") from exc

    @app.get("/api/catalogue/artists/{artist_id}/releases")
    async def artist_releases(artist_id: str, offset: int = 0, kind: str | None = None):
        if offset < 0 or offset > 10000:
            raise HTTPException(400, "Invalid page.")
        if kind is not None:
            if kind not in {"album", "single", "ep", "other"}:
                raise HTTPException(400, "Choose a supported release type.")
            query = release_query(valid_id(artist_id), kind)
            data = await metadata(
                "release-group/", query=query, limit=100, offset=offset
            )
        else:
            data = await metadata(
                "release-group", artist=valid_id(artist_id), limit=50, offset=offset
            )
        identity = store.read_document(
            "catalogue:artist/" + valid_id(artist_id) + "[]"
        ).get("data", {})
        albums = [
            a
            for a in store.library["albums"]
            if normalise(a["artist"]) == normalise(identity.get("name", ""))
        ]
        releases = sorted(
            {r["id"]: r for r in data.get("release-groups", [])}.values(),
            key=lambda r: (
                bool(r.get("first-release-date")),
                r.get("first-release-date", ""),
                r.get("title", ""),
            ),
            reverse=True,
        )
        return {
            "total": data.get("count", data.get("release-group-count", 0)),
            "offset": offset,
            "releases": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("first-release-date", ""),
                    "saved_album_id": next(
                        (
                            a["id"]
                            for a in albums
                            if normalise(a["title"]) == normalise(r["title"])
                        ),
                        None,
                    ),
                    "type": " · ".join(
                        [
                            r.get("primary-type", "Release"),
                            *r.get("secondary-types", []),
                        ]
                    ),
                }
                for r in releases
            ],
        }

    @app.get("/api/artists/{artist_id}/catalogue")
    async def library_artist_catalogue(artist_id: str):
        artist = store.artists_by_id.get(artist_id)
        if artist is None:
            raise HTTPException(404, "Artist not found.")
        known = store.read_document("library-artist:" + artist_id)
        if known and known.get("name") == artist["name"]:
            return known
        data = await metadata(
            "artist/", query="artist:" + quoted(artist["name"]), limit=100
        )
        matches = [
            a
            for a in data.get("artists", [])
            if normalise(a["name"]) == normalise(artist["name"])
        ]
        if len(matches) != 1 or data.get("count", len(matches)) > 100:
            raise HTTPException(
                409, "Choose this artist in Search to distinguish matching names."
            )
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (
                    "catalogue:artist/" + matches[0]["id"] + "[]",
                    json.dumps({"time": time.time(), "data": matches[0]}),
                ),
            )
        identity = {"id": matches[0]["id"], "name": matches[0]["name"]}
        store.write_document("library-artist:" + artist_id, identity)
        return identity

    async def preload_library():
        if os.environ.get("PIG_MUSIC_PRELOAD", "true").lower() == "false":
            return
        # One new/changed local item per pass. No periodic discography walk.
        seen = set()
        while not preload_stopping.is_set():
            for kind in ("albums", "artists"):
                for item in list(store.library[kind]):
                    signature = (
                        kind,
                        item["id"],
                        item.get("cover_url"),
                        json.dumps(public_settings(store), sort_keys=True),
                    )
                    if signature in seen:
                        continue
                    if not (item.get("cover_url") or "").startswith(
                        "/api/library-artwork/"
                    ):
                        seen.add(signature)
                        continue
                    if enrichment.submit(
                        library_image_key(kind, item),
                        lambda kind=kind, item=item: enrich_library(kind, item),
                    ):
                        seen.add(signature)
                    break
            live_ids = {
                i["id"] for kind in ("albums", "artists") for i in store.library[kind]
            }
            seen = {key for key in seen if key[1] in live_ids}
            await asyncio.sleep(15)

    class ArtistRequest(BaseModel):
        kinds: list[str] = Field(default=["album"], max_length=3)
        monitor: bool = False
        request: bool = False

    @app.get("/api/catalogue/artists/{artist_id}/acquisition")
    def artist_acquisition(artist_id: str):
        return artist_jobs.state(valid_id(artist_id))

    @app.put("/api/catalogue/artists/{artist_id}/acquisition")
    def artist_acquisition_update(artist_id: str, body: ArtistRequest):
        try:
            return artist_jobs.configure(
                valid_id(artist_id), body.kinds, body.monitor, body.request
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/catalogue/artists/{artist_id}/popularity")
    async def artist_popularity(artist_id: str):
        return await popularity.get(app.state.http, valid_id(artist_id))

    @app.get("/api/catalogue/artists/{artist_id}/background")
    async def catalogue_artist_background(
        artist_id: str, w: int = 0, soft: bool = False
    ):
        artist_id = valid_id(artist_id)
        config = public_settings(store)
        if not config["portraits"] or not config["fanart_configured"]:
            raise HTTPException(404, "Artwork unavailable.")
        target = background_target(store, artist_id)
        if not target.is_file():
            enrichment.submit(
                "background:" + target.stem,
                lambda: backgrounds.get(app.state.http, artist_id),
            )
        return await image_response(target, w, soft)

    async def enrich_background(artist_id):
        identity = await library_artist_catalogue(artist_id)
        return await backgrounds.get(app.state.http, identity["id"])

    @app.get("/api/artists/{artist_id}/background")
    async def artist_background(artist_id: str, w: int = 0, soft: bool = False):
        if artist_id not in store.artists_by_id:
            raise HTTPException(404, "Artist not found.")
        config = public_settings(store)
        if not config["fanart_configured"] or not config["portraits"]:
            raise HTTPException(404, "Artwork unavailable.")
        identity = store.read_document("library-artist:" + artist_id)
        target = background_target(store, identity["id"]) if identity else None
        if not target or not target.is_file():
            enrichment.submit(
                "library-background:" + artist_id, lambda: enrich_background(artist_id)
            )
        return await image_response(target, w, soft)

    async def enrich_catalogue_artist(artist_id, cache_key):
        if public_settings(store)["portraits"]:
            identity = await metadata("artist/" + artist_id)
            target = await portraits.get(
                app.state.http, identity.get("name", ""), artist_id
            )
            if target:
                store.write_document(cache_key, {"file": target.name})
                return target
        data = await metadata(
            "release", artist=artist_id, inc="release-groups", limit=50
        )
        releases = [
            r
            for r in data.get("releases", [])
            if r.get("cover-art-archive", {}).get("front")
        ]
        releases.sort(
            key=lambda r: (
                r.get("release-group", {}).get("primary-type") != "Album",
                bool(r.get("release-group", {}).get("secondary-types")),
            )
        )
        if releases:
            target = await artwork.catalogue_cover(
                app.state.http, "release", valid_id(releases[0]["id"])
            )
            if target:
                store.write_document(cache_key, {"file": target.name})
                return target
        return None

    @app.get("/api/catalogue/artists/{artist_id}/artwork")
    async def artist_artwork(artist_id: str, w: int = 0):
        artist_id = valid_id(artist_id)
        cache_key = "catalogue-artist-image:" + artist_id + ":" + image_config()
        cached = store.read_document(cache_key).get("file", "")
        target = (
            store.cover_dir / cached if cached and Path(cached).name == cached else None
        )
        if not target or not target.is_file():
            enrichment.submit(
                cache_key, lambda: enrich_catalogue_artist(artist_id, cache_key)
            )
        return await image_response(target, w)

    @app.get("/api/catalogue/groups/{group_id}/editions")
    async def editions(group_id: str, offset: int = 0):
        if offset < 0 or offset > 10000:
            raise HTTPException(400, "Invalid page.")
        data = await metadata(
            "release",
            **{
                "release-group": valid_id(group_id),
                "inc": "media",
                "limit": 50,
                "offset": offset,
            },
        )
        ranked = sorted(data.get("releases", []), key=edition_rank)
        return {
            "total": data.get("release-count", 0),
            "offset": offset,
            "editions": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "date": r.get("date", ""),
                    "country": r.get("country", ""),
                    "description": r.get("disambiguation", ""),
                    "status": r.get("status", ""),
                    "formats": [
                        m.get("format", "Unknown format") for m in r.get("media", [])
                    ],
                    "track_count": sum(
                        m.get("track-count", 0) for m in r.get("media", [])
                    ),
                }
                for r in ranked
            ],
            "recommended_id": ranked[0]["id"] if ranked else None,
        }

    async def release_data(release_id):
        return await metadata(
            "release/" + valid_id(release_id), inc="recordings+artist-credits+isrcs"
        )

    @app.get("/api/catalogue/releases/{release_id}")
    async def catalogue_release(release_id: str):
        data = await release_data(release_id)
        tracks = music_catalogue.presence(release_tracks(data))
        jobs = store.queue()["items"]
        for track in tracks:
            job = next(
                (
                    j
                    for j in jobs
                    if j.get("musicbrainz_release_id") == data["id"]
                    and j.get("musicbrainz_recording_id")
                    == track.get("musicbrainz_recording_id")
                    and j.get("track_number") == track["track_number"]
                    and j.get("disc_number") == track["disc_number"]
                ),
                None,
            )
            if job and track["status"] != "downloaded":
                track.update(
                    download_status=job["status"],
                    received_bytes=job.get("received_bytes", 0),
                    total_bytes=job.get("total_bytes", 0),
                )
        return {
            "id": data["id"],
            "title": data["title"],
            "artist": credit(data.get("artist-credit", [])),
            "date": data.get("date", ""),
            "description": data.get("disambiguation", ""),
            "tracks": tracks,
        }

    class CatalogueRequest(BaseModel):
        track_ids: list[str] | None = Field(default=None, max_length=500)
        quality_profile: str | None = None

    @app.post("/api/catalogue/releases/{release_id}/request")
    async def request_release(release_id: str, body: CatalogueRequest):
        if body.quality_profile is not None and body.quality_profile not in PROFILES:
            raise HTTPException(400, "Choose a supported quality.")
        tracks = music_catalogue.presence(
            release_tracks(await release_data(release_id))
        )
        if body.track_ids is not None:
            if not set(body.track_ids).issubset({t["id"] for t in tracks}):
                raise HTTPException(400, "Unknown tracks in this edition.")
            tracks = [t for t in tracks if t["id"] in body.track_ids]
        if not tracks:
            raise HTTPException(400, "This edition has no selected tracks.")
        return store.submit_catalogue(tracks, body.quality_profile)

    class AlbumQuality(BaseModel):
        profile: str | None = None

    @app.post("/api/albums/{album_id}/quality")
    def album_quality(album_id: str, body: AlbumQuality):
        try:
            return store.quality_override("album", album_id, body.profile)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/albums/{album_id}/quality")
    def album_quality_status(album_id: str):
        try:
            return store.quality_status("album", album_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/artists/{artist_id}/quality")
    def artist_quality_status(artist_id: str):
        try:
            return store.quality_status("artist", artist_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/artists/{artist_id}/quality")
    def artist_quality(artist_id: str, body: AlbumQuality):
        try:
            return store.quality_override("artist", artist_id, body.profile)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    class MediaSettings(BaseModel):
        portraits: bool
        remote_playback: bool
        fanart_key: str | None = Field(default=None, max_length=128)
        listenbrainz_token: str | None = Field(default=None, max_length=128)

    @app.get("/api/settings/media")
    def media_settings():
        return public_settings(store)

    @app.put("/api/settings/media")
    def update_media_settings(body: MediaSettings):
        try:
            result = save_settings(store, **body.model_dump())
            store.refresh_library()
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/v1/playback/{track_id}/url")
    def playback_url(track_id: str, request: Request):
        try:
            track_file(store, track_id)
        except FileNotFoundError:
            raise HTTPException(404, "File unavailable")
        return {
            "url": security.sign_url(
                "/api/playback/files/" + track_id,
                request.state.user,
                request.state.session,
            ),
            "expires_in": 6 * 3600,
        }

    @app.get("/api/playback/saved/{track_id}")
    def playback_saved(track_id: str):
        try:
            track_file(store, track_id)
        except FileNotFoundError:
            raise HTTPException(404, "This saved file is unavailable on the server.")
        track, _ = saved_track(store, track_id)
        return {
            **track,
            "url": "/api/playback/files/" + track_id,
            "source": "Saved library",
        }

    @app.get("/api/playback/files/{track_id}")
    @app.head("/api/playback/files/{track_id}")
    def playback_file(track_id: str):
        try:
            target = track_file(store, track_id)
        except FileNotFoundError:
            raise HTTPException(404, "This saved file is unavailable on the server.")
        types = {
            ".mp3": "audio/mpeg",
            ".flac": "audio/flac",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".opus": "audio/ogg",
            ".wav": "audio/wav",
        }
        return FileResponse(
            target,
            media_type=types[target.suffix.lower()],
            headers={"Cache-Control": "private, no-cache"},
        )

    class PlaybackRequest(BaseModel):
        release_id: str
        track_id: str

    @app.post("/api/playback/catalogue")
    async def playback_catalogue(body: PlaybackRequest):
        tracks = music_catalogue.presence(
            release_tracks(await release_data(body.release_id))
        )
        track = next((t for t in tracks if t["id"] == body.track_id), None)
        if track is None:
            raise HTTPException(404, "Song not found in this release.")
        if track.get("saved_id"):
            return playback_saved(track["saved_id"])
        if not public_settings(store)["remote_playback"]:
            raise HTTPException(
                409, "Experimental remote playback is disabled in Settings."
            )
        try:
            url = await remote_audio.resolve(app.state.http, track)
        except (httpx.HTTPError, TimeoutError):
            raise HTTPException(
                503,
                "Remote streaming is unavailable right now. Saved music and downloads still work.",
            )
        except (ValueError, KeyError, TypeError):
            raise HTTPException(
                404,
                "No reliable remote stream matched this release. You can still download it.",
            )
        return {
            **track,
            "url": url,
            "source": "Remote · JioSaavn",
            "note": "Not saved. Provider quality and exact mastering are unverified.",
        }

    app.include_router(artwork_router(store, image_slots, enrichment, image_response))

    dist = client_dir or ROOT / "client" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
        if (dist / "brand").is_dir():
            app.mount("/brand", StaticFiles(directory=dist / "brand"), name="brand")
        if (dist / "manifest.webmanifest").is_file():

            @app.get("/manifest.webmanifest", include_in_schema=False)
            def manifest():
                return FileResponse(
                    dist / "manifest.webmanifest",
                    media_type="application/manifest+json",
                    headers={"Cache-Control": "no-cache"},
                )

        @app.get("/")
        def index():
            return FileResponse(
                dist / "index.html", headers={"Cache-Control": "no-cache"}
            )

    audit_routes(app, guard)
    return app


app = create_app()
