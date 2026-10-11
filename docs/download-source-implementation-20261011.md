# Download-source implementation — 11 October 2026

## Delivery status

All seven source IDs now have acquisition paths: Soulseek, FreeMp3Cloud, zvu4no, JioSaavn, YouTube, SoundCloud and Monochrome. The three new adapters are registered and selectable in owner settings. Existing enabled lists, order, download defaults and saved quality meanings are preserved. This is a local implementation candidate; production parity acceptance still requires actual supported transfers in the candidate Linux image and player checks.

This increment follows the [assessment](download-source-parity-assessment-20261011.md) and [native-audio foundations](source-parity-foundations-20261011.md). No deployment, production settings change or live-library acquisition was performed. Concurrent Swift source and generated contract files were left untouched.

## Acquisition behavior

| Source | Implemented path | Eligible profiles |
| --- | --- | --- |
| YouTube | Anonymous or optional owner session; bounded search and hydration; independently credited audio; fresh extraction before transfer; native Opus/AAC retention | Native standard; AAC 256 when a genuine qualifying rendition exists |
| SoundCloud | Public search and hydration; structured or explicit upload credits; progressive/native HLS; supported original downloads; preview/private/protected rejection | Native standard; MP3/AAC/FLAC only when the delivered file meets that exact profile |
| Monochrome | Tracks search; millisecond duration normalization; exact known ISRC; release hydration; public HTTPS FLAC endpoint | Lossless; native standard |
| Existing sources | Retained parsers through guarded, bounded search workers; bounded HTTPS transfer; existing Soulseek integration | Existing capabilities plus the prior native-standard foundation |

YouTube never takes the requested artist/title and writes them into an otherwise ambiguous search result. It accepts structured music credits, a narrowly parsed auto-generated music credit block, or explicit artist/title credits from an independently matching verified channel. Full artist/title/version/duration and conflicting-ID checks remain mandatory. An official video with extra intro/outro fails the duration check. Missing evidence is a candidate miss.

SoundCloud's artist/title and full duration must match. Format selection rejects video, storyboards, protected formats and preview-labelled formats. Original downloads may omit codec/bitrate metadata; a supported declared type can be tried, but only measured file validation can accept it. WAV/AIFF/ALAC originals are outside this launch scope. A public stream is not automatically a full recording or a high-bitrate source.

Monochrome numeric recording/release/track IDs remain provider IDs, separate from MusicBrainz UUIDs. A conflicting known ISRC is rejected without a rescue lookup. When the request lacks ISRCs, a bounded Deezer metadata lookup may supply an ISRC only after exact artist/title/release/duration checks. Its failure leaves strict Monochrome release matching available. Requested release conflicts remain rejection criteria even with an equal ISRC. Monochrome receives no spoofed official-client Origin/Referer.

Every source shares the final application-owned pipeline: actual codec/container/bitrate/duration checks; one audio stream and no video (attached cover art is allowed); canonical tags; complete final-file decode; hash; guarded publication; durable queue/index update. An adapter does not publish directly. Legacy MP3/AAC profiles never accept unlike codecs or lossy encoding. Native-standard acquisition retains supported source codecs.

## Boundaries and recovery

`server/providers/contracts.py` supplies operation context and fixed public error categories. Extractor and retained-parser searches run in isolated Python subprocess groups using the foundation process runner. Cancellation, deadlines and oversized output terminate the group, including JavaScript children. Search, transfer, source and preferred/fallback attempts have finite budgets; fragment retry counts are bounded.

`network.py` enforces HTTPS, port 443, no userinfo, and source-specific host allowlists before each redirect/request. The TCP backend validates every DNS address as public and connects to the selected numeric address, preserving hostname TLS verification. DNS caller waits and the number of resolver threads are bounded. Environment proxies are disabled. This restriction applies to yt-dlp metadata, manifests, fragments and encryption-key requests, as well as retained parser search/redirects and Monochrome.

