# Household and native audit continuation

7 October 2026. This continuation completes the staged account-facing work beyond the M04 removal checkpoint and starts the production Swift API package. It is a release candidate, not the live account cutover.

## Delivered

- M04: member quality preferences at general, artist and edition scopes; highest requested shared quality; invalidated acquisition claims when that target changes; explicit administrator assignment of externally scanned music; stable logical IDs after metadata rescans. Batch policy resolution avoids repeatedly opening settings/databases per track. Recoverable shared-file removal and private undo remain in place.
- M05: independent Plex export controllers and path/status caches for each connected member. Tokens use authenticated encryption bound to the user, never appear in responses, and the original owner's token is migrated idempotently out of the legacy connection file. Existing owned remote playlist markers are retained.
- M06: bounded JSON bodies, same-origin content policy, external theme initialization, HSTS on HTTPS, stable redacted errors, administrator activity, member disable/enable with immediate session/setup-code revocation, and dependency audits before image publication. The threat model is in `security.md`.
- M07: branded sign-in/setup, personal library, favourites, private playlist import/edit/reorder, household add, catalogue discovery/edition requests, personal artist following, quality preferences, private Plex connection, session/password management, people and Unassigned inbox. Members continue to import their own playlists. Administrator tools load separately. Logout clears media and account read caches; revoked sessions return to sign-in while preserving the hash route.
- X01–X03 foundations: committed v1 OpenAPI export/drift check, typed library/detail/identity/playlist/search/request responses, user-bound revision cursors, original Range file access, versioned content-addressed artwork, scoped SSE with four connections per session, heartbeat and revocation checks, progress and durable 30-day final-state deltas including private playlists. Checkpoints materialise at sync reads rather than recording every intermediate edit; the client converges to the latest state. Unknown/expired revisions return 410; a changed cursor returns 409 and restarts its collection.
- Swift commencement: official Apple OpenAPI generation with a locked dependency resolution, a HTTPS-only server-origin validator, Keychain token storage and session middleware. No stored passwords. Tests call the generated client against the disposable loopback fixture and verify sign-in, identity and cursor reads. An unsigned iPhone simulator build passes. This is an API foundation; a production iPhone UI, GRDB storage, playback/download engine and Watch app are not claimed.
- Structure: a small startup entry point, separate personal/account/discovery/quality views, delayed administrator code, nine smaller style files with the original cascade order, and distinct household/native/discovery routers. The advanced legacy administrator controller and remaining owner/provider routes still have incremental extraction debt; renaming the old controller does not make that debt disappear.

## Evidence

Local backend suite: 202 passed before final presentation changes; rerun results and exact published source/image are recorded at the final checkpoint. Frontend tests and strict build passed. Locked Python and full frontend dependency audits found no known advisories. Migration and owner attribution passed on a disposable copy of the stopped production backup: all 1,395 tracks and durable state retained. Native DTOs also passed on that copy (177 artists, 98 albums, 1,395 tracks).

Two-account native sync benchmark: 10k tracks each, 181.11 MB peak RSS and 1.03 s cold capture; 50k tracks each, 422.78 MB and 2.985 s. A 200-track JSON page is 128,896 bytes. These are synthetic Mac measurements, not phone launch/scroll results. CI additionally runs inside a 1 GB Linux container before publishing the candidate.

Browser fixture evidence is saved in the chat workspace `outputs/household-audit-20261007`. Synthetic credentials and music are used. Checks cover owner/member separation, phone layout, themes, personal favourites, sign-out and session replacement. Real-device accessibility and cellular acceptance remain outstanding.

## Release and user gates

Keep the verified live audit release running until this candidate has passed registry/Unraid checks and the administrator has created the real owner account through an interactive terminal. Do not request or put a password in chat, a command argument, environment variable or a log. The account CLI supports:

```
python -m server.admin create-owner --username mark
```

Run inside the prepared candidate with `docker exec -it`; it prompts twice without echo. Candidate staging and the final exact command belong in the operational handover once the image is verified. Then create household members in Account → People and share their one-use setup codes privately. All original shared library files and legacy playlists are attributed to Mark once, new external scans stay Unassigned, and personal imports remain available to each member.

Actual phone Tailscale/cellular and accessibility checks need the user's devices. The feasibility IPA is still uninstalled; Watch installation, headphone playback and the re-sign cycle remain unproven. Production Watch work stays behind that gate. M10 device-copy storage/invalidation and the complete iPhone app are subsequent roadmap packages, not shipped by this API foundation. Original NAS files are never transcoded to meet a library quality preference. Optional new artwork-accent treatments require their own brand decision.
