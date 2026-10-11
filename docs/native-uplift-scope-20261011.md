# Pig Music native uplift: scope and delivery plan

Prepared 11 October 2026, Australia/Melbourne. Source review and product scoping, not an implementation or deployment. Estimates are engineering estimates, not measured delivery commitments.

## 1. Agreed outcome

Build a production Swift app with all everyday web features, first on **iPhone and iPad**, then **Apple Watch**, then **Mac**. Administration stays in the web app. The platform remains self-hosted and private, serving **2–3 people with 5,000–50,000 songs per personal library**. Files remain shared and stored once; libraries, playlists, favourites, requests and history remain personal.

Confirmed in this scoping conversation:

- Everyday feature parity includes experimental catalogue/cloud-song streaming, with clear failure and fallback behaviour.
- Downloads default to original quality, with optional smaller AAC copies and compatibility conversions where necessary.
- Downloaded music remains playable while offline. Revocation and membership removals reconcile when the device next connects.
- True gapless playback and crossfade are first-release requirements. CarPlay is outside this release.
- Initial phone/tablet testing will use a free Apple account with Xcode Personal Team signing. Paid distribution remains a later decision.
- Watch follows iPhone/iPad and precedes Mac.

Current implementation is recorded in [the 12 October phone/Watch build](native-phone-watch-build-20261012.md). The owner subsequently required Watch-owned offline downloads, requests from either device, and gapless/crossfade on Watch as well as phone. Devices: iPhone 16 Pro Max/iOS 27 and Watch Ultra 3/watchOS 27; Developer Mode on Watch will follow software build completion.

Initial crossfade UX proposal: a simple on/off control, a short duration selected through listening tests, and gapless album-order playback preserved by default. A duration slider is not needed for initial parity. Crossfade and gapless are different modes: gapless preserves the original boundary; crossfade intentionally overlaps it.

No delivery deadline, staffing level or budget has been supplied. Exact iPad inventory, OS versions and distribution method remain planning inputs. The earlier iPhone/Watch inventory is recorded in [native-spike.md](native-spike.md); it is historical device evidence, not a fresh inventory check.

## 2. What actually exists

This section records the baseline before build authorization. For subsequent implementation and verification, see [first connected-alpha delivery](native-uplift-delivery-20261011.md).

| Area | Observed in current checkout | Implication |
| --- | --- | --- |
| Production Swift app | No production app target or feature screens found. `swift/NativeSpike` is explicitly disposable | This is substantially a new client, rather than polishing an existing app |
| Shared Swift package | `PigAPI` generated client, HTTPS address validation, Keychain token vault, session middleware; `PigBrand` tokens | Reuse these foundations after testing their integration into the production lifecycle |
| Server identity | Accounts, device tokens, revocation, personal libraries and owner/member boundaries | Existing authentication and household rules can be reused |
| Native reads | Typed tracks/albums/artists, personal details, playlists, Home feeds, requests, change feed and SSE | Enough groundwork for a production client, but not complete end-to-end coverage |
| Contract | 55 paths / 69 operations in the committed v1 schema; 16 operations have explicit structured success JSON schemas | Contract publication does not mean every feature has a typed interface. Binary and SSE operations need their own contracts; remaining JSON operations need DTOs |
| Schema copies | `api/openapi.v1.json` and the PigAPI copy are byte-identical in this checkout | Current copies match; runtime completeness and drift still need delivery checks |
| Offline services | No production PigStore/PigSync/PigPlayback/PigDownloads modules; no device-copy routes found | Local persistence, offline edits, audio and download management must be built |
| Distribution/device proof | Unsigned spike builds documented; physical installation/refresh/network/Watch audio remain unverified in the recorded evidence | Compilation cannot close device acceptance gates |
| Source versus release | Existing working tree is dirty; 9 October music fixes are recorded as local and not deployed | Freeze and release a known baseline before native integration acceptance |

The older [multi-user/native roadmap](roadmap-multiuser-native.md) is useful background, but it does not satisfy the present scope unchanged. It excludes experimental remote playback, places personal device management on the web, describes an older navigation structure, and allows playback gaps up to 0.5 seconds. Those assumptions are superseded by this scope. Initial testing now explicitly uses a free Xcode Personal Team; the earlier Sideloadly workflow is not required for this handoff.

The recorded 9 October fixes matter to parity: complete cloud/repeated-entry playlist playback, Previous behaviour, request clearing, catalogue navigation, artist identity resolution and album request formatting. Use [music-bug-fixes-20261009.md](music-bug-fixes-20261009.md) as release input. Do not assume the running server already includes them.