The worker installs one app-owned yt-dlp request handler and disables plugin discovery, remote challenge scripts, postprocessors and external downloaders. yt-dlp's native HLS code can internally fall back to FFmpeg; the worker explicitly blocks that path. FFmpeg is used only for local stream-copy remuxes and validation, with local protocol restrictions. WebM Opus, AAC HLS and MP3 HLS are retained in `.opus`, `.m4a` and `.mp3` respectively. No acquisition encoder path is added.

The source circuit breaker counts transient metadata and transfer failures separately, so successful searches do not hide repeatedly broken audio. Three transient failures trigger five minutes of cooldown, increasing to at most one hour; one operation can probe at expiry. Candidate identity/quality/protection failures do not count as provider outages. Health observations are ephemeral and reset on restart; durable acquisition provenance remains in the library.

Successful publication records source, effective quality, selected format and available original/declared properties, measured audio, remux flag and validation time. Signed stream URLs, raw extractor responses, manifests, cookie contents and stderr are not public queue/library provenance.

## Owner controls and deployment configuration

The owner settings panel includes all source toggles and earlier/later order controls. Saving settings never appends newly registered sources. The diagnostics disclosure distinguishes metadata reachability from a verified audio acquisition and displays setup/access/cooldown information.

Owner endpoints:

- `GET /api/v1/admin/download-sources`
- `POST /api/v1/admin/download-sources/{source}/check` — metadata only
- `PUT /api/v1/admin/download-sources/youtube/cookies` — JSON `cookies` in Netscape format
- `DELETE /api/v1/admin/download-sources/youtube/cookies`

Authentication, owner restriction and browser write protection use the existing default-deny guard. Cookie upload is bounded, validated and limited to YouTube/Google cookie domains. Files are atomically saved with private permissions; operation snapshots isolate running extractors from owner upload/removal and are removed afterward. Responses and validation errors do not echo contents. Removing a session affects future operations; an already-running operation retains its private snapshot until completion.

Monochrome defaults to `https://tracks.monochrome.st`. Operators may configure `PIG_MUSIC_MONOCHROME_API` with another HTTPS public endpoint and explicitly list additional public CDN suffixes in `PIG_MUSIC_MONOCHROME_CDN_HOSTS` (comma-separated). Addresses are never learned into the allowlist from a redirect or manifest. Invalid Monochrome configuration leaves other sources usable.

The Python runtime pins `yt-dlp==2026.8.19`, `yt-dlp-ejs==0.8.0` and default dependencies in the lockfile. The final image copies Node 24 from the existing digest-pinned frontend stage, includes its system runtime libraries, and checks Node/extractor availability during build. No floating download or runtime self-update is used. Node 24 is the chosen supported JavaScript runtime instead of adding a second Deno image dependency. Keep extractor/EJS changes pinned and release them through the existing container CI.

## Contract handoff for the Swift app

The server OpenAPI schema includes typed source diagnostics and the additive `TrackInput.isrcs` field. Personal requests and legacy migration requests now preserve known recording/release/ISRC evidence. Existing API profile strings remain unchanged; `native_standard` was introduced by the foundation increment.

The server contract was exported with `python -m scripts.export_openapi --server-only`. The Swift agent must synchronize `api/openapi.v1.json` into its generated contract and regenerate as appropriate; this task deliberately does not overwrite concurrent Swift files. Native client UI/playback work belongs to that agent. Source selection continues to be server-owned; the Swift app need not implement extractors.

## Verification and remaining acceptance

Automated provider tests cover identity/conflict/preview/protection rejection, safe URL and DNS handling, redirect credential stripping, DNS wait limits, bounded bytes, gateway retry, private cookie snapshots, owner authorization/redaction, breaker behavior, tentative original formats, actual yt-dlp progressive/native-HLS downloaders using synthetic HTTP payloads, local AAC packet retention, and verified publication/restart for all three new adapters. Foundation tests cover Opus packet retention, existing source/quality behavior, cancellation/descendant cleanup, native format tagging, migration, household preferences and replacement protection.

Final local verification:

