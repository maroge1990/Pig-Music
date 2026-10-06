# Pig Music review and cleanup scope

6 October 2026. Review of the Phase 1a implementation and the deployed `pig-music:preview-20261006-phase1a-final-v2` image.

**Historical baseline and approved scope.** The cleanup has since been delivered in `cleanup-20261006-v3`. Findings below describe the pre-cleanup build; see [blueprint.md](../blueprint.md) for implementation, measurements, verification and remaining limits.

## Recommendation

Keep the current React, FastAPI, SQLite and embedded Soulseek architecture. The single-container approach is working, and the core download, validation, replacement and Plex workflows have useful verification behind them. The next step should be a structured cleanup before adding household accounts and separate libraries in Phase 1b.

The largest gains will come from consistent music identity, indexed library reads, shared request state and reusable interface components. A visual redesign alone would leave the expensive work and conflicting behaviour underneath it.

This is an investigation and implementation scope. No application code, settings, downloads, library files or deployment were changed during the review.

## Evidence and limits

- Read the current backend, frontend, tests, deployment configuration and milestone documentation. Compared the approved Pig family standard in the sibling Pig-Branding project with the standard and tokens in this repository.
- Inspected the live application on LAN at `192.168.1.203:8765`, including desktop and an emulated 390 × 844 phone viewport. Inspected empty Import, artist browsing and Settings without submitting actions.
- Measured read-only API responses against the current 1,395-track library. Profiled playlist matching and saved-track lookup using a separate process, read-only database access and an in-memory library view.
- Reproduced edition grouping, import/discovery disagreement and cross-edition cancellation with disposable local fixtures. These tests did not touch the NAS or live queue.
- Ran TypeScript's unused-declaration checks. Normal build configuration does not currently enable those checks.
- The preceding milestone records 98 passing backend tests on the deployed image and a successful frontend build. Those results are prior validation, not a new full-suite run in this audit. The newly reproduced cases expose coverage gaps.
- Measurements below are five sequential requests per endpoint from Windows over LAN, against existing warm data. They are medians and observed maxima, not p95 estimates, cold-provider performance, a concurrency test or a physical iPhone/Tailscale test. Dark-theme tokens were checked in code; this is not a complete accessibility or dark-theme visual certification.

## How the application fits together

The browser reads a local library projection and joins it with remote catalogue metadata, artwork and optional popularity. Requests feed a persistent queue; source adapters acquire files; validation and publication place them into the existing NAS structure. Quality policy submits replacement downloads. Scanning refreshes the library projection. Playlists retain requested song membership and resolve saved files for playback and Plex export. Recovery and organisation use guarded filesystem operations and journals.

That separation is sensible. The weak point is that several of those layers independently decide whether two songs are the same, independently reload or normalise library data, and independently refresh the browser. A shared identity and library-query layer would improve correctness and speed together.

There is no reason in this review to introduce another database service, split the app into more containers, replace the UI framework or bring back the four retired applications. Embedded slskd remains an intentional dependency, rather than redundant application code.

## Measured response baseline

| Read-only operation | Median | Maximum observed | Response size |
| --- | ---: | ---: | ---: |
| Health | 7.7 ms | 8.4 ms | 299 B |
| Library summary | 16.1 ms | 18.3 ms | 78 KB |
| Artist detail | 9.1 ms | 24.6 ms | 33 KB |
| Album detail | 4.2 ms | 4.5 ms | 5.5 KB |
| Queue | 14.3 ms | 24.3 ms | 17 KB |
| Playlist list | **830.0 ms** | **1,163.0 ms** | **622 B** |
| Local search | 45.4 ms | 51.8 ms | 15 KB |
| Migration inventory | 41.2 ms | 42.2 ms | 54 KB |
| Organisation review | 1,421.8 ms | 2,208.2 ms | 544 KB |
| Cached artist identity | 89.5 ms | 227.3 ms | 66 B |
| Cached first discography page | 12.9 ms | 14.9 ms | 1.2 KB |
| Cached popularity | 9.4 ms | 10.2 ms | 4.3 KB |

Raw samples and the repeatable measurement script are in `.localdata/review-20261006/`. These private, ignored artifacts are evidence, not application dependencies.

The playlist result is disproportionate to its response size. Profiling its two playlist details produced approximately 4.2 million calls, including **450,138 normalisation calls**, while repeatedly scanning saved music for each entry. The profiled 2.26-second runtime includes profiler overhead; the table shows actual API timings.

