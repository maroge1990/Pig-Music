# Pig Music blueprint and engineering handover

Primary handover document. Updated 7 October 2026 (Australia/Melbourne).

Read this document first. It records the product contract, current implementation, prioritised future work and the decisions behind it. Update it at the end of every meaningful delivery, including verification and any remaining gaps. A plan is not evidence of delivery: distinguish **delivered**, **in progress**, **planned**, **proposed** and **unverified**.

## Product and non-negotiable behaviour

Pig Music is a private household music-library manager with one container, one interface, shared settings and one persistent download queue. It replaces the household's Lidarr, Soularr, Music Grabber and separate slskd containers. The slskd engine remains embedded inside Pig Music. Plex reads the same Synology files and remains the principal listening app during Phase 1.

- Phone use should be quick: find an artist, inspect saved and available music, then request an artist, album or song without choosing a backend. Desktop supports investigation and troubleshooting. Keep technical and advanced options in Settings or collapsed disclosures; ask the owner before adding nonessential main-interface controls.
- Preserve requested context. A live recording, compilation appearance or specific release edition must retain that identity. Conflicting known release or recording IDs never become a confident match based on equal names. Uncertain or ambiguous matches require review.
- The same exact file may support multiple memberships and be stored once. Removing a membership must retain files still needed elsewhere. Household libraries are deferred to Phase 1b.
- Quality defaults apply system → artist → album, with album most specific. Explicit upgrades **and downgrades acquire new source files**; never transcode to obtain a target quality. Validate the replacement before retiring the existing managed file. Lossless fallback and periodic improvements are supported. Automatic improvements never downgrade.
- Import is reviewed before acquisition. An Apple XML playlist becomes a persistent ordered Pig Music playlist. Available files appear in Plex immediately; missing files join after acquisition/publication/indexing. Importing an inventory alone must not download everything.
- Favourites are membership only. Starring a missing song must never submit a download.
- Existing music can be scanned without modification. Naming/tagging changes need a concrete review, recoverable originals and hash/path guards. Do not bulk reorganise music as an incidental code migration.
- Separate only multi-artist compilations; single-artist greatest hits remain with their artist. Soundtracks and musicals have separate sections. Empty section headings stay hidden.
- Private deployment uses LAN/Tailscale. Do not add public exposure or new authentication assumptions. Existing secrets remain server-side and must not enter Git, bundles, logs, browser responses or handover documents.
- Fanart and ListenBrainz are optional. Without a configured key/token, their optional artist enhancements should disappear naturally.

## Current status and evidence

Phase 1a operates independently on live NAS data. The four old container definitions have been retired; recovery data/images remain. The approved cleanup was delivered as `pig-music:cleanup-20261006-v3` on 6 October 2026. A01 and D01 were delivered on 7 October 2026. The current release is **`audit-followup-20261007-v1`**, including A01–A03, approved B01/B02 branding, M00 migrations, private HTTPS and the remaining accessibility/grid/artwork/token audit fixes. Exact-image and live acceptance are recorded in `docs/audit-followup-delivery.md`. The Phase 1a image `pig-music:preview-20261006-phase1a-final-v2` remains retained as historical recovery material; the immediate rollback is recorded with the current release.

Existing delivered capabilities include local/discovered search, artwork, artist discographies, popular songs/albums, saved and experimental remote playback, song/album/artist acquisition, optional artist monitoring, quality replacement/fallback/upgrades, scans, recovery/restore, reviewed organisation, Apple XML import, custom playlists, favourites and a single Plex owner integration.

The pre-cleanup milestone verified 1,395 files with zero missing/read failures, 25 managed files indexed in Plex, genuine MP3→FLAC→MP3 replacement, restart persistence and 98 backend tests in an isolated Linux container. It is archived evidence, not a claim that every current UI journey or external provider has been verified.

The cleanup review found fresh Import missing its file input, inconsistent edition matching/grouping/removal, repeated 20.6 MB snapshot reads, expensive playlist matching, overlapping polling, dead search code/styles and inconsistent playback branding. See [the audit](docs/cleanup-review-20261006.md) for baseline measurements and work packages. In particular, playlist listing had a five-request LAN median of 830 ms while library summary was 16 ms. Do not label five samples as p95.

### Cleanup delivery, 6 October 2026

- Shared indexed matching now serves import, discovery, playlists and favourites. Edition anchors retain prior album links/preferences; removal/exclusion/cancellation respects the edition. Saved-song fallback uses the in-memory snapshot index rather than reparsing the snapshot.
- Browser requests share transport and mounted song membership is batched. Restart-safe content fingerprints replace repeated full-library/migration refreshes on queue ticks. Idle release/popular-song polling stops, hidden-page work pauses, artist scans yield to foreground metadata, and discography pagination fetches visible pages. Artist-job cancellation uses generation guards.
- Shared song controls and saved/discovered artist presentation reduce duplicated UI. Search dead state and 59 obsolete style rules were removed; unused TypeScript declarations are checked. Mobile player metadata remains readable with protected dark/rose playback colours in both appearances. Settings spacing, album disclosures and playlist/direct artist links were checked.
- Missing/wrong NAS markers permit cached browsing/settings but block workspace creation and managed writes. The runtime retries engine startup after the mount returns. Fanart metadata is shared by portraits/backdrops and changes its cache key when credentials rotate.
- Documentation is consolidated into this blueprint plus current operations/testing guidance; 19 historical records are archived and labelled. Deployment uses source-only bundles, pinned image bases/lockfiles, isolated candidate tests, stopped-state backups and a migration check against a disposable copy of that backup.

Verification: **106 backend tests passed on Windows and in the final isolated Linux image**, both frontend regression tests passed, strict TypeScript/build and Black/Prettier checks passed. The production-state migration check retained **1,395 tracks**, all existing album links and every existing durable row (queue, preferences, memberships), with only the additive edition-anchor document permitted. Live health confirms the NAS is available, downloads enabled as before, Soulseek connected and Plex connected; all 25 managed files are still indexed in Plex. All 27 existing queue entries remain completed.

A final read-only NAS check opened all **1,395 files** with **zero missing files/read errors**, and all **25 managed file hashes matched** their validated records. The check did not modify files or submit downloads. All 27 Markdown documents passed the local-link check.

