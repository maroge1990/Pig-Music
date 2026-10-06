> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Browsing and source quality management — 5 October 2026

Live preview: http://192.168.1.235:8765. Image: `pig-music:preview-20261005-feedback-v2` (`sha256:e45c4333094392aca31f13225187faf56ddea1f7f0fd6dc17767100e8245d023`). Source: `/mnt/user/appdata/pig-music-preview/source-feedback-v2`.

## Quality rules

Album preference overrides artist preference, which overrides the system default. Clearing an override restores inheritance. Artist and album pages hold override controls; System holds the default, lossless fallback, attempt budget, upgrade interval and concurrency limit.

Upgrades and downgrades always acquire a new matching source file. Runtime acquisition never encodes or converts existing music. Codec, measured bitrate, duration, recording context and full audio decoding are checked before tagging and publication. The replacement retains the track ID. Only after commit does cleanup remove the superseded Pig Music download, checking both hashes and containment within the managed library. Failed or cancelled attempts keep the old file. Interrupted cleanup is durable and retried.

Changing the default queues replacements for managed acquisitions that follow it. **NAS originals remain read-only.** Overrides on NAS tracks download a separate appdata copy and update the app's visible track, without deleting the NAS original. Production NAS replacement and Plex placement still need the planned export workflow.

Initial lossless acquisition may fall back to MP3 320 after preferred sources are exhausted or a ten-minute attempt budget. The desired lossless policy remains and is checked every 24 hours. Automatic upgrade attempts never publish a lower-quality fallback over saved music; uncertain existing quality is skipped by automatic scans. Explicit overrides can request either direction. Success depends on available matching source files.

Three jobs run concurrently by default, configurable from one to six. Soulseek searches share a cache/admission lock and each peer permits one transfer at a time. Different peers and supported HTTP providers can overlap.

## Browsing

Header search is a dropdown. Header and discovery search automatically query saved music and outside artists after a short debounce, with separate result sections and whole-row links. The large library banner is removed, and navigation resets each section to its start.

Saved artists include catalogue browsing below saved releases. Discographies are chronological with Albums, Singles, EPs and Other tabs; default Albums exclude compilations, live, remix and demo releases. Catalogue pages load progressively, currently capped at 1,000 groups per tab. A release group opens a preferred edition directly; the heuristic favours official standard editions and digital/CD formats, with a bottom edition chooser for explicit alternatives. This is not a canonical-edition guarantee from MusicBrainz.

Download all submits missing songs only. Individual songs use compact circular download, queued, progress and saved controls. Library state refreshes after queue changes. Musicals have their own section; Hamilton and The Book of Mormon now appear there, with manual category control still available.

## Validation and recovery

The frontend build passes. All **56 tests pass in the exact Linux image**, as user `99:100`, without network or live-library access. Coverage includes source-only FLAC upgrades and MP3 downgrades, failed replacements, misleading bitrates, preference inheritance, system-default changes, durable improvement policies, guarded cleanup, interrupted replacement recovery, concurrent claims, chronological release filtering and musicals.

Deployment transferred source only, checked for active jobs, paused claiming briefly, backed up stopped data and restored the original enabled settings. All 12 completed requests and 1,382 tracks were retained. Verification did not submit the migration batch or real replacement requests. Browser checks at 390 × 844 confirmed whole-row discovery navigation, automatic edition selection, 32-pixel circular song controls and no horizontal overflow. An expanded quality panel clears when switching sections. A mobile screenshot is saved at `.localdata/unraid-feedback-mobile.png`; the viewport override was reset.

Immediate rollback: `pig-music-preview-before-feedback-v2`, with matching `/mnt/user/appdata/pig-music-preview/backups/pre-feedback-v2-20261005/data`. This intermediate image already contains the main quality feature. The previous media-only build is `pig-music-preview-before-feedback`, with `pre-feedback-20261005/data`. Never run rollback containers alongside the active app against the same data. Preserve current data separately before restoring a backup.

Full four-container consolidation remains unfinished: slskd is still a separate temporary engine, more Music Grabber providers and production NAS placement remain pending. Remote playback reliability and physical iPhone testing are separate from the browser viewport verification.
