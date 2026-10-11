# Integrated native and download-source testing candidate

11 October 2026, Australia/Melbourne. This candidate combines the iPhone/iPad alpha, opt-in seamless playback and the additional server download clients with current main. It is an early testing build; the everyday parity backlog remains in [the approved scope](native-uplift-scope-20261011.md).

## Install with a free Apple account

1. Pull `main`, open `swift/PigMusic.xcodeproj`, and select **PigMusic**.
2. In Xcode Settings → Accounts, add your Apple Account. In the app target's Signing & Capabilities, select your **Personal Team** and automatic signing. If Xcode reports an unavailable bundle identifier, use a unique local identifier. Keep account/signing changes local.
3. Connect your iPhone or iPad, select it as the run destination, and follow Xcode/device prompts for Developer Mode and trust. Build and run. The app currently requires iOS/iPadOS 18 or later.
4. Enter your reachable private HTTPS server address and existing Pig Music username/password. Ensure your private-network connection works before signing in. User creation and server/provider setup remain in the web app.

Apple permits personal-device testing through Xcode with a free account. Personal Team provisioning expires after seven days, requiring a rebuild and reinstall; account/device limits also apply. See [Apple's current account guidance](https://developer.apple.com/help/account/basics/about-your-developer-account). No signed IPA, TestFlight delivery or physical-device installation is produced by this repository push.

## Compare playback modes

Streaming is the default. In **Account → Playback testing**, enable **Seamless playback** to exercise the bounded AVAudioEngine candidate. Changing modes stops playback. Crossfade is enabled by default for this mode: unrelated songs blend for three seconds; sequential tracks with stable album identity and numbering retain continuous album order. Crossfade changes apply to the next queue.

The candidate prepares complete temporary files, prefetching one occurrence ahead. It reuses files for seeks and repeated tracks through independent reader leases, with at most two cached files, a 128 MiB file limit and a 256 MiB total limit. Startup clears abandoned playback directories in the account cache. This is transient playback storage, not an offline download library. Source failure is displayed; return to Streaming mode if preparation fails. Slow next-song transfers can still cause buffering or initial startup delay.

Test on both phone and tablet, recording model, OS version, connection, mode, format, queue order and the exact failure:

- Sign in, refresh, reopen with cached metadata, search, page large libraries, open album tracks and saved/cloud playlist queues. Repeat with a second user and server; their metadata, artwork and temporary audio must stay separate.
- Play a continuous album and compare boundaries in Streaming and Seamless modes. Include AAC/MP3 encoder delay, mixed sample rates, long songs and very short songs. A software PCM capture does not establish audible device gaplessness.
- Enable crossfade for unrelated songs, verify the transition and midpoint metadata/artwork change, then disable it and start a new queue. Confirm ordered albums remain continuous.
- Pause during preparation, seek while paused, skip repeatedly, play duplicate tracks, reach the queue end, then replay. Confirm no cancelled occurrence starts later and paused music remains paused.
- Use lock-screen controls, switch to the background, lock the screen, interrupt playback, unplug headphones and change Bluetooth routes. Verify resume intent, artwork, elapsed time and user pause behavior. Hardware timing and route recovery are acceptance gates.
- Play a cloud-only playlist entry. When the experimental provider is unavailable, confirm a clear error and that no library acquisition request is created.
- Remove cached music or replace its source on the server, then refresh. Temporary playback cache is stopped/cleared after a successful reconciliation; failed/offline refresh retains cached metadata. Revoke the device and refresh: session and temporary playback access must clear. Durable offline playback/reconciliation is still future work.

Debug builds can use `--demo` and optionally `--seamless-demo` for a synthetic library and bundled short tone. Both entry points are excluded from Release compilation. Remove these arguments for server/device acceptance.

## Server download-source testing

The integrated server includes YouTube, SoundCloud and Monochrome alongside existing sources, bounded provider processing, diagnostics, optional owner-managed YouTube cookies and the `native_standard` quality option. Administrative source ordering, credentials and diagnostics remain web-only. The generated Swift contract includes the new profile; native personal quality settings are still pending.

The existing main-branch workflow builds and tests the exact Linux image before publishing the commit tag and `main` image. Check its result before selecting an image for server testing. A source push does not prove a live acquisition, deployment or successful migration of your server state.

Before running the candidate against existing state, stop the server and make a consistent backup of appdata/database and retain the prior image digest. The candidate adds schema migration 7. Rolling back an image alone does not reverse that migration: restore the matching pre-upgrade backup when reverting. Prefer a copied state and separate library destination for initial acceptance; leave existing household files untouched.

Use owner diagnostics to distinguish **metadata reachable** from **audio transfer verified**. For an authorized test recording, `python -m scripts.verify_download_source --source SOURCE --track /tmp/authorized-track.json --output /tmp/new-isolated-source-test` runs a complete acquisition in a new isolated directory; `--metadata-only` performs no audio download. SOURCE is `youtube`, `soundcloud` or `monochrome`. Never reuse the output directory or point this smoke tool at the live household library.

For each enabled source, verify the expected artist/recording/album/duration, retained codec and bitrate, file publication, restart persistence, private authenticated playback and range delivery. Include unavailable providers, fallback ordering, preview/identity rejection, cancellation, retries and broken/expired sessions. Test retained Opus/Vorbis/FLAC on each Apple device; Mac synthetic codec observations do not establish iOS support for all provider files. Live Unraid/provider acceptance remains pending.

## Remaining delivery

Home/catalogue discovery, personal mutations and settings, SSE, persisted queue/history, durable original/AAC downloads and full accessibility/device acceptance remain pending. Watch follows the phone/tablet release; Mac follows Watch. The software evidence is recorded in [delivery](native-uplift-delivery-20261011.md) and [realtime playback](native-realtime-queue-20261011.md).
