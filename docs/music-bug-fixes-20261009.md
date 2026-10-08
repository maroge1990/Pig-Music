# Music browsing, downloads and playback fixes — 9 October 2026

Implemented locally, not deployed. The live Unraid instance was inspected read-only.

## Changes

- Album downloads use the same request formatter as individual songs, including converting the catalogue's numeric year to the string required by `TrackInput`. Release and recording IDs, album context, track/disc numbers and duration are retained. Submission is disabled while pending and server errors are shown.
- Downloads now has **Clear downloads**. It dismisses the signed-in person's completed, failed and cancelled requests. Active requests, music files, library memberships, playlists and other people's request history are retained. Shared queue records remain available to administration.
- Artist cards in Search open the full catalogue even when the artist is already partly saved. Known catalogue IDs take precedence in song artist navigation.
- Full artist albums use one responsive row with Previous/Next controls, preserving the existing popular/chronological order. The observed layout displays five cards on desktop and two at 375 px. Additional catalogue pages remain reachable through Next.
- The artist hero reserves its graphical layout while artwork loads, using fallback only after artwork failure. Warm catalogue popularity/release data is retained briefly in a bounded, session-cleared memory cache and used for initial rendering. Library media settings are remembered with session-generation guards.
- Saved artist resolution reuses a known identity, then uses saved release credits or exact album-title credits to distinguish namesakes. Unresolved ambiguity still requires selection in Search.
- Previous is available in both player views and uses the same behaviour for media-session controls: restart after three seconds; otherwise go to the previous queue entry. The first song can also restart.
- Playlist Play and Shuffle build the same complete queue used by individual song rows, preserving cloud songs and repeated entries. Imported cloud songs without catalogue IDs use the existing strict remote provider matcher through an authenticated endpoint. Remote playback never submits a download; provider availability and the remote-playback setting still apply.

The versioned API schema and native schema copy include the new endpoints.

## Madonna investigation

Read-only inspection of the running PigMusic container confirmed two cached catalogue identities named Madonna: the US artist and a Lebanese singer. The old personal artist resolver required exactly one name match and ignored saved release evidence.

The saved `Like a Prayer` album has release ID `02e515ed-1626-412c-af0e-318bca521724`. Its cached release credits identify Madonna as `79239441-bfd5-4981-a70c-55c3f15c1287`. The new release-credit path resolves this case; a regression test covers a namesake with a saved release ID. No production identity or library data was modified during investigation.

## Verification

- Full backend suite: **243 passed** before the final additional Madonna release-credit regression. The additional test and focused security/catalogue checks were run separately afterward: **16 passed**.
- Frontend: **11 tests passed**, including cloud/repeated playlist entries, album year/edition formatting, direct catalogue navigation and session-isolated warm cache reads.
- TypeScript and production Vite build passed. Black and Prettier checks passed.
- Disposable loopback browser fixture: album request accepted; completed/failed entries cleared with active entries preserved; saved artist Search result opens full catalogue; album Previous/Next preserves order; Play advances from a saved file to a cloud stream; Shuffle includes both; Previous restarts then returns to the previous track.
- Desktop and 375 px layouts inspected. Browser artwork/audio/provider data was synthetic; this is not live provider acquisition or physical-device acceptance.

## Release status

No image was built or deployed for this change. The inspected running image was `ghcr.io/maroge1990/pig-music:sha-c1f01aa1ac6c1c1b6fc05eb1cb28912270c901f1`. Production music files, settings and requests remain untouched. Exact-image Linux checks, live acquisition/provider checks and physical-device acceptance remain release work. Use the existing account-aware release procedure with its backups and rollback protections for deployment.