- Full backend suite with an explicitly absent disposable library root: **306 passed in 146.04 seconds**. Initial runs inherited macOS `/Library` via case-insensitive `/library` and were stopped; they are not successful verification evidence. The first isolated run exposed a Soulseek transfer-return compatibility bug, corrected before the final passing run.
- Focused acquisition/native/quality checks: **80 passed**; the final provider suite contains **38 passing tests**, including parameterized network/transfer cases.
- Web: **11 tests passed**, TypeScript/Vite production build passed, Prettier check passed. Existing nonfatal lucide module-directive build warnings remain.
- Black check passed across **154 files**; server-only OpenAPI freshness, `git diff --check`, dependency consistency (`pip check`) and documentation links/fences passed.
- The new acceptance CLI completed an isolated Monochrome metadata-only run, returned one matching candidate and wrote zero audio. No production appdata or source configuration was used.
- At the adapter milestone, the Swift schema copy was stale. The subsequent integrated testing candidate synchronizes both copies and passes the combined drift check.

Public metadata-only checks on this Mac found:

- YouTube and SoundCloud public pages reachable through the guarded handler.
- YouTube independently structured Forss/Flickermood credits with full duration and native Opus formats; ambiguous Bastille/Pompeii uploads were rejected.
- SoundCloud Forss/Flickermood with structured artist/title, full duration and AAC/MP3 formats. Its licence metadata was all-rights-reserved; no audio was downloaded.
- Monochrome Bastille/Pompeii with exact ISRC, full duration and Bad Blood release context. No FLAC was downloaded.

These observations establish metadata/schema viability, not actual audio transfer on Unraid.

Use the opt-in isolated harness with controlled/authorized material:

```sh
python -m scripts.verify_download_source --source soundcloud \
  --track /tmp/authorized-track.json --output /tmp/pig-source-smoke-new
```

The JSON needs artist, title, album and expected full duration; ISRCs are optional. The output directory must be new. `--metadata-only` avoids audio transfer. The harness creates fresh appdata, clears the process's configured NAS download root, uses the real acquisition pipeline and writes a sanitized report. A transfer success includes measured properties, tags/publication, file hash and a restart check. It does not read production settings, cookies or appdata. The script is included in the candidate image.

Still required before claiming full production parity:

1. Build and run the exact candidate Linux image, including Node/EJS and dependency audit. Docker is unavailable in this Mac session; the existing container CI is the build path.
2. Complete one supported full acquisition for each new provider from the candidate Unraid network in an isolated library. Confirm Monochrome audio access/redirects and any actual YouTube session requirement.
3. Verify range playback/indexing and the retained codecs on the intended desktop browser, physical iPhone Safari, Plex and Swift playback path.
4. Synchronize the Swift contract, run backed-up-state migration/candidate checks, then perform the separately authorized production rollout and rollback preparation.

Full source parity is an operational acceptance claim. Registered sources, synthetic transfer tests and metadata-only probes are recorded separately so partial external acceptance is not reported as complete.

## Native/main integration follow-up

The native task incorporated this implementation and current main into the combined testing candidate. Both OpenAPI copies now match; 347 backend and 38 web tests pass locally after integration, with the TypeScript/production build and formatting checks passing. The native suite passes 61 tests including signed saved-media range delivery against an isolated fixture. Live Unraid/provider acquisitions and Apple-device codec acceptance remain pending. See the [integrated testing handoff](native-testing-handoff-20261011.md).

## Linux Opus timing correction

The first integrated Linux candidate passed 346 tests and failed the Opus remux timing regression; its image was not published. The container's FFmpeg stream copy retained compressed packets but lost WebM terminal DiscardPadding, adding 648 stereo frames (13.5 ms) to decoded output. The Mac FFmpeg behavior had passed the earlier tolerance, so this required exact-container verification.

The remux now reads bounded packet skip/discard metadata, verifies packet count and initial padding, and corrects only the final Ogg granule/checksum when terminal padding differs. It reads one Ogg page at a time, checks cancellation, validates the corrected metadata and then publishes atomically. No compressed packets are encoded or changed. [Ogg Opus end-trimming rules](https://www.rfc-editor.org/rfc/rfc7845.html#section-4.4) describe the terminal granule mechanism.

The regression simulates the older muxer on every platform and now requires exact decoded PCM equality, alongside exact compressed packet hashes and overwrite protection. All 63 focused source/provider cases pass locally; the combined Linux image must pass its rerun before publication.
