# Native uplift: first connected alpha

11 October 2026, Australia/Melbourne. Local implementation only. No server deployment, signed IPA, account enrollment or physical-device acceptance is claimed. Existing uncommitted web/server fixes were preserved.

## Delivered in source

- A distinct production `swift/PigMusic.xcodeproj` target for iPhone and iPad, provisional minimum iOS/iPadOS 18, shared scheme, original approved icons/transparent brand mark, explicit background-audio plist and reproducible project generator. The disposable NativeSpike remains separate.
- Shared PigDomain, PigStore, PigSync and PigPlayback modules. GRDB 7.11.1 is added to the existing resolved package set; existing Apple package versions are retained.
- Keychain device sign-in, HTTPS server validation, server/person-specific hashed cache namespaces, cached-session restoration, authenticated refresh and sign-out/revocation handling. Neither passwords nor device tokens are stored in the library database or defaults.
- Transactional SQLite full replacement/deltas, local FTS5 search, bounded library list pages, album-track lookup, migration and old-cache preservation when network/resync fails. Bootstrap checks revision coherence across collections and closes the read window with a delta before publication. Changing revisions retry at most three times.
- Initial SwiftUI library/album/song/artist/playlist views, local search, Account connection/sync/sign-out, phone tabs, tablet sidebar, mini-player and Now Playing sheet. These are partial screens, not completed parity journeys.
- Saved signed-URL and experimental cloud playlist source resolution. Queues preserve repeated occurrences; Previous restarts after three seconds or selects the previous occurrence. Basic AVPlayer playback, seek/next/pause, system media commands, interruption/route handling and Now Playing metadata are implemented. Cloud failure does not acquire music.
- A separate decoded-PCM transition renderer and command-line PigAudioProbe for measuring direct joins/linear crossfades. This is not the production live transition engine.
- A realtime queue scheduling candidate with one-occurrence source prefetch, source lease cleanup, per-transition decoder continuity, audible-position markers, seek/skip/pause intent and stale-callback rejection. [Realtime queue evidence and app/device gates](native-realtime-queue-20261011.md). The default app player remains AVPlayer.
- A temporary signed-audio preparation layer with explicit file leases, bounded chunk writes/storage, one expired-link refresh and cancellation fencing. It is connected to the bounded engine in synthetic capture tests; [source preparation evidence and remaining gates](native-source-preparation-20261011.md). The live app is not wired to complete-file preparation yet.
- A bounded block decoder/transition stream and AVAudioEngine output-capture prototype, with immutable PCM transfer across actor boundaries, mixed-rate conversion and fixed-size tail/head storage. See [audio prototype evidence and gates](native-audio-prototype-20261011.md). The app's live player remains AVPlayer.
- Authenticated saved-library artwork in song rows, album previews/details, mini-player, Now Playing and system media metadata. Encoded disk cache is isolated by server/person, capped at 64 MiB per account, with coalesced fetches, persistence, corruption recovery and least-recently-used eviction. Decoded thumbnails use NSCache with 24 MiB/128-entry eviction targets, background decoding and 2 MiB/per-variant pixel bounds. Missing/failed artwork falls back to a music symbol and retries on the next library refresh; sign-out clears memory and cancels pending artwork work.
- Native fixture tests and a 50k cache regression; CI now also builds the production iPhone/iPad target. A Debug-only synthetic demo supports UI inspection without real credentials or server access.

## Verification actually run

| Check | Result / limits |
| --- | --- |
| Earlier backend baseline | **244 passed** in the local Python 3.14 virtual environment, aligned to the committed runtime lockfile; disposable fixtures only. This predates the concurrent download-source implementation |
| Earlier web baseline | **11 passed**, strict TypeScript/production build passed; routine lucide bundler warning remains. This predates the concurrent download-source implementation |
| Native suite after realtime queue continuation | **45 passed**: 5 XCTest API/transport/real-fixture journeys and 40 Swift Testing core/audio/scale/artwork/source/queue cases; fixture journeys enabled, no skipped contract tests |
| Realtime queue software | Ten new cases passed: three-occurrence engine capture with complete mix-envelope checks, every sample in a unique three-part album, repeated short tracks, seek, pause intent, skip/replacement/callback cancellation, source lease cleanup and outgoing-audio completion before an upcoming-source error. Lifecycle tests use silent controlled output; live adapter/device acceptance remains pending |
| Source preparation | Eight new synthetic cases passed: bounded complete writes, signed-link refresh, credential isolation, error/size/partial cleanup, storage leases and cancellation during resolution/body transfer. Prepared extensionless WAV responses fed the bounded engine for an 8,400-frame capture with 1,200-frame overlap |
| Generated client integration | Member sign-in, full typed collections → SQLite, local search/album lookup, unchanged delta refresh, personal signed media URL and session revocation against the disposable loopback server |
| Large local cache | 50,000 tracks fully persisted, distinct bounded pages and indexed search; test completed in **6.4–28.5 seconds on this Mac across observed runs**; the latest realtime regression run took 20.6 seconds, with other work sharing the machine. This is not a controlled benchmark, phone timing or three-user server load result |
| Audio reference | PCM output boundary samples/envelopes checked; existing 44.1 kHz AAC tone decoded and joined to 264,600 frames, one-second overlap to 220,500 frames with 44,100 overlap frames |
| Bounded engine capture | Unique 44.1 kHz samples preserved across an album boundary; 48 kHz join/fade envelope, mixed-rate/channel conversion and long-track storage regression passed. Synthetic eight-format observations and Vorbis input-padding qualification are in the audio prototype record |
| Artwork | Real fixture WebP response decoded at 256 px; cache persistence/isolation/coalescing, corruption/eviction, cancelled waiter, unsafe keys, image/byte bounds, bearer destination, missing token, 401 clearing and non-image/error responses covered |
| Production app build | Unsigned generic iOS simulator build succeeded, followed by arm64 incremental builds; iPhone and iPad device families present |
| Simulator launch/layout | Installed/launched on booted iPhone 17 Pro Max and iPad Pro 13-inch (M5) simulators; synthetic library, artwork and sign-in screenshots inspected. No physical-device or live-system-artwork acceptance claimed |
| Contract/source checks | OpenAPI drift check passed; Python project-generator formatting and whitespace checks passed; new Swift sources formatted with Xcode swift-format |

