> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Phase 1a delivery and acceptance — 6 October 2026

Pig Music now runs independently on live data at **http://192.168.1.203:8765**. Final image: `pig-music:preview-20261006-phase1a-final-v2`. The container is `pig-music-preview`; its health check passes. The deployed Compose definition is `/mnt/user/appdata/pig-music-preview/compose.yaml`, corresponding to `compose.unraid-preview.yaml` in this repository.

## Delivered

- One container, shared library, settings and durable queue; the pinned slskd engine is internal and its API is loopback-only.
- Local/discovered search, cached artwork and discographies, preferred release editions, newest-first browsing and separate compilation/soundtrack/musical sections.
- Optional Fanart artist backgrounds and optional ListenBrainz popularity. Popular albums are checked against MusicBrainz and exclude singles, EPs and secondary releases such as compilations/live albums. Up to 20 songs and 10 eligible albums have paging controls.
- Popular songs use play/download controls directly. Album and player artist/album labels navigate to their corresponding pages. Album quality and section controls sit under **Album settings**.
- Circular playlist and favourite controls on saved, catalogue, popular and playlist songs and on the player. New playlists persist in order. Favourites have a dedicated library view. Marking a favourite stores membership only and never submits a download; missing songs can subsequently be reviewed for acquisition.
- Artist-wide acquisition from saved and discovered artist pages, with release-type selection under collapsed artist settings. Optional monitoring defaults off and checks opted-in artists daily. Jobs persist progress and resume after restart through the unified queue.
- System quality defaults, artist/album overrides, validated replacement downloads in both directions, timed lossless fallback and periodic improvement checks. No file conversion is used for acquisition or quality changes.
- Recoverable song/album/artist removal, restore, intentional-removal exclusions and cancellation of related incomplete requests. Artist removal disables monitoring. Completed download history is retained. Shared file memberships keep their required original file.
- Independent initial/incremental scanning and review/apply existing naming with optional current-metadata tags. Album folders are retained; collisions require review. Originals, operation journals and undo are available. Organisation and scanning cannot overlap; temporary and recovery files are excluded from scanning/Plex.
- Apple XML migration/imported playlists and native Plex playlist sync. Available songs appear immediately; missing songs join after publication/indexing. This remains a single Plex owner connection.

## Verified on live data

All four legacy music containers were stopped during these checks.

1. A new request for Bruce Springsteen's **Dancing in the Dark**, in the selected **Born in the U.S.A.** release, completed through embedded Soulseek, passed file validation and published into the NAS artist/album structure.
2. Recoverable removal and restoration of that newly acquired file returned identical SHA-256 bytes.
3. An album quality override fetched a genuine FLAC replacement. Changing it back fetched a native 320 kbps MP3 replacement. The original remained until validated publication. The test album now inherits the system/artist preference again.
4. Review covered **1,395 songs in about 1.42 seconds**. Applying tags/naming to only the new test file and undoing the operation restored its exact original bytes. Existing music was not bulk reorganised or retagged.
5. The independent NAS scan indexed **1,395 files**, with **zero missing files and zero read failures**.
6. All **25 managed published files** were verified in the real Plex index. Plex connection and playlist sync report connected.
7. A clean container restart retained 1,395 library tracks, 27 queue entries, download settings and playlist memberships. No duplicate requests were created.
8. A real catalogue artist request in isolated temporary appdata queued Chappell Roan's 14 feature-album tracks with downloads disabled. The completed artist job survived reopening the store, with monitoring off.
9. Chappell Roan's popularity returned 20 songs and one eligible feature album; Bruce Springsteen returned 20 songs and 10 eligible feature albums.
10. The final Linux image passed **98 backend tests**, as user 99:100 with networking disabled and no live library mounts. Its frontend built successfully. A 390 × 844 browser viewport verified compact song actions, favourite toggling without acquisition, the playlist picker and keyboard dismissal, and artist/album navigation. Saved-file playback advanced its timer.

Tailscale is running on Unraid and advertises `192.168.1.0/24`. An actual off-site phone session still needs the household's confirmation; LAN/emulated phone checks do not establish that.

## Retirement and recovery

The original **music-grabber, lidarr, soularr and slskd container definitions have been removed** after acceptance. No volume-deletion option was used. Their original appdata/download folders and images remain, and their container definitions, Unraid templates and copied appdata are backed up under:

`/mnt/user/appdata/pig-music-preview/backups/legacy-phase1a-20261006/`

This backup contains credentials and must remain private. To recreate a legacy service, use its retained Unraid template and original appdata. Pause Pig Music acquisition/organisation before re-enabling another manager against the same library.

The immediate pre-final-update appdata backup is:

`/mnt/user/appdata/pig-music-preview/backups/pre-phase1a-final-v2-20261006/data`

The retained immediate rollback container is `pig-music-preview-before-phase1a-final-v2`. Do not run it alongside the current container on shared data. Preserve newer appdata separately before any backup restoration; never overwrite live state with a stale Windows development snapshot.

Recovery originals live under `.pig-music-trash` on the same NAS. Recovery is not an independent disaster-recovery backup. Organisation uses current library metadata and preserves existing release/folder context; it does not silently guess and rewrite unresolved catalogue editions.

## Source coverage and remaining boundaries

Enabled acquisition adapters are **Soulseek, FreeMp3Cloud, zvu4no and JioSaavn**, selected automatically within the configured policy. This is selected functional consolidation, not complete feature parity or incorporation of every upstream source. YouTube and SoundCloud adapters remain unconnected; their native formats/identity and quality would need an explicit supported policy. Monochrome endpoint reliability has not justified enabling it as a core acquisition dependency. Source availability can change and does not guarantee every song or desired quality exists.

Saved-file playback works; remote playback remains experimental and optional. Its successful JioSaavn checks do not establish universal coverage, exact mastering or immediate availability. It is not required for downloading or library management.

No artist-wide bulk download or monitoring was enabled against the live collection during acceptance. Monitoring/recovery behavior also has automated coverage; a day-long production monitoring cycle has not been observed. Physical device/off-site testing and ongoing household feedback remain useful before adding complexity.

## Phase 1b direction

Start with household profiles and ownership of favourites/playlists/Plex connections. Then define each person's library memberships over shared assets, so wanting the same album does not automatically require two audio copies. Resolve shared quality preferences, removals and Plex library mapping before adding a second filesystem tree. Keep user selection and exceptional settings out of routine artist/album browsing wherever possible.

Shazam import/listening integration and native iOS/Watch offline playback remain later phases.
