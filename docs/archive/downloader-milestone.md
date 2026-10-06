> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Working downloader milestone

5 October 2026: actual acquisition works into an isolated local library.

## Verified live transfer

One supplied migration track, Bastille's Pompeii from Bad Blood, was searched and downloaded using the extracted Music Grabber FreeMp3Cloud parser. Measured output: MP3, 320 kbps, 214.587 seconds versus 214.148 seconds requested. FFmpeg decoded the entire file successfully. Artist, album artist, track title, album, year and track/disc tags were written; the file was indexed as downloaded in the separate smoke-test appdata.

The first attempt exposed a relative/absolute staging-path issue; that was corrected and the retry completed. A fresh transfer into `.localdata/download-verified/downloads/library` passed the finalized embedded-metadata checks as well. The initial smoke test used `.localdata/download-smoke/downloads/library`. FreeMp3Cloud returned candidates for the live search; zvu4no returned none for the same query. This is evidence of a working transfer, not a guarantee of catalogue coverage or provider reliability.

## Runtime

The serial worker consumes persisted requests when downloads are enabled. Sources are tried in configured order. Candidates must match artist/title and recording markers, with duration tolerance. Full files are checked with Mutagen and FFmpeg before tagging and publication. MP3 320 and 128-or-better profiles check actual bitrate; no transcoding or upscaling is used. Lossless cannot be enabled with the currently connected lossy sources.

The queue reports search, transfer progress, validation, completed, failed and cancelled states. Failed/cancelled requests support explicit retry. Interrupted active requests resume from search on restart; partial transfers are restarted, not range-resumed. A publication journal recovers a completed rename before the database commit. Incomplete or failed audio is not indexed. A completed queue entry means the isolated file has been published, not that Plex has scanned it.

Production-preview output is `.localdata/downloads/library`. Downloads are enabled in the local preview; existing selections are retained and nothing is submitted merely by enabling the worker. Save source/quality preferences in System settings. Synology snapshot files remain read-only inputs. Local downloaded tracks merge into app browsing and migration presence checks.

## Soundtracks

Soundtrack/OST/original-score/music-from names and genre tags form a separate Soundtracks section. Composer-only soundtrack releases are omitted from the main artist grid and remain searchable. Album details include a persistent library-section override for ambiguous game albums. Changing grouping does not rewrite files. Genre is now included by the snapshot exporter for future refreshes.

## Remaining scope

Soulseek/slskd, album-aware source searches, additional Music Grabber providers, lossless acquisition, upgrades/cutoffs, actual Synology/Plex export, recoverable removals, artist-wide requests and further catalogue/library integration and Unraid deployment remain phase 1 work. A strict match can reject legitimate alternate credits or uncertain release versions; it does not establish mastering identity. Existing-library reorganisation still requires approved proposals.

Vendored source and licence notes are in `server/vendor/NOTICE.md`. Twenty-one tests pass, including decoded/tagged fixture imports, corrupt-audio fallback, recording/embedded-metadata mismatch, cancellation/pause, quality/address rejection, publication recovery, soundtrack grouping and queue/migration tests. The production frontend build passes. Browser confirmed the completed transfer appears in the queue and as a MP3 320k library track, enabled source/quality settings, and La La Land/Interstellar/Final Fantasy entries in Soundtracks. Physical iPhone, Docker image and NAS placement are not yet validated.

The subsequent [catalogue and source milestone](catalogue-and-source-milestone.md) adds external release-edition browsing, album/single requests and native JioSaavn AAC acquisition. The MP3 profiles retain their original semantics; the explicit AAC profile accepts AAC at 256 kbps or better. A second real isolated download measured 322 kbps AAC.