Disposable browser journeys verified fresh XML import/review, favourite without acquisition, creating/adding a playlist, durable playlist reload and switching views, actual saved playback, readable phone player labels, and light/dark/system appearance. Live browser checks verified artist artwork/enrichment, separated dropdown search and direct discovered-artist navigation. Physical iPhone smoothness and off-site access remain V01, below. No new live acquisition or bulk file organisation was performed during this cleanup.

Post-deployment performance: 1,395-track live library; Windows over LAN; one warmup and **30 sequential samples per endpoint**, nearest-rank p95. Baseline medians used five samples; compare medians, not inferred baseline p95.

| Read-only endpoint | Baseline median | Cleanup median | Cleanup p95 |
| --- | ---: | ---: | ---: |
| Library summary | 16.1 ms | 16.49 ms | 22.66 ms |
| Artist detail | 9.1 ms | 8.61 ms | 10.47 ms |
| Album detail | 4.2 ms | 4.40 ms | 5.59 ms |
| Queue | 14.3 ms | 13.92 ms | 17.62 ms |
| Playlist cards | 830.0 ms | **22.52 ms** | 46.69 ms |
| Local search | 45.4 ms | 30.64 ms | 34.27 ms |
| Migration inventory | 41.2 ms | 30.19 ms | 38.40 ms |
| Organisation review | 1,421.8 ms | 1,243.00 ms | 2,161.43 ms |

Playlist cards are approximately **37× faster** by median. Cached local browsing meets the proposed 100 ms p95 gate and playlist cards the 150 ms gate. Organisation review remains a slower explicit NAS operation; preserve its fresh path/hash safeguards. These figures do not establish cold-provider latency, remote-stream reliability or physical-device performance. Synthetic matching of 200 songs took about 1.8 ms at 1k, 10k and 50k indexed tracks; index construction took 4.34, 42.70 and 259.41 ms respectively. Reproduce with the benchmark scripts in [testing guidance](docs/testing.md).

Release image digest: `sha256:6eac49803706839ce8404733d93a6c7e993a544253ee7dfd5d900a0625964bfa`. Stopped-state backup: `/mnt/user/appdata/pig-music-preview/backups/pre-cleanup-20261006-v3`; retained prior container: `pig-music-preview-before-cleanup-20261006-v3`. Release source and final handover: `/mnt/user/appdata/pig-music-preview/releases/cleanup-20261006-v3`. The immediate rollback image is `pig-music:cleanup-20261006-v2`; its stopped container was recreated with the existing resource/storage protections after Compose selected its old service labels. The deployment tool now uses unique Compose project names, verified with isolated stopped containers, to preserve renamed predecessors. The pre-cleanup container/image and backup are also retained under the `pre-cleanup-20261006-v2` / `before-cleanup-20261006-v2` suffix. Do not remove these recovery artifacts during Phase 1b design.

The release directory retains `source.tar.gz` as the original tested build input and `handover.tar.gz` as the closing source/documentation package. The latter adds final evidence, archived documents and the corrected deployment tooling; its runtime/backend/frontend/test source is checked against the tested input. The extracted blueprint and current docs are also available directly in that directory. Neither package includes appdata or credentials.

## Prioritised roadmap

Order is deliberate. Add new entries with a stable ID, rationale, dependencies and status; reorder here rather than leaving contradictory plans in scattered milestones.

| Priority / ID | Feature or work | Status | Dependencies / completion gate |
| --- | --- | --- | --- |
| 1 / C01 | Approved cleanup: canonical matching, edition-safe identities/removal, indexed reads, batched membership, shared requests/navigation/components, brand/mobile polish, provider scheduling, documentation and reproducible deployment | Delivered, 6 October 2026 | Verified image/evidence above; retain regression coverage and rollback material |
| 2 / A01 | Content-addressed artwork, metadata-only snapshots, streaming migration, edition artwork, rescan detection and safe pruning | Delivered 7 October 2026; live migration and integrity checks passed | [A01 evidence](docs/a01-cover-store.md); 117 image tests, Linux/Unraid 1 GB gates and stopped-state migration passed |
| 2 / A02 | Non-blocking enrichment, derivatives, immutable caching and incremental provider work | Delivered 7 October 2026; image, scale and live HTTP gates passed | [A02/A03 evidence](docs/a02-a03-delivery.md) |
| 2 / A03 | Library compression/conditional reads, indexed lookups and grid performance | Delivered 7 October 2026; image, scale and live HTTP gates passed | [A02/A03 evidence](docs/a02-a03-delivery.md) |
| 3 / B01–B02 | Brand tokens/type and final PigMusic identity integration | Delivered 7 October 2026; local, image and production checks passed | Approved Pig family 1.4.0; see [branding delivery](docs/b01-b02-delivery.md) |
| 2 / D01 | GitHub-linked GHCR image releases for the existing Unraid deployment | Delivered 7 October 2026; published and running on Unraid | [Container releases](docs/container-releases.md); immutable digest, image tests, stopped-state migration and authorised switch |
| Alongside foundations / S00 | Unbranded iPhone/Watch feasibility spike | Preparation and unsigned device IPA built; actual-device proof pending | [Native spike](docs/native-spike.md); free-account Sideloadly installation/refresh and private HTTPS/device tests |
| 2 / V01 | Physical iPhone scrolling/player checks and a real off-site Tailscale session | Unverified acceptance work | Owner's device/off-site session; emulator/LAN results are insufficient |
| 1 / U01 | One experience: Home · Search · Library · Account for everyone, plus Admin for the owner; owner additions always at the bottom of shared views; retire the nested legacy shell | Delivered on `main`, not yet released | [Review and combined roadmap](docs/review-roadmap-20261007.md) §4–6; owner and member browser fixture at desktop and 375 px |
| 1 / N13 | Per-person library validators (shared-browser 304 leak) | Fixed on `main`, not yet released | Regression test; release before inviting members |
| 1 / R03 | Routine account release (`deploy_release.py`) with retention reporting | Delivered on `main`; first live use pending | Required to release anything after first-run; see operations |
| 2 / Q02, U03 | Web-session UI contract tests, full route audit, type scale, single song actions | Delivered on `main` | Remaining: Playwright smoke run |
| 2 / U01-4 | Owner APIs as `/api/v1/admin` in the OpenAPI contract | Planned | Before a native Admin tab |
| 3 / H01 | Phase 1b household profiles and two library memberships over shared file assets | Planned; design first | Cleanup stable; agree ownership, sharing/removal semantics, visibility and scan mapping before implementation |
| 4 / H02 | Per-user favourites/playlists and Plex owner/account export mapping | Planned | H01; validate native Plex users and each library mapping without changing another owner's playlists |
| 5 / H03 | Overlapping album membership, shared quality policy and disk ownership across household libraries | Planned design question | H01; decide what happens when users request different editions or qualities; do not guess precedence |
| 6 / S01 | Shazam capture → song inbox/request workflow | Planned Phase 2 investigation | Prefer a reliable share/import route first; determine supported access to the user's private Shazam library and review/matching behaviour before promising automatic sync |
| 7 / S02 | Optional direct recognition/listening capability | Future Phase 2 | Investigate supported APIs/platform requirements and keys; preserve requested recording context |
| 8 / P01 | Native iOS playback and library management | Future Phase 3 | Stable account/library API, playback contract and offline membership model; Mac available for Apple development |
| 9 / P02 | Apple Watch playback with offline downloads | Future Phase 3 | P01; watch storage, transfer, sync and background behaviour require actual-device testing |
| 10 / R01 | Additional remote-playback sources or replacement provider | Proposed experiment, not a reliability promise | Measure resolution latency, ambiguity and availability; owner is comfortable removing remote playback if inconsistent |

