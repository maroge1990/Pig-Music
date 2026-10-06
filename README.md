# Pig Music

Private household music-library management in one Unraid container, with shared settings, a durable download queue and an embedded Soulseek engine. Verified files publish into the existing Synology library read by Plex.

**Start with [blueprint.md](blueprint.md).** It is the primary handover, current status, product contract, prioritised roadmap and running decision dialogue. [Documentation map](docs/README.md), [operations](docs/operations.md) and [testing](docs/testing.md) contain current procedures; historical milestones are archived.

## Capabilities

- Saved/discovered music browsing, artist portraits/backgrounds, discographies and optional popular songs/albums.
- Song, album and artist requests, optional monitoring, parallel transfers and recoverable queue state.
- Soulseek, FreeMp3Cloud, zvu4no and JioSaavn acquisition adapters, with actual-file validation before publication.
- System/artist/album quality preferences, replacement upgrades and explicit downgrades, fallback and periodic improvement checks. No conversion to obtain download quality.
- Native initial/incremental scanning, reviewed naming/tagging, recoverable removal/restore and undo.
- Reviewed Apple XML imports, ordered playlists, favourites without automatic downloading and single-owner Plex playlist export.
- Saved playback, experimental provider-dependent remote listening and system-default light/dark appearance.

Household profiles, two library memberships and per-user Plex integration are planned Phase 1b, not delivered capabilities. Physical iPhone/off-site checks and remote-provider limits are recorded in the blueprint.

## Development and delivery

Use Python 3.14, Node 24 and FFmpeg. Install the locked Python dependencies in a virtual environment and run `npm ci` in `client/`. Fresh appdata is empty and downloads are paused. Use the native scanner for existing files; the retired containers are not prerequisites.

```powershell
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
Set-Location client
npm test
npm run build
```

Full setup, formatting checks and isolated candidate tests are documented in [operations](docs/operations.md) and [testing](docs/testing.md). `scripts/deploy_unraid.py` is the source-only build/test/deploy procedure; it preserves live state and rollback material. Local `compose.yaml` and household `compose.unraid-preview.yaml` have different storage assumptions.

Private runtime data, credentials, caches, exports and research checkouts stay outside Git and deployment source bundles. The app is intended for the authorised LAN/Tailscale environment. Preserve NAS-marker, path/hash, cancellation and replacement safeguards through changes. Upstream provenance/licences remain under `server/vendor/`.
