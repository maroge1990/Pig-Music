# Native audio source preparation — 11 October 2026

This slice connects secure media URL resolution to the existing bounded local-file audio prototype. It adds `AudioSourcePreparer` in PigPlayback. It does not replace the application's live AVPlayer, implement progressive decoding, or create persistent offline downloads.

## Implemented contract

- An injected asynchronous resolver obtains a fresh URL. The production owner can supply `NativeService.resolve(track)`, retaining its same-origin validation for saved media and provider fallback for remote music. The preparer accepts HTTPS URLs without embedded credentials or fragments.
- Media transfer uses an ephemeral session with cookies, URL cache, credential storage and inherited additional headers disabled. Device bearer authentication belongs to the resolver's server API call; it is never added to the media request. HTTP redirects are refused. Providers requiring redirects will report unavailable until a separately validated redirect policy exists.
- A media response of 401 or 403 triggers one fresh resolution and one retry. Persistent rejection, redirects, 404 and server errors stop. Resolver authentication errors propagate; a signed-file rejection alone does not clear the device credential.
- Only complete HTTP 200 audio or octet-stream responses become leases. Declared oversized bodies are rejected before writing; undeclared bodies are counted while reading. Empty and declared-length-mismatched bodies fail. MIME metadata is not codec validation: AVAudioFile/decoder acceptance remains a separate gate.
- Encoded bytes are written in 64 KiB chunks to a unique partial file, then renamed after successful completion. MIME-derived suffixes support server routes with no filename extension. Error and cancellation paths remove partial files. Signed URLs and query tokens are not recorded in filenames or logs.
- Default policy is one transfer at a time, 128 MiB per file, 256 MiB per preparer. Existing leases reserve their actual byte sizes and each new transfer reserves the full per-file allowance. Concurrent calls fail explicitly rather than starting extra transfers. Limits are configurable constructor policy, not user preferences yet.
- The caller explicitly releases current/upcoming leases when decoding ends. Queue/account replacement must stop the decoder before calling `reset()`. Reset cancels pending preparation, invalidates publication and removes owned leases. Destruction cancels the session and removes its unique directory.

The file limit and chunk sizes bound owned application buffers and encoded storage. They do not establish a total memory bound for URLSession, the operating system or codec services. A failed filesystem deletion is best effort; filesystem capacity/error acceptance and startup cleanup remain below.

## Evidence

Eight synthetic source tests cover complete chunked writes and release, absence of bearer/cookie headers even when injected into session configuration, one expired-link retry, persistent rejection, advertised/unadvertised size overflow, empty/truncated bodies, insecure URLs, redirects/error pages, storage reservation, cancellation/reset during resolution, partial-file cleanup after cancellation during a stalled body transfer, and concurrent-request refusal.

The integration case transfers two synthetic WAV responses at extensionless signed endpoint-shaped URLs, opens the prepared files with the bounded decoder, and captures actual offline AVAudioEngine output: **8,400 frames**, **1,200 overlap frames**, with the existing 8,192-frame scheduling lead bound. It releases both files afterward. This proves the prepared-file/decoder handoff with synthetic URLProtocol transport, not live TLS or provider delivery.

Logs are ignored local artifacts: `swift/build/audio-source-tests.log`, `swift/build/source-native-final.log` and `swift/build/source-app-build.log`. At this source-preparation milestone, the complete native suite passed **35 tests** (5 XCTest, 30 Swift Testing), including real disposable-server journeys. The unsigned arm64 iPhone/iPad simulator app build passed. The fixture was stopped after validation. The 50k local cache case passed in 25.0 seconds in the final run; shared-machine timing is not a controlled performance result. No production server/provider implementation was changed by this slice.

## Next gates and choices

1. Add a realtime queue owner that prepares current/upcoming sources, owns their leases and decoder lifetime, and replaces seek/skip work with generation fencing. Preserve pause intent while preparation completes; system metadata must follow the audible occurrence through fades.
2. Measure startup delay and next-track readiness over household network/cellular. Complete-file preparation is intentionally the first verifiable handoff, but can delay playback and exhaust a 120-second transfer timeout on slow links. Choose a progressive decoder/range transport or a stream-first fallback based on those captures; do not silently promise complete-file gapless for every network condition.
3. Test cancellation during a live body transfer, timeouts, disconnect/reconnect, actual signed-link renewal/revocation, provider expiry/redirect behavior and TLS on iPhone/iPad. Deterministic cancellation tests cover resolution and a stalled body; physical network cancellation remains unverified.
4. Validate downloaded formats and MIME behavior from the actual server/provider encoders, including octet-stream bodies and decoder rejection. Large lossless songs over 128 MiB require an explicit larger-budget or streaming policy; the current preparation path rejects them with a clear storage error.
5. Integrate account-scoped temporary-root ownership and startup scavenging. Unique directories prevent cross-owner overwrites; per-preparer limits are not a global multi-instance disk quota. Process crashes can leave temporary directories until that owner performs cleanup. Durable original/AAC downloads will have separate identity, quotas and reconciliation.
6. Complete encoder trimming and resampled-album filter-history captures, realtime gapless/crossfade, interruptions/routes/background acceptance before replacing the app player. This remains N01/N05 development, not release acceptance.