Current remote playback is experimental and provider dependent. It never adds a file to the library. Do not confuse acquisition adapters with fast streaming providers or reintroduce an inactive Monochrome prototype as though it were a supported source.

## Running decision dialogue

Append dated entries with **Owner direction → Engineering response → Result/next question**. Keep current decisions reflected in the sections above; this log preserves why they changed.

- **Phase 1 discovery, carried forward:** Owner requested one integration application, shared library, queue and settings, with Music Grabber sources as fallbacks where Soulseek is missing music. Engineering response: app-owned orchestration/publication plus embedded slskd and reused adapter parsers; retain upstream licence notices. Result: independent container delivered; do not recreate separate managers.
- **Library/version policy, carried forward:** Owner said compilation/live/request context takes precedence and identical copies can be used in multiple places but stored once. Response: conservative contextual matching and future asset/membership separation. Result: cleanup strengthens edition handling; household ownership remains a Phase 1b design dependency.
- **Quality clarification, carried forward:** Owner explicitly prohibited conversion and requested system defaults with artist/album overrides in both directions. Response: acquire and validate a new source, then retire the previous file. Result: live replacement was verified; retain recovery/failure checks through refactors.
- **Playlists/favourites, carried forward:** Owner approved Plex showing available songs immediately and updating as missing songs arrive; favourites should not implicitly acquire songs. Result: these are acceptance requirements for every delivery.
- **Storage/access, carried forward:** Owner approved direct existing SMB folder publication and existing Tailscale access. Per-user Plex work was deferred until the single-owner functionality worked. Result: no additional public exposure; NAS marker identity remains required before managed writes.
- **6 October 2026 — cleanup review:** Owner requested a full review of integration, redundancy, interface, brand and speed. Response: reproduce defects, measure live read-only behaviour and scope five ordered packages. Result: review delivered without live changes.
- **6 October 2026 — cleanup endorsement:** Owner endorsed the cleanup and added consolidation of all documentation plus a prioritised running blueprint as the primary engineering/agent handover. Response: implement the approved packages, archive historical milestones, establish current architecture/operations/testing guidance and record verified delivery here. Result: in progress; append final verification rather than silently changing this entry to a completion claim.
- **6 October 2026 — cleanup delivery:** Engineering delivered `cleanup-20261006-v3`, with 106 passing backend tests on both platforms, isolated production-state migration verification and the live measurements above. Result: existing library/state retained; playlist-card median improved from 830 to 22.52 ms. Next: owner physical-phone/off-site acceptance, then agree Phase 1b ownership and Plex mappings before adding household complexity. Future decisions should append here and update the prioritised table, rather than start another competing roadmap.

## Architecture and source map

One Unraid container supervises FastAPI and a pinned internal slskd binary. The React/Vite bundle is served by FastAPI. SQLite owns durable queue, acquired records, playlists, preferences and metadata documents. Appdata holds the snapshot, private connection files, artwork caches and operation journals. NAS music remains the source of truth for files; scanning refreshes the application projection.

| Area | Source / responsibility |
| --- | --- |
| HTTP composition and provider lifetime | `server/app.py` |
| Durable state, queue claims, preferences, library refresh | `server/store.py` |
| Album grouping and Apple XML ingestion/review | `server/library.py` |
| Indexed contextual matching | `server/matching.py` |
| Catalogue cache/rate limiter and editions | `server/catalogue.py`; release classification in `server/releases.py` |
| Acquisition and complete-file validation/tagging | `server/downloader.py`; Soulseek API adapter `server/soulseek.py`; upstream parsers under `server/vendor/` |
| Artist requests/monitoring | `server/artist_jobs.py`; generation-guard progress/cancellation |
| Preferred/fallback quality and replacement bookkeeping | `server/quality.py`, quality methods in `server/store.py` |
| NAS boundaries/publication and recovery | `server/storage.py`, `server/exporter.py`, `server/recovery.py`, `server/organisation.py` |
| Initial/incremental tag scan | `server/scanner.py` |
| Playlist/favourite membership and Plex | `server/playlists.py`, `server/plex.py` |
| Playback/file range requests and optional remote resolution | `server/media.py`, `server/remote.py`, `client/src/Player.tsx` |
| Artwork / optional rankings | `server/artwork.py`, `server/portraits.py`, `server/fanart.py`, `server/artist_backgrounds.py`, `server/popularity.py` |
| Shared browser transport, membership, navigation/actions | `client/src/api.ts`, `membership.ts`, `navigation.ts`, `SongControls.tsx`, `SongActions.tsx` |
| Main UI composition and views | `client/src/main.tsx` plus feature components |
| Runtime supervision | `server/runtime.py` |

### Identity and migration notes

Snapshot track IDs remain stable; acquired records supersede snapshot IDs/paths for published replacements. The matching index is rebuilt on library refresh and excludes unavailable files from presence matches. Known release/recording conflicts reject matching. Multiple candidates require identical known hashes before choosing a file.

