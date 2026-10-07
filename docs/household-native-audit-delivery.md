# Household and native audit continuation

7 October 2026. This continuation completes the staged account-facing work beyond the M04 removal checkpoint and starts the production Swift API package. It is a release candidate, not the live account cutover.

## Delivered

- M04: member quality preferences at general, artist and edition scopes; highest requested shared quality; invalidated acquisition claims when that target changes; explicit administrator assignment of externally scanned music; stable logical IDs after metadata rescans. Batch policy resolution avoids repeatedly opening settings/databases per track. Recoverable shared-file removal and private undo remain in place.
- M05: independent Plex export controllers and path/status caches for each connected member. Tokens use authenticated encryption bound to the user, never appear in responses, and the original owner's token is migrated idempotently out of the legacy connection file. Existing owned remote playlist markers are retained.
- M06: bounded JSON bodies, same-origin content policy, external theme initialization, HSTS on HTTPS, stable redacted errors, administrator activity, member disable/enable with immediate session/setup-code revocation, and dependency audits before image publication. The threat model is in `security.md`.
- M07: branded sign-in/setup, personal library, favourites, private playlist import/edit/reorder, household add, catalogue discovery/edition requests, personal artist following, quality preferences, private Plex connection, session/password management, people and Unassigned inbox. Members continue to import their own playlists. Administrator tools load separately. Logout clears media and account read caches; revoked sessions return to sign-in while preserving the hash route.
- X01–X03 foundations: committed v1 OpenAPI export/drift check, typed library/detail/identity/playlist/search/request responses, user-bound revision cursors, original Range file access, versioned content-addressed artwork, scoped SSE with four connections per session, heartbeat and revocation checks, progress and durable 30-day final-state deltas including private playlists. Checkpoints materialise at sync reads rather than recording every intermediate edit; the client converges to the latest state. Unknown/expired revisions return 410; a changed cursor returns 409 and restarts its collection.
- Swift commencement: official Apple OpenAPI generation with a locked dependency resolution, a HTTPS-only server-origin validator, Keychain token storage and session middleware. No stored passwords. Tests call the generated client against the disposable loopback fixture and verify sign-in, identity and cursor reads. An unsigned iPhone simulator build passes. This is an API foundation; a production iPhone UI, GRDB storage, playback/download engine and Watch app are not claimed.
- Structure: a small startup entry point, separate personal/account/discovery/quality views, delayed administrator code, nine smaller style files with the original cascade order, dedicated library/detail, queue and settings views, distinct household/native/discovery/catalogue/artwork routers, and artwork maintenance outside the durable store. The administrator shell now coordinates these views instead of rendering them all. Further simplification of its import controller is routine maintenance, rather than a prerequisite for these audit fixes.

## Evidence

Local backend suite: Final suite results and exact published source/image are recorded at the release checkpoint below. Frontend tests and strict build passed. Locked Python and full frontend dependency audits found no known advisories. Migration and owner attribution passed on a disposable copy of the stopped production backup: all 1,395 tracks and durable state retained. Native DTOs also passed on that copy (177 artists, 98 albums, 1,395 tracks).

Two-account native sync benchmark: 10k tracks each, 181.11 MiB peak RSS and 1.03 s cold capture; 50k tracks each, 422.78 MiB and 2.985 s. A 200-track JSON page is 128,896 bytes. These are synthetic Mac measurements, not phone launch/scroll results. CI additionally runs inside a 1 GB Linux container before publishing the candidate.

Browser fixture evidence is saved in the chat workspace `outputs/household-audit-20261007`. Synthetic credentials and music are used. Checks cover owner/member separation, phone layout, themes, personal favourites, sign-out and session replacement. Real-device accessibility and cellular acceptance remain outstanding.

## Release and user gates

Keep the verified live audit release running until this candidate has passed registry/Unraid checks and the administrator has created the real owner account through an interactive terminal. Do not request or put a password in chat, a command argument, environment variable or a log. The account CLI supports:

```
python -m server.admin create-owner --username mark
```

Run inside the prepared candidate with `docker exec -it`; it prompts twice without echo. Candidate staging and the final exact command belong in the operational handover once the image is verified. Then create household members in Account → People and share their one-use setup codes privately. All original shared library files and legacy playlists are attributed to Mark once, new external scans stay Unassigned, and personal imports remain available to each member.

Actual phone Tailscale/cellular and accessibility checks need the user's devices. The feasibility IPA is still uninstalled; Watch installation, headphone playback and the re-sign cycle remain unproven. Production Watch work stays behind that gate. M10 device-copy storage/invalidation and the complete iPhone app are subsequent roadmap packages, not shipped by this API foundation. Original NAS files are never transcoded to meet a library quality preference. Optional new artwork-accent treatments require their own brand decision.

## Audit closure and release checkpoint

The code findings are addressed across the existing live audit release and this household candidate. Account-dependent changes become live at the account cutover.

