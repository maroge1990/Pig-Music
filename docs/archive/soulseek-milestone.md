> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Soulseek and FLAC milestone

The Windows wiring below records the initial development milestone. The current live deployment uses direct engine file access on Unraid; see [Unraid preview and recovery](unraid-preview.md). The temporary engine now restarts unless stopped.

5 October 2026.

## Verified behaviour

Pig Music now has an app-owned slskd API adapter. Searches use artist and album, cached for ten minutes across the requested album's songs. Candidates must identify the requested artist, album and track in their paths, respect recording-version markers and duration, and advertise compatible quality. Folder coverage across sibling requests ranks complete album folders above partial folders, then peer queue length breaks ties. This favours consistent sources; it is not yet an atomic whole-album transfer or a guarantee of identical mastering across songs.

MP3, AAC-in-MP4 and FLAC candidates are supported according to the selected profile. Lossless currently means FLAC. Actual codec, bitrate where applicable, duration, embedded metadata and full FFmpeg decoding are checked after transfer. FLAC receives native Vorbis tags; no lossy-to-lossless conversion is performed. A FLAC container does not independently prove the original recording was never transcoded.

A real isolated Soulseek test retrieved Bastille / Pompeii / Bad Blood as FLAC at a measured 916 kbps and 214.147664 seconds (214.148 seconds requested). It passed full decoding and tagging and was published/indexed at `.localdata/download-soulseek/downloads/library/Bastille/Bad Blood/01-01 Pompeii [ecfe3bbd].flac`. Initial peer transfers succeeded but the file bridge failed because Unraid has no host Python. The bridge was corrected and a retry completed with no error.

Twenty-six tests pass, including album folder ranking/caching, wrong-title/version/album/duration/codec/quality rejection, failed peers, cancellation, completed-file ambiguity, native FLAC import and existing MP3/AAC/catalogue behaviour. The frontend build passes. System displays engine connectivity, a Soulseek checkbox and a FLAC lossless profile.

## Current preview wiring

An isolated **temporary** `pig-music-slskd-test` container runs on Unraid using the already-installed pinned slskd image digest `sha256:ecd4026d4f8fb504e2cc55323efa2c1f5b56d20d3686b018249cc36b48ea17a6`. Its appdata and downloads are under `/mnt/user/appdata/pig-music-slskd-test`. It shares no library directories. The existing slskd, Soularr and Lidarr containers remain stopped; Music Grabber remains running. Existing Synology library files and Plex mounts were not changed.

The test API binds to Unraid localhost port 5031 and is reached via a private SSH tunnel to Windows localhost port 5031. The engine uses the existing Soulseek connection credentials and a separately generated API key. Credentials are kept in ignored local appdata and private engine config; the health endpoint returns only configured/connected booleans. This is a development bridge, not the final single-container deployment.

Completed audio is copied through SSH using a short-lived, network-disabled, read-only helper based on the already-installed Music Grabber image. That helper mounts only the isolated completed-download folder read-only and exits after copying. It does not modify the running Music Grabber service. The copied path must resolve under the configured root, match basename, parent directory and byte size, and be unique. Unsafe/ambiguous files are refused. Publication still occurs only after app-owned validation.

The main preview is configured to try **Soulseek → FreeMp3Cloud → zvu4no** for the existing **MP3 320** profile. The main queue was empty when the new source was enabled. JioSaavn remains an available opt-in AAC source. Selecting FLAC lossless requires Soulseek; it never silently falls back to MP3/AAC. Existing requests retain their submitted quality profile.

Private connection configuration is `.localdata/slskd-connection.json`. Final deployment should use a local shared download directory in the combined service, eliminating the SSH bridge, helper and extra test container. Preserve the stock engine's licence/notices when packaging it; no slskd/Soularr implementation code was copied into this adapter.

## Operational limits and next work

- The development tunnel must be running. After Windows/Unraid restarts it needs restarting; the test engine has no automatic restart policy. The UI reports an unavailable engine, and MP3 requests can fall through to other enabled MP3 sources.
- Search waits are bounded at 35 seconds; peer transfer waits at four minutes per candidate, up to three candidates. API calls and the completed-file bridge have their own bounded timeouts. Queue position is used for ranking, not an ETA.
- Pauses/cancellations check between polls and cancel only the exact peer transfer. If the engine becomes unreachable, remote cancellation cannot be guaranteed. Engine-side transfer IDs are not yet durable in Pig Music across crashes; retries can rediscover/reuse an existing transfer, but persistent transfer ownership and reconciliation need hardening before production.
- Completed/partial engine files are retained for debugging/recovery. Storage cleanup is not yet automatic. Imports copy validated content into local appdata; physical deduplication and NAS placement remain future work.
- Multi-disc folders, alternate artist credits, compilations and releases whose names differ between MusicBrainz and peers can be conservatively rejected. There is no manual candidate review UI yet.
- Further work: remaining source adapters and quality cutoffs, stronger edition-aware library identity and atomic album import, Synology/Plex test placement, then the combined Unraid service.