Album edition anchors are an additive SQLite document (`album-edition-anchors`). The original context-derived album ID remains assigned to its first known edition; further editions receive separate IDs. Persist anchors so scan order does not move old links/preferences between editions. Unknown tags may join a sole known edition, but should not choose among multiple editions. Do not change this policy without migration fixtures and a backed-up production-state comparison.

Intentional-removal exclusions use edition-aware keys; legacy exclusions still require compatibility. Restoration must clear only its removal's exclusions. Quality overrides and queued references must follow the correct album edition. Shared-file preservation is a boundary condition, not a licence to deduplicate unknown files automatically.

Queue workers use claim tokens. Cancellation/clear invalidates a claim; stale workers must not publish into a new request with a reused ID. Artist jobs use a separate generation guard. Preserve both across refactoring and restarts.

## Deployment and critical handover details

Current household topology:

- Unraid host: `192.168.1.235`; app LAN address: `192.168.1.203:8765`.
- Container: `pig-music-preview`; appdata: `/mnt/user/appdata/pig-music-preview/data`.
- Host music mount: `/mnt/remotes/SERVER01_Audio`; container mount: `/library`.
- Direct download workspace: `/library/.pig-music-work`; published files use existing artist/album folders. Recovery originals live in hidden `.pig-music-trash`, with Plex exclusion handling.
- Compose reference: `compose.unraid-preview.yaml`; deployed definition: `/mnt/user/appdata/pig-music-preview/compose.yaml`.
- Container protections: user `99:100`, read-only root filesystem, dropped capabilities, no-new-privileges, bounded CPU/RAM and writable temporary filesystem. Internal engine API binds loopback; keep that boundary.
- Two existing Docker networks: `pig-music-preview` and `br0`. The LAN address is static. Preserve network wiring and gateway priorities during updates.
- Existing SSH key is provisioned on the engineer's machine. Supply it to the deploy tool; never copy it into this repository or a source archive.

Private connection/config files include `slskd-connection.json`, `engine/engine.env`, `engine/slskd.yml`, `plex-connection.json`, `media-settings.json` and `library-export.json` in appdata. Document field requirements in [operations](docs/operations.md), not actual values. Plex export is currently one owner connection; never imply household support exists already.

Use `scripts/deploy_unraid.py` for source-only candidate build and isolated Linux tests. Add `--deploy` only for an authorised live delivery. It refuses active transfers, pauses/restores download settings, retains the old container, backs up stopped appdata/Compose and checks health/storage/API readiness. No live data belongs in a candidate source bundle. See [operations](docs/operations.md) for commands and manual recovery, including partial-update failures.

The pre-cleanup rollback image/container and `/mnt/user/appdata/pig-music-preview/backups/` must remain until the owner is happy. Old manager recovery material is under `backups/legacy-phase1a-20261006`; do not purge it during cleanup. Copying a database while active is not a substitute for SQLite backup or a stopped-state backup.

If the NAS disappears, cached browsing/settings should remain accessible while managed writes and transfers pause. Never create a substitute empty library at the mount point or bypass marker validation. Restore the correct mount/marker and verify the engine/queue resume before reporting recovery.

## Verification and ongoing maintenance

Use [testing guidance](docs/testing.md). Backend tests use disposable fixtures, not live library paths. Complete-file FFmpeg validation and actual format checks remain required. Provider tests use mock transports; they do not establish live service availability.

Before a release: format checks, unused TypeScript checks/build, frontend tests, backend suite and candidate Linux tests. Exercise browser journeys that backend tests cannot catch: fresh Import, reload/back/direct links, favourite-without-acquisition, playlist picker, active queue states, album settings and phone player metadata. Distinguish existing test results from checks actually run against the release candidate.

Record before/after read-only performance samples and request counts. Cached responses, cold provider work and downloads are different measurements. Include dataset size, sample count and transport. Do not trade identity/file validation for speed.

Brand source: [approved family standard](docs/pig-family-brand-standard.md) and [tokens](docs/pig-family-brand-tokens.json), originally supplied by the Pig-Branding sibling project. Preserve pig transparency, proportions and optical anchor. Playback keeps protected dark surfaces and fixed rose accent in both appearances. Any new wordmark needs approved Pig Music artwork; do not repurpose PigTV lettering.

Historical documents are indexed in [the documentation directory](docs/README.md). Their URLs, container counts and safety assumptions may describe retired builds. This blueprint and current operations/testing documents take precedence.

## Known limits / next engineer checklist

- Single household owner/library and one Plex owner mapping today; no user-account isolation yet.
- Experimental remote playback may fail or be slow; saved playback is independent. No guarantees about exact remote mastering.
- Metadata/provider limits and availability are external dependencies. Optional enrichment must never block library browsing or expose credentials.
- No filesystem watcher: use Scan library for changes made outside Pig Music. Initial ingestion uses native scanner; retired Music Grabber tooling is not a requirement.
- Plex's native playlist deduplication means repeated songs appear once there; Pig Music retains all ordered occurrences.
- Physical-phone smoothness and actual off-site access require real-device confirmation.
- At task start: inspect repository instructions/status, read this blueprint, verify current deployed image and health, then check queue activity before a restart. Protect uncommitted work; the repository originally arrived with all inception files untracked.
- At handover: state what changed, what was verified, current image/rollback path, open risks and the next prioritised work item. Update this document and the decision dialogue; do not scatter another competing roadmap into a new milestone.

- **6 October 2026 — audit follow-up authorised:** Owner approved artwork foundations first, Swift feasibility preparation alongside them, and branding deferred until confirmed complete. A01 implementation removes image bytes from snapshots without changing track/edition identities. Local benchmark and regression evidence is in `docs/a01-cover-store.md`; Linux image and stopped-state release acceptance remain pending. A02 is next.

- **6 October 2026 — registry transition:** Owner requested a proper repository-linked container and confirmed existing Unraid plus Container Registry. Source is the private `maroge1990/Pig-Music` GitHub repository; target is `ghcr.io/maroge1990/pig-music`. D01 prepares image test/publish automation and immutable-digest deployment using existing backups and topology. GitHub access is verified; Unraid SSH access is currently unavailable. No live switch has occurred.