| Audit items | Implementation status |
| --- | --- |
| P0-1–3 | Metadata-only snapshot, edition/content identity, safe pruning and non-blocking artwork enrichment |
| P1-1–2, P1-6 | Modern image derivatives, immutable URLs/validators, bounded off-thread/per-key work |
| P1-3–5 | Approved branding/icons/manifest, generated CSS/Swift tokens, rem text, accessible controls and protected player roles |
| P1-7, P2-1–2 | Compressed conditional summaries, bounded collection pages, ID maps and cached settings |
| P2-3–6 | Small/pre-blurred hero derivatives, dominant metadata, local provider fallback, incremental preload and vocabulary tokens |
| P2-7–9 | Dedicated views/styles/routers, artwork maintenance extraction, horizontally scrolling tabs and branded placeholders |
| P2-10, F-1 | Scoped revocable events, typed v1 contract, revision cursors and durable final-state sync; Swift API package commenced |
| P3 | Redundant personal saved ticks removed, rare tools split, TestClient dependency warning resolved, authenticated native/browser writes |
| F-2 | Private household libraries/playlists/favourites/imports/requests and independent Plex connections |
| F-3–4 | Shared generated brand foundation and private listening events; new artwork-accent treatment, manual artwork editor and recently-added shelf remain optional roadmap ideas |

Local final checks: 205 backend tests, four frontend tests, strict production build, formatting, token/OpenAPI drift checks, three generated-client tests and unsigned iPhone build. Stopped-backup owner attribution retains 1,395 tracks and durable state. At 50k tracks the authenticated Mac HTTP fixture starts in 6.761 seconds, uses 435.65 MB cumulative peak RSS and transfers 223,760 gzip bytes; conditional p95 is 3.720 ms.

A final release-check review found and fixed two issues: output logging had masked the old unauthenticated HTTP benchmark failure, and household inbox refresh rebuilt a large union for each track. CI now fails on benchmark errors and guards metadata startup time. The older deployment shortcut rejects account releases before any service changes.

The protected setup container is isolated from networking and the NAS is read-only. Its data starts from a retained backup. After interactive owner setup, take a fresh stopped backup and preserve the setup credential while attributing the latest live state before switching. Do not promote the staged backup wholesale or discard intervening playlist/queue changes. Keep the current live container and rollback available until authenticated acceptance passes.

Remaining human acceptance: Mark's password through the interactive CLI; phone HTTPS over cellular/Tailscale, VoiceOver/enlarged text and revocation during playback; Sideloadly iPhone/Watch installation, headphones audio and refresh cycle. The complete production iPhone/Watch apps and device-copy policy/storage are subsequent native roadmap packages, not completed by this API foundation.

### Exact candidate acceptance

Runtime source: `c4bedc305ed939dfd09cb4c8ded3da827af5c57c`. Image: `ghcr.io/maroge1990/pig-music@sha256:6ae265a8200ca89bf373c3ebdd78e27d9f60e159eae56edcc3b04fab9d9cb3a4`. [Registry verification](https://github.com/maroge1990/Pig-Music/actions/runs/37558311809) and [native verification](https://github.com/maroge1990/Pig-Music/actions/runs/37558311857) passed. The image passed **205 tests on both GitHub and Unraid**.

All Unraid scale commands ran with a 1 GB limit: 50k artwork migration/refresh peak **322.76 MB**; authenticated HTTP peak **379.22 MB**, startup **13.708 s**, conditional p95 **5.166 ms**, gzip body **223,760 bytes**; two people sharing 50k tracks peaked at **388.63 MiB**, cold sync **10.703 s**. A separate worst-case fixture gave each person 50k distinct tracks (100k unique in total): **573.36 MiB**, refresh **8.910 s**, cold sync **10.663 s**. Artwork and HTTP peaks use decimal MB; native sync peaks use binary MiB (the benchmark retains its historical `peak_rss_mb` field name). These are server measurements, not phone scroll/launch results. The Unraid host enforces memory but reports no swap-limit capability. The native gate was completed with its default arguments after correcting the deployment helper's unsupported `--sizes` option; no already-passing application checks were omitted.

Exact-image stopped-backup migration and owner attribution retained **1,395 tracks**, existing links and durable rows; the source backup was read-only and unchanged. The disposable attribution account was removed with its validation fixture. `pig-music-household-setup` contains a separate copy of the retained appdata and has no owner yet. Its network is `none`, it publishes no ports, uses `99:100`, a read-only root, a 1 GB limit and a read-only `/library` NAS mount. It runs only a sleeping helper, not the web application. Candidate data: `/mnt/user/appdata/pig-music-preview/candidates/household-audit-20261007-v1/data`.

In **Unraid's terminal**, create Mark's password with:

```sh
docker exec -it pig-music-household-setup python -m server.admin create-owner --username mark
```

It prompts twice without echo and accepts 12–256 characters subject to the password policy. Report only completion; never send the password in chat. The live container remains the verified `audit-followup-20261007-v1` image pending this prerequisite and fresh-state authenticated cutover. The actual setup result must be checked before promotion. Later acceptance-script, deployment-helper and handover changes do not alter the runtime source/image above.

Reproduce the disjoint-collection check with:

```sh
docker run --rm -i --network none --memory=1g --entrypoint python \
  ghcr.io/maroge1990/pig-music@sha256:6ae265a8200ca89bf373c3ebdd78e27d9f60e159eae56edcc3b04fab9d9cb3a4 - \
  < scripts/benchmark_disjoint_sync.py
```

The subsequent acceptance-tool checkpoint `0dea5d5` also passed [container verification, including the permanent 100k-track gate](https://github.com/maroge1990/Pig-Music/actions/runs/37560383753) and [native verification](https://github.com/maroge1990/Pig-Music/actions/runs/37560383755). This does not replace the exact Unraid-tested runtime image above.
