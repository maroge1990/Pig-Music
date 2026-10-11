# Download-source parity: assessment and build specification

Assessed 11 October 2026, Australia/Melbourne. Status: **assessment delivered; implementation proposed; no new adapter delivered or deployed**.

## 1. Outcome and scope

Pig Music can be extended to support all seven Music Grabber acquisition sources: YouTube, SoundCloud, zvu4no, FreeMp3Cloud, JioSaavn, Monochrome and Soulseek. Four are already integrated. The missing three require a shared provider contract, native audio support, conservative recording matching and new provider adapters.

The implementation can start from this specification. Provider production acceptance remains conditional on actual transfers from the candidate Unraid container. Metadata access alone cannot establish downloadable audio, measured quality, sustained availability or library/playback compatibility.

The proposed scope is **source parity within Pig Music's existing product contract**: catalogue requests automatically try eligible sources; files retain their source codec; quality is measured; publication and replacement remain recoverable. Music Grabber's optional transcoding, normalisation, playlist scrapers, DJ mix splitting, browser automation and other product features are outside this delivery. Acquisition and experimental remote listening remain separate.

Existing sources, profiles, configured order, paused/enabled state and queued jobs retain their current meanings. New sources start deselected. No settings migration should automatically start new acquisitions or bulk replacements.

## 2. Evidence and limits

Local baseline: repository HEAD `40aa4e700418d6df4cee834318d3e2f9fec686f9`, with existing uncommitted web/backend/native work. This assessment reads that working tree, not an exact production checkout. Existing changes were preserved. No live appdata, NAS library, provider credentials or production queue were used.