## 3. Everyday feature parity matrix

Every row below needs owner and member journeys, loading/empty/error states, offline behaviour, accessibility and iPhone/iPad layouts. A feature is complete when its behaviour is equivalent, not when its screen resembles the web.

| Capability | Swift work | Server dependency / acceptance |
| --- | --- | --- |
| Connect and sign in | Editable private HTTPS server, connectivity check, device sign-in, activation/setup-code flow, remembered server, Keychain session, sign-out | Existing auth; structured failure codes; account/server isolation; no password persistence |
| Home | Recently added, popular and recommended artists/albums/songs, navigation into exact catalogue identities | Existing Home endpoints; typed drill-down results; unavailable discovery must leave personal library usable |
| Personal library | Artists, albums, songs, compilations, soundtracks, musicals, playlists and favourites; sorting, filtering, Play and Shuffle | Paged API/local indexed reads; complete queues at 50k tracks rather than copying the web's sampled shuffle limitation |
| Artist and album detail | Saved music plus full catalogue, release types, editions, disc/track order, compilation credits, popular songs, portraits/backgrounds/logos | Complete typed catalogue and artwork contracts; distinguish same-name artists and release/recording/track IDs |
| Search | Local-first library results, household music, external catalogue; cancellation and pagination; navigate from song to artist/album | Existing personal/catalogue search; define missing album result and paging contracts where needed; external provider degradation |
| Add/request music | Instant membership for household files; song/album requests; artist follow/monitoring and release-type selection | Existing membership, requests and personal acquisition endpoints; idempotent replay and exact edition context |
| Request status | Queued/progress/completed/failed/cancelled states, pagination and clear finished requests | Existing personal request list/clear; match current web permissions. New personal retry/cancel controls are an optional server feature, not assumed parity |
| Favourites | Explicit set/unset from rows/player, cloud favourites, favourites playlist and play/shuffle | Existing favourite semantics; heart never acquires music; replay-safe explicit state |
| Playlists | Create/rename/delete, add/remove/reorder, repeated entries, saved and cloud songs; XML import and matching/review outcomes exposed by personal import | Existing playlist revision checks and import; stable entry identities and offline replay contract; admin inventory migration remains web-only |
| Personal removal | Preview consequences, confirm membership/file effect, undo while available | Existing removal preview/confirmation/undo; online-only confirmation so stale offline state cannot delete shared files |
| Quality preferences | Household-default override and personal album/artist preferences; explain shared highest-requested-quality rule | Existing personal quality service; typed responses; device-copy quality is separate from server acquisition quality |
| Playback | Album/playlist/song queues, full-library shuffle, Previous restart/previous behaviour, pause/seek/next, mini-player and Now Playing, queue editing | Saved signed URLs, remote resolution, preserved playlist occurrences; exact playback behaviour agreed in prototype |
| Gapless and crossfade | True gapless for validated saved-file formats; two-track overlap for crossfade; album-order rules; interruption and route handling | Early audio architecture gate; source readiness and decoding/prebuffering; remote limitations explicitly tested |
| Remote catalogue/cloud playback | Play without requesting; strict identity matching; source/status and provider failure explanation | Type `/api/v1/remote-playback`; bring catalogue playback and required settings reads into a personal v1 contract; member authorization regression |
| Downloads | Track/album/playlist/favourites downloads, progress/cancel/retry, originals or AAC, stale updates, offline filter, storage budget, optional keep-favourites-downloaded | New device-copy service, media metadata/version/Range contract, background transfers and account-bound local state |
| Account | Appearance, password change, own sessions/revoke, personal quality, personal Plex mapping, sign-out, connectivity/storage settings | Existing personal endpoints, typed DTOs. Provider secrets and global integration settings stay in web Admin |
| Apple integration | Lock Screen and headphone controls, Now Playing artwork, AirPlay, Bluetooth, background audio | AVFoundation/MediaPlayer/audio-session implementation and physical-device acceptance |
| iPad | Adaptive sidebar/detail navigation, portrait/landscape, resizing and multitasking, keyboard/pointer, usable player/queue | Same services; dedicated layout and lifecycle tests, not an enlarged phone screen |

