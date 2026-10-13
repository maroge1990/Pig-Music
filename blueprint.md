# Pig Music blueprint

Durable facts: the product contract, current state, the one roadmap, decisions and architecture. How to build, test and ship is in [AGENTS.md](AGENTS.md); operations in [docs/operations.md](docs/operations.md). Delivery history is in git (`git log`), not here. Update the current-state and roadmap sections when a delivery lands. Say whether each item is **delivered**, **in progress**, **planned** or **unverified**.

## Product contract

Pig Music is a private household music-library manager with one container, one interface, shared settings and one persistent download queue. It replaces the household's Lidarr, Soularr, Music Grabber and separate slskd containers. The slskd engine stays embedded inside Pig Music. Plex reads the same Synology files.

- Phone use should be quick: find an artist, see what is saved and what is available, then request an artist, album or song without choosing a backend. Desktop supports investigation and troubleshooting. Keep technical options in Settings or collapsed disclosures; ask the owner before adding nonessential main-interface controls.
- Preserve requested context. A live recording, compilation appearance or specific release edition keeps that identity. Conflicting known release or recording IDs never become a confident match just because the names are equal. Uncertain or ambiguous matches require review.
- Each person has their own library memberships over shared files. One exact file may back several memberships and is stored once. Removing a membership keeps files that are still needed elsewhere.
- Quality defaults apply system → artist → album, with album the most specific. Explicit upgrades **and downgrades acquire new source files**; never transcode to reach a target quality. Validate the replacement before retiring the existing file. Fallback order:
  1. preferred quality;
  2. MP3;
  3. AAC 256 kbps (lowest rank). AAC is used only when JioSaavn is an enabled source, only for requests made after this fallback was added, and never when the owner chooses to wait for lossless.

  Lower-quality saves are re-checked every `recheck_hours`. Upgrade jobs never fall back, and automatic improvements never downgrade.
- Import is reviewed before acquisition. An Apple XML playlist becomes a persistent ordered playlist. Available files appear in Plex immediately; missing files join after acquisition. Importing an inventory must not download everything.
- Favourites are a special playlist and membership only. Starring a missing song never submits a download.
- Existing music can be scanned without modification. Naming/tagging changes need a concrete review, recoverable originals and hash/path guards. Never bulk-reorganise music as a side effect of a code migration.
- Only multi-artist compilations are separated; a single artist's greatest hits stays with that artist. Soundtracks and musicals get their own sections. Empty section headings stay hidden.
- Internet access uses one public HTTPS origin (`https://music.markrogers.au` via Cloudflare Tunnel), gated only by Pig Music accounts. Tailscale remains the owner's administration route. People join only by a one-use invite link or QR code, never an external allowlist. See [internet access](docs/internet-access.md). Secrets stay server-side and never enter Git, bundles, logs, browser responses or docs.
- Fanart and ListenBrainz are optional. Without a key or token, their artist enhancements disappear quietly. Remote playback is experimental and provider-dependent; it never adds a file to the library. Household files play for every member without being added.
- The owner sees the member experience plus an Admin section, with admin options always at the bottom of shared views. Administration stays web-only.

## Current state (13 October 2026)

- **Live:** `listening-20261008-v1` on Unraid, released through `scripts/deploy_release.py`. Rollback container: `PigMusic-before-listening-20261008-v1`. Backup: `…/backups/pre-listening-20261008-v1`. Verify on the server before relying on this.
- **On `main`, not released:**
  - assessment priorities 1–2 (one quality vocabulary, Apple Music AU chart, Admin status);
  - invite links and the public-origin join flow;
  - the 9 October music bug fixes;
  - YouTube, SoundCloud and Monochrome acquisition adapters;
  - the native contract and AAC device copies;
  - the 12 October artwork and layout fixes;
  - the 14 October native fixes and features (N14A–D, W02, HH; see the roadmap).

  Schema migrations 7–9 are additive. Back up appdata before releasing, because rolling the image back does not reverse a migration.
