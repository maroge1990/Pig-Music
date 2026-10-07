"""Private Plex integration. Only playlists carrying our ownership marker are edited."""

import asyncio
import time
import json
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import PurePosixPath

import httpx
from .library import load_json


class Plex:
    def __init__(self, store, playlists, user_id=None):
        self.store, self.playlists = store, playlists
        self.stopping = asyncio.Event()
        self.path_cache = None
        self.user_id = user_id
        self.accounts = None
        self.controllers = {}

    def config(self):
        config = load_json(self.store.directory / "plex-connection.json")
        if self.user_id:
            from .plex_accounts import PlexAccounts

            config["token"] = PlexAccounts(self.store).token(self.user_id)
        return config

    def status(self):
        if not self.user_id:
            with self.store.connect() as conn:
                owner = conn.execute(
                    "SELECT id FROM users WHERE role='owner'"
                ).fetchone()
            if owner:
                return Plex(self.store, self.playlists, owner[0]).status()
        config = self.config()
        return {
            "configured": bool(config.get("token") and config.get("section_id")),
            **self.store.read_document(
                "plex-status:" + self.user_id if self.user_id else "plex-status"
            ),
        }

    def save(self, name, value):
        with self.store.connect() as conn:
            conn.execute(
                "INSERT INTO documents VALUES (?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload",
                (name, json.dumps(value)),
            )

    async def query(self, client, method, path, **params):
        response = await client.request(method, path, params=params)
        response.raise_for_status()
        return (
            ET.fromstring(response.content)
            if response.content.strip()
            else ET.Element("MediaContainer")
        )

    async def index(self, client, config):
        paths = defaultdict(set)
        offset = 0
        while True:
            page = await self.query(
                client,
                "GET",
                "/library/sections/" + str(config["section_id"]) + "/all",
                type=10,
                **{"X-Plex-Container-Start": offset, "X-Plex-Container-Size": 500},
            )
            tracks = page.findall("Track")
            for track in tracks:
                key = track.get("ratingKey")
                if key and key.isdigit():
                    for part in track.findall(".//Part"):
                        if part.get("file"):
                            paths[part.get("file")].add(key)
            offset += len(tracks)
            if not tracks or offset >= int(page.get("totalSize", offset)):
                break
            if offset > 1_000_000:
                raise ValueError("Plex inventory is too large.")
        return paths

    def desired(self, detail, paths, config):
        keys = []
        with self.store.connect() as conn:
            managed = {row[0] for row in conn.execute("SELECT id FROM acquired")}
        for entry in detail["entries"]:
            track = entry.get("saved_track")
            if not track:
                continue
            # Acquired files are not published to the NAS until their export is committed.
            relative = track.get("export_relative_path") or (
                track.get("relative_path") if track["id"] not in managed else None
            )
            if (
                not relative
                or ".." in PurePosixPath(relative).parts
                or PurePosixPath(relative).is_absolute()
            ):
                continue
            matches = paths.get(
                str(PurePosixPath(config.get("library_root", "/Audio")) / relative),
                set(),
            )
            if len(matches) == 1:
                keys.append(next(iter(matches)))
        return keys

    async def reconcile(self, client, config, detail, desired):
        available_memberships = len(desired)
        # Plex's native playlist API deduplicates rating keys. Pig Music retains
        # every occurrence; Plex gets the order of the first available occurrence.
        desired = list(dict.fromkeys(desired))
        state = self.store.read_document("plex-playlist:" + detail["id"])
        marker = "Managed by Pig Music: " + detail["id"]
        if self.user_id and detail.get("favourites"):
            with self.store.connect() as conn:
                owner = conn.execute(
                    "SELECT id FROM users WHERE role='owner'"
                ).fetchone()
            legacy = self.store.read_document("plex-playlist:pig-favourites")
            if (
                owner
                and owner[0] == self.user_id
                and legacy.get("remote_id")
                and legacy["remote_id"] == state.get("remote_id")
            ):
                marker = "Managed by Pig Music: pig-favourites"
        remote = state.get("remote_id")
        if remote:
            try:
                item = (
                    await self.query(client, "GET", "/playlists/" + str(remote))
                ).find("Playlist")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 404:
                    raise
                item = None
            if item is None:
                remote = None
            elif state.get("status") == "creating" and not item.get("summary"):
                await self.query(
                    client, "PUT", "/playlists/" + str(remote), summary=marker
                )
            elif item.get("summary") != marker:
                raise ValueError(
                    "Playlist ownership changed; automatic editing stopped."
                )
        if not remote:
            existing = (await self.query(client, "GET", "/playlists")).findall(
                "Playlist"
            )
            owned = [p for p in existing if p.get("summary") == marker]
            if len(owned) > 1:
                raise ValueError("Multiple managed Plex playlists require review.")
            if owned:
                remote = owned[0].get("ratingKey")
            elif desired:
                title = detail["name"]
                if any(p.get("title") == title for p in existing):
                    title += " · Pig Music"
                uri = (
                    "server://"
                    + config["machine_id"]
                    + "/com.plexapp.plugins.library/library/metadata/"
                    + ",".join(desired)
                )
                created = (
                    await self.query(
                        client,
                        "POST",
                        "/playlists",
                        uri=uri,
                        type="audio",
                        title=title,
                        smart=0,
                    )
                ).find("Playlist")
                if created is None:
                    raise ValueError("Plex did not create the playlist.")
                remote = created.get("ratingKey")
                # Persist ownership immediately; restart can finish setting the marker.
                self.save(
                    "plex-playlist:" + detail["id"],
                    {**state, "remote_id": remote, "status": "creating"},
                )
                await self.query(
                    client, "PUT", "/playlists/" + str(remote), summary=marker
                )
        if remote:
            if not str(remote).isdigit():
                raise ValueError("Invalid Plex playlist identifier.")
            current = (
                await self.query(client, "GET", "/playlists/" + str(remote) + "/items")
            ).findall("Track")
            if [t.get("ratingKey") for t in current] != desired:
                # Add before removing or moving, so a failed provider request retains existing songs.
                have = defaultdict(int)
                for track in current:
                    have[track.get("ratingKey")] += 1
                missing = []
                for key in desired:
                    if have[key]:
                        have[key] -= 1
                    else:
                        missing.append(key)
                for key in missing:
                    uri = (
                        "server://"
                        + config["machine_id"]
                        + "/com.plexapp.plugins.library/library/metadata/"
                        + key
                    )
                    await self.query(
                        client, "PUT", "/playlists/" + str(remote) + "/items", uri=uri
                    )
                current = (
                    await self.query(
                        client, "GET", "/playlists/" + str(remote) + "/items"
                    )
                ).findall("Track")
                by_key = defaultdict(deque)
                for track in current:
                    by_key[track.get("ratingKey")].append(track.get("playlistItemID"))
                ordered = []
                for key in desired:
                    if not by_key[key]:
                        raise ValueError(
                            "Plex did not preserve the requested playlist membership."
                        )
                    ordered.append(by_key[key].popleft())
                after = None
                for item_id in ordered:
                    await self.query(
                        client,
                        "PUT",
                        "/playlists/"
                        + str(remote)
                        + "/items/"
                        + str(item_id)
                        + "/move",
                        **({"after": after} if after else {}),
                    )
                    after = item_id
                for remaining in by_key.values():
                    for item_id in remaining:
                        await self.query(
                            client,
                            "DELETE",
                            "/playlists/" + str(remote) + "/items/" + str(item_id),
                        )
                final = (
                    await self.query(
                        client, "GET", "/playlists/" + str(remote) + "/items"
                    )
                ).findall("Track")
                if [t.get("ratingKey") for t in final] != desired:
                    raise ValueError("Plex playlist order needs review.")
        self.save(
            "plex-playlist:" + detail["id"],
            {
                "remote_id": remote,
                "status": "synced" if desired else "waiting_for_files",
                "available_count": len(desired),
                "pending_count": detail["track_count"] - available_memberships,
                "repeated_count": available_memberships - len(desired),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def sync(self):
        if not self.user_id:
            with self.store.connect() as conn:
                ready = conn.execute(
                    "SELECT 1 FROM users WHERE role='owner'"
                ).fetchone()
            if ready:
                from .plex_accounts import PlexAccounts
                from .playlists import Playlists

                await asyncio.to_thread(PlexAccounts(self.store).migrate_owner)
                with self.store.connect() as conn:
                    users = [
                        r[0]
                        for r in conn.execute(
                            "SELECT p.user_id FROM plex_accounts p JOIN users u ON u.id=p.user_id WHERE u.disabled=0"
                        )
                    ]
                for identity in users:
                    if identity not in self.controllers:
                        self.controllers[identity] = Plex(
                            self.store, Playlists(self.store, identity), identity
                        )
                    await self.controllers[identity].sync()
                self.controllers = {
                    key: value
                    for key, value in self.controllers.items()
                    if key in users
                }
                return
        config = self.config()
        if not config.get("token") or not config.get("section_id"):
            return
        try:
            async with httpx.AsyncClient(
                base_url=config["url"],
                headers={"X-Plex-Token": config["token"]},
                timeout=20,
            ) as client:
                refresh_required = self.store.read_document("plex-refresh-required")
                if refresh_required:
                    await self.query(
                        client,
                        "GET",
                        "/library/sections/" + str(config["section_id"]) + "/refresh",
                    )
                    self.save("plex-refresh-required", False)
                cache_key = (
                    config["url"],
                    config["section_id"],
                    config.get("library_root"),
                    config["token"],
                )
                revision = self.store.library_revision
                if (
                    not self.path_cache
                    or self.path_cache[:2] != (cache_key, revision)
                    or self.path_cache[2] < time.monotonic()
                    or refresh_required
                ):
                    paths = await self.index(client, config)
                    self.path_cache = (
                        cache_key,
                        revision,
                        time.monotonic() + 60,
                        paths,
                    )
                else:
                    paths = self.path_cache[3]
                for card in self.playlists.list():
                    detail = self.playlists.detail(card["id"])
                    await self.reconcile(
                        client, config, detail, self.desired(detail, paths, config)
                    )
            self.save(
                "plex-status:" + self.user_id if self.user_id else "plex-status",
                {
                    "connected": True,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except (httpx.HTTPError, ValueError, ET.ParseError, KeyError):
            # Never put a token, signed URL or transport exception in a public document.
            self.save(
                "plex-status:" + self.user_id if self.user_id else "plex-status",
                {
                    "connected": False,
                    "error": "Plex playlist sync is unavailable. Existing playlists are retained.",
                },
            )

    async def run(self):
        while not self.stopping.is_set():
            await self.sync()
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=60)
            except TimeoutError:
                pass