Web-only administration: system overview, all-user acquisition queue/settings, providers/Soulseek/media settings, people creation/reset/disable/activity, Unassigned assignment, scan, organisation/undo, recovery/trash, physical removal tools, migration inventory/selection/review and household maintenance. Owners receive the same everyday Swift experience as members. An optional link can open web Admin, but no native admin implementation is included.

“Server Requests” and “On this device” must remain distinct. The cloud means on the server; the download arrow means on this device. Catalogue Request is a plus action. Use one reusable status model across library, search, playlists, player and downloads, with text/VoiceOver labels.

## 4. Architecture and dependency choices

Keep a modular monolith on the server and a modular Swift package shared by app targets. Three users do not justify microservices, Kubernetes or a distributed database. Large libraries and concurrency, rather than account count alone, drive the engineering work.

| Module | Responsibility | Boundary |
| --- | --- | --- |
| PigAPI | Generated transport, auth, typed errors, request IDs, capability discovery | Generated DTOs remain outside view logic; redact tokens and signed URL queries |
| PigDomain | Stable identities, availability, playlist occurrence, playback source and quality policy | Platform-independent models/use cases; do not model a cloud recording as a saved file |
| PigStore | Local SQL migrations, indexed library/search, playlist entries, outbox, downloads and cached metadata | Separate store and file namespace per server and person |
| PigSync | Full sync, deltas, SSE, foreground reconnect, conflict/replay handling | Network failure never discards the last valid offline library |
| PigPlayback | Queue, source resolution, buffering/decoding, gapless/crossfade, audio lifecycle and system controls | Platform adapters for iOS/watchOS/macOS; views do not own playback state |
| PigDownloads | Background sessions, transfer receipts, integrity, durable state, quotas and cleanup | Downloads belong to the server/person namespace; they are disposable device copies |
| PigBrand / PigUI | Existing tokens plus reusable artwork, availability, rows, menus and player components | Platform-specific navigation/layout; share behaviours rather than forcing identical screens |

