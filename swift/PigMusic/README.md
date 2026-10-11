# Pig Music iPhone/iPad client

Production target under active development. This first connected alpha supports private HTTPS device sign-in, account-bound SQLite library caching, local song search, paged library lists, album tracks, saved/cloud playlist queues, signed saved playback, experimental remote source resolution, transport/Now Playing controls and sign-out. Phone tabs and tablet sidebar layouts share the same services.

Saved-library covers now display in library/album/player views and system Now Playing metadata, with an account-isolated disk cache, bounded thumbnail memory cache and symbol fallback. Catalogue portraits/logos and catalogue-only covers remain pending.

It is not the complete native feature-parity release. Home/catalogue discovery, personal mutations/account settings, SSE, offline audio downloads, AAC service, and full gapless/crossfade device acceptance remain in the [approved scope](../../docs/native-uplift-scope-20261011.md). Administrative tools remain web-only.

Open `swift/PigMusic.xcodeproj` from the repository root and select the **PigMusic** scheme. Minimum build target is iOS/iPadOS 18; exact household device/OS acceptance remains pending. Choose the developer team only in Xcode's signing UI. No signing account is stored in the repository.

From the repository root:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  xcodebuild -project swift/PigMusic.xcodeproj -scheme PigMusic \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath swift/build/PigMusic \
  -skipPackagePluginValidation CODE_SIGNING_ALLOWED=NO build

DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  swift test --package-path swift/PigKit
```

For the native-server contract journey, start `python -m scripts.serve_contract_fixture` using the backend virtual environment in a separate terminal, then run `PIG_CONTRACT_SERVER=http://127.0.0.1:8781 swift test --package-path swift/PigKit`. That loopback HTTP exception exists only in the test transport; the app requires HTTPS. The fixture contains generated users and disposable audio, not household data.

Add `--demo` in the Debug scheme's launch arguments to browse a synthetic in-memory library and play a bundled three-second tone without networking or credentials. Demo entry points are excluded from Release compilation. This is a UI review aid, not proof of real-server or physical-device playback.

The checked-in Xcode project is reproducible with `python scripts/generate_native_project.py`. Regenerate after adding app Swift files. PigKit packages remain separately testable, and both app/package dependency lockfiles are checked in.

Audio investigation tool:

```sh
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer \
  swift run --package-path swift/PigKit PigAudioProbe \
  first-audio-file second-audio-file output.wav 0
```

The last argument is overlap seconds, 0–12. Zero joins decoded samples directly; a positive value applies complementary gain ramps. Inputs must have the same sample rate/channel count and fit the probe's allocation bound. This offline tool is deliberately separate from streaming playback; it does not establish live AVPlayer gaplessness or crossfade. Apple audio codec services must be accessible when decoding compressed files.

See [delivery evidence and remaining work](../../docs/native-uplift-delivery-20261011.md).

Use `PigAudioProbe --bounded first second output.wav overlap-seconds` for bounded decoding, mixed-rate normalization and actual AVAudioEngine manual-rendering output capture. Streaming remains the default; Account → Playback testing enables the seamless candidate. [Audio prototype evidence](../../docs/native-audio-prototype-20261011.md) records measured boundaries, memory limits, codec fixtures and the remaining realtime/network/device gates.

`AudioSourcePreparer` provides temporary encoded-file leases for the opt-in engine integration. It writes bounded chunks, refreshes an expired signed link once, and cleans cancelled transfers. [Source preparation evidence](../../docs/native-source-preparation-20261011.md) distinguishes the tested handoff from pending realtime playback and durable downloads.

`RealtimeQueueSession` connects prepared source leases to a bounded multi-song scheduler and exposes playback controls/snapshots. Its AVAudioEngine adapter is available through Account → Playback testing; streaming remains the default until device acceptance. [Realtime queue evidence and acceptance gates](../../docs/native-realtime-queue-20261011.md).

Initial testing uses a free Apple account and Xcode Personal Team signing. See the [integrated testing handoff](../../docs/native-testing-handoff-20261011.md) for installation, playback comparison, server migration and remaining acceptance.
