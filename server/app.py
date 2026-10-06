import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .library import normalise
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
from .media import public_settings, save_settings, track_file, saved_track
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

    app = FastAPI(title="Pig Music", version="0.1.0", lifespan=lifespan)
    app.state.store = store

    @app.middleware("http")
    async def headers(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return Response("Cross-origin writes are not allowed.", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/") and not request.url.path.startswith(
            ("/api/artwork/", "/api/library-artwork/")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        try:
            download_root(store)
            storage_available = True
        except (OSError, ValueError):
            storage_available = False
        return {
            "status": "ok",
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
        album = next((a for a in store.library["albums"] if a["id"] == album_id), None)
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
        artist = next(
            (a for a in store.library["artists"] if a["id"] == artist_id), None
        )
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
    def library():
        return store.summary()

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

    @app.get("/api/library-artwork/{kind}/{item_id}")
    async def library_artwork(kind: str, item_id: str):
        if kind not in {"albums", "artists"}:
            raise HTTPException(404, "Artwork not found.")
        item = next((i for i in store.library[kind] if i["id"] == item_id), None)
        if item is None:
            raise HTTPException(404, "Library item not found.")
        target = (
            await portraits.get(app.state.http, item["name"])
            if kind == "artists"
            else None
        )
        if target is None:
            target = await (
                artwork.artist(app.state.http, item)
                if kind == "artists"
                else artwork.cover(app.state.http, item)
            )
        if target is None:
            raise HTTPException(404, "Artwork unavailable.")
        return FileResponse(
            target,
            media_type="image/jpeg",
            headers={
                "Cache-Control": (
                    "no-cache" if kind == "artists" else "public, max-age=86400"
                )
            },
        )

    @app.get("/api/albums/{album_id}")
    def album(album_id: str):
        match = next((a for a in store.library["albums"] if a["id"] == album_id), None)
        if match is None:
            raise HTTPException(404, "Album not found.")
        return match

    @app.get("/api/catalogue/artwork/{kind}/{item_id}")
    async def catalogue_artwork(kind: str, item_id: str):
        if kind not in {"release", "release-group"}:
            raise HTTPException(404, "Artwork not found.")
        try:
            target = await artwork.catalogue_cover(app.state.http, kind, item_id)
        except ValueError:
            raise HTTPException(400, "Invalid catalogue identifier.")
        if target is None:
            raise HTTPException(404, "Artwork unavailable.")
        return FileResponse(
            target,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/artists/{artist_id}")
    def artist(artist_id: str):
        match = next(
            (a for a in store.library["artists"] if a["id"] == artist_id), None
        )
        if match is None:
            raise HTTPException(404, "Artist not found.")
        return {
            **match,
            "albums": [
                a for a in store.library["albums"] if a["id"] in match["album_ids"]
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
        return store.queue()

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
        artist = next(
            (a for a in store.library["artists"] if a["id"] == artist_id), None
        )
        if artist is None:
            raise HTTPException(404, "Artist not found.")
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
        return {"id": matches[0]["id"], "name": matches[0]["name"]}

    async def preload_library():
        background_metadata.set(True)
        if os.environ.get("PIG_MUSIC_PRELOAD", "true").lower() == "false":
            return
        # One background request at a time shares the existing persistent cache
        # and global metadata rate limiter with interactive browsing.
        while not preload_stopping.is_set():
            for saved in list(store.library["artists"]):
                if preload_stopping.is_set():
                    return
                if saved.get("compilation_only"):
                    continue
                try:
                    identity = await library_artist_catalogue(saved["id"])
                    await portraits.get(app.state.http, identity["name"])
                    await backgrounds.get(app.state.http, identity["id"])
                    for kind in ("album",):
                        offset = 0
                        covers = 0
                        while offset < 100:
                            page = await artist_releases(identity["id"], offset, kind)
                            releases = page["releases"]
                            # Eagerly cache the first page's most recent covers;
                            # the remainder stay lazy to bound disk/network use.
                            for release in releases[: max(0, 3 - covers)]:
                                await artwork.catalogue_cover(
                                    app.state.http, "release-group", release["id"]
                                )
                                covers += 1
                            offset += len(releases)
                            if not releases or offset >= page["total"]:
                                break
                            await asyncio.sleep(0)
                except (HTTPException, httpx.HTTPError, ValueError, KeyError, OSError):
                    continue
                await asyncio.sleep(0)
            for album in list(store.library["albums"]):
                if preload_stopping.is_set():
                    return
                if (album.get("cover_url") or "").startswith("/api/library-artwork/"):
                    await artwork.cover(app.state.http, album)
            try:
                await asyncio.wait_for(preload_stopping.wait(), timeout=900)
            except TimeoutError:
                pass

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
    async def catalogue_artist_background(artist_id: str):
        target = await backgrounds.get(app.state.http, valid_id(artist_id))
        if target is None:
            raise HTTPException(404, "Artwork unavailable.")
        return FileResponse(
            target,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/artists/{artist_id}/background")
    async def artist_background(artist_id: str):
        if (
            not public_settings(store)["fanart_configured"]
            or not public_settings(store)["portraits"]
        ):
            raise HTTPException(404, "Artwork unavailable.")
        identity = await library_artist_catalogue(artist_id)
        target = await backgrounds.get(app.state.http, identity["id"])
        if not target:
            raise HTTPException(404, "Artwork unavailable.")
        return FileResponse(
            target, media_type="image/jpeg", headers={"Cache-Control": "no-cache"}
        )

    @app.get("/api/catalogue/artists/{artist_id}/artwork")
    async def artist_artwork(artist_id: str):
        if public_settings(store)["portraits"]:
            identity = await metadata("artist/" + valid_id(artist_id))
            portrait = await portraits.get(
                app.state.http, identity.get("name", ""), valid_id(artist_id)
            )
            if portrait:
                return FileResponse(
                    portrait,
                    media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache"},
                )
        # An artist tile uses a credited release cover, not an inferred portrait.
        # Lookup is lazy and shares the persistent catalogue cache/rate limiter.
        data = await metadata(
            "release", artist=valid_id(artist_id), inc="release-groups", limit=50
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
        if not releases:
            raise HTTPException(404, "No artist release artwork available.")
        return RedirectResponse(
            "https://coverartarchive.org/release/"
            + valid_id(releases[0]["id"])
            + "/front-500"
        )

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

    app.mount("/api/artwork", StaticFiles(directory=store.cover_dir), name="artwork")
    dist = client_dir or ROOT / "client" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(
                dist / "index.html", headers={"Cache-Control": "no-cache"}
            )

    return app


app = create_app()
