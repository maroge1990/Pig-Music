# Operations and recovery

Current guidance. Read [blueprint.md](../blueprint.md) for the product contract and handover status. Historical deployment instructions in `archive/` are not current commands.

## Local development

Python 3.14, Node 24 and FFmpeg are the container runtimes. Install project dependencies into a virtual environment and use `npm ci` in `client/`. Build the client before serving FastAPI.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt -r requirements-dev.txt
Set-Location client
npm ci
npm run build
Set-Location ..
$env:PIG_MUSIC_DATA = "$PWD/.localdata/dev"
$env:PIG_MUSIC_PRELOAD = "false"
.venv/Scripts/python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8765
```

Fresh appdata starts empty and downloads paused. Use the native Scan library against the explicitly configured music directory, then review any matching or organisation changes. The Import screen starts empty; it does not automatically load the historical Favourites export. `scripts/seed_prototype.py` is an explicit optional import tool and queues nothing. Retired Music Grabber is not required for ingestion.

`compose.yaml` is an isolated local example; `compose.unraid-preview.yaml` describes the current household NAS deployment. Do not assume they mount the same music. `PIG_MUSIC_LIBRARY` selects the scan/playback root; `PIG_MUSIC_DOWNLOAD_ROOT` selects the managed workspace. Direct NAS mode requires the export configuration's `library_id` to match the marker on the expected library.

## Private configuration

Keep these under appdata, excluded from source control/bundles and accessible only to the runtime owner:

| File | Purpose / required fields |
| --- | --- |
| `slskd-connection.json` | Internal API `url`, `api_key`, engine `download_root` mapping |
| `engine/engine.env` / `engine/slskd.yml` | Engine login/runtime configuration; internal API stays loopback-only |
| `media-settings.json` | Portrait/remote toggles and optional `fanart_key`, `listenbrainz_token`; public API returns configured flags only |
| `plex-connection.json` | `url`, owner `token`, `section_id`, `machine_id`, Plex-visible `library_root` mapping |
| `library-export.json` | Publication `enabled`, expected `library_id`, relative `marker_path` and optional publication folder settings |

Use existing authorised credentials; this document deliberately contains no values. Download/quality preferences, membership and queue state are in SQLite. Back up the entire appdata directory, not just one connection file.

## Candidate and live delivery

Use a unique version suffix. From the repository root:

```powershell
# Replace this sample suffix with a new, unique release name.
.venv/Scripts/python.exe scripts/deploy_unraid.py --version candidate-yyyymmdd-v1
```

This allowlists source, uploads to a new release directory on Unraid, builds the image and runs backend tests in a separate Linux container as `99:100`, without networking or live appdata/music mounts. The frontend builds inside the image. It does not deploy unless `--deploy` is included.

For an authorised delivery, use a **new** version suffix and include `--deploy` in that invocation. Existing `cleanup-20261006-v1/v2/v3` names are already used; choose a new suffix for the next release. Each invocation builds and tests its exact source before any live update; it does not resume an earlier release directory. The tool checks for active transfers, pauses downloads, stops the old container, backs up appdata/Compose, verifies migration on a disposable copy, retains the old container, applies the reviewed Compose with the candidate image, checks readiness/storage and read-only APIs, then restores the original download settings. An active transfer defers deployment rather than interrupting it. Run frontend journey checks and compare performance against the release before declaring completion.

The default topology is recorded in the blueprint. `--host`, `--key` and `--url` allow explicit access overrides; this is a household deployment tool, not a generic infrastructure provisioner. A version's release directory must not already exist. Do not use unique names to claim an untested image is equivalent to a passing candidate.

Historical tools `package_unraid_preview.py` (private initial bootstrap), `unraid_preview_smoke.py` (real provider acquisition probe) and `export_library_snapshot.py` (retired Music Grabber snapshot extraction) are retained for migration history. They are not required for normal delivery or fresh-library ingestion.

Each live release uses a unique Compose project name (`pig-music-<version>`). A renamed container retains its old Compose service labels; reusing that project would let Compose delete the rollback container during recreation. Keep external network names/static LAN address unchanged. The unique-project behaviour was verified with isolated stopped containers. The current release uses the unique project `pig-music-audit-followup-20261007-v1`; its stopped predecessor and matching backup are retained.

## Rollback and partial failures

Automatic rollback retains the failed candidate and restores the previous container/Compose when possible. Read the command result: a failed rollback is not recovery. A failed update must leave downloads paused until the correct library and state are confirmed.

Manual recovery order:

1. Inspect container names/images and queue/storage status without dumping private environment values.
2. Stop the candidate before reconnecting the former container to the static LAN address. Disconnect the candidate from `br0` so there is no IP collision.
3. Restore the prior container name/network wiring and corresponding Compose from the stopped-state backup; start it and verify health, storage marker and API reads.
4. Restore original download settings only after readiness. Compare library track counts, playlist membership and queue state.
5. If durable state needs restoration, stop all app writers first and restore a matching appdata backup. Do not blindly restore old state after new music has published: compare journals/files and use guarded recovery to reconcile changes.

Backups live below `/mnt/user/appdata/pig-music-preview/backups/`; retained containers identify their release suffix. Keep old manager recovery material and images until explicitly retired by the owner. Do not purge trash, backups or old images as an incidental cleanup.

## Troubleshooting

- **NAS unavailable:** cached browsing/settings remain available; engine/workspace creation and downloads wait for the correct marker. Restore the actual SMB mount, not an empty local folder. Verify storage availability and engine connection before resuming transfers.
- **Missing external changes:** use Scan library. There is no live filesystem watcher.
- **Missing artwork/popularity:** check configured flags and provider availability. Optional failures hide enrichment; library browsing should remain usable.
- **Playlist missing in Plex:** verify the single-owner connection and path mapping, then file publication/Plex indexing. Pig Music retains the complete ordered membership while Plex receives available files. Ownership markers prevent edits to unrelated playlists.
- **Slow remote listening:** provider resolution is independent from library response. Saved-file playback is preferred; remote listening is experimental and does not queue or save a song.
- **Quality mismatch:** inspect actual file format/bitrate and effective system/artist/album preference. Preserve existing music until a validated replacement completes. Do not bypass complete-file decoding to make the queue faster.

## Registry images

The owner has selected GHCR for the existing Unraid server. See [container releases](container-releases.md). Use `deploy_unraid.py --image ghcr.io/maroge1990/pig-music@sha256:<digest>` to verify a published image against its exact source commit. The normal backup, migration and explicit live-release safeguards still apply.

## Private HTTPS transition

The approved PigMusic endpoint is `https://passyflix.tail6d1471.ts.net:10000`. Keep the other service on 8443 unchanged. See [T01 delivery](t01-delivery.md) for source/proxy configuration and verification status. Both iPhones must run Tailscale and be tested on LAN and cellular before retiring the existing private LAN URL.
