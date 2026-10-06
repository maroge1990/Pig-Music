> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Unraid live preview — 5 October 2026

Current deployment and verification are documented in [the 6 October library and playlist milestone](library-playlists-milestone.md). The entries below record earlier deployments.

Open http://192.168.1.235:8765 on the home network. This deployment is now the live testing instance; the Windows downloader is paused. No Windows tunnel or file-copy helper is required by the Unraid app.

## Deployment

- App: `pig-music-preview`, image `pig-music:preview-20261005-media-v2`.
- Verified image ID: `sha256:b20122380b6f6613fca2f5bc97a3012e3b8aaec6366cee699a006d7e24baee1e`.
- Persistent data: `/mnt/user/appdata/pig-music-preview/data`.
- Current build source: `/mnt/user/appdata/pig-music-preview/source-media-v2`; initial source retained at `source`.
- Runtime settings: [compose.unraid-preview.yaml](../../compose.unraid-preview.yaml), also saved as `/mnt/user/appdata/pig-music-preview/compose.yaml`.
- Runtime user `99:100`, read-only container filesystem, dropped capabilities, 2 CPUs and 1 GiB memory. LAN port 8765, restart unless stopped.
- Existing Synology library is mounted read-only at `/library`. New imports stay in appdata, outside the Plex library.
- The temporary stock `pig-music-slskd-test` engine remains a separate container on the private `pig-music-preview` Docker network. Its completed downloads are mounted read-only at `/engine-downloads`. Both containers have restart policies. Final single-container packaging remains outstanding.

The consistent SQLite snapshot, catalogue cache, library snapshot, classification overrides and migration choices were transferred. Initial state: 1,370 library tracks, 71 selected migration tracks and an empty main download queue. Downloads are enabled with MP3 320 and source order Soulseek, FreeMp3Cloud, zvu4no. JioSaavn is an opt-in AAC source. No migration batch was submitted automatically.

## Verified

All 26 regression tests passed inside the Linux container as its non-root account. A real Soulseek FLAC download completed decoding, tagging, publication and indexing in the separate `/data/deployment-smoke` store. Measured audio: FLAC, approximately 916 kbps, 214.148 seconds. The main library and queue were not used for this test. App restart preserved settings and the engine connection.

The artwork update subsequently passed all 28 local regression tests and its Linux image build. It uses Cover Art Archive release-group thumbnails for album browsing and exact release thumbnails for edition/track pages. Artist results use a credited release cover, preferring a regular album; these are representative covers rather than artist portraits. Image loads are lazy, fail back to initials, and use normal browser image caching. Artist metadata lookups share the persistent MusicBrainz cache and rate limiter. No paid account or API key is required for this artwork source.

The update transferred source only, checked the queue for active work, briefly paused claiming, and reused current live data. The stopped initial container is retained as `pig-music-preview-before-artwork`; do not start it alongside the current app. Pre-update data is saved under `backups/pre-artwork-20261005/data`. Downloads resumed with the original settings.

## Suggested live tests

1. Open the URL on an iPhone connected to home Wi-Fi. Browse Artists and Soundtracks, and check the saved/missing indicators.
2. Search an artist outside the existing library, choose an album edition and submit one missing song. Follow it in Queue and confirm that it appears in the library after completion.
3. Try a small album, then a FLAC request by changing the quality for new requests. Existing requests retain their original profile. Keep the initial batch small while assessing source coverage and version matching.
4. Review the migration choices before submitting Import now; those selections are preserved, but submission will start real downloads.

External access through the household's existing Tailscale setup has not been tested. No public exposure or additional tunnel was created.

## Operations and recovery

Use Unraid's Docker controls to pause/stop or restart `pig-music-preview`. Start the test engine first when restarting both, then confirm Connected in System settings. Stopping the app preserves its persistent files.

For a consistent backup, stop the app and back up its entire `data` directory, including SQLite, snapshot, acquired files and `slskd-connection.json`. Also retain the build source, image ID, compose settings and the separate engine's appdata. The connection file and initial state archive contain credentials; keep these backups private.

Before an update, stop the app and back up data. Rebuild source into a new image tag and recreate using the saved runtime mounts/settings. Reuse the current Unraid data directory; **do not replace it with an older Windows snapshot** after live testing begins. For rollback, stop the updated app and restore the matching image and backed-up data. Keep current data separately so new test results can be recovered.

The earlier managers and their settings were not repurposed. Production NAS placement, existing-file change review, storage cleanup, durable engine transfer reconciliation, additional download sources and final engine consolidation still require work. Library freshness is snapshot-based rather than a live NAS watcher.

Saved-library fallback is now deployed and approved. Bruce Springsteen’s Greatest Hits cover was verified and cached using the 1995 album-folder hint because the snapshot date tag was missing. All 34 local regression tests passed. See [saved-library artwork](library-artwork-milestone.md). The saved-library artwork rollback container is `pig-music-preview-before-library-artwork-v2`, with data backup under `backups/pre-library-artwork-v2-20261005/data`; do not start it alongside the live app.


Portraits and saved-library playback are now deployed and verified, with experimental remote playback available but currently failing upstream. See [media milestone and Shazam recommendation](media-milestone.md). The immediately preceding stopped container is `pig-music-preview-before-media-v2`, with backup under `backups/pre-media-v2-20261005/data`. Source is `source-media-v2`. Download settings, the snapshot and migration selections were retained.


Browsing and source-only quality management are deployed in `pig-music:preview-20261005-feedback-v2`. All 56 Linux tests pass. The current 12 completed live requests and 1,382 tracks were retained. See [quality rules, browser changes and matching rollback backups](browsing-quality-milestone.md).