An early 50k test exposed quadratic full-text maintenance. Search rows now share indexed row IDs with track rows, with a v2 rebuild migration. The rerun passed. An AAC command failed inside the filesystem/process sandbox but passed with access to Apple's codec services; the AAC decoder is now also covered by the native suite. These are corrected verification findings, not provider/device acceptance results.

Build/test logs, audio exports and simulator screenshots are under ignored `swift/build/`. Screenshots use only synthetic library/person data. The fixture process is stopped after validation. No live library files, appdata, requests or settings were accessed or changed.

## Remaining before everyday parity

The live player still uses an initial AVPlayer implementation. It does not yet guarantee true gapless or implement live crossfade. The offline probe proves sample manipulation/decoding only. Streaming decode/prebuffering, format/sample-rate transitions, encoder trimming and actual audio output must drive the N01 architecture choice and N05 implementation.

The client has no offline audio downloader/AAC service, persisted playback queue/history outbox, SSE subscription, full catalogue search/Home feeds, artist catalogue/details, playlist/favourite/request mutations/import review, removal/undo, personal quality/Plex/password/device management, or full accessibility/device acceptance. Library metadata caching does not imply downloaded audio playback. Experimental provider availability was not tested live. Artwork support currently covers content-addressed saved-library covers; catalogue portraits, logos and catalogue-only covers remain future work.

Auth/cache logic is exercised through package tests and the real fixture transport; end-to-end app sign-in with Keychain on physical devices remains unverified. Audio interruption/route behaviour, locked/background streaming, Tailscale over cellular, resizing/Dynamic Type/VoiceOver, signing/update distribution and three-user 50k concurrency remain acceptance work.

Package status against [the scope](native-uplift-scope-20261011.md): N00 baseline recorded; N01 probe in progress; N03 production foundation in progress; N04 cached browsing and N05 initial playback started. N02 server contract completion, N06 personal feature parity, N07 offline media and N08 release acceptance remain pending. Watch and Mac remain later phases.

## Concurrent server work and artwork contract boundary

The owner advised that another agent is implementing additional download clients. Native artwork work changes no production server/provider implementation or server OpenAPI source. The disposable fixture now includes generated cover bytes. The concurrent server agent supplied a `--server-only` export option; after its contract check passed, the native schema copy was synchronized to that export, including the new `native_standard` profile enum, and rebuilt. Native quality controls do not yet expose this option. Shared working-tree server/API changes belong to that concurrent work; the earlier backend/web baseline is not a verification claim for those later changes.

The current generated artwork operation incorrectly declares JSON, while the endpoint actually returns WebP. `ArtworkTransport` is an interim binary adapter to the existing authenticated route, with HTTPS-origin validation, ephemeral sessions, cookies/URL cache disabled, redirect refusal and bounded streaming bytes. It does not interpret arbitrary catalogue/CDN URLs or forward device credentials to them. Correct binary response declarations can replace this adapter in a later coordinated contract pass.

Image downsampling follows Apple's [Image I/O thumbnail pixel bound](https://developer.apple.com/documentation/imageio/kcgimagesourcethumbnailmaxpixelsize) and binary reads use [URLSession async bytes](https://developer.apple.com/documentation/foundation/urlsession/bytes(for:delegate:)). Automated transport tests use a synthetic URLProtocol; live TLS/redirect delivery and system media artwork on physical devices remain acceptance work.

The download-source assessment proposes retained Opus/Vorbis formats. Native original playback/download compatibility must be tested for the actual formats that implementation enables. Codec-specific preferences are not exposed by this native slice; future quality UI must consume the final server contract and keep acquisition separate from remote listening.

Next development slice: add an opt-in app integration for the realtime queue with audio-session lifecycle and system playback controls; complete live network/device acceptance, then expand the personal typed contract and Home/catalogue discovery with replay-safe personal actions against the same cached domain/store. Preserve the web-only administrative boundary.
