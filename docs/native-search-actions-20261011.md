# Native search and personal music actions

11 October 2026. Local review candidate following the Home/catalogue milestone. The owner requires explicit approval before any push to main. This milestone has not been pushed, published or deployed.

## Delivered

- Saved songs, albums and artists searched through account-scoped SQLite full-text indexes. Artist results open paged saved album lists. An additive v3 migration indexes albums/artists already present in an existing cache; updates and deletes maintain those indexes.
- Separate household song and catalogue artist results, with bounded pages, per-source loading/error/empty states and independent availability. Query replacement, cancellation and account expiry cannot publish obsolete results. Saved results continue to work offline; catalogue/household discovery requires a connection.
- Personal and household server search now returns totals, albums and a projection revision. Loading a page after the projection changes returns 409 and requires a refresh. Existing web calls retain their default first-page behaviour. Catalogue artist search forwards bounded provider paging and normalizes missing descriptions.
- Song actions from a long press/context menu or the VoiceOver custom action: read favourite status, explicitly set/unset favourites, add a household file to personal membership, or request a catalogue/cloud song. Favourites never acquire music. Confirmed writes refresh the personal cache; writes are serialized against library sync and other personal writes.
- Album-level add/request, preserving release/recording, disc/track, album artist and year metadata. Already requested songs are excluded from the album action. Requests go to the existing server acquisition pipeline and consume its enabled/disabled state; no download-client worker or provider behaviour changes.
- A personal Music requests page showing status, bounded progress, sanitized errors, paging, refresh and clearing finished requests. Clearing does not discard active requests. Queue changes between page loads require refresh for a complete current view.
- Typed favourite/membership/acquisition/clear response contracts exported into both OpenAPI copies. No new dependencies or server database migrations.

## Playback and membership boundary

The security guard checks personal membership before issuing a signed file URL and again on file requests. The release handler alone does not describe that authorization boundary. This milestone preserves it.

Catalogue release detail can expose a sanitized `household_track` with the physical file ID for an explicit add action, alongside the existing personal-only `saved_track`. No filesystem paths or another person's membership are exposed. Tapping a household song opens Add to my library; after confirmation the sheet offers Play. A whole edition containing household songs must be added before those file sources can play. Pure catalogue/cloud songs continue through the experimental provider, with unavailable/disabled fallback messaging and no implicit acquisition.

The web player currently adds household membership during playback. The native scope requires membership to be an explicit action, so the native UI makes that step visible. Signed media access has not been widened.

## Verification

- **353 backend tests passed**, including search beyond 200 household songs, page uniqueness, path exclusion, personal membership transitions, stale revision rejection, bounds, typed provider paging and physical household file identity.
- **75 native tests passed, no skips**: 17 XCTest, 46 core Swift Testing and 12 API Swift Testing. The real disposable-server journey verifies search, explicit favourite true/read/false without acquisition, explicit membership followed by signed playback, acquisition creation/status and retaining active requests on clear.
- New native cases cover late results after query replacement/account clear, independent provider failure, stale cache revision, expired-account callback, existing-cache migration, entity rename/deletion, metadata preservation and no automatic mutation retry. The 50k saved-track cache case passed in 14.5 seconds in the final run on this shared Mac; this is not a controlled phone/server concurrency benchmark.
- **38 web tests passed**; strict TypeScript and production build passed with the existing lucide module-directive bundler warnings.
- Final unsigned Debug and Release builds for generic iOS Simulator: **passed**, targeting iPhone and iPad on iOS 18 or later. No signed device build, simulator interaction acceptance or physical device test is claimed for these new screens. An initial overlapping-build database lock was corrected by completing both builds sequentially.

Validation uses generated music and disposable accounts/files. No live settings, libraries or acquisition jobs were accessed. The fixture is stopped after testing.

## Dependencies and remaining work

Deploy server and native contract changes together after approval. New paging/revision fields and typed household identities are required by this candidate. Native cache migration is additive; server acquisition clients remain behind the existing request/status API.

These are online confirmed actions. Explicit favourite state and membership adds are repeatable, but there is no durable offline mutation outbox. Acquisition retries can intentionally restart terminal jobs, so the client does not automatically retry an uncertain write. Refresh server requests before repeating an unconfirmed acquisition. Durable idempotency keys and replay semantics remain part of N02.

Next: revision-aware playlist create/rename/delete/add/remove/reorder and personal XML import/review; richer artist details/filters/artwork and request retry/cancel/bulk artist flows; personal removal/undo, account/quality/Plex/password/devices and production invite onboarding; persistent Home caches; offline originals/AAC and storage/background transfers; persisted playback/history and SSE reconnect. Real-device gapless/crossfade, interruption/background/network/accessibility acceptance and three-user 50k load tests remain release gates. Administrative tools stay on the web. Watch follows phone/tablet, then Mac.

Publishing is on hold: obtain the owner's explicit approval before pushing to main or triggering a new published candidate.
