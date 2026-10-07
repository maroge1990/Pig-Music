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
    JSONResponse,
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
from .request_limits import JsonBodyLimit
from .transport import public_origin
from .enrichment import Enrichment
from .change_feed import ChangeFeed
from .image_cache import public_image
from .routes.artwork import artwork_router
from .routes.household import household_router
from .portraits import portrait_target
from .artist_backgrounds import background_target
from pydantic import BaseModel, Field

from .library import normalise, identifier
from .fanart import Fanart
from .storage import download_root
from .store import Store
from .downloader import Downloader
from .catalogue import (
    Catalogue,
    release_tracks,
    background_metadata,
)
from .soulseek import Soulseek
from .artwork import Artwork
from .portraits import Portraits
from .popularity import Popularity
from .artist_backgrounds import Backgrounds
from .media import (
    public_settings,
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
        if not security.legacy_test and not await asyncio.to_thread(auth.has_owner):
            # Intentional one-time operator handover; never log submitted passwords.
            print(
                "Pig Music first-run setup: open the private HTTPS WebUI, then enter this installation code:",
                flush=True,
            )
            print(security.installation_code(), flush=True)
            print(
                "This code stops working once the administrator account is created. Keep it private.",
                flush=True,
            )
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
    app.include_router(auth_router(auth, security))
    app.include_router(household_router(store))
    from .routes.native import native_router

    app.include_router(native_router(store, auth, feed_health))
    from .routes.discover import discover_router

    from .routes.home import home_router

    app.include_router(home_router(store, music_catalogue))
    app.include_router(discover_router(store, music_catalogue, popularity))
    app.include_router(personal_router(store, artist_jobs, recovery))
    install_validation_redaction(app)
    app.state.store = store
    app.state.enrichment = enrichment
    app.state.change_feed = change_feed
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(JsonBodyLimit)

    @app.middleware("http")
    async def headers(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") not in {
                https_origin,
                str(request.base_url).rstrip("/"),
            }:
                return JSONResponse(
                    {
                        "detail": "Cross-origin writes are not allowed.",
                        "code": "invalid_origin",
                    },
                    status_code=403,
                )
        response = await call_next(request)
        if getattr(request.state, "refresh_cookie", None):
            set_cookie(response, request.state.refresh_cookie)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"

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

    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = (
            exc.detail
            if isinstance(exc.detail, str) and exc.detail.replace("_", "").isalnum()
            else {
                400: "invalid_request",
                401: "authentication_required",
                403: "forbidden",
                404: "not_found",
                409: "conflict",
                410: "resync_required",
                413: "request_too_large",
                422: "invalid_request",
                503: "setup_required",
            }.get(exc.status_code, "request_failed")
        )
        return JSONResponse(
            {"detail": str(exc.detail), "code": code},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"detail": "Check the submitted fields", "code": "invalid_request"},
            status_code=422,
        )

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

    @app.get("/api/catalogue/artwork/{kind}/{item_id}", tags=["personal-library"])
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

    from .routes.catalogue import catalogue_router

    catalogue_routes, library_artist_catalogue, valid_id, release_data = (
        catalogue_router(
            store,
            music_catalogue,
            artist_jobs,
            popularity,
            backgrounds,
            portraits,
            artwork,
            enrichment,
            image_response,
            image_config,
            lambda: app.state.http,
        )
    )
    app.include_router(catalogue_routes)

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

    from .api_models import PlaybackURL

    @app.post("/api/v1/playback/{track_id}/url", response_model=PlaybackURL)
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

    @app.get("/api/v1/tracks/{track_id}/file", tags=["personal-library"])
    @app.head("/api/v1/tracks/{track_id}/file", tags=["personal-library"])
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

        @app.get("/theme.js", include_in_schema=False)
        def theme():
            return FileResponse(
                dist / "theme.js",
                media_type="text/javascript",
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