The snapshot is **20.6 MB**. `server/media.py:saved_track` rereads and parses it for individual saved-song lookups; five internal measurements had a median of approximately **119.5 ms**. This also affects operations that resolve song membership. The fast album endpoint does not eliminate this separate lookup cost.

## Prioritised findings

### 1. Fix confirmed functional inconsistencies first

**Fresh Import cannot open a file chooser.** In `client/src/main.tsx:553`, the empty Import branch renders the Import XML button. Its referenced file input is mounted only in the loaded branch at line 563. The live empty screen has zero file inputs. Mount the input independently of imported data and cover both first import and replacement import in browser tests.

**Known album editions can be merged.** `server/library.py:build_library` groups by normalised album artist and album title. Two fixture albums with different known release IDs become one two-track album. Title-derived album IDs also couple preferences and classification to that grouping. Preserve known edition identity; treat unknown metadata conservatively. Any ID migration must retain preferences, queue references, playlists and navigation compatibility.

**Import and discovery disagree about the same request.** `build_migration` uses names and duration without the same edition checks as `server/catalogue.py:presence`. A fixture request for another known edition is missing in discovery but downloaded during import. Playlist matching has its own ambiguity handling. Introduce one matching result with exact, probable, conflicting and absent outcomes, used by import, catalogue, playlists, favourites and acquisition. Recording, release and album context must remain meaningful; compilations and live versions must not be silently substituted.

**Removal cancels a different edition's pending request.** `server/recovery.py:36-38` matches queue cancellation by four normalised names without a release-ID guard. Removing edition A cancelled both A and B in a fixture. Exclusion keys also need edition/membership-aware handling. Removal and restoration should affect the intended membership and its jobs while retaining shared file assets still required elsewhere.

These are reproduced defects. They justify putting correctness ahead of cosmetic changes, but they do not establish that the live library has been damaged.

### 2. Eliminate repeated library work

Build a revisioned library index for track ID, file path, release/recording identity, normalised context and search terms. Rebuild it when scanning or publication changes the library, rather than reparsing the snapshot for every song lookup. Keep SQLite as the durable state store and the snapshot as an ingestion/cache artifact; a new external service is unnecessary.

Use the index for playlist resolution and lightweight playlist counts. Avoid resolving complete playlist details just to list cards, then resolving them again during Plex sync. Return favourite and playlist membership in a batch for the visible view instead of one request per `SongActions` instance. Keep ambiguity review intact when optimising matching.

Plex currently reloads its section index on periodic sync. Cache the path index with bounded reconciliation and refresh it when library publication or Plex indexing requires it. Available songs must still appear promptly and playlists must retain order.

### 3. Consolidate frontend requests, refresh and navigation

There are approximately 36 raw fetch sites and overlapping loading/error/state conventions. The main app has a five-second queue loop; on the Queue page it also fetches full library and migration data repeatedly. Popular visible songs and open catalogue releases poll every three seconds, artist requests every five seconds, and playlist views every fifteen seconds. Several loops continue when no relevant work is active.

Introduce a small typed API client and shared query/cache layer with request deduplication, cancellation, entity revisions and targeted invalidation. Poll active work at an appropriate cadence, slow down idle views and suspend unnecessary work in hidden tabs. Start here before deciding whether server events are needed.

Replace the broad membership event that causes all mounted songs to requery after unrelated playlist actions. Replace broad cache clearing with the affected track, album, artist and playlist revisions. Handle removal of the currently open entity without an unhandled 404.

`MusicLink` refetches the library and searches by name to navigate. Pass resolved identities through song data and cached state. Catalogue selections and playlist destinations need stable URLs, so reload, browser back and direct links retain the actual artist/release instead of depending on transient React state or custom events.

### 4. Give saved and discovered content one interface

Saved artist pages and discovered artist pages take different paths through hero, discography and settings components. Use one artist page with saved/discovered status, optional artwork and popularity, and a shared discography view. Keep Local/Discovered separation and newest-first sections.

Saved, catalogue, popular and playlist songs each implement their own row arrangement. Consolidate them around a shared song row and action group with explicit capabilities and state: playable, saved, queued, downloading, missing, favourite and playlist membership. Preserve exact-version context and make the action order predictable. Favouriting must continue to store membership without queuing a download.

