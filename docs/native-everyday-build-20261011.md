# Expanded iPhone and iPad testing build

11 October 2026. The owner authorized publishing this expanded candidate to main, superseding the earlier hold in the search/actions milestone. It remains a testing candidate; physical-device acceptance, production Watch and Mac apps are not complete. No live Unraid rollout is included.

## Implemented

- Saved/household/catalogue search, Home feeds, remote provider fallback, favourites, explicit household membership and song/album acquisition from the previous milestone.
- Revision-aware playlist create, rename, delete, song addition/removal and reorder. Swift explicitly appends repeated occurrences; legacy callers retain deduplicated addition. Uncertain writes are not automatically replayed. Apple XML import includes a read-only personal/household/missing match preview and a 20 MiB limit. Import never submits acquisition.
- Account appearance, personal Plex credentials, acquisition quality preferences, password change and session review/revocation. Invitation links or codes activate a member account. Administrative controls stay on the web.
- Catalogue artist acquisition by albums/singles/EPs, new-release monitoring, cancellation and failed/cancelled song-request retry. Typed artist responses exclude internal ownership and generation fields. Monitoring records existing releases as a baseline unless the user explicitly requests the catalogue.
- Account-bound original/AAC device downloads, storage budgets, Wi-Fi transfers, pause/resume/retry/removal, downloaded playback and artwork caching. Files publish only after exact byte-count/SHA-256 verification. Receipts survive restart; partial transfers restart from the beginning. Successful authenticated sync removes downloads whose membership or source version changed. Outages retain downloaded access; detected revocation/account switch clears local download access.
- A separate server AAC service: migration 8, durable deduplicated jobs keyed by source checksum/preset/encoder version, one worker, priority for acquisition publication, decode validation, atomic publication, bounded LRU cache and leases protected until delivery ends, including disconnects. Originals remain unchanged. Default cache budget is 5 GiB; `PIG_DEVICE_COPY_CACHE_BYTES` configures it. Source checksums are cached using filesystem identity/version; oversized sources above 2 GiB are rejected.
- Cached Home content/preferences, foreground SSE revision/revocation updates, bounded frames, reconnect backoff and manual refresh fallback. Live connections and device downloads pause when the scene is inactive; audio playback retains its existing background session behavior.
- Full cached-library shuffle, play-next/add-to-queue, upcoming occurrence movement/removal, and a persisted queue/position that restores paused. Now Playing shows a bounded preview with a lazy full queue editor. Queue metadata is rewritten only after occurrence changes; position checkpoints remain small.
- Durable SQLite listening outbox with stable occurrence event IDs and server replay deduplication. One qualified listen is recorded after 30 seconds of actual playing time; seeking does not add listening time. It records a qualified play, not full listening-duration analytics. Removed tracks and events outside the server's 30-day window are discarded after confirmed sync; failed delivery remains queued.

## Verification

Validation: 358 backend, 80 native (disposable server enabled; no skips) and 38 web tests pass, as do the web production build, schema and formatting checks. Final simulator build results are recorded in the testing handoff. Tests cover original-copy authorization and Range delivery, AAC encode/decode with unchanged originals, duplicate jobs, lease/quota eviction, restart/source invalidation, disconnected transfers, read-only import review, native download checksum/quota/restart/reconciliation, bounded SSE parsing, occurrence-preserving queues and durable history replay. The generated Swift client is exercised against a disposable authenticated server for playlist conflicts/repeats, imports, settings, artist controls, listening and device-copy manifests.

Use the matching candidate server: old server versions do not provide device-copy/import-preview contracts. Server migration 8 and native cache migration v4 are additive. Back up stopped server state before testing an upgrade; reverting the image requires its matching database backup. Device-copy files are disposable appdata cache, separate from the original music library. Container build/runtime checks run in GitHub CI because Docker is unavailable on this Mac.

## Remaining roadmap

| Package | Status and remaining work |
| --- | --- |
| N00 baseline | Scope and baseline recorded; this candidate substantially extends everyday phone/tablet features. |
| N01/N05 playback | Streaming remains the default. The opt-in seamless engine supports gapless/crossfade scheduling and downloaded sources; real iPhone/iPad captures, codec compatibility, interruptions, Bluetooth/AirPlay, background timing and low-storage acceptance are pending. Explicit seamless queue edits rebuild prefetch at the current position and can briefly rebuffer. Repeat/shuffle modes, richer unavailable-song recovery and exact overlap-aware duration analytics remain. |
| N02 server contract | Everyday typed contracts expanded, AAC and idempotent history added. General offline mutation outbox/idempotency/conflict resolution, cached 50k three-user concurrency/load acceptance and richer diagnostics remain. Do not automatically replay uncertain playlist/acquisition writes. |
| N03 onboarding | Sign-in/invite/keychain/account isolation implemented; free Personal Team installation/update must be proven on owner devices. No signed IPA or TestFlight artifact is supplied. |
| N04 browsing | Saved search, Home, catalogue, household and artist release navigation implemented. Rich artist biography/popular content/portraits, release filtering, broader offline discovery cache, contextual sorting and accessibility/large-library device acceptance remain. |
| N06 personal features | Core playlists/imports/favourites/membership/removal/undo/settings/acquisition/monitoring implemented. Remaining deeper import review/selection, playlist Plex export/status workflows and individual shared acquisition cancellation need scoped contracts and journeys. General editing is online only. |
| N07 offline | Original/AAC foreground downloads and authoritative reconciliation implemented. OS-managed background transfers, byte-range resume, scheduling/cellular policies, storage-pressure handling, smarter preservation of an existing copy during quality changes, transcode artwork/compatible-source reuse and file-integrity/codec device acceptance remain. Enqueue batches are currently limited to 10,000 tracks; storage budgets limit downloaded bytes. |
| N08 acceptance | Simulator builds and automated tests pass as recorded; physical-device, provider/network, accessibility and three 50k-user load gates are open. |
| Watch then Mac | Production applications, phone/Watch transfer/session semantics, standalone networking and hardware proof remain later phases. The old feasibility Watch target is not a delivered production Watch app. |

This build is useful for broad testing but does not claim full parity or close the approved acceptance gates.
