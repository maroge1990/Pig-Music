# Native realtime queue candidate — 11 October 2026

This slice adds a realtime scheduling candidate and connects it to temporary source preparation. Streaming remains the default; Account → Playback testing now exposes the opt-in seamless candidate. Hardware output, interruptions/routes/background playback and live networking have not been accepted. This is N01/N05 implementation evidence, not completion of native playback parity.

## Implemented

`QueuePCMStream` opens current and upcoming source leases, prefetching one occurrence ahead. It decodes on its actor into bounded stereo blocks, holds the outgoing tail/incoming head for each transition, and carries the incoming decoder's position forward. It releases outgoing encoded storage before acquiring the following occurrence. Source identity follows occurrence UUIDs and queue positions, including repeated track IDs.

A sequential album uses the existing stable-album/numbering policy to suppress overlap. Other transitions use complementary linear gains with the configured internal duration (0–12 seconds). Very short songs bound overlap by the available decoded tail/head; audio consumed as an incoming head is not replayed when that song becomes outgoing. A song fully consumed by the preceding overlap has no remaining tail for another fade. This is an engineering policy, not an approved crossfade settings UI.

The stream emits timeline markers: incoming audio origin, principal-metadata switch at overlap midpoint, actual decoded duration and queue index. The realtime scheduler computes elapsed time from the output sample clock and that origin, so the incoming occurrence has already advanced by half the overlap when its metadata becomes principal. On seek, a fresh decoder opens at the corresponding source-frame position; converter/filter history resets. Ordered mixed-rate albums and seek precision in compressed files still require format/device captures.

`RealtimeQueueSession` owns preparation/pumping and exposes snapshots plus play/pause/seek/next/previous/stop controls. Pause intent is independent of preparation: late completion cannot start music the user paused. Queue replacement and seek cancel previous work, stop its output, invalidate old callbacks and wait for old lease cleanup before reserving new sources. Cancellation propagates into an awaited upcoming transfer. Previous restarts after three seconds; otherwise it selects the prior occurrence. Stop-and-wait guards against clearing a replacement session created while cleanup was suspended.

The scheduler keeps no more than four full blocks' worth of PCM outstanding (8,192 frames at the default 2,048-frame block size). Consumption callbacks do only a bounded main-actor counter update. Decoding/file transfer never executes in an audio render callback. Obsolete timeline markers are pruned; an independent clock refreshes snapshots about ten times a second, including while the pump awaits the next source, and reports buffering when scheduled audio drains.

`EngineQueueOutput` is the AVAudioEngine/AVAudioPlayerNode live adapter. It schedules buffers using `.dataPlayedBack` completions, exposes the player's sample clock and supports pause/resume/stop. The app must own AVAudioSession activation, interruptions and route/configuration changes. The output protocol also permits silent deterministic lifecycle tests.

The source-preparer overload accepts `AudioSourcePreparer` and an asynchronous track URL resolver, such as `NativeService.resolve`. It maps acquired files to explicit leases and releases them through the preparer. It does not create a second provider implementation or send server credentials with audio requests.

If the upcoming source fails acquisition/decoder preparation, the outgoing retained tail is emitted normally. The scheduler drains already queued audio before reporting the failure and clear provider fallback. It does not silently skip requests or substitute a different recording.

## Software evidence

Ten new tests exercise:

- Three-song crossfade decoding: 120,000 frames from three 48,000-frame sources with two 12,000-frame overlaps; incoming origins at frames 36,000 and 72,000, principal metadata switches at 42,000 and 78,000. At most two source leases are active, all released on close.
- Actual offline AVAudioEngine capture of that three-song mix, checking the output envelope across every sample and the 8,192-frame scheduling lead bound.
- A three-part continuous album containing a unique 14,400-sample ramp: actual engine capture preserves every sample, with maximum error below 0.0000001 and boundaries at frames 4,800 and 9,600.
- Three very short repeated occurrences, preserving separate identities and avoiding replay of consumed heads.
- Ordered-album suppression of crossfade and a half-second seek starting at the expected position/frame count.
- Pause during preparation, paused seek, explicit resume and complete lease cleanup.
- Replacement of a playing queue and rejection of stale output callbacks.
- Skip during initial preparation while preserving paused intent.
- Cancellation of an awaited 30-second synthetic upcoming transfer, with replacement ready inside a five-second test deadline rather than waiting for that timeout.
- Failure of the upcoming source: all 48,000 outgoing frames are consumed before error reporting.

Lifecycle tests use a silent output whose consumption callbacks are controlled by the test. Engine capture tests use offline manual rendering. No speakers, real provider, household media or physical device are involved. This does not measure realtime audible continuity or prove device sample-clock/latency behavior.

Build/test logs are ignored local artifacts: `swift/build/realtime-queue-tests.log`, `swift/build/realtime-native-final.log` and `swift/build/realtime-app-build.log`. The final complete suite passed **45 tests** (5 XCTest and 40 Swift Testing), with real disposable-server journeys enabled and no skipped contract tests. The unsigned arm64 iPhone/iPad simulator app build passed. The 50k local cache case passed in 20.6 seconds on this shared machine; this is not a controlled performance result. The fixture was stopped after validation.

## Remaining before app replacement

1. Accept the new opt-in app integration on physical devices. Media commands/artwork/Now Playing publishing, on-demand audio sessions, interruption intent and route/configuration recovery are implemented. Teardown awaits decoder cleanup before resetting source storage; paused pumps intentionally remain alive until stopped. Hardware lifecycle behavior remains unverified.
2. Measure live source readiness/startup latency and actual output on iPhone/iPad, including locked/background output and Bluetooth/wired route changes. The current transport prepares complete files. If the upcoming file is late, awaiting it can underrun scheduled PCM; no seamless streaming claim or underrun recovery is made. A short first song can also wait for its upcoming source during initial prebuffering. Design buffering feedback and progressive/range or stream-first fallback from these observations.
3. Confirm `.dataPlayedBack` callback timing and scheduling lead under CPU/network load, and correlate the node clock with device output latency. Current midpoint metadata policy uses that clock; hardware timing has not been measured. The independent clock observer removes the pump-readiness dependency, but output timing remains a hardware gate.
4. Measure compressed-file seek accuracy, encoder delay/padding, real Opus/Vorbis/FLAC inputs and resampler filter history across album boundaries. Existing synthetic codec observations are in the earlier audio evidence record, not blanket format/device acceptance.
5. Accept the account-scoped two-file temporary cache, startup cleanup and successful-refresh invalidation on device, then implement durable original/AAC offline storage/reconciliation. Per-preparer encoded storage limits remain 128 MiB/file and 256 MiB total, while queue PCM storage is bounded separately by fade and block size.

The live adapter compiles for the app's provisional iOS 18 target; runtime observations so far use the installed Mac toolchain. The app integration preserves the server download-client work and consumes the synchronized contract. See the [combined testing handoff](native-testing-handoff-20261011.md).
