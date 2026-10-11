# Native Home and catalogue read journeys

11 October 2026. An incremental iPhone/iPad milestone within the [approved scope](native-uplift-scope-20261011.md), following the [connected alpha](native-uplift-delivery-20261011.md).

## Delivered

- Home tab/tablet sidebar destination, personal recently added albums, regional popular feed and library-seeded recommendations. The three requests run independently; one unavailable provider does not discard another successful feed. Refresh retains previous content while loading. Preparation, no seeds, empty results, provider failure and expired session have distinct handling.
- Recent albums navigate to saved-library details with existing artwork and playback. Pull-to-refresh also refreshes the personal library.
- Discovery artists navigate to release groups, then editions, then tracks. Release/edition pages load bounded server pages on demand, display release type/date and edition format/country/status, and offer retry/error/empty states.
- Play an edition or an individual song. Exact catalogue recording/release identity survives source resolution. Saved songs use their actual personal file IDs and revisions; household-only/requested songs remain experimental playback candidates. Playback never implicitly adds membership or requests an acquisition.
- Typed response models for personal catalogue groups, editions and release detail, exported into both OpenAPI copies. Release tracks include an optional sanitized `saved_track` only when the matching file belongs to the caller. No household file path or another person's saved DTO is exposed.
- Account-generation fences and cancellation checks stop obsolete Home/catalogue reads publishing after sign-out/account changes. Home results remain in memory and clear on detach.

## Verification

- Full backend suite: **350 passed**, including the updated personal catalogue regression using a physical saved-file ID different from the catalogue track ID. It checks household-only suppression, personal ID/revision exposure and filesystem-path exclusion.
- Native suite against a disposable loopback fixture: **67 passed, no skips** (17 XCTest; 41 core and 9 API Swift Testing cases). Six new cases cover Home feed states/routes, recording/release identity, personal recent metadata, authentication expiry, saved-file mapping and catalogue paging/edition metadata. The real fixture journey also checks that recent albums match the member's two-track personal projection.
- Unsigned Debug build for generic iOS Simulator: **passed** for the production phone/tablet target.
- Both committed OpenAPI exports match server generation; Swift/Python formatting and whitespace checks pass.

## Limits and next work

This is read/discovery progress, not everyday parity completion. External catalogue/household search, artist biography/popular tracks/release-type filters/catalogue artwork, personal write actions, downloads/AAC, live SSE, persisted queue/history and physical gapless/crossfade acceptance remain pending. Discovery feeds and catalogue details do not yet have durable offline caches. Live provider playback, navigation interaction/accessibility on real devices and installed server rollout have not been accepted.

Catalogue personal saved-file playback requires the matching updated server response. Keep server/client releases aligned. The change adds response metadata only and needs no database migration; prior household/personal state values and web journeys remain intact.

Next development slice: catalogue/household search and typed, replay-safe favourites/membership/request actions; continue the physical playback architecture gate alongside those features. Administrative tools remain web-only. Watch follows iPhone/iPad completion, then Mac.