Use one Album settings disclosure and shared quality controls. Avoid nested forms/disclosure markup that hides a summary inside a non-disclosure container. Keep advanced artist and album preferences below the music and collapsed by default.

Release eligibility differs across catalogue browsing, artist acquisition and popularity. The three implementations exclude different secondary types. Centralise release classification with explicit section intent: feature albums, singles, EPs and other releases. Different views may intentionally select different sets, but their definitions must agree. Keep compilations, soundtracks and musicals available without empty section headings.

### 5. Apply the existing brand consistently

The approved light and dark semantic palette values already match. The pig image preserves transparency, aspect ratio and the prescribed optical anchor. Selection, focus and status treatments largely follow the family standard. Retain those assets and the large artist imagery the user likes.

The main outstanding brand discrepancy is playback: the standard requires protected dark playback surfaces, white labels and fixed rose `#EF7AAE` in both appearances. `.music-player` currently inherits theme surfaces and accents. Implement the protected playback treatment, or resolve an explicit brand exception before diverging from the standard.

Unify product-name casing and wordmark treatment across desktop sidebar and phone header. Do not reuse a PigTV wordmark for Pig Music or redraw the pig; use a supplied/approved Pig Music asset when available.

Replace accumulated CSS overrides with component styles and clear responsive rules. Apply the existing radius roles and spacing vocabulary without reducing useful density. Standardise button-label centring, card gaps, form labels, disclosures, headings and loading/empty/error states. Keep descriptive storage/recovery explanations where they affect a decision; remove repeated explanations and development-facing provider language from everyday browsing.

On phones, the player action area leaves too little room for artist/album labels in the current build's recorded player view. Adjust the layout so those navigation targets remain readable, rather than relying on ellipsis. Standardise circular action appearance and larger transparent touch regions; some overflow controls are considerably smaller than the play/download controls. Review hero fade on a physical phone, with reduced motion and both appearances. Emulated screenshots alone cannot establish scroll smoothness.

Representative audit capture: [mobile Settings](../.localdata/review-20261006/settings-phone.png). Earlier same-build capture: [mobile player](../.localdata/oct6/phase1a-player-phone.png).

### 6. Remove confirmed redundancy and organise responsibilities

- TypeScript unused checks find seven declarations in `main.tsx`: old query/search/catalogue state, `searchCatalogue` and the old mosaic. `SearchPanel` superseded this path. Remove obsolete state, effects and functions, then enable unused checks in normal validation.
- Remove confirmed dead promotional hero/search/player-note styling. Approximately twenty selectors are candidates; verify dynamic usage before deletion. Repeated selectors across responsive rules are not automatically dead code.
- `server/remote.py` retains a standalone Monochrome prototype alongside the active `RemoteAudio` adapter. Remove or explicitly archive unused runtime helpers and update tests so prototype coverage is not mistaken for active playback coverage.
- Split the large app/store/UI modules by responsibility after shared behaviour is defined. File size alone is not a reason to move code. Format compressed JSX/Python/CSS and add consistent linting so future diffs can be reviewed.
- Extract common mount/path-boundary checks and journal helpers from publication, recovery and organisation. Keep their specialised operations and existing hash/rollback safeguards. Do not collapse them into an opaque general-purpose filesystem engine.
- Keep vendor notices, pinned upstream provenance and required adapter fallbacks. Multiple sources are an intentional capability, not duplication to remove.

## Provider and background-work scope

Foreground catalogue requests share a rate-limited lock with broad background discography prefetch. Popularity holds a global lock while doing provider requests and potentially many release-group lookups. Cold work for one artist can delay another. Prioritise interactive requests within existing provider limits, deduplicate by artist/release, bound background batches and fetch additional release pages on demand. The browser currently loads further catalogue pages while initially displaying only a subset.

Fanart portraits and backgrounds can share one artist metadata response/cache, with separate cached image variants and existing fallback behaviour. Keep API-key absence silent for optional features.

Remote playback remains an experimental provider-dependent path. Cleaner caching and resolution can reduce overhead; it cannot guarantee an external source will resolve quickly or remain available. Measure source resolution separately from UI response and keep saved-file playback reliable. Do not add new sources or promise instant remote play as part of this cleanup.

Two resilience concerns need deterministic tests before changing them:

