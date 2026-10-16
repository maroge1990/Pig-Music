# Verification beyond the automated suites

The commands for the three test tiers are in [AGENTS.md](../AGENTS.md#test-cheapest-first). Use disposable data and music fixtures. Never point tests at live appdata or the real NAS. Provider tests use mocked HTTP; FFmpeg tests decode real disposable audio. Each handover states which checks actually ran against which image. Earlier passes are not evidence for a new candidate.

## Behaviour the suites must keep covering

- Edition and recording conflicts, ambiguous matches, compilation and live context, identical-byte memberships.
- Edition anchors across scan order and restarts; edition-specific removal, cancellation, exclusions and restore.
- An idempotent persistent queue; claim cancellation and clear; interrupted publication; full decoding; quality replacement and fallback.
- Favourites without acquisition; playlist order, duplicates and missing files; Plex ownership.
- Artist-job cancellation cannot submit work after cancelling.
- A missing or wrong NAS marker allows reads but creates no workspace or media paths.
- Default-deny routes, per-person scoping, signed media revocation, and provider rate limits (`tests/test_rate_limits.py`).

## Browser checks

Use local disposable fixtures for mutations, on desktop and at 375 px, in light, dark and system appearance, with keyboard focus and reduced motion.
- Fresh Import opens a chooser; a synthetic XML import starts a review without downloading; replacement import works.
- Artist and playlist links survive reload and back.
- The playlist picker handles focus and Escape.
- Player labels stay readable and actionable.
- Saved, queued, downloading and failed states are distinguishable.
- Admin options sit at the bottom of shared views.

## Performance

Mix acceptance uses a disposable library and cache: open Home on web and iOS/iPadOS 26+, confirm one horizontal row and five distinct Pig-Branding-based cover motifs where there is sufficient music, then play a ready mix end to end. Pause downloads and exhaust a small cache budget: keep the last ready edition playable and defer preparation. Rotate while a queue plays; a song shared by another member/mix must stay available. Add a discovery to the library while preparation is paused, resume publication, retire its mix and clean the cache: the library copy must remain. Save an edition, hide a song or edition and restart; metadata and feedback must persist. Expire a saved edition's cache, then play it with experimental streaming disabled: a standard cache download must restore playback without library membership. Check seedless regional charts, imported-but-unavailable taste seeds, bounded preparation resumption and day-to-day diversity. Verify real sources, several daily editions, Dynamic Type, VoiceOver, both appearances and large phone/tablet layouts before accepting mix quality. Server caching alone does not make music available when the phone is offline. Use the [isolated source-acceptance harness](operations.md#download-source-acceptance) with `--mix-cache` to verify real transfers without household appdata or NAS access.

For each measurement, record the dataset size, sample count and network location. Report warm cached reads separately from cold metadata, image or provider work, and use at least 30 samples for a p95 claim. Gates:
- cached local browsing: p95 under 100 ms;
- playlist cards: p95 under 150 ms;
- 50k-track artwork, delivery and two-person sync: under 1 GiB (CI repeats these in the image).

Never trade matching or validation guarantees for throughput.

```sh
.venv/bin/python scripts/benchmark_library.py
.venv/bin/python scripts/benchmark_api.py --url http://192.168.1.203:8765 --samples 30 --output .localdata/api-performance.json
.venv/bin/python scripts/benchmark_cover_store.py --sizes 10000 50000
.venv/bin/python scripts/benchmark_delivery.py
.venv/bin/python scripts/benchmark_native_sync.py
.venv/bin/python scripts/benchmark_mixes.py
```

`benchmark_api.py` sends GET requests only. `deploy_unraid.py` also runs `verify_state_migration.py` against a read-only copy of a stopped-state backup, and any migration failure aborts the release.

## Native device acceptance

Simulator builds and PCM captures don't prove device behaviour. For each finding, record the device, OS, connection, playback mode, format and exact failure.

1. **Phone and tablet:** install, update and reopen. Check:
   - owner/member separation and provider fallback;
   - large text and VoiceOver;
   - search and paging at 50k;
   - playlists, import review, settings, edit conflicts and replay after an uncertain response.
2. **Playback:**
   - continuous-album and crossfade boundaries with real AAC, MP3, FLAC and mixed-rate sources;
   - repeat, pause/seek and lock-screen controls;
   - interruptions, Bluetooth/AirPlay, background timing and storage pressure;
   - streaming fallback.
3. **Downloads:**
   - original and AAC transfers, then background, lock and reopen;
   - cellular policy, interrupted resume and relaunch;
   - low storage, quality or source replacement, and confirmed revocation.

   An outage alone must keep files. A confirmed access change must stop playback and remove access.
4. **Watch Ultra 3:**
   - push from the phone and request from the Watch;
   - lower the wrist during delivery, then disconnect and retry;
   - remove and redownload;
   - turn the phone off and play through headphones (gapless, crossfade, repeat, seeks);
   - reconnect and verify listening history, access reconciliation and user switching.
5. **Watch battery on a run:** charge to 100%, send at least two hours of music, turn the phone off and Watch Wi-Fi/cellular off, start a workout with Bluetooth headphones and play for 60 minutes with the screen asleep. Record the start and end battery and the audio format. Compare with the same run using Apple Music downloads. Anything above about 10% per hour needs profiling with Instruments (Energy Log) before it is called acceptable.
6. **Diagnostics after a failure:** on iPhone, Account › Diagnostics › Ask the Watch for its log, then Export diagnostics. The file holds both devices' lifecycle logs and any crash reports, with no tokens or links.
7. **Server:** match server state and provider acquisition on an isolated Unraid library copy, with a backup.

Debug builds accept `--demo` and `--seamless-demo` for a synthetic library; remove them for real acceptance.