The original extraction used Music Grabber commit `7fd57573a47ee9d1de0b8331964f294abc68799a`. The current inspected upstream is **4.3.1**, commit `a9476a80b662911b392135188153f2fb5b05c3a0`, committed 8 October 2026. The historical investigation checkout is absent on this Mac; public upstream files were fetched afresh into temporary storage. [Music Grabber project](https://gitlab.com/g33kphr33k/musicgrabber), [versioned README](https://gitlab.com/g33kphr33k/musicgrabber/-/blob/a9476a80b662911b392135188153f2fb5b05c3a0/README.md).

Monochrome's inspected main reference was `b85c2c16e09b850f4aa8a0bd83a556676eb14358`; yt-dlp's reported main reference was `897341241f2bfb2439fe0367f4c7c9ccd29a3828`. Metadata extraction used the separately released **yt-dlp 2026.08.19**, not main. Its official zip executable was checked against the release SHA-256 manifest before execution. No dependency was installed in Pig Music's environment. [Release and checksums](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.08.19).

### Checks actually performed

| Check | Observation | What it establishes |
| --- | --- | --- |
| Monochrome `/search/tracks`, Bastille / Pompeii, limit 3 | HTTP 200 JSON; 3 results; about 1.70 seconds | Metadata endpoint reachable from this Mac's network on this date |
| Monochrome first result | `playable: true`, track ID `165809267296882688`, ISRC `GBAAA1200795`, duration `214147` | Useful identity fields; duration is milliseconds in this response |
| Deezer search, same query | HTTP 200 JSON; about 0.93 seconds | Metadata fallback reachable; no audio entitlement or transfer tested |
| YouTube yt-dlp flat search | 3 results; full extraction of first result succeeded; combined about 7.28 seconds | Search and format discovery work here without cookies |
| YouTube first result | Official music video, 233 seconds; audio manifests include AAC around 129.5 kbps and Opus around 128 kbps | It fails the roughly 214-second catalogue request despite being an official upload |
| YouTube lyric result hydration | 214 seconds; verified channel; AAC around 129.5 kbps and Opus around 130.7 kbps; no structured artist/track fields | Duration and formats are promising, but artist identity still needs evidence beyond the uploader name |
| SoundCloud yt-dlp flat search | Remix first, then two 30-second Pompeii results | Search results can be wrong versions or previews |
| SoundCloud first result detail | yt-dlp rejected it as DRM protected; combined search/detail about 6.83 seconds | Search success must not be treated as downloadable audio |
| SoundCloud public fixture, Forss / Flickermood | Hydration succeeded in about 3.41 seconds; structured artist/track, duration 213.886 seconds; MP3 128 and AAC 96/160 format declarations | A positive ordinary metadata/format path exists, alongside the commercial-result failures; no bytes or measured quality verified |
| Existing relevant regression suite | **36 passed in 55.52 seconds**, with local FFmpeg available | Current downloader/quality/Soulseek/scanner/media/remote baseline passed |
| Household policy and OpenAPI baseline | **5 passed in 1.97 seconds** | Current shared-preference/claim reconciliation and API contract baseline passed |

Extraction was metadata only (`--skip-download`); no stream bytes were requested deliberately. Measurements are single observations, not latency percentiles or reliability statistics. Temporary probe output is summarised in [the evidence manifest](download-source-parity-evidence-20261011.json), including additional extractor checks.

Baseline command, from the repository root:

```sh
.venv/bin/python -m pytest tests/test_downloader.py tests/test_quality.py tests/test_soulseek.py tests/test_scanner.py tests/test_media.py tests/test_remote_sources.py -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_household_policy.py tests/test_openapi_contract.py -q -p no:cacheprovider
```

No full-suite, frontend build, candidate Linux image, actual provider transfer, Plex indexing or physical iPhone acceptance was run for this documentation assessment.

## 3. Current integration gaps

| Component | Actual limitation | Build consequence |
| --- | --- | --- |
| `server/downloader.py:PROVIDERS` | Registry holds three HTTP search functions; Soulseek uses a separate branch | Registry must represent search, resolution, transfer, capabilities and health |
| `Downloader.attempt` | All non-Soulseek providers excluded from lossless; AAC eligibility is equivalent to being JioSaavn | Monochrome cannot work by registration alone; eligibility must come from capabilities and resolved formats |
| `Downloader.attempt` | Non-Soulseek extension is `.m4a` for JioSaavn, `.mp3` otherwise | File extension/container must follow the actual selected format |
| `matches` | Exact folded `channel == artist` and `title == title`; duration within 5 seconds | Official web uploads often fail; uploader is not recording artist. Add source-aware normalisation without inventing matching evidence |
| `matches` | Checks version words but does not compare known recording/release IDs or ISRCs | Enforce conflicts in acquisition, not just in local library matching |
| `Downloader.transfer` | HTTP CDN allowlists, 80 MB and 180-second bounds, no HLS fragment handling | Keep direct HTTP path; introduce constrained extractor transfer with fragment checks and native-format remux |
| `Downloader.validate/tag` | Validation accepts only MP3/AAC/FLAC profiles; tags dispatch to FLAC, MP4 or ID3 | Opus/Vorbis need validation and Vorbis-comment tagging; WebM cannot enter this pipeline unchanged |
| `server/quality.py` | Four profile IDs; simple rank; Opus/Vorbis and low-bitrate AAC classify unknown | New native profile requires explicit classification, satisfaction and replacement semantics |
| `Store.save_download_settings` | Four allowed sources and provider-specific profile validation | Registry becomes source of truth; retain existing validation behaviour through wrappers |
| `Store._enqueue_quality` | Unknown files do not auto-upgrade; equal rank prevents automatic replacement | Preserve protection and avoid treating unlike lossy codecs as equivalent quality |
| `server/household_policy.py` | Shared preferences choose highest rank, then current profile or lexical tie-break; pending changes invalidate claims | Add native-profile precedence explicitly; preserve shared-file protection and pending-job reconciliation |
| `Downloader.process` | Fallback runs only for lossless; preferred phase can end before time limit if sources are exhausted | Define new native fallback deliberately; do not silently expand fallback for existing profiles |
| `server/scanner.py` / probe | Ogg Vorbis codec names differ (`ogg` versus `vorbis`); probe reads upstream provenance keys, tagging writes Pig Music keys | Canonical codec names and provenance readers must agree; add backward-compatible aliases |
| `Store.publish_request` | Stores codec, bitrate, duration, hash; no structured source/format evidence in published track payload | Add sanitised provenance and measured audio properties, without signed URLs or credentials |
| Settings / API | UI hardcodes four source toggles and four profiles; personal request schema uses a four-value Literal | Update all validators, controls and contract exports together |
| Docker runtime | FFmpeg exists; yt-dlp and a JS runtime do not. Node exists only in frontend build stage | Add pinned runtime dependencies to final image, not just builder |

Existing strengths to retain: durable claim tokens; cancellation/clear guards; storage marker checks; complete-file decoding; native FLAC/MP4/ID3 tags; same-filesystem publication; hash/path-protected replacement journals; restart recovery; artist-job generation guards; album/artist/system quality hierarchy.

## 4. Provider design

### YouTube

Adapt small parsing and failure-classification ideas from [upstream `youtube.py`](https://gitlab.com/g33kphr33k/musicgrabber/-/blob/a9476a80b662911b392135188153f2fb5b05c3a0/youtube.py). Do not import its database, cookie-user model, global settings or blocking retry runner wholesale.

1. Search a bounded `ytsearch` result set. Discard playlists, live streams and incomplete results. Flat results are discovery hints; hydrate only plausible candidates.
2. Prefer structured track/artist metadata where supplied. Parse presentation text such as `Artist - Song (Official Audio)` only under narrowly tested rules. Retain the raw title/uploader, verified channel ID and evidence used. A verified channel alone is not proof of the requested recording.
3. Compare duration with catalogue context before spending transfer bandwidth. The observed 233-second music video must be rejected; do not trim an intro to make it fit.
4. Resolve an explicitly eligible audio-only format. Exclude storyboards, video-only formats, DRM, previews and formats with unknown codec until independently inspected. `vcodec == none` alone is insufficient: observed storyboards also used that value.
5. Preserve AAC in M4A, or remux WebM Opus to Ogg Opus using stream copy. No audio encoding. Record source codec, source container, chosen format and the remux operation separately.
6. Re-resolve expiring media URLs immediately before transfer; queue durable provider IDs, not signed CDN URLs.
7. Anonymous access is the default. Provide owner-only optional Netscape cookie upload/delete with a configured/expiry indicator. Keep cookie contents server-side, private and outside logs/source bundles. Cookie invalidation or bot challenges should produce a specific actionable status.

Current yt-dlp requires a supported JavaScript runtime and EJS scripts for full YouTube support. Package these together; choose pinned Deno for the final Linux image, while Node may serve local development. [yt-dlp EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

Cookies do not guarantee access to all formats; some YouTube paths can require externally provided PO tokens. Treat that as a separately tested deployment capability, not an automatic dependency on a new browser/proxy service. Launch does not promise private, members-only or age-restricted acquisition. [Extractor requirements](https://github.com/yt-dlp/yt-dlp/wiki/Extractors).

### SoundCloud

Use `scsearch` discovery and individual-track hydration. The inspected Music Grabber [search adapter](https://gitlab.com/g33kphr33k/musicgrabber/-/blob/a9476a80b662911b392135188153f2fb5b05c3a0/search.py) supplies uploader and display title; neither is guaranteed to be recording identity. Extract structured publisher/artist fields when available, apply conservative title parsing and reject contradictory credits.

The adapter must explicitly skip 30-second previews, unrequested remixes/sets, unavailable streams and protected formats. A protected result is a candidate failure, not proof the whole provider is down. Continue to other candidates and permitted sources. No DRM bypass is part of this implementation.

Handle ordinary progressive HTTP and supported HLS through the same constrained extractor worker. Resolve the manifest before committing to a format; transfer all fragments under the global deadline and resource cap. Accept only supported native codecs. Original-download formats may differ from streaming formats; unsupported originals fail clearly rather than being converted. SoundCloud account authentication and premium/private access are separate future work. [Current yt-dlp SoundCloud extractor](https://github.com/yt-dlp/yt-dlp/blob/897341241f2bfb2439fe0367f4c7c9ccd29a3828/yt_dlp/extractor/soundcloud.py).

The current live query is a useful negative fixture: the exact-name results were previews and the top remix was protected. Source parity cannot promise that a specific commercial release becomes available on SoundCloud.

### Monochrome

Use an app-owned HTTP adapter, not the retired remote-playback prototype. Current Music Grabber combines Deezer metadata with exact ISRC matching in the tracks API, plus direct tracks search; audio resolution produces a `/track/{id}` address. Reuse small parsing/resolution components with notices. [Upstream tracks adapter](https://gitlab.com/g33kphr33k/musicgrabber/-/blob/a9476a80b662911b392135188153f2fb5b05c3a0/monochrome_tracks.py), [upstream acquisition adapter](https://gitlab.com/g33kphr33k/musicgrabber/-/blob/a9476a80b662911b392135188153f2fb5b05c3a0/monochrome.py).

Build direct tracks search/resolution first, then the Deezer enrichment/rescue leg in the same provider package. A failed Deezer leg must not suppress a working tracks search. A conflicting known requested ISRC must not be silently replaced by an upstream rescue ISRC. Exact ISRC is supporting recording evidence; it does not prove the requested album pressing/master.

The observed tracks schema supplies `artistNames`, `releaseId`, `recordingId`, `isrc`, `playable` and millisecond duration. Provider numeric recording/release IDs must remain in a **Monochrome namespace**, never be copied into MusicBrainz UUID fields. Hydrate `/releases/{releaseId}` if needed for album/version context. Missing album metadata cannot be filled from the request and then used as evidence of a match.

Default endpoint proposal: `https://tracks.monochrome.st`. Keep an owner-controlled server-side HTTPS endpoint override; validate it and its redirect/CDN policy. Do not automatically trust new hosts scraped from arbitrary JavaScript. Endpoint discovery can report a possible move for review, without widening the allowlist.

Provider documentation describes fixed FLAC delivery; require measured FLAC and full decoding before calling it lossless-format audio. Do not claim that this proves lossless origin or a specific mastering. Monochrome's README warns about hosted API restrictions for self-hosting; metadata success today does not resolve audio access for our deployment. Do not spoof an official deployment to bypass restrictions. [Monochrome client](https://github.com/monochrome-music/monochrome/blob/b85c2c16e09b850f4aa8a0bd83a556676eb14358/js/tracks-api.js), [self-hosting notes](https://github.com/monochrome-music/monochrome/blob/b85c2c16e09b850f4aa8a0bd83a556676eb14358/README.md#self-hosting).

## 5. Shared contract and orchestration

Proposed new package: `server/providers/`, with a registry and small typed records. Existing HTTP functions receive wrapper adapters; Soulseek retains its engine and peer locking behind the same contract.

```text
ProviderSpec
  id, display_name, possible_codecs, supported_profiles,
  credential_kind, search_concurrency, transfer_limits

Candidate
  provider, provider_track_id, webpage_url (validated), raw_title,
  title, artists, uploader_id, uploader_name, album, duration_seconds,
  identities {isrcs, musicbrainz_*, provider_specific}, match_evidence

ResolvedAudio
  candidate, format_id, codec, source_container, output_container,
  declared_bitrate, declared_size, protocol, preview, protected,
  ephemeral_transfer_details (worker-private)

TransferResult
  contained_staging_path, source_codec/container, stored_codec/container,
  bytes_received, remuxed, sanitised_provenance

search(target, context) -> candidates or typed provider failure
resolve(candidate, quality_policy, context) -> eligible audio formats
transfer(resolved, context) -> TransferResult
health(context) -> capability/metadata observations, checked_at
```

`context` carries monotonic deadline, claim token, cancellation callback, progress callback and bounded retry budget. No adapter may publish files, update memberships, retire originals or write canonical request tags.

Candidate ordering: recording confidence and eligibility first; then the requested quality; then configured source order and within-provider format preference. Preserve existing configured source ordering; the stored source list already supplies order, so an independent priority field is unnecessary at launch. Settings may expose reorder controls in an advanced disclosure.

Initial capability matrix (possible, not guaranteed availability): FreeMp3Cloud/zvu4no retain MP3 profiles; JioSaavn retains AAC 256 and can satisfy native standard; Soulseek retains existing MP3/AAC/FLAC support; YouTube starts with native standard and measured AAC 256 only if such a format is actually available; SoundCloud starts with measured MP3/AAC and native standard; Monochrome starts with measured FLAC/lossless and native standard. Public supported-format SoundCloud originals can use the same validation gates, but a declared original file is not automatically a lossless-capable source. Advertise additional capability only once the resolver and validation path support it.

Start with bounded sequential source traversal and shared per-provider semaphores. Each source/candidate gets a deadline slice so one failing provider cannot consume all preferred-quality time. Parallel source search is a later measured optimisation; source parity does not require it.

Starting limits, to validate in the candidate image:

| Operation | Proposed bound |
| --- | --- |
| Search / hydration | 20 discovered candidates/provider; hydrate at most 5 plausible candidates; 3 transfer candidates |
| HTTP metadata | 15-second network timeout plus 30-second operation deadline |
| Extractor search / hydration | 45-second search deadline; 45-second hydration deadline |
| Transient retries | At most 2 retries, jittered/cancellable delays, within original operation budget; honour bounded Retry-After |
| HTTP redirects | At most 5, validated at each hop |
| Lossy transfer | Existing 80 MB cap, up to 180 seconds, additionally constrained by request deadline |
| FLAC transfer | Proposed 256 MB cap, up to 300 seconds; retain explicit max-track duration/size handling |
| Decode/remux | Up to 90 seconds each, with cancellation and process-group termination |
| Provider concurrency | Start at 1 search/hydration operation per provider; transfers count toward existing global 1–6 job limit |

Do not multiply retry layers: extractor internal retries, fragment retries, outer retries and cookie fallback share one bounded budget. Set explicit fragment concurrency. Missing/private/protected content fails promptly. Refresh an expired URL once; repeated expiry/403 is a typed failure.

The extractor wrapper must launch argv without a shell, ignore user config, disable unapproved plugins, use a fixed staging template and disable playlist expansion, automatic thumbnail/subtitle downloads, arbitrary hooks and re-encoding. Poll child status/cancellation; terminate the process group, including FFmpeg, on pause/cancel/deadline. Handle bounded output as it arrives so pipes cannot deadlock or grow without limit.

Use yt-dlp's supported request-handler integration or another verified network boundary to validate media, manifest, fragment and redirect destinations. Checking only the input webpage URL is insufficient. Restrict HTTPS hosts to provider endpoints/CDNs; reject private/link-local/loopback addresses, userinfo and unexpected ports. Where an external FFmpeg input cannot enforce the same policy, download validated fragments through the controlled layer first. This boundary must have redirect/HLS tests before enabling extractor transfer.

Recommended process shape: launch a Pig Music Python extractor helper (`python -m server.providers.extractor_worker`) using the pinned yt-dlp library and controlled request handlers. Emit bounded JSON progress/result records to the parent; keep transient transfer details in the helper. A bare CLI subprocess may be used for discovery experiments but must not be assumed to enforce all network boundaries. SP01 includes proving the chosen yt-dlp request-handler hook against the pinned version; if it cannot cover redirects/fragments, implement the validated-fetch layer before enabling transfers.

## 6. Matching rules

1. Reject conflicting known MusicBrainz recording/release IDs and disjoint known ISRCs. Keep provider identity namespaces separate.
2. Preserve version words and named mixes, live/studio context, compilation/edition requirements and duration. Keep the current 5-second tolerance initially; any relaxation needs a demonstrated fixture and reason.
3. Structured recording artist/title take precedence over uploader presentation. Narrowly normalise case, accents, whitespace and verified presentation suffixes. Do not strip `live`, `remix`, `edit`, `remaster`, `acoustic`, collaborations or meaningful version text.
4. An uploader alias can support a match only with explicit evidence: structured artist credits or a maintained provider channel-ID mapping. Never set the artist to the requested artist merely because a query found the upload.
5. A title-only/uploader-only ambiguous candidate is unsuitable for unattended acquisition. Return an actionable identity-review failure; do not broaden the queue status enum unless a complete review UI is included. Multiple equivalent-looking results need sufficient recording/version evidence rather than arbitrary first-result selection.
6. Recheck duration, actual bytes, embedded tags and conflicting identities after transfer and before retagging. Canonical request tags express the chosen library context; retain separate source evidence so they cannot erase a mismatch.

Use existing `server/matching.py` conflict helpers where appropriate, but do not apply its strict album-equality rule blindly to web uploads with absent album metadata. Candidate matching and existing-library matching have different evidence shapes and should share conflict primitives rather than fake identical records.

## 7. Quality and native formats

### Compatibility decision

Retain existing `mp3_320`, `mp3_128`, `aac_256`, `lossless` IDs and thresholds. They remain codec-specific: YouTube Opus/AAC cannot satisfy an MP3 request. Preserve existing exact MP3 128 downgrade behaviour separately from the existing “128 or better” fallback semantics.

Add **`native_standard`**, displayed as “Native audio — standard or better”. This is an explicitly selected codec-flexible target/fallback for web sources, not a replacement default or an assertion of codec equivalence. Proposed initial acceptance floors:

| Measured codec | Native standard acceptance | Storage |
| --- | --- | --- |
| MP3 | At least 120 kbps | `.mp3` |
| AAC | At least 112 kbps | `.m4a` |
| Opus | At least 96 kbps | `.opus` in Ogg; stream-copy remux if WebM |
| Vorbis | At least 128 kbps | `.ogg` |
| FLAC | Valid full file, measured duration/channels/sample rate | `.flac` |

These are proposed operational floors with margins for VBR measurement; they are not listening-test evidence or “MP3 320 equivalent” claims. Unknown/absent bitrate requires a reliable measured value, not a provider's label. Tests must include near-threshold VBR files; if Mutagen cannot give a dependable bitrate, use ffprobe or audio-payload accounting with defined limitations. Do not use total file bitrate when video/container overhead would inflate it.

Launch supports these common formats. ALAC/WAV/AIFF and other original-download formats are not silently converted or accepted as FLAC; broader original-format support is a separately named extension. This bounds source parity without claiming support for every possible format a provider can return.

Add native standard to system/artist/album preferences and optional lossless fallback. Existing non-lossless profiles continue to fail when no compliant source exists rather than gaining an implicit lower-quality fallback.

### Replacement policy

Replace `rank()` as the sole decision mechanism with `satisfies(profile, measured_audio)` and `is_improvement(existing, candidate, requested_policy)`. Existing saved files of unknown quality remain protected from automatic replacement. Cross-codec lossy bitrate comparisons must not trigger upgrades by themselves.

For `native_standard`, prefer a file already satisfying the policy and avoid churn. Permit an automatic move to verified FLAC when lossless remains the desired preference. Explicit user quality changes may reacquire a different codec under the selected policy, subject to the existing original-hash/path guards. Preserve the requested lossless preference after a native fallback so periodic checks can later improve it.

Shared household policy is already present in this working tree. Do not rely on older README text describing it as future work. A codec-flexible native preference must not override another member's stricter legacy target because its string sorts later. Proposed arbitration: lossless remains highest; preserve existing arbitration between legacy high profiles; strict MP3 128 takes precedence over native standard when both are requested; native standard supplies a minimum only where no stricter target wins. Preserve the existing prohibition on shared-file downgrades and invalidate pending claim tokens when the effective target changes. Cover native-plus-MP3, native-plus-AAC, native-plus-lossless and member removal/restart cases in `tests/test_household_policy.py`.

### Format, tagging and provenance

Canonicalise codec names (`vorbis`, `opus`, `aac`, `mp3`, `flac`) across scanner, probe and quality logic; read legacy `ogg` records as Vorbis when evidence supports it. Do not recategorise unrelated `.ogg` codecs solely by extension.

Add Mutagen OggOpus/OggVorbis tag writers for the existing canonical fields, MusicBrainz IDs and Pig Music provenance. Distinguish `.m4a` AAC from ALAC by actual codec. Write/read Pig Music source keys while retaining legacy Music Grabber key compatibility.

Store source/provider ID, format ID, original codec/container, declared properties, measured properties, remux flag and validation timestamp in acquisition provenance. Preserve complete-decoding results and explain that lossless container/codec inspection does not prove source mastering. Never persist tokens, cookie contents, signed CDN addresses, raw stderr or full manifests in public queue/library responses.

Prove stream-copy remux preserves the audio stream with packet/frame evidence or decoded PCM hashes; whole-file hashes naturally change with containers/tags. Decode and validate the final tagged file before calculating its publication hash.

## 8. Settings, API, migration and playback

Add a read-only provider capability/status response for the owner settings surface, rather than expanding public `/api/health` with private details. Suggested authenticated owner endpoints: `GET /api/v1/admin/download-sources`, `POST /api/v1/admin/download-sources/{id}/check`, and owner-only YouTube cookie PUT/DELETE. Final placement must follow the current admin-route contract; existing settings routes are not all represented there yet.

Status fields: configured, enabled, possible profiles, metadata health, last transfer outcome/time, next retry time and sanitised reason. Metadata checks must not download music; an explicit acquisition smoke test is a different operation. Label “metadata reachable” separately from “audio transfer verified”. Empty search results never make a provider unhealthy.

Implement a small provider circuit breaker: after 3 consecutive transient operation failures, cool down for 5 minutes, with a single permitted probe and capped exponential cooldown up to 1 hour. This is an initial engineering default; test with a fake clock. Protected/private content, identity rejection and insufficient quality do not count as provider outages. Restart may reset ephemeral health; recent sanitised observations may persist, secrets/transfer URLs may not.

Settings expose friendly source names, available quality choices, optional order controls and collapsed diagnostics. Ordinary song/album request flows continue to choose sources automatically. Keep existing source order; allowlist and deduplicate saved source IDs. A selected but temporarily unhealthy source should not invalidate saved settings or pause other sources. Validate configured capability separately from live health.

Migration is additive: older documents missing new fields receive defaults; old quality-policy snapshots retain their meanings; new provider IDs are not appended to enabled lists. Any durable provenance schema change must use the existing migration framework and preserve historical records. Test restart midway through old and new requests; do not replay previously completed work.

Update `server/app.py`, `server/api_models.py` as applicable, `server/routes/personal.py`, `server/routes/catalogue.py`, `server/household_policy.py`, quality controls and `client/src/types.ts`. Audit identity propagation as well: personal `TrackInput` currently omits ISRCs, and the legacy import queue builds a reduced payload; carry known IDs/ISRCs through every enqueue path so the new matcher can enforce them. Regenerate/check OpenAPI and the Swift contract copies using the repository's existing generation procedure. Old clients keep working with old profile strings. New native profile choices must not be sent by clients that cannot render or validate them.

The web media route already recognises `.ogg`/`.opus`, and scanning recognises them, but this is not evidence of playback on every device. Check desktop browsers, actual iPhone Safari, Plex and the native playback path. Native-standard users must receive an honest compatibility explanation if their player cannot play the retained codec. Do not force an AAC/MP3 conversion to solve compatibility inside this acquisition project.

## 9. Dependencies, provenance and delivery

Use pinned `yt-dlp[default]` and its matching EJS dependencies in the Python lockfile, plus a checksum/digest-pinned Deno runtime in the final image. Alternative: checksum-pinned official zip executable with bundled EJS; choose one packaging route and test its notices. Do not copy Music Grabber's floating `latest` download or entire browser-equipped image.

The official documentation distinguishes licensing of Python distributions from bundled executable dependencies. Record the selected packaging route and third-party notices alongside the existing upstream NOTICE. Small copied upstream functions retain source commit and licence; application-specific orchestration remains Pig Music-owned. [yt-dlp distribution/licensing](https://github.com/yt-dlp/yt-dlp#licensing).

Pin a tested dependency version at build time and release extractor updates through candidate CI; no uncontrolled runtime self-update. The assessed stable release demonstrates metadata capability but is not a final version choice. Resolve and record the actual pinned package/EJS/Deno combination in SP01 and verify Python 3.14/Linux compatibility. Maintain a short extractor-update path because providers can change independently of Pig Music.

No account/browser scraping dependency, standalone music manager or additional service container is required for the proposed public-source path. If production YouTube needs a PO-token service or Monochrome requires a separate endpoint, that is a concrete additional deployment decision, with evidence, rather than an assumed dependency.

## 10. Ordered implementation backlog

Estimates are engineering judgement, not measured delivery dates; one engineer familiar with this codebase, excluding service-access waits and device coordination.

| Package | Scope and primary files | Done when | Estimate |
| --- | --- | --- | --- |
| SP00 | Versioned provider fixtures and viability record; tests/provider fixtures; candidate endpoint inventory | Positive/negative schemas recorded without credentials/stream URLs; deployment-only gates named | 1–2 days |
| SP01 | Registry/contracts, HTTP/Soulseek wrappers, cancellation/deadlines/network boundary; `server/providers/`, `downloader.py`, Docker/lockfiles | Existing four sources behave as before; process/network boundary tests pass; pinned toolchain works in final image | 3–5 days |
| SP02 | Native-standard and household policy, Opus/Vorbis tags/remux, provenance and additive migration; quality/store/household/scanner/probe | Existing profiles unchanged; shared preferences reconcile safely; native files validate/scan/restart; replacement never churns or downgrades automatically | 3–4 days |
| SP03 | YouTube adapter and optional owner cookie controls | Search/hydration/matching/transfer fit shared contract; anonymous and session failures classified; unsuitable official video rejected | 2–3 days |
| SP04 | SoundCloud adapter | Progressive/HLS fixtures work; previews/remixes/protected formats skip; supported ordinary public transfer verified | 1–2 days |
| SP05 | Monochrome adapter, release context and bounded Deezer leg | Exact identity matching, millisecond units and redirect rules pass; candidate-container FLAC transfer and decode verified | 2–3 days |
| SP06 | Settings, status, admin API, OpenAPI/client copies and regression/release evidence | Source/quality/order controls usable on phone; old settings/clients preserved; all acceptance gates recorded | 3–5 days |

Total: **15–24 engineering days**, roughly 3–5 working weeks, plus any external access/device delays. SP03/SP04 share the extractor worker; SP05 uses the HTTP path. Build all foundations before enabling new sources. Roll out sources independently so an unavailable service does not block delivery of working adapters, but report partial parity accurately.

## 11. Acceptance matrix

| Gate | Required evidence |
| --- | --- |
| Existing-source regression | Existing tests plus wrapper contract tests; source order, exact downgrade, lossless fallback and Soulseek album/peer behaviour retained |
| Native audio | Real generated AAC/Opus/Vorbis/MP3/FLAC fixtures; thresholds, VBR, wrong extension, unreadable/truncated content, multi-stream/video rejection, tag round trip, complete decode |
| Identity | Official video with extra intro, lyric upload, wrong artist/namesake, remix/live/remaster, compilation/edition, missing album, conflicting IDs/ISRC, provider ID namespace, ambiguous uploads |
| Transfer boundaries | Expired URL, retry storm, redirects, HTTPS/host/IP restrictions, malicious manifest/fragment, output traversal, oversized and slow files, false content length, bounded child output |
| Cancellation/recovery | Cancel/pause/deadline during search, hydration, fragment download, remux, decode and publication; no surviving process group; invalidated claims never publish; restart preserves existing music |
| Quality replacement | Native fallback retains lossless goal; retry can improve to FLAC; unlike lossy codecs do not churn; unknown-quality original remains protected; explicit downgrade remains recoverable |
| Household sharing | Native/strict profile precedence, two-person membership, shared downgrade prevention, membership changes and pending claim invalidation survive restart |
| Credentials/status | Owner permission checks; cookie upload/delete/redaction; malformed/expired cookie; provider cooldown; empty result and protected candidate do not trip outage state |
| Contracts/UI | Settings round trip, friendly names/order, profile validation, phone/keyboard UX, OpenAPI drift checks and old-client compatibility |
| Actual source acceptance | Candidate Linux image, isolated appdata/library: one supported full transfer per new provider; measured codec/bitrate/duration, tags, provenance, hash, restart and publication/indexing |
| Playback | Saved audio range requests; desktop, physical iPhone Safari, Plex and native checks for formats actually enabled |
| Release | Full backend/frontend/build/format checks; pinned image; disposable backed-up-state migration comparison; provider defaults remain unchanged; documented rollback |

Use synthetic audio for automated validation. External-media smoke tests use controlled/authorised material in an isolated destination; they are opt-in and excluded from deterministic CI. Do not download a commercial catalogue track merely to turn metadata evidence into a green check. Record each source as implemented, metadata-reachable and transfer-verified separately.

## 12. Build-start decisions and unresolved acceptance

Engineering defaults supplied by this assessment: preserve current profiles/order/defaults; add opt-in native standard; retain native codec with stream-copy remux; common-format launch scope; registry-based eligibility; optional owner-only YouTube cookies; no new browser/proxy service; Monochrome endpoint override with a fixed network policy; sequential bounded source traversal; source-level rollout.

Implementation can begin without another broad design exercise. The following are evidence gates, not reasons to postpone foundation work:

- Final tested yt-dlp/EJS/Deno pins and final-image compatibility.
- At least one ordinary supported SoundCloud track must successfully transfer; observed commercial results included previews/protection.
- Monochrome audio endpoint access, redirects, throughput and codec from the candidate Unraid network. Historical timeout evidence is superseded only for current metadata access.
- Actual player support for retained Opus/Vorbis and any required owner choice to exclude incompatible formats.
- A positive recording-identity fixture for unattended YouTube acquisition; successful extraction of an official music video is insufficient.

**Completion claim:** all seven sources must be selectable and use the durable verified pipeline, with an actual supported transfer recorded for each newly added source. A registered but unusable adapter, a mock-only success, a working search with protected audio, or a Monochrome metadata result alone does not meet source parity.