- **Native:** iPhone/iPad and an embedded independent Watch app, version **0.2.0 (3)**, Pig family brand 1.7.0. Everyday browsing, personal actions, offline edits, background downloads, gapless/crossfade and Watch offline playback are implemented and simulator-verified. Physical-device acceptance is open. Signing uses a free Personal Team.
- **Not yet deployed or verified by agents:** the Cloudflare Tunnel (owner step in internet-access), and real provider transfers for the three new sources.

## Roadmap

Order is deliberate. Add entries with a stable ID and a gate. Reorder here; don't start a competing plan in another doc.

| # | ID | Work | Status | Gate |
| --- | --- | --- | --- | --- |
| 1 | REL | Release `main` to Unraid | Planned | `deploy_unraid.py --image` exact-image verification, then `deploy_release.py --apply`; backup first (migrations 7–9) |
| 2 | NET | Cloudflare Tunnel for `music.markrogers.au` | Owner step | Steps and rollback in [internet access](docs/internet-access.md); cellular sign-in, invite and lockout checks |
| 3 | V01/N08 | Physical iPhone, iPad and Watch Ultra 3 acceptance | Unverified | Device journeys in [testing](docs/testing.md#native-device-acceptance); simulator results don't count |
| 4 | SP | Real transfers for YouTube, SoundCloud and Monochrome from Unraid | Unverified | `scripts/verify_download_source.py` on an isolated output; codec playback on each Apple device |
| 5 | SC1 | SoundCloud uploader identity | Owner decision | Official uploads lack a structured artist credit; accepting uploader names would admit fan uploads |
| 6 | COV | Source coverage test: search-only, no downloads (`scripts/source_coverage.py`) | Delivered (first run 14 Oct, from the household network) | 159 recordings (Apple AU top 100 plus 59 curated). Confident matches: JioSaavn 81% (AAC 320, 0.6 s), YouTube 63% (~130 kbps, 23 s), Monochrome 61% (FLAC), zvu4no 45% (MP3), freemp3cloud 19% (MP3 320), SoundCloud 5% (mostly access errors). JioSaavn+zvu4no+freemp3cloud reach 144; adding YouTube reaches 149 (94%). Re-run from Unraid before changing download defaults |
| 7 | N14A | Native quick fixes: graphic-only request status, open the recommended edition (other editions at the bottom), Full discography link at the bottom of both artist pages, album artist name opens the right artist page, Search artists open the full artist page (with a library link), catalogue pages draw from memory, splash held until the first refresh | Delivered, unverified | Built and unit-tested; not seen on a simulator or device (the app needs an HTTPS server). Device check of each journey and the launch flash |
| 8 | N14B | Requested albums appear in full in the library, pending songs with status graphics | Delivered, unverified | Projection-only (no schema change); test covers merge, failed, replacements and counts. Compare a production-state projection before release |
| 9 | N14C | Downloads: Clear finished (Server, iPhone, Watch); On this device grouped by album and playlist, with remove buttons | Delivered, unverified | PigKit test covers the album-and-playlist rule; device check |
| 10 | N14D | Native graphical artist page (background, logo, scroll fade) matching the web | Delivered, unverified | Device check with and without Fanart |
| 11 | W02 | Watch redesign: Now Playing, Playlists, Artists, Albums, Songs; send playlists and artists from the phone; sent playlists update automatically | Delivered, unverified | Watch Ultra 3 and Series 7 |
| 12 | HH | Household songs play for every member without adding them first | Delivered | Streaming only; device copies still need membership. Security test covers it |
| 13 | U01-4 / R17 | All client calls on `/api/v1`, owner APIs as `/api/v1/admin`; then retire legacy routes | Planned | Test rejecting unversioned client paths; needed before any native Admin |
| 14 | R18 | Admin uses the shell's `/api/v1/events` stream | Planned | One visibility-aware fallback poll |
| 15 | R19 | Playwright smoke tests (album cover, ambiguous artist, Home order, Admin status) at 1366/375 px, both themes | Planned | Runs in CI |
| 16 | R12–R15 | Library vs catalogue artist pages, request-centred Downloads, type-ahead Search, identifiable device sessions | Planned | Assessment priority 3 |
| 17 | RET | Prune old backups/containers listed by `deploy_release.py --retention 2` | Owner decision | The tool never deletes; keep `pre-first-run-20261007-v1` and legacy manager material |
| 18 | P03 | Mac app; standalone Watch sign-in; CarPlay; cross-device queue handoff; advanced import matching | Future | After V01 |
| 19 | S01/S02 | Shazam capture → song inbox; optional direct recognition | Future | Find a supported access route first |
| 20 | R01 | Remote playback from more lossy sources | Delivered, partly verified | Never lossless. JioSaavn streams directly; otherwise the server fetches the first confident match from zvu4no, freemp3cloud, then YouTube (AAC preferred) into `remote-cache/` (an hour, 500 MB) and serves it through a link signed for that listener. Live check from the Mac: zvu4no 7 s, YouTube 28 s; freemp3cloud was returning no results at the time. Check playback on each Apple device |

Polish backlog: a single Apple XML import entry point; artist names on album tiles; splash only on loading surfaces; retire the plain LAN port `192.168.1.235:8765` once the tunnel is live; turn off Cloudflare Web Analytics for the hostname.

## Decisions

- **Phase 1 (Oct 2026):** One app owns orchestration and publication, with slskd embedded and upstream parsers reused under `server/vendor/` (licences retained). Never recreate separate managers.
- **Identity:** Compilation, live and request context take precedence. Identical copies may serve several places but are stored once.
- **Quality:** No conversion. System defaults with artist/album overrides in both directions; acquire and validate a new source, then retire the old file.
- **Playlists:** Plex shows available songs immediately and updates as missing ones arrive. Plex dedupes repeated songs; Pig Music keeps every ordered occurrence.
- **6 Oct:** Docs consolidate into this blueprint as the single roadmap. GHCR (`ghcr.io/maroge1990/pig-music`, private) is the release channel for the existing Unraid server.
- **7 Oct:** Accounts with personal libraries; owner bootstrap through the first-run WebUI with a console installation code. Docker Manager (`unraid/PigMusic.xml`) is the only management source; Compose is retired.
- **9 Oct:** Internet via Cloudflare Tunnel gated by Pig Music accounts, not Cloudflare Access (a second guest list that would block the native app). Two artist pages: library = play what you have, catalogue = find what you could have. Members keep their own quality. Recommendations sit above popularity. Popular in Australia comes from Apple only. ListenBrainz is kept only for LB Radio similarity and per-artist popularity. A one-time owner choice is acceptable for ambiguous artists.
- **11 Oct:** All seven acquisition sources are implemented. Existing source lists and defaults are unchanged.
- **12 Oct:** Layout: integrated phone player/tab dock, settings below the music on detail pages, compact headers, and Home without song recommendations (web and native). Watch music lives on the Watch, prepared by the paired phone; the Watch never receives server credentials.

- **14 Oct:** Search artist results open the full artist page, which links to the library page. Household files play for any member without being added first; adding still creates a library membership. A device download that belongs to both an album and a playlist shows under both, and the file stays on the device until both are removed. Playlists sent to the Watch update automatically. Remote playback never streams lossless, even on Wi-Fi; MP3 sources come first.

## Architecture

One Unraid container supervises FastAPI and a pinned internal slskd. FastAPI serves the React/Vite bundle. SQLite owns the durable queue, acquired records, playlists, preferences, accounts and metadata documents. Appdata holds the snapshot, private connection files, artwork and operation journals. NAS music is the source of truth; scanning refreshes the projection. There is no filesystem watcher, so use Scan library after external changes.

| Area | Source |
| --- | --- |
| HTTP composition, provider lifetime | `server/app.py`, `server/routes/` |
| Durable state, queue claims, library refresh | `server/store.py`, `server/migrations/` |
| Album grouping, Apple XML import; classification | `server/library.py`; `server/releases.py` |
| Contextual matching | `server/matching.py` |
| MusicBrainz cache and rate limit | `server/catalogue.py` |
| Acquisition, validation and tagging; sources | `server/downloader.py`, `server/providers/`, `server/soulseek.py`, `server/vendor/` |
| Quality and replacement | `server/quality.py` |
| NAS boundaries, publication, recovery, organisation | `server/storage.py`, `server/exporter.py`, `server/recovery.py`, `server/organisation.py` |
| Scanning | `server/scanner.py` |
| Accounts, security, transport | `server/auth.py`, `server/security.py`, `server/transport.py` |
| Personal libraries, removal | `server/user_library.py`, `server/personal_removal.py` |
| Playlists, favourites, Plex | `server/playlists.py`, `server/plex.py` |
| Playback, remote resolution, device AAC copies | `server/media.py`, `server/remote.py`, `server/device_copies.py` |
| Artwork, enrichment, pre-cache | `server/artwork.py`, `server/cover_store.py`, `server/enrichment.py`, `server/warmer.py`, `server/popularity.py` |
| Web client | `client/src/` (`api.ts`, `AppShell.tsx`, `SongRow.tsx`, `Player.tsx`) |
| Native | `swift/PigKit` (API, store, sync, playback, downloads), `swift/PigMusic`, `swift/PigMusicWatch`; contract `api/` ↔ `swift/PigKit/Sources/PigAPI/openapi.json` |
| Runtime supervision | `server/runtime.py` |

**Identity invariants:**
- Snapshot track IDs stay stable; acquired records supersede them for published replacements.
- Album edition anchors (`album-edition-anchors` document) keep the original album ID on its first known edition, so scan order cannot move links or preferences between editions. Unknown tags may join a sole known edition but never choose among several.
- Removal exclusions are edition-aware, and a restore clears only its own exclusions.
- Queue workers use claim tokens, so a cancelled or stale worker cannot publish into a reused request ID. Artist jobs use a separate generation guard.

Change none of these without migration fixtures and a backed-up production-state comparison.

## Household topology

- **Unraid host:** `192.168.1.235`, container **PigMusic**, managed by Docker Manager (template `/boot/config/plugins/dockerMan/templates-user/my-PigMusic.xml`, source `unraid/PigMusic.xml`).
- **Networks:** bridge `pig-music-preview` at 172.25.0.2 and `br0` at `192.168.1.203:8765`. Preserve both and their gateway priorities.
- **Private HTTPS:** `https://passyflix.tail6d1471.ts.net:10000` through Tailscale Serve. The other service on 8443 is unchanged. Trusted proxies: `127.0.0.1,172.25.0.1`.
- **Storage:**
  - Appdata: `/mnt/user/appdata/pig-music-preview/data`.
  - Music: `/mnt/remotes/SERVER01_Audio` → `/library`.
  - Workspace: `/library/.pig-music-work`.
  - Recovery originals: `.pig-music-trash`.
  - Backups: `/mnt/user/appdata/pig-music-preview/backups/`.
- **Protections:** UID/GID 99:100, read-only root, dropped capabilities, no-new-privileges, two CPUs, and a 1–8 GiB memory limit (template 4 GiB; release gates test under 1 GiB). The internal engine API binds to loopback only.
- **Test devices:** iPhone 16 Pro Max (iOS 27), iPhone 12, Apple Watch Ultra 3 (watchOS 27) and Series 7.

## Known limits

- Experimental remote playback may fail or be slow; saved playback is independent of it.
- Provider metadata and availability are external. Optional enrichment must never block browsing or expose credentials.
- If the NAS disappears, cached browsing and settings stay available, while managed writes and transfers pause. Never create a substitute empty library or bypass the marker check.