- Artist-job cancellation can race with awaited metadata/submission and later whole-document progress writes. Use a generation/claim check and transactional job updates so a cancelled job cannot resume through stale state. This is a code-level risk, not a reproduced live failure in this audit.
- Runtime checks the NAS marker before starting the web service. An unavailable mount therefore prevents the settings/troubleshooting UI from starting. Consider a degraded mode that serves cached browsing/diagnostics while pausing all filesystem writes and transfers. Preserve mount validation; do not bypass it to keep downloading.

## Ordered implementation packages

| Package | Scope | Completion evidence | Relative size |
| --- | --- | --- | --- |
| 1. Correctness and identity | Fresh Import fix; shared matching policy; edition-safe grouping, cancellation and exclusions; compatible migration | Browser import regression; edition/compilation/live fixtures; retained preferences, memberships and queue references; no unexpected acquisition | Large |
| 2. Indexed reads and membership | Revisioned library index; playlist counts/detail resolution; batch membership; Plex index reuse | Repeatable baseline improvement; identical ambiguity/order results; bounded reads as library grows | Medium–large |
| 3. Requests and navigation | Shared API/query state; targeted invalidation; active/idle polling; durable artist/album/playlist URLs | Request-count checks; reload/back/direct-link tests; cancellation/error handling; no duplicate jobs | Medium–large |
| 4. Interface and brand | Shared rows/actions/pages/settings; consolidated CSS; protected player colours; mobile layout/copy | Phone/desktop light/dark/system review; keyboard/focus and reduced-motion checks; simple default workflows retained | Medium |
| 5. Providers, resilience and operations | Foreground/background budgets; unified release rules; Fanart caching; cancellation/mount recovery tests; deploy/docs cleanup | Provider fixtures; NAS-unavailable recovery test; restart and live smoke checks; one documented deployment/rollback path | Medium–large |

Introduce focused regression tests first. Land and deploy reviewable batches rather than one wholesale rewrite. Formatting-only changes should be separable from behavioural changes.

## Acceptance criteria

These are proposed targets for implementation, not results already achieved:

- At the current library size, cached local browsing APIs should have LAN p95 below 100 ms and playlist-card listing below 150 ms, measured with at least thirty samples. Separate cold provider timings and network effects.
- One batched membership read per visible view replaces per-row favourite queries. Idle popularity/release panels stop making repeated three-second requests. Hidden tabs avoid unnecessary polling.
- Benchmark representative 1k, 10k and 50k metadata fixtures for indexed reads and playlist resolution. Performance should not deteriorate as the product of playlist length and library size.
- Fresh Import works from an empty instance; replacement import works; selection/conflict review remains explicit; importing does not unexpectedly queue every export entry.
- Known different editions, recordings and compilation contexts retain the intended identity. Unknown metadata produces reviewable matching instead of confident substitution. Removing one membership neither cancels another edition nor removes a shared file still needed elsewhere.
- Quality changes download a replacement source in either direction, validate it before publication and keep recovery behaviour. No quality conversion is introduced.
- Favourites never auto-download. Playlists preserve order, show available songs immediately and gain missing songs in Plex after acquisition/indexing.
- Artist/album/player navigation survives reload and browser back. Empty, loading, unavailable and failed states behave consistently.
- Phone song controls and player navigation remain usable; settings are aligned; brand tokens and protected playback styling are verified in light/dark/system modes. Real-phone scrolling and off-site access receive explicit live checks.
- Existing backend suite and meaningful browser journey tests pass. Build, restart, state persistence, saved-file playback, one controlled acquisition, playlist export and quality replacement are checked on the deployment candidate without bulk changes to existing music.

## Deployment, documentation and Phase 1b

Create one repeatable source-only build/deploy/smoke/rollback procedure. Current private helper scripts and historical milestone documents are useful evidence but should not be the operational source of truth. Keep credentials and appdata outside build artifacts. Document current architecture, supported integrations, matching/quality semantics and recovery; label older milestones as history. Preserve vendor licensing and rollback backups.

Before identity/schema changes, back up durable state and prove the migration on a disposable copy. Retain a compatible rollback image and the corresponding data backup. Do not bulk rename, retag, deduplicate, reorganise or purge recovery files as a side effect of code cleanup.

Phase 1b can then add household identity, library memberships, per-user favourites/playlists and Plex connections on top of a stable asset/edition/membership model. Shared music stored once is still the goal. This audit scopes that prerequisite model; it does not add household controls to the current interface.
