> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Catalogue requests and source coverage

5 October 2026.

## Delivered

Search & discover can now browse a MusicBrainz artist's release groups, choose a release edition, inspect its track list and request an individual song or all missing songs. Release-group and edition pagination use 50-item pages. Requests are assembled from server-side metadata; client-supplied song names and download URLs are not accepted. Empty selections and track IDs outside the selected edition are rejected.

Metadata responses are cached in SQLite for 24 hours across restarts. Artist searches and release browsing share a serial admission gate spaced at least 1.05 seconds apart. Saved presence is recalculated against the current library rather than stored in the metadata cache. The earlier artist-search result cache is only a short-lived convenience cache.

Requests enter the existing persisted queue and preserve disc/track numbers, duration, recording and release IDs and available ISRCs. Repeated submissions do not add duplicate jobs. Explicit conflicting release IDs receive distinct queue identities even when visible tags are identical. Known local release-ID conflicts do not count as saved. Files without catalogue IDs can only be matched by tags and duration; the UI explains this limitation. Existing Apple migration selections and files are untouched.

MusicBrainz IDs are retained in acquired metadata and written to MP3 ID3 tags. These represent the requested catalogue context. Current source matching still cannot independently prove exact mastering identity. Album grouping in the local snapshot still uses album artist and title; edition-aware library grouping needs further work before production migration.

The live browser check traversed Bastille → Bad Blood → the 2013 European 12-track CD edition, including its combined final track. Twenty-one tests pass and the production frontend builds. Catalogue submission tests use an isolated database with downloads disabled; no album was submitted to the user's enabled main queue for testing.

## Native AAC acquisition

JioSaavn is now connected with an explicit AAC 256 kbps-or-better profile (measured threshold 240 kbps for bitrate variation). MP3 profiles remain MP3-only, and AAC requests skip MP3 providers. No transcoding is performed in acquisition. Settings reject an enabled profile without a compatible selected source. Existing main-preview settings remain MP3 320 with FreeMp3Cloud and zvu4no; adding the adapter does not switch them or submit requests.

The real isolated test at `.localdata/download-jiosaavn` retrieved Bastille / Pompeii / Bad Blood as AAC, measured 322 kbps and 214.227 seconds versus 214.148 seconds requested. The worker fully decoded it, wrote MP4 title/artist/album/album-artist/year/disc/track tags and published/indexed it as `.m4a`. The source parser retains Music Grabber's upstream search behaviour, including its regional request header. No source credentials were needed in this check. Availability and regional coverage may change.

Regression checks exercise actual stereo AAC encoding, lower-bitrate and incompatible-codec rejection, URL-origin restrictions, tagging, indexing and restart persistence.

## Music Grabber sources

Inspected source: `.investigation/upstream/musicgrabber`, commit `7fd57573a47ee9d1de0b8331964f294abc68799a`, Unlicense. This assessment describes inspected code, not guaranteed current provider availability.

| Source | Mechanism in Music Grabber | Pig Music status / required work |
| --- | --- | --- |
| FreeMp3Cloud | HTML search, direct MP3 transfer | Connected; one real 320 kbps transfer verified |
| zvu4no | HTML search, direct MP3 transfer | Connected; no matching result in the earlier Pompeii probe |
| Soulseek | slskd search and peer transfer | Connected in the subsequent [Soulseek milestone](soulseek-milestone.md); real FLAC transfer verified, album-folder preference and measured quality checks implemented |
| Monochrome | Deezer/ISRC metadata plus separate tracks API resolver, intended FLAC output | Not connected; the inspected tracks endpoint timed out from this Windows machine during the read-only probe |
| JioSaavn | API search and direct AAC-in-MP4 transfer; code advertises 320/160 kbps renditions | Connected; live native AAC download measured 322 kbps, full decoding/tagging/indexing passed in an isolated library |
| YouTube | yt-dlp search, metadata and transfer, bounded retry/backoff and optional cookies | Not connected; reuse extraction/matching/backoff within a bounded adapter, preserve native codec/quality, do not claim a 320 kbps conversion is a quality upgrade |
| SoundCloud | yt-dlp extraction of source URLs | Not connected; validate artist/recording credits, preserve actual source quality and handle unavailable streams |

The order should be governed by the chosen quality profile and source health, with configurable precedence. Lossless requests must fail clearly if no usable lossless source exists, rather than fall back to lossy silently. Lower-quality YouTube/SoundCloud candidates can only satisfy profiles that explicitly allow them. A source problem must fall through to the next permitted source without requiring the user to choose a service.

## Remaining phase 1 sequence

1. Soulseek/slskd album-aware adapter and shared source capability/health layer.
2. Remaining Music Grabber adapters, native FLAC tagging, codec-aware profiles and quality cutoffs. Live source checks must distinguish no matches from a failed search.
3. Artist-wide requests with release-type filters and optional per-artist monitoring; catalogue artwork, edition-aware library identity and local/catalogue discography merging.
4. Approved test placement on Synology, naming/tagging/artwork checks, exact-file reuse and Plex verification in a separate directory.
5. Unraid single-container deployment, restart/recovery checks, iPhone/Tailscale validation and backup instructions.
6. Migration conflict improvements, proposed existing-file organisation, recoverable removal and optional upgrades. Retire the old managers only after the replacement passes these checks.
