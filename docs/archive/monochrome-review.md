> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Monochrome review — 5 October 2026

Reviewed version 2.5.1 at commit `5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7`. This was a source review; no upstream code was executed, third-party playback benchmarked, or live Pig Music settings changed.

Terminology clarification: a hosted API/streaming endpoint does not establish that its operator hosts or stores music. The client exposes `/track/{id}` as the playback address, abstracting the ultimate audio origin. The backend could redirect, proxy, or resolve third-party content; this review has not established which applies to that service, its ownership, or whether it caches audio. Monochrome's quoted no-media-hosting disclaimer is consistent with a frontend using external sources. There is no evidence here of intentional concealment.

## Search and playback

The current [`MusicAPI`](https://github.com/monochrome-music/monochrome/blob/5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7/js/music-api.js#L111) searches its hosted Tracks Streamer first, then Apple Music and its existing Tidal/HiFi path. One response can populate artists, albums and songs. This separates discovery from audio acquisition.

[`tracks-api.js`](https://github.com/monochrome-music/monochrome/blob/5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7/js/tracks-api.js#L404) describes a Rust proxy/streamer at `tracks.monochrome.st`. It caches results and resolved identities, and coalesces duplicate in-flight searches. Native tracks produce `/track/{id}` URLs immediately. Other provider tracks are searched and scored using identity metadata. The backend implementation and its actual acquisition/storage latency are not established by this frontend repository.

[`player.js`](https://github.com/monochrome-music/monochrome/blob/5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7/js/player.js) uses browser audio elements, Shaka Player for adaptive streams, system media controls, and next-track preloading. Playback can start before the entire file transfers. A download queue is therefore unnecessary for starting an available stream. This explains the architecture behind responsiveness, rather than proving a measured speed advantage.

The Unreleased Music page in the screenshot is another distinct path: it loads an ArtistGrid CSV once and filters its artist cards locally. That page's artist filtering does not make a new music catalogue request on every keystroke.

## Artist artwork

The screenshot's portraits come from ArtistGrid, explicitly credited in [`tracker.js`](https://github.com/monochrome-music/monochrome/blob/5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7/js/tracker.js#L115). Its assets use normalized artist names, with JPEG XL/WebP/JPEG alternatives and lazy loading. That integration describes a curated list; it does not establish coverage for every saved Pig Music artist. Name-based matching would need disambiguation before general use.

Regular catalogue artist images are different: the Tracks response supplies avatars, while [`api.js`](https://github.com/monochrome-music/monochrome/blob/5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7/js/api.js#L3296) constructs Tidal image-CDN URLs from artwork IDs and provides responsive image sizes. These are actual artist portraits, whereas our current artist tiles use representative album covers.

My preferred first portrait provider for Pig Music is [Fanart.tv](https://api.fanart.tv/), which accepts MusicBrainz artist IDs and requires an API key. We already use MusicBrainz for catalogue identity. Provider coverage still needs sampling before choosing it. Keep manual selection available when identities or images are ambiguous, with album art and initials as fallbacks.

## Changes worth applying

| Priority | Pig Music change | Scope |
| --- | --- | --- |
| 1 | Separate artist portraits from album artwork | Persist verified artist IDs and image provenance; cache portraits locally; preserve existing album covers. |
| 2 | Add a small persistent web player for saved music | Play/pause, seek, next/previous and a playback queue independent of downloads. Stream app-owned files first, then safely resolved read-only NAS files. |
| 3 | Make discovery return artists, albums and songs together | Show cached/local matches immediately; cancel stale searches and coalesce duplicate requests. Keep MusicBrainz edition identity for import decisions. |
| 4 | Assess a Monochrome streaming/download adapter | Establish usable API access and measured availability before enabling it as an optional source. Retain actual codec, bitrate, duration and version validation. |

For saved-file playback, a server endpoint should resolve a track ID to a contained file path, support byte-range requests for seeking, and send the correct media type. Use native browser audio first; add transcoding only for formats that fail on target iPhone browsers. Shaka becomes relevant if we later support DASH/HLS. Web playback can be introduced earlier than the native iOS/Watch phase; it does not provide Watch offline capability.

## Reuse boundaries

The repository's [Apache-2.0 licence](https://github.com/monochrome-music/monochrome/blob/5b1e6ef9b2531e3c9c9a83a1c7690b5a833567a7/license) supports adapting selected components with retained notices. Its player is coupled to its own database, storage, router and UI, so copying the whole player would create significant integration work in our React application.

The [README](https://github.com/monochrome-music/monochrome#self-hosting) says its hosted streaming API restricts non-official deployments and points self-hosters towards a separately obtained HiFi endpoint. These service dependencies are distinct from the code licence. Official Tidal integration also has [authentication](https://developer.tidal.com/documentation/api-sdk/api-sdk-authorization) and [content/display requirements](https://developer.tidal.com/documentation/guidelines/guidelines-design-guidelines).

Do not copy the loose external-track matching into library imports: its normalization removes parenthetical version information, and its native stream descriptor labels audio as FLAC/lossless without our file probe. Preserve Pig Music's stricter live/remaster/edition and measured-quality checks.

Recommended next implementation: artist portraits, followed by saved-library web playback. Treat external streaming as a separately verified provider rather than a dependency of basic library playback.

## Follow-up: coverage and playback before import

The public ArtistGrid index was retrieved successfully and compared locally against the snapshot; library names were not sent in that request. It lists 578 artists, with matches for five of our 27 library artists: Chappell Roan, Coldplay, Pink Floyd, Prince and Radiohead. This verifies index membership, not successful image downloads or identity for every result. Bruce Springsteen is not listed. ArtistGrid alone therefore cannot fill the whole library with portraits.

Fanart.tv's current documentation describes free project/personal tiers and API keys, with MusicBrainz artist IDs for lookup. It remains the recommended broader portrait provider, subject to actual coverage checks once configured. Preserve provider attribution/provenance and album-image fallbacks.

Requested remote playback should expose distinct Play and Add to library actions. Play uses an available remote stream, or a disposable playback cache when necessary; Add to library enters the existing verified import pipeline. Neither should imply that a catalogue result has been downloaded. Soulseek requires a peer transfer and cannot promise immediate playback like a ready HTTP stream. Monochrome-compatible remote stream availability for our deployment has not yet been verified.
