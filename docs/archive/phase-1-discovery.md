> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Pig Music discovery

Interview and initial read-only investigation, 5 October 2026. Architecture is not yet selected and implementation has not started.

## Agreed scope

- One integrated application and server container with a shared library, queue, settings, metadata, artwork, and responsive web interface. Desktop supports troubleshooting; phone supports library management.
- Replace the necessary download and management functions of Lidarr, Music Grabber, slskd, and Soularr; remove redundant functions rather than merely packaging their separate interfaces together.
- Keep Plex/Plexamp and Shazam initially. Later phases cover Shazam integration and an iOS player with Apple Watch offline support.
- Use the existing Synology music library read by Plex. Ingest existing libraries and offer consistent tags and naming, showing proposed changes for approval before modifying existing files.
- Support artist, album, and track requests. Artist requests offer release-type selection and an optional per-artist switch to monitor future releases.
- Quality profiles should offer arr-style allowed qualities, ordering, and upgrade preferences, including lossless and lossy bitrate tiers.
- Retain sources beyond Soulseek. Source support, reliability, and fallback order need investigation; the newly installed Music Grabber has not been thoroughly tested.
- A whole album may be downloaded to fulfil one song request, importing only the requested track.
- Preserve requested and existing release context, including live recordings and compilations. Do not substitute a different version merely because the title matches.
- Identical audio should ideally be stored once and belong to multiple releases/locations. Feasibility alongside release-specific tags and Plex folders remains unresolved.
- Permit releases absent from MusicBrainz using existing tags and manually editable metadata.
- Use existing services' matching behaviour as a baseline rather than introducing mandatory review of every download candidate. Review of existing-library modifications is separately required.
- Apple Music import is for initial migration; the household intends to retire Apple Music afterward. Playlist submissions are once-only; retaining/syncing playlists in Plex is unnecessary.
- Remote access uses existing Tailscale.
- Multiple users and two household libraries are phase 1b. Plan for shared audio and separate membership; Plex behaviour needs assessment.
- Project is intended for private household use.
- Apple Music playlists may be private. A paid developer membership is not established as a requirement the user accepts; assess existing import methods and exported-library files before making account authorisation a dependency.
- Primary pain points are clunky mobile interfaces, uncertainty about service operation, and slow library browsing. Target a quick artist-to-request workflow with automatic provider selection and recovery.
- Search combines saved and available catalogue entries, highlighting downloaded and missing music. Partially present albums need track-level status.
- Storage clarification: separate physical files are acceptable where release-specific tags differ. Avoid duplicate acquisition and deduplicate identical files where storage supports it; preserving correct Plex release presentation takes priority in this case.
- Migration must inventory and compare first, then let the user select retained music before queueing downloads. Do not bulk-download the Apple Music collection automatically.
- Migration review groups artists and their releases separately from compilation albums; albums and individual tracks are selectable.
- Artists present only through compilations are hidden from the main artist grid, but searchable and visible in compilation track listings. This display rule must not discard track artist credits or change existing release context.
- Compilation segregation applies only to multi-artist releases. Single-artist best-of/greatest-hits releases stay under their artist. Apple's Compilation flag alone is not sufficient to classify a release or hide an artist.
- A Mac is available for Apple Music migration. Development currently uses Windows; the Mac can supply exported library/playlist metadata without moving the development environment.
- Phase 1 supports removal of artists, albums and tracks using recoverable trash.

## Interview status

Core product scope is sufficiently defined for the phase 1 implementation plan. Remaining technical validations are source reliability/quality, a representative Mac Music XML export, Plex export behaviour and storage link capabilities. These are engineering investigations rather than unresolved broad product requirements. No implementation or production migration is yet performed.

For removal, the proposed implementation records deliberate exclusion, cancels relevant requests/monitoring and avoids automatically reacquiring intentionally removed material. Removing one membership must not remove audio still used by another release. Exact suppression/restore behaviour will be made visible in the implementation and verified with acceptance tests.

## Environment observations

Unraid at 192.168.1.235; observed version 7.3.3-rc.2. SSH key access works. Root's .ssh resolves to /boot/config/ssh/root. Credentials and private key material are not stored in this repository.

| Container | Image | State | Relevant mounts | Web port |
| --- | --- | --- | --- | --- |
| music-grabber | g33kphr33k/musicgrabber:latest | Running | SERVER01_Audio -> /music; appdata/music-grabber -> /data | 8080 |
| lidarr | lscr.io/linuxserver/lidarr | Created | SERVER01_Audio -> /music; SERVER01_Downloads -> /downloads; appdata/lidarr -> /config | 8686 |
| slskd | slskd/slskd:latest | Stopped | SERVER01_Downloads/slskd -> /downloads; appdata/slskd -> /app | 5030 |
| soularr | mrusse08/soularr:latest | Stopped | SERVER01_Downloads/slskd -> /downloads; appdata/soularr -> /data | 8265 |