Use SwiftUI, Observation, async/await and strict concurrency. Preserve the existing OpenAPI generator/runtime/URLSession packages. Recommended persistence is GRDB/SQLite with explicit migrations and FTS5, consistent with the earlier roadmap; verify current toolchain/platform compatibility and pin a tested release. [GRDB project documentation](https://github.com/groue/GRDB.swift) describes its database, migration and concurrency facilities.

An image cache may be a small bounded implementation or Nuke, chosen through a short spike. Its contract matters more than the package: identity by artwork hash and size, coalesced fetches, bounded memory/disk, cancellation, and account isolation. Do not fetch full-size art for every row.

Do not add a third-party playback engine before the audio spike proves it necessary. For crossfade, evaluate two-player overlap versus a decoded-audio engine. AVQueuePlayer alone is not a design proof for true gapless or crossfade. A decoded engine offers sample scheduling and mixing, but adds stream decoding, buffering, format conversion and route/sample-rate complexity. Select using real files and traces, not screen-level prototypes.

## 5. Server packages required for native delivery

### S1 — Complete the personal v1 contract

- Inventory every parity journey against runtime routes and the exported schema. Type success bodies for catalogue, mutations, sessions, quality, Plex, preferences, imports, removal and remote playback. Define binary, SSE and error contracts separately.
- Standardize stable error codes, retryability and retry-after behaviour. An APIError model existing in source does not mean every raised HTTPException conforms to it.
- Publish client capabilities/minimum compatible API information, including device-copy presets, supported features, media support and request limits. App and server release versions should evolve independently within a documented compatibility window.
- Version catalogue playback, public personal media configuration and artwork metadata/artist assets currently reached through legacy routes. Do not give members global settings access to obtain a read flag.
- Validate user/server identity before accepting cached responses. Parse relative signed URLs against the configured HTTPS origin, preserving the custom port; constrain authenticated redirects and never forward a bearer token to provider hosts.
- Maintain additive rollout and old-client compatibility; freeze DTO/enum semantics and deliberate unknown-enum handling. Run actual Swift generated-client journeys, not only schema comparison.

Acceptance: all everyday journeys represented by usable native contracts; owner and member both succeed; anonymous/other-user calls fail; old client and new server remain compatible for the agreed window.

### S2 — Reliable, bounded synchronization

Current sync materializes final-state checkpoints on reads, retains 30 days, and returns 409 when pagination revisions change or 410 when history expires. It is not simply a per-mutation event log. `NativeSync.capture` scans projections, persists entity JSON and embeds complete playlists in deltas. Scope around the implementation that exists.

- Define one consistent bootstrap across artists, albums, tracks, playlists/favourites and required personal settings. Typed library page routes currently cover three entity collections; playlists require their own bootstrap.
- Use a staged local store: download complete coherent data, atomically publish the new library and revision, then apply later deltas. On interrupted bootstrap keep the previously valid library and offline files.
- Handle 409 restart, 410 full resync, duplicate/out-of-order notifications, reconnect and server restart without data loss. Bound retries so active server changes cannot cause endless bootstrap restart.
- Separate library projection revisions, durable sync checkpoint revisions and playlist edit revisions; they are not interchangeable.
- Prove no missed mutation between collection reads and the initial change cursor. If the current revision scheme cannot support this coherently, add a bootstrap/checkpoint token or retained snapshot strategy.
- Bound delta bytes and full playlist payloads; add paging/continuation or bounded batches where measurements require it. Include preference/follow-state reconciliation rather than assuming it is already in entity deltas.
- Share personal SSE collection per user where useful; current native streams poll per connection every two seconds. Suspend foreground subscriptions while inactive and resync on return.

Acceptance: complete 50k libraries for three users, multiple devices, concurrent edits and full-page traversal; no lost/deleted playlist occurrences; bounded response/memory; successful resume and expired-cursor recovery.

### S3 — Replay-safe offline mutations

Existing playlist revisions provide conflict detection and play-event IDs provide deduplication. These are useful foundations, not a general offline mutation protocol.

- Add a user-scoped operation ID/idempotency key for non-idempotent actions, especially playlist create/add and acquisition requests. Persist the result transactionally with the write, reject reused keys with different payloads, and define retention sufficient for supported offline periods.
- Use stable playlist entry IDs for occurrence edits. Position-based removal plus revision protects against some stale edits, but stable IDs make intent clearer during replay. Preserve intentionally repeated songs.
- Persist local outbox order, payload, expected revision, attempt/result and dependency links for temporary playlist IDs. Handle “write succeeded but response was lost.”
- Favourites replay explicit set/unset, never a toggle. Playlist conflicts should refresh server state and preserve the user's failed edit for explanation/reapply; silent overwrite is not acceptable.
- Initial online-only actions: removal/undo, password/session changes, import review/submit where it depends on live matching, and quality replacement decisions. Browsing, playback and supported personal edits remain offline-capable.
- Play history accepts only personal saved tracks and a 30-day timestamp window today. Define whether/how cloud listening is recorded and what happens to older offline events or removed memberships; a rejected event must not block an entire outbox indefinitely.

Acceptance: disconnect before/after server commit; replay twice; edit the same playlist on two devices; delete the target while offline; verify no duplicate acquisition or accidental entry loss.

### S4 — Media/download contract and source identity

- Add/verify size, container/codec, content type, version, checksum where available, ETag and Range/If-Range semantics. FileResponse alone is not acceptance evidence for interrupted downloads and source replacement races.
- `track_dto` has nullable source_sha and a source_revision derived from ID/hash/size/mtime. The scanner hashes path identity and covers but does not visibly produce an audio content hash. Do not treat source_revision as proof of file contents. Choose lazy content hashing with cached results or an explicit version identity; prove consistency when a source changes during hashing/transcode/download.
- Make downloads select a specific source version; verify bytes before atomic publication. Never leave a partial file marked downloaded or merge resume bytes from two versions.
- Signed saved URLs are session-bound and expire after six hours. Define delayed background scheduling, renewal and resumable retries; signed links cannot be assumed valid when the OS finally starts a transfer.
- Validate real codec/container combinations with AVFoundation on supported devices. Avoid the old roadmap's blanket format claims. Apple's [AVURLAsset media-type APIs](https://developer.apple.com/documentation/avfoundation/avurlasset/audiovisualcontenttypes) are a starting point; actual file fixtures and device playback close the gate.

Acceptance: locked-device download, interrupted/resumed Range transfer, source upgrade during transfer, low storage, cancelled transfer, invalid bytes, expired URL, server unavailable and revoked session.

### S5 — AAC device-copy service

Build the missing M10 service for optional phone/tablet AAC, compatibility fallback and Watch copies. Keep library originals unchanged.

- Durable jobs, user authorization at request/status/file access, source-version + preset + encoder-version cache key, deduplicated work and typed progress/failure responses.
- One transcode initially; pause/deprioritize while acquisitions or interactive demand require resources. Measure CPU, RSS and NAS read load before increasing concurrency.
- FFmpeg into a temporary cache file outside `/library`, validate decode/output, retain appropriate metadata/artwork, atomically publish. Avoid needless lossy-to-lossy conversion when an existing compatible smaller source suffices.
- Bounded cache, configurable quota, LRU for unpinned copies, restart recovery, cancellation/reference handling and protection for active transfers. Permission changes must not expose shared cached bytes to former members.
- Distinguish acquisition quality, local storage preference and playback compatibility. A device copy never upgrades the library or silently replaces its original.

Acceptance: concurrent duplicate requests generate one valid copy; source replacement invalidates it; queue/restart/quota/authorization failures are recoverable; all library originals remain untouched.

### S6 — Reconcile access and operate safely

- On successful authenticated reconnect, reconcile removals before selecting new playback sources. Cancel disallowed transfers and remove/invalidate their local files, metadata and Watch manifests. Interrupted reconciliation must be resumable.
- Revoked authentication must clear that account's usable local session/cache access when detected. Offline devices cannot learn revocation immediately; already buffered playback may require explicit stopping when detection occurs.
- Distinguish timeouts/server outage from authoritative revocation or removal. Do not erase downloads because Tailscale is unavailable.
- Sign-out/account/server switch cancels work and detaches the prior library/player. Recommend clearing that account's downloaded files on explicit sign-out; this local retention detail remains a UX decision.
- Keep storage-marker checks, backups, additive SQLite migrations and rollback. Native delivery cannot bypass NAS publication protections or expose the service publicly.
- Record privacy-safe timings, queue/transcode backlog, active streams, revision/restart counts, cache bytes and memory. Keep diagnostic export optional and scrub credentials, signed links and personal filesystem paths.

## 6. Playback scope: the highest-risk native package

Build a vertical prototype before finalizing the production player architecture. Test local MP3/AAC/ALAC/FLAC and actual library variants, progressively streamed originals, and provider streams. Inspect encoder delay/padding, sample rate/channel changes, track duration inaccuracies and overlapping audio-session behaviour.

Deliver:

1. A queue whose occurrence identity is separate from song/file identity. Play and Shuffle retain cloud entries and repeats; Previous restarts after the agreed threshold and otherwise changes occurrence.
2. Source resolution: valid downloaded original/copy, saved server file or compatible copy, then appropriate experimental remote resolution for cloud/catalogue songs. Household membership addition remains an explicit action.
3. Gapless scheduling with trim/padding treatment and advance buffering. Crossfade with two sources ready, a tested gain curve, clipping prevention, seek/skip/cancel behaviour and transition ownership of metadata/history.
4. Background audio, Now Playing and remote controls, AirPlay/Bluetooth, phone-call interruption, unplug/disconnect, route/sample-rate changes and app relaunch recovery.
5. Persistent queue/progress and history accounting: avoid double-counting overlapping songs, preserve user queue edits, avoid prebuffering the entire library.
6. Failure handling that keeps the queue visible and identifies unavailable songs, with retry/request/skip choices. Remote streaming never silently submits acquisition.

Proposed acceptance: for reference files with known continuous boundaries and adequate buffered data, capture output and compare around each boundary to prove no introduced silent gap or duplicated samples. Listen to continuous/live albums as well. “No gap over 0.5 seconds” is not true gapless. Crossfade tests prove the overlap, level envelope, cancellation and no clipped output. Test headphones plus a representative AirPlay/Bluetooth route; external route latency is characterized separately.

Unreliable third-party streams or insufficient network buffering cannot support an unconditional transition guarantee. True gapless remains required for supported saved/downloaded files; remote results must state tested capability and visibly recover when the next stream cannot be prepared. If guaranteed remote gapless is also required, it may require an authorized stable media delivery/cache strategy beyond the current experimental provider; do not silently label that solved.

## 7. Offline and storage behaviour

Store metadata separately from downloaded audio. Offline library browsing/search can show all previously synced items; an “On this device” filter shows playable downloads. Clearly identify unavailable network-only songs. Cache enough playlist/detail/artwork metadata to browse downloaded music without contacting the server.

Use a durable transfer state machine: queued, running, paused/retryable, verifying, ready, stale, failed, cancelled. A downloaded file remains valid while an upgrade is staged; atomically replace only after verification. Wi-Fi preference, cellular permission, quota/free-space headroom and per-collection selection belong in download settings. Streaming should not require downloading an entire album first.

Background URLSession handles OS-managed transfers, but force-quit cancels transfers and does not automatically relaunch the app. Persist intent and reconcile tasks on relaunch rather than promising uninterrupted downloads in every circumstance. See [Apple background session behaviour](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/background(withidentifier:)). Tailscale reachability while locked/backgrounded needs actual-device proof.

Example storage sizing, excluding metadata/artwork and filesystem overhead: 50,000 songs averaging four minutes at 256 kbps need about **384 GB decimal**. At an illustrative 1 Mbps lossless bitrate they need about **1.5 TB**. These are assumptions for sizing, not measurements of this library. A 50k metadata library must not imply downloading 50k songs to a phone. Selection, quota and visible byte estimates are essential.

## 8. Scale targets and verification

Target the agreed household, not hypothetical commercial SaaS. Worst-case planning fixture: three 50k memberships, both overlapping and disjoint files, realistic artwork, long playlists including repeated/cloud entries, and multiple native/web devices. The disjoint case can mean 150k physical tracks, while the overlapping case stresses personal projection duplication.

The existing native benchmark covers two users, the first two pages and an unchanged delta, with a 900 MB RSS guard. It does not prove complete 50k bootstrap throughput, three-user concurrency, long-playlist delta bounds or production memory headroom. Extend it rather than citing it as end-to-end scale acceptance.

Proposed gates, to calibrate with actual NAS/device baselines:

| Gate | Target / evidence |
| --- | --- |
| Warm native launch | First usable cached library within 1.5 seconds on oldest supported phone; no full network refresh blocking UI |
| Local search | p95 below 150 ms on a 50k metadata library; measure unicode/namesake/title searches |
| Scrolling | Smooth device-native refresh cadence; no main-thread stalls over 50 ms in an Instruments trace |
| Bootstrap | Measure all pages for all three entity collections plus playlists, not just first-page time; publish LAN/cellular bytes and completion times |
| Memory | Stay within the configured server limit with headroom under scan + sync + playback + artwork + transcode load; proposed steady-state ≤70% and peak ≤85%, refined from measurement |
| Streaming | Representative concurrent phone/web streams, seek/Range and artwork while another device syncs; no metadata request monopolizes interactive playback |
| Offline correctness | Download/kill/relaunch/airplane-mode/reconnect/source replacement/removal/account-switch matrix; deterministic replay and cache isolation |
| Playback | Measured gapless boundaries and crossfade envelopes on valid reference files plus real-device listening |
| Accessibility | VoiceOver, largest Dynamic Type, Reduce Motion/Transparency, contrast and touch targets on both phone and tablet |

Optimize measured bottlenecks: indexed SQL reads, bounded projections, cached checkpoints, batched writes, short lock scope and worker scheduling. SQLite/WAL remains appropriate unless concurrency measurements prove otherwise. Ensure only one coordinator owns acquisitions/transcodes; adding multiple API worker processes to the current in-memory locks/listeners can introduce correctness issues. PostgreSQL or object storage is a later deployment decision if the product becomes a broader shared service.

CI should run backend contract/security/migration regressions, generated Swift contract journeys, local store migrations, sync fault/replay tests, audio scheduling tests, app UI smoke journeys and iPad resizing. Real-device audio/network/battery/distribution acceptance complements simulator tests. Restore a stopped fixture backup into the exact candidate image before deploying migrations.

## 9. Phased packages, dependencies and estimates

Estimates include implementation, meaningful automated checks, documentation and package-level validation. They assume an experienced Swift/server engineer and existing server reuse. They exclude waiting for accounts/devices/review and the later optional features. They are person-weeks, not AI execution-time estimates.

| Package | Deliverable and completion gate | Depends on | Person-weeks |
| --- | --- | --- | --- |
| N00 | Freeze source/release baseline, parity checklist, device/distribution matrix and detailed backlog | Scope decisions | 1–2 |
| N01 | Gapless/crossfade + locked-device transfer vertical prototypes; choose audio architecture | N00, sample media/devices | 2–4 |
| N02 | Personal API typing/capabilities, coherent bootstrap, replay-safe mutations and media versions (S1–S4) | N00; N01 informs media | 3–5 |
| N03 | Production project, domain/store modules, sign-in/account isolation, adaptive phone/tablet shell | N00; N02 contract slices | 2–3 |
| N04 | Full sync, local search, library/details/playlists/favourites/Home | N02, N03 | 3–5 |
| N05 | Production player, queues, remote source/fallback, gapless/crossfade and Apple controls | N01, N03, media contracts | 4–7 |
| N06 | Requests/following, playlist mutations/import, removal/undo, account/quality/Plex | N02, N04 | 3–5 |
| N07 | AAC service, background/offline downloads, quotas/source upgrades/access reconciliation (S5–S6) | N02, N04, N05 | 3–5 |
| N08 | iPad interaction polish, accessibility, three-user 50k load, exact-image and device release acceptance | N04–N07 | 2–4 |

Base total: **23–40 person-weeks**. With roughly 25% contingency for audio, source-version/sync edge cases and real-device failures: **29–50 person-weeks** for full iPhone/iPad scope. Re-estimate after N01 and contract inventory; audio failure can widen the range. Two complementary engineers can overlap client/server work but cannot halve the critical path automatically. Account enrollment, signing, device availability and test cycles affect elapsed time.

Useful release slices:

- **Connected alpha:** sign-in, synced library, search and initial saved playback, after N01 architecture choice. This is explicitly not full parity or gapless/crossfade acceptance.
- **Everyday beta:** complete personal navigation, cloud playback/fallback, collections/actions/account, tested player transitions. Run alongside the web client against the same personal state.
- **iPhone/iPad complete:** offline/AAC/reconciliation plus all parity rows and real-device/scale gates pass. Admin remains web-only by design.
- **Watch complete**, then **Mac complete**, each with separate platform acceptance below.

Critical path: N00 → N01/audio decision + N02/contracts → N03/local foundation → N04/N05/N06 → N07/offline convergence → N08/release. Server capability work and UI foundations can overlap only where contracts are stable.

## 10. Watch, then Mac

### Watch: additional 5–9 person-weeks before contingency

Focused Watch experience: browse transferred/downloaded albums, playlists and favourites; independent offline playback to headphones; volume/transport; storage; phone remote control; sync/transfer status. Full catalogue discovery, imports and account editing stay on phone/tablet/web unless later requested. This is a task-focused companion, not a tiny copy of every phone screen.

- Prove paid-account install/update and paired-phone transfer on both Watch models. Do not assume standalone Watch traffic reaches the phone's VPN.
- Phone requests bounded AAC copies and sends versioned files/manifests using WatchConnectivity; verify metadata, checksum, acknowledgements, cancellation, stale updates, interrupted transfers and storage pressure.
- Apple explicitly requires paired-device testing for [WatchConnectivity file transfers](https://developer.apple.com/documentation/watchconnectivity/wcsession/transferfile(_:metadata:)); simulator results cannot close this gate.
- Decide phone-mediated-only credentials versus a separate Watch device session. A child-session endpoint is needed only if the Watch authenticates to the server itself. Local offline playback does not inherently require a server token on the Watch.
- Reconcile revoked/membership access through the phone when direct networking is unavailable. Include phone/Watch account switch and unpair/re-pair.
- Evaluate gapless/crossfade engine reuse and battery/thermal cost on Watch. The phone requirement does not automatically imply identical Watch DSP behaviour; approve Watch transition scope before coding its player.
- Complications/Smart Stack are optional after reliable playback and transfers, not prerequisites.

### Mac: additional 4–8 person-weeks before contingency

Start with a short comparison of Catalyst reuse against a native macOS SwiftUI target. Recommend native SwiftUI if desktop navigation, keyboard shortcuts, menus, resizable split views, system media controls and long-running downloads matter; Catalyst can shorten initial reuse but still needs desktop validation. Shared domain/store/sync/download/player code keeps either option viable.

Deliver the same everyday feature matrix, desktop queue/search/selection interactions, downloads/storage, sleep/wake, audio-device changes, multiple-window ownership and a single coherent playback session. Keep administration in the web app. Confirm macOS hardware/minimum OS before estimating compatibility. Package signing/notarization and updates separately from phone distribution.

## 11. Distribution and future improvements

| Choice | Benefit | Cost / dependency | Recommendation |
| --- | --- | --- | --- |
| Paid account + Ad Hoc | Small private registered-device audience, no need to make the server public for distribution | Device registration, signing/provisioning renewal and manual update process | Strong fit for this 2–3-person household; prove installation/update/Watch first. See [Apple registered-device distribution](https://developer.apple.com/documentation/xcode/distributing-your-app-to-registered-devices) |
| Paid account + TestFlight | Convenient beta installation and feedback | Builds expire after 90 days; external beta review/access requirements; private Tailscale-only service complicates review testing | Useful beta option; plan synthetic review/demo access rather than exposing the household server. See [Apple TestFlight overview](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/) |
| Free-account Sideloadly | Retains current no-paid-account route | Refresh/capability/Watch proof and ongoing household maintenance remain unresolved | Fallback if paid enrollment is deferred; do not use old refresh assumptions as acceptance evidence |
| Public App Store | Easier broader distribution | Product/support/privacy/review and authorized content/provider questions become a separate project | Not required for a private household app |

Distribution does not change the private server access policy. A paid account enables distribution choices; it does not by itself solve Watch networking, background transfers or reliable provider streaming.

Future improvements to consider after parity:

- Cross-device queue/position handoff: useful for phone-to-Mac/Watch continuity, but requires device-scoped playback sessions, explicit transfer ownership and conflict rules. The acquisition queue is not a playback queue.
- Push request completion: convenient if paid-account capabilities and APNs server work are acceptable; foreground SSE/polling remains sufficient initially. Never rely on push for sync correctness.
- Smart downloads: selected playlists/favourites first; later frequency/storage-aware rotation, with pinned-file protection and clear user control.
- Shared listening history improvements and better Home recommendations: settle cloud/offline history semantics before adding recommendation algorithms.
- Direct recognition/Shazam inbox: separate external integration and request provenance package, consistent with the existing later roadmap.
- More reliable remote playback: provider adapters, contract fixtures, failure metrics and circuit breakers first; stable proxy/cache delivery only where technically and contractually supported. Do not turn an experimental matcher into an implied catalogue guarantee.
- Filesystem change watcher: reduces manual scans, but must cooperate with atomic publication/organisation and NAS identity protections.
- CarPlay, widgets and other platforms: independent feature/capability packages; CarPlay is explicitly not required now.

Avoid prematurely adding public accounts, cross-household sharing or multi-tenant hosting. If that direction changes, revisit storage authorization, tenancy, provider limits, backups, quotas, deployment isolation and operations rather than assuming the present household design scales unchanged.

## 12. Decisions still needed and definition of done

Remaining decision points do not prevent this scope from being actionable:

1. Complete free-account Xcode device installation for initial testing; confirm devices/OS, especially iPads. Revisit paid enrollment and Ad Hoc versus TestFlight for sustained distribution.
2. Accept simple crossfade on/off with a tested default and album-order exception, or specify another interaction. This is a recommendation, not a recorded approval.
3. Agree media matrix and remote transition guarantees after N01. Saved/downloaded gapless is required; experimental stream guarantees need evidence.
4. Choose local download cleanup on explicit sign-out, cellular default, quotas and pinned-download rules during UX design.
5. Confirm Watch transition requirements and standalone network expectations before its implementation.
6. Supply staffing/deadline if an elapsed-time schedule is needed; person-week estimates alone are not a calendar commitment.

Completion means every in-scope parity row has passed owner/member journeys on iPhone and iPad, supported gapless/crossfade have measured evidence, downloaded music works offline and reconciles correctly, three 50k libraries pass representative concurrency tests, generated contracts match the exact candidate server, migrations/backups/rollback are exercised, and installation/update instructions are proven on real devices. Watch and Mac have their own later completion gates. A simulator build, feature stub or generated endpoint does not count as feature delivery.

## 13. Evidence and review limits

Source reviewed: Swift package/spike and contract tests; API schema/models; personal/auth/native/catalogue/Home/artwork routes; sync/store projection/scanner/security/media handling; web shell/library/search/player/requests/account/admin components; current blueprint, prior native roadmap and delivery notes. Contract operation counts and schema equality were checked with a local script.

This review did not run the backend/Swift suites, modify runtime code, contact Unraid, inspect actual media files, measure device/server performance or verify current signing/provider availability. Existing test/build results cited in older documents remain historical results, not freshly rerun checks. The existing dirty working tree was preserved; this scope file is the only change made for the request.

Key implementation references: [PigKit](../swift/PigKit/Package.swift), [API models](../server/api_models.py), [native sync](../server/native_sync.py), [native events](../server/routes/native.py), [personal routes](../server/routes/personal.py), [source DTO/projections](../server/user_library.py), [scanner](../server/scanner.py), [media and remote routes](../server/app.py), [security](../server/security.py), [current web navigation](../client/src/AppShell.tsx), [playlist song identities](../client/src/songs.ts), [native benchmark](../scripts/benchmark_native_sync.py).