- **6 October 2026 — native inventory/signing:** Owner specified iPhone 16 Pro Max, iPhone 12, Apple Watch Ultra 3 and Series 7, all reportedly on latest OS, and chose a free Apple account with Sideloadly. Exact OS builds and installation/refresh proof remain pending. S00 has an unbranded unsigned simulator build and shared probe tests; production iOS/Watch delivery is not claimed. Branding integration remains deferred.
Local closing verification for A01/D01: **117 backend tests passed** (Python 3.12), Black passed across server/tests/scripts, and frontend tests/build/format passed. A01 benchmarks and release gates are documented in `docs/a01-cover-store.md`. Draft review packages: A01 PR #1, D01 PR #2. This local verification preceded the verified 7 October deployment below.


### A01/D01 release evidence, 7 October 2026

Owner direction → Continue after provisioning SSH access. Engineering response → Verify the exact GHCR candidate on Unraid, check idle transfers, preserve stopped state, test migration on a disposable copy and switch using a unique Compose project. Result → **Delivered**; branding remains deferred and A02 is next. Earlier 6 October pending/access notes above are historical.

- Running image: `ghcr.io/maroge1990/pig-music@sha256:e2db668bfb99e41102cfbe6a8f6ad7b975262326347467057c1d39029b4dba8b`.
- Source repository: `https://github.com/maroge1990/Pig-Music`; OCI revision: `e3fc247a5bd183d0787281319a7076da3f2cd781`. Published by [Actions run 37445421140](https://github.com/maroge1990/Pig-Music/actions/runs/37445421140). Runtime is this revision; later native/documentation commits are not the deployed image.
- **117 backend tests passed** in the exact image on Linux and Unraid. Both 10k/50k artwork benchmarks passed under the 1 GB limit. Final Unraid peaks: 88.14 MB / 307.04 MB; schema 3 snapshots: 3.01 MB / 15.37 MB. Frontend tests/build/format and backend Black checks passed.
- Stopped-state migration retained **1,395 tracks**, existing album links and durable records. Live snapshot is schema 3, **927,914 bytes**, no image map, **81 referenced artwork files**, none missing. Legacy snapshot is retained. Five live artwork responses matched their content hashes.
- Read-only integrity checks opened all **1,395 files** with zero failures; all **25 managed file hashes matched**. Live API retains **98 albums** and **27 completed queue entries**; health is healthy, NAS available and original downloads-enabled setting restored.
- Container retains **1 GB**, **UID/GID 99:100**, read-only root filesystem and existing private address/storage. Rollback container: `pig-music-preview-before-registry-20261007-v1` (stopped). Matching stopped-state backup: `/mnt/user/appdata/pig-music-preview/backups/pre-registry-20261007-v1`. Release input: `/mnt/user/appdata/pig-music-preview/releases/registry-20261007-v1`. Restore matching state before returning to the pre-v3 image; preserve these artifacts.
- Review packages remain draft: [A01 #1](https://github.com/maroge1990/Pig-Music/pull/1), [D01 #2](https://github.com/maroge1990/Pig-Music/pull/2), [S00 #3](https://github.com/maroge1990/Pig-Music/pull/3). GitHub main has not been merged.
- S00 shared tests and unsigned simulator/embedded Watch builds pass locally and in Actions. An unsigned physical-device archive/IPA was built on 7 October (iPhone arm64; Watch arm64/arm64_32). Free-account Sideloadly installation, refresh, exact OS builds, private HTTPS connectivity and physical Watch playback remain unverified; no production native delivery is claimed.


- **7 October 2026 — continue through audit:** Owner requested continuation through audit findings. A02/A03 now implement non-blocking provider work, responsive immutable artwork, compressed/conditional library reads, indexed lookups and settings caching. Related phone-tab, hero, incremental preload, lazy operator-view and SSE findings are included. Branding remains deferred. Local tests/benchmarks and an explicit finding-by-finding disposition are in `docs/a02-a03-delivery.md`; image/live acceptance is still pending at this entry. Secure account/API/private HTTPS and actual-device gates remain separate.


### A02/A03 current release, 7 October 2026

Owner direction → Continue through the audit findings, keeping branding deferred. Engineering response → Implement bounded non-blocking image enrichment, content-hash derivatives/caching, compressed and conditional library delivery, indexed reads/settings caching, incremental preload, phone tab containment, pre-blurred hero layers, lazy operator views and shared latest-state SSE. Result → **Delivered on Unraid**; remaining branding, account/API/HTTPS and actual-device milestones are explicitly separated in the [finding disposition and evidence](docs/a02-a03-delivery.md).

Current image: `ghcr.io/maroge1990/pig-music@sha256:2bd79291eb160058a711772a9c8288ca3c6ad1bf6a0a1894f1f4fd1059abfbd9`; deployed source: `47a2c86b0897c15b1c37684ef5eaf8df1ed7a6ba`. Later handover commits do not alter that runtime. **127 backend tests** and both 1 GB scale gates passed on GitHub and Unraid; three frontend regressions, strict build and formatting passed. The 50k Unraid artwork peak is **316.34 MB**; compressed library fixture is **223,760 bytes** with **1.897 ms** conditional median (30 local-container samples).

Live migration retained **1,395 tracks**, album links and durable rows. API/HTTP acceptance retains **98 albums**, **27 completed queue entries**, original download settings and healthy available storage. Library transfer is **23,280 bytes** compressed; unchanged reads return 304; five content-hash/WebP/conditional artwork checks, immutable static assets and immediate SSE passed. Physical iPhone and off-site results remain V01; no new acquisition, music/tag edit, branding adoption or private transport configuration change was performed.

Current rollback container: `pig-music-preview-before-audit-20261007-v1` (stopped); matching state backup: `/mnt/user/appdata/pig-music-preview/backups/pre-audit-20261007-v1`; release input: `/mnt/user/appdata/pig-music-preview/releases/audit-20261007-v1`. Existing 1 GB, UID/GID 99:100, read-only root and private topology are preserved. Draft review: [PR #4](https://github.com/maroge1990/Pig-Music/pull/4), stacked on S00; all draft branches remain unmerged.

Final A02/A03 read-only integrity acceptance: all **1,395 files** opened with **zero read failures**, all **25 managed hashes matched**, schema 3 snapshot **927,914 bytes** with no image map, **81 referenced covers** and none missing. The pre-v3 snapshot is retained. The running image is Docker-healthy; its source labels and preserved resource/storage protections were inspected after deployment.


### Branding and household decisions, 7 October 2026

Owner confirmed branding complete and authorised remaining work. Pig family 1.4.0 exact product exports replace the previous generic pig and handwritten wordmark. Approved colours generate CSS and a compiled Swift PigBrand package. All CSS type is rem with a 0.75rem minimum. Approved spacing/radius values use tokens; existing nonstandard spacing remains where changing it would change density. The protected player uses approved dark secondary/border roles. See `docs/b01-b02-delivery.md` for verification and deployment status.

Owner accepted Mark as administrator, highest requested shared-file quality, owner-only Unassigned inbox for external files, one shared Plex music section with personal playlists/favourites, and existing Unraid private Tailscale HTTPS hostname. **Members can import and manage their own playlists and request music.** Owner role governs system/provider settings, physical scans, organisation, recovery and account administration. No credentials were requested in chat.

### M00 implementation, 7 October 2026

Versioned baseline migration and foreign-key connection enforcement are implemented and pass 133 backend tests. Existing rows are unchanged; the deployment verifier admits only the validated additive schema ledger. Container/stopped-state deployment verification remains pending. See `docs/m00-delivery.md`.

### T01 implementation, 7 October 2026

Private HTTPS origin and exact-proxy trust are implemented; 145 backend tests pass. Existing Unraid hostname and port443 are approved, with the other service on8443 preserved. Proxy/certificate deployment and physical phone acceptance remain pending. See `docs/t01-delivery.md`.

### M01 account foundation, 7 October 2026

Additive accounts, Argon2id hashing, opaque revocable sessions, secure HTTPS-only account router, one-use activation and interactive owner recovery are implemented. Full local suite: **159 tests passed**. Account router is not yet mounted into the main app; no live account cutover is authorised by this implementation status. M02 default-deny protection and M03 personal-library scope precede sign-in deployment. See `docs/m01-delivery.md`.

### M02 default-deny implementation, 7 October 2026

The main app now has a startup-audited default-deny guard, HTTPS account routes, cookie CSRF protection and session-bound signed media URLs. **165 backend tests pass.** Members can manage their account but are blocked from unscoped household routes until M03. This development branch is excluded from the live transport release; no owner account or live sign-in cutover is claimed. See `docs/m02-delivery.md`.

### Current branding/private HTTPS release, 7 October 2026

**Delivered:** B01/B02, M00 and T01 as `brand-https-20261007-v1`. Image source revision `6fafc59e2f352139844c810a8929991367c4ab17`; immutable digest `sha256:37b16f9cdad35bf9dbe013fa8293c90a06a22069d3cda6b15c0dfce4af158e43`. Exact-image Unraid tests145, scale gates and stopped-state verification passed. Prior audit release is retained as immediate rollback, with matching backup `pre-brand-https-20261007-v1`.

Private URL: **https://passyflix.tail6d1471.ts.net:10000/**. Port443 remains Unraid administration;8443 remains the existing other service. Proxy uses the existing container bridge; exact gateway trust and public origin were corrected in final runtime configuration. Certificate/HTTP2/HTTPS-health/icons/manifest/Origin checks passed from Unraid. This Mac lacks private hostname resolution; both phones still need LAN/cellular acceptance. No Funnel/public exposure. Account branches are development only and excluded from this release.

## Remaining audit checkpoint — 7 October 2026

The live release is audit-followup-20261007-v1, including approved PigMusic branding, schema migrations and private HTTPS on passyflix.tail6d1471.ts.net:10000. This release adds enlarged-text layout, bounded collection pages, generated protected-media/shadow roles, local artwork metadata and removal of the test-client warning. See docs/audit-followup-delivery.md for exact implementation and outstanding evidence. Accounts/personal libraries remain separate un-deployed development foundations. The physical Watch spike is not installed.


### Personal-library continuation — 7 October 2026

**Implemented in development, not deployed:** private playlist imports and lifecycle controls, revision checks for stale edits, personal artist monitoring/cancellation, bounded personal search with household-availability annotation, membership-checked artwork and playback, personal history/preferences and shared request beneficiaries. The full local suite passes 177 tests. The mounted-test import failure is corrected; exact-container acceptance is tracked in docs/m03-delivery.md.

A disposable copy of the stopped production backup passed migration and exact first-owner attribution for 1,395 tracks, existing playlist/request payloads and stable links. Repeating attribution changes nothing. Live accounts remain uncreated. The deployed audit release independently passed all file/hash/cover checks. Next in the account sequence are shared-file removal/restore and quality/scan rules (M04), personal Plex output (M05), account management (M06) and authenticated screens (M07). Physical Watch playback remains pending installation of the prepared feasibility IPA.

### Shared-file removal checkpoint — 7 October 2026

**Implemented in development, not deployed:** personal removal preview/confirmation, preservation for other members and pending requests, durable final-member trash intent, private 30-second undo, restoration of original memberships, cancellation/detachment of in-flight requests, and coordination with publication/scans/organisation/export. See docs/m04-delivery.md for scope, tests and current limitations. M04 remains in progress: quality preferences, explicit scan assignment and native-copy invalidation are still outstanding. The live audit image and actual NAS music remain unchanged.

- **7 October 2026 — remaining audit continuation candidate:** M04 quality/scanned-music assignment, M05 separate encrypted Plex credentials, M06 security/dependency review and M07 personal web screens are implemented. X01–X03 typed contract, revision-bound cursor pages, scoped events and durable library/playlist deltas are staged. The generated PigAPI Swift package, secure token middleware and unsigned iPhone simulator build pass; this does not claim a production iPhone/Watch app. See [household/native continuation](docs/household-native-audit-delivery.md) for verified scope, remaining extraction debt and account/device gates. Live release unchanged pending candidate acceptance and interactive owner bootstrap.

- **7 October 2026 — final remaining-audit candidate acceptance:** runtime `c4bedc305ed939dfd09cb4c8ded3da827af5c57c`, immutable image `sha256:6ae265a8200ca89bf373c3ebdd78e27d9f60e159eae56edcc3b04fab9d9cb3a4`. All 205 tests pass in GitHub and on Unraid, with completed 1 GB artwork/authenticated-HTTP/shared-and-disjoint native-sync gates. Two separate 50k collections (100k unique tracks) peak at 573.36 MiB on Unraid. Inbox refresh is linear and benchmark errors now block publication. Native tests and both unsigned simulator builds pass. The offline `pig-music-household-setup` helper is prepared; no real owner exists yet. Interactive password creation, fresh-state authenticated cutover and physical phone/Watch acceptance remain. See the household/native delivery ledger for exact scope and commands. The original live audit image remains healthy; no NAS music was changed by this acceptance work.

- **7 October 2026 — native Unraid Docker management and testing feedback:** The live service is now `PigMusic`, owned by Docker Manager with a native template, correct GHCR/GitHub links, approved local icon and autostart. It retains the exact prior live image, all 1,395 tracks and both private addresses; Compose is retired and a fresh stopped backup/rollback container is retained. Home, player alignment, anchored playlist selection, playlist playback/navigation, saved/full artist separation and search cleanup are implemented in the next candidate. See `docs/unraid-home-feedback-delivery.md`. Normal browser access recovered on the owner-requested retry. Disposable desktop/phone visual checks caught and fixed row artwork sizing, personal player offsets, dialog focus and album captions; evidence and exact scope are in the delivery document. Owner setup/fresh-state migration is still required before making the account-facing candidate live.

- **7 October 2026 — intuitive first-run setup:** Owner requested browser-based initial password creation. The candidate now automatically shows a first-administrator form, protected by a one-time installation proof in Unraid container logs, private HTTPS and existing request/rate-limit controls. It signs the owner in after creation and never reopens registration for an existing/disabled owner. The interactive CLI remains recovery only. The revised release sequence is latest-image Unraid acceptance → fresh-state backed-up account release → owner completes the WebUI → authenticated production acceptance; the legacy live image is unchanged until that switch. See the first-run follow-up in `docs/unraid-home-feedback-delivery.md`.

- **7 October 2026 — first-run release live:** Owner reported checks complete. The exact `131e464` image passed 211 tests and 1 GB Unraid scale gates, fresh stopped-state migration/attribution acceptance and the native Docker Manager switch. Live private HTTPS now offers locked first-run setup, preserving 1,395 tracks and all existing state/protections; backup and stopped rollback are in the release delivery document. Owner creates the administrator in the WebUI using the installation code from PigMusic Logs. This Mac's private hostname does not resolve; use a Tailscale-connected device. Authenticated production acceptance awaits that setup.

- **7 October 2026 — audit verification and unified experience:** Owner asked for both audits to be verified and an independent review, combined into one roadmap, and said the administrator should have the same experience as members plus an Admin section, with any extra options at the bottom of shared sections. Response: `docs/review-roadmap-20261007.md`. Both audits verified; review findings N01 (withdrawn after implementation evidence) to N13. Implementation went straight into `main` after fast-forwarding it to the live M11 source, as the owner directed. Delivered U01, part of U02, Q01, Q04, B03 (Pig family 1.5.1) and the N13 validator fix. 213 backend and 6 frontend tests pass, and the owner/member browser fixture was checked. Next: push `main` (this publishes a GHCR candidate) and release with the existing first-run deployment path once the owner has completed setup. Then Q02/U03.
- **7 October 2026 — continued build:** Owner asked to keep building. Delivered:
  - web-session UI contract tests, plus a fix to the route audit, which was missing 80 lazily included routes (N14)
  - one set of song actions
  - the seven-role type scale for web and Swift, and a legacy CSS prune
  - live system appearance, Recently added, album Play/Shuffle and heading focus
  - `deploy_release.py`, the routine Docker Manager release path; `main` had none after first-run

  221 backend and 7 frontend tests pass. Still unpushed and unreleased. Next: owner approval to push `main`, then exact-image verification and `deploy_release.py` once the owner account exists.
- **7 October 2026 — third build pass:** Delivered:
  - one Search across library, server and catalogue
  - a fix so following an artist no longer downloads its back catalogue (N15)
  - polish to playlists, favourites, requests and buttons
  - an Admin at-a-glance overview

  Still unpushed and unreleased. `/api/v1/admin` is deferred until native Admin work begins, because the legacy owner handlers live inside `create_app` and return untyped payloads.

### Unified experience release, 7 October 2026

**Delivered:** `unified-20261007-v1`, the first routine release through `scripts/deploy_release.py`.
- Image `ghcr.io/maroge1990/pig-music@sha256:d02d7b208077b32dd58a31ff53f2e3036e797d9039475c238962dfa3f5bcd4c2`, source `4d27e4804121a709b6d39867e67bc9ddf224ecd2` on `main`.
- GitHub image checks passed (223 tests).
- Exact-image Unraid acceptance passed: 223 tests; artwork peak 96.98 / 321.95 MB at 10k/50k; HTTP 165.67 / 381.73 MB; two-person sync at 50k each 380.65 MiB, cold sync 10.0 s; all limited to 1 GB.
- The release paused downloads, took a stopped backup, verified migration on a disposable copy (baseline computed by the previous image), recreated PigMusic from the reviewed Docker Manager template, verified private HTTPS, owner state and container protections, and restored the original download setting.
- Backup: `/mnt/user/appdata/pig-music-preview/backups/pre-unified-20261007-v1`. Rollback container: `PigMusic-before-unified-20261007-v1`.
- `--retention 2` lists 29 older backups and 30 stopped legacy containers; nothing was deleted, pending the owner's decision.

The first preflight caught a quoting error in the release state probe before any live change. It is fixed, and the snippet is now executed against SQLite in tests. Owner live testing is next.

### Listening experience pass, 8 October 2026

**Owner direction:** Musicals, soundtracks and compilations each get their own Library tab, and Artists shows only standalone artists. Tapping anywhere on a song plays it, whether it is saved or not; unsaved songs stream. The download state sits inline on the right, and a ⋯ menu offers context-aware favourite and go-to actions. Other asks: an edge-to-edge artist photo, an Apple-style tab bar that folds while scrolling, smaller Home songs, Downloads as its own section, pre-cached artwork and pages, more Fanart art, and a fix for the stretched player button.

**Engineering response (delivered on `main`, unreleased):**
- **Library tabs.** Artists, Albums, Musicals, Soundtracks, Compilations, Playlists and Favourites. Empty sections stay hidden. Artists excludes people who only appear on compilations, soundtracks or musicals. The Songs tab is gone, and Shuffle all moved beside the tabs.
- **Classification.** `server/library.py` `classify()` now also recognises score, game and cast genres, "Music from…" and "Motion Picture" titles, tie-ins such as "Transformers: The Album", and "Sound Team" album artists. An explicit owner category still wins.
- **Downloads.** Requests are now a top-level section; `#/library/requests` redirects to it. The change feed moved to `AppShell`, so download progress updates in every section.
- **One song row.** `SongRow.tsx` and `songs.ts` are used in albums, artist pages, playlists, favourites, search, catalogue releases, Popular and Home. Tapping plays your file when saved and streams otherwise. Songs already on the server are added to your library instantly, then played. The new `POST /api/v1/library/lookup` marks catalogue songs already in this person's library. The ⋯ menu offers Play next, Add to queue, Favourite, Add to playlist, Download, Go to album and Go to artist (the go-to items are hidden on that album's or artist's own page), then Remove, with Admin last.
- **Player.** The queue mixes saved and streamed songs. It has a compact mini player and a full-screen Now Playing view with an Up next list. The stretched play button was a 32 px button raised to 44 px tall by the coarse-pointer rule; it is now sized on both axes.
- **Phone navigation.** The tab bar floats. Scrolling down folds it to two circles, the current tab and Search, with the mini player between them. Account moved to a header initials button on phones.
- **Artist photo.** It starts at the top of the screen with a floating back button, and the existing fade is retained. A Fanart logo (`hdmusiclogo`, else `musiclogo`, English preferred, transparent PNG under `covers/logos/`) replaces the name when available.
- **Fanart.** Album covers now fall back to Fanart when Cover Art Archive has none. Fanart 404s are cached as empty answers.
- **Streaming fix.** Unsaved songs could never play in the browser because the CSP's `media-src` blocked the provider's CDN. It now allows only `https://*.saavncdn.com`, which is the host `RemoteAudio` already enforces. Members may stream as well.
- **Caching.** `client/public/sw.js` keeps artwork cache-first and serves catalogue and Home JSON stale-while-revalidate, within a 500 MB oldest-first budget. Everything is cleared on sign-out or session expiry. `prefetch.ts` warms every Home artist (full detail for the first two), the first three search results (full detail for two) and all library covers. Read-only POSTs no longer flush the read cache. Missing covers retry after 2 s and 6 s instead of waiting up to a minute, and the artist photo no longer re-downloads every minute.
- **Cleanup.** The old `.music-player` and `.player-*` CSS was removed.

**Verification:**
- 232 backend tests, 7 client tests, Prettier, Black, the strict TypeScript build and the regenerated OpenAPI contracts all pass.
- Browser checks used a disposable local library (ffmpeg tone files tagged as the owner's examples, under `.localdata/dev-review`) at phone and desktop sizes, in light and dark.
  - Categories and tabs.
  - Tap-to-play.
  - Mini and full player.
  - Menus and go-to links.
  - Folding nav.
  - Artist photo with logo, using a placeholder Fanart key and generated images.
  - Real remote streaming after the CSP fix.
  - Service-worker caching and prefetch.

**Not verified / gaps:**
- Live-library categorisation of the owner's five examples was not inspected, because reading production data was not permitted. Owner check needed.
- Real Fanart logos and album-cover fallback with the household key.
- Physical iPhone PWA behaviour: safe areas, scroll folding, service worker on iOS.
- Download to *device* (offline audio) does not exist. Rows show only server/library state.

### Server pre-cache, 8 October 2026

**Owner direction:** Home is the same on every device, and each person's library is known, so prepare these on the server rather than only on each device.

**Delivered:** `server/warmer.py` is a background worker that prepares artist pages in the server's shared caches. It covers the portrait, Fanart photograph and logo, popular songs, the first album page, and up to 24 covers (12 for library artists), with 256 and 512 px sizes pre-generated.
- **Every 30 minutes** it queues Home, each active person's recommendations and every library artist that is not compilation-only. Home artists come first, with full detail for the first two.
- **Every catalogue search** queues the top three results at once, with full detail for the first two.
- **Priority.** Search runs before Home, and Home before library. All provider calls run as background metadata work, so a person waiting on a page always goes first.
- **Early renewal.** While warming, day-long catalogue and popularity answers renew four hours early and hour-long Home feeds twenty minutes early, so foreground requests do not meet an expired cache.
- **Off switch.** The warmer runs only when `PIG_MUSIC_PRELOAD` is not `false`.
- **Status.** Owner-only `GET /api/warmer` returns the status. Admin → Overview shows "Artist pages ready", and each pass logs `Pre-cache pass complete …`.

**Verification:** 237 backend tests pass, including `tests/test_warmer.py`. On local disposable data the first pass prepared 16 artist pages in 29.5 s with no failures, and a search prepared its results within seconds.

### Listening and pre-cache release, 8 October 2026

**Delivered:** `listening-20261008-v1` through `scripts/deploy_release.py`. It includes both 8 October passes.
- Image `ghcr.io/maroge1990/pig-music@sha256:5bf112791ad1bae2f2398c22337f6813fa121712ad2c99f535b8ea520b3f4750`, source `c1f01aa1ac6c1c1b6fc05eb1cb28912270c901f1` on `main`.
- GitHub image checks passed.
- Exact-image Unraid acceptance passed:
  - 237 backend tests.
  - Artwork and HTTP delivery scale gates under 1 GB; 50k HTTP peak 382.4 MB.
  - Two-person sync at 50k each: 384.27 MB.
- Backup: `/mnt/user/appdata/pig-music-preview/backups/pre-listening-20261008-v1`. Rollback container: `PigMusic-before-listening-20261008-v1`.
- Live warmer check:
  - The container is healthy on the new image.
  - Within ten minutes, 372 artwork files had been written, including 12 Fanart logos.
  - The first pass logged `Pre-cache pass complete in 843.9s: 27 artist pages and 47 covers prepared so far, 0 failures`.
  - Most of the first-pass time is one-off catalogue identification of library artists at MusicBrainz's 1 request/s. Later passes reuse it.

**Owner checks next:**
- The categorisation of Hamilton, Westworld, Persona, Book of Mormon and Transformers.
- Real artist photos and logos.
- Folding navigation and safe areas on the iPhone.
- Admin → Overview "Artist pages ready".