The user deliberately stopped Lidarr, slskd, and Soularr. Inspection has not restarted them or changed their settings or music files.

- Synology library mount: /mnt/remotes/SERVER01_Audio, source //SERVER01/Audio, filesystem cifs (SMB).
- Downloads mount base: /mnt/remotes/SERVER01_Downloads.
- Music Grabber's installed constants report version 4.3.0. Its cached library index contains 1,370 file rows; this is not a fresh independent file count.
- Music Grabber includes matching.py, acquisition.py, audio_provenance.py, metadata.py, library_index.py, slskd.py, apple.py, watched_artists.py, and upgrades.py. Presence does not establish that each feature works or meets our requirements.
- Matching code uses confidence scoring and penalties for unrequested versions. Automatic fallback confidence floor defaults to 0.70. Exact inheritance and contextual constraints require more review.
- Apple import code has separate public URL and private-library paths. Private imports require a music-user token; public imports use a token extracted from Apple web bundles with HTML fallback. Reliability and a supported authentication approach remain unverified.
- Current Soularr configuration allows mp3 320, mp3 256, mp3, m4a, ogg, opus; it is not evidence of the desired future quality profile.

## Source references

- Music Grabber upstream: https://gitlab.com/g33kphr33k/musicgrabber
- Lidarr upstream: https://github.com/Lidarr/Lidarr
- slskd upstream: https://github.com/slskd/slskd
- Soularr upstream: https://github.com/mrusse/soularr

Initial upstream license inspection: Music Grabber uses the Unlicense; Lidarr and Soularr use GPLv3; current slskd upstream uses AGPLv3 with additional notice/rebranding terms. Preserve pinned version notices and assess selected dependencies before copying or modifying code. Private intent does not itself waive license conditions.

## Source snapshots inspected

Public sources are downloaded under .investigation/upstream for local analysis; those nested checkouts are excluded from future project tracking.

| Project | Inspected upstream commit | Installed observation |
| --- | --- | --- |
| Music Grabber | 7fd57573a47ee9d1de0b8331964f294abc68799a | 4.3.0; matching.py, apple.py, library_index.py, acquisition.py hashes match after normalising Windows checkout line endings |
| Soularr | 0700090ed1c539455b05af9e16ab1a5bf8b9baff | Image revision matches inspected source |
| slskd | 2d432e52cbe7e8483783010fe3f8f1415245c1a5 | Installed 0.26.0.0+e42a525d; inspected upstream is newer |
| Lidarr | da7b4dfb1a9e7e1d6625c2dbc3fff96971ab26bd | Installed LinuxServer 3.1.0.4875-ls42; upstream snapshot not established as exact installed revision |

Installed image digests:

- Music Grabber: g33kphr33k/musicgrabber@sha256:8145082baab0e2a2e3ad0a672bee0ef1ed91d84983b701344ce0a20ba476729f
- Lidarr: lscr.io/linuxserver/lidarr@sha256:044d616beb43c5e7810991242c6a9c42b93ff238c8c0850684939634ea751208
- slskd: slskd/slskd@sha256:ecd4026d4f8fb504e2cc55323efa2c1f5b56d20d3686b018249cc36b48ea17a6
- Soularr: mrusse08/soularr@sha256:9d17bdc35108afd747c4862dc32a0c1cba821638d170e1374188a977ce255c76

Plex also maps SERVER01_Audio, internally as /Audio. Cached Music Grabber index reports 175 distinct nonempty artist tag values, 93 distinct nonempty album names, 1,297 MP3 and 73 FLAC files. These are tag/index statistics, not definitive catalogue counts. No selected source or organisation overrides were found in its environment/global settings. Defaults therefore apply for these keys, subject to source-health gating; sources have not been verified operational.

## Remaining investigation

- Compare shared-library and acquisition models, provider interfaces, matching, quality/provenance checks, metadata and artwork, imports, artist monitoring, and queue persistence.
- Identify exact installed versions/image revisions and compare to pinned upstream revisions.
- Inspect supported sources and effective enabled settings without exposing credentials; distinguish search/metadata providers from actual audio download providers.
- Assess Apple Music public versus private playlist requirements.
- Determine feasible deduplication and Plex-compatible release-specific metadata on Synology/SMB, using isolated test files before production changes.
- Choose migration, preview, rollback, and validation approach; do not use the live library as an initial experimental target.
- Produce a concrete architecture and phased implementation proposal after the interview and technical assessment.
