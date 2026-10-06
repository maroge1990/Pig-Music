> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Read-only prototype validation

Validated locally on Windows on 5 October 2026. This is the first phase 1 milestone, not the completed consolidated downloader.

## Real data

- Read-only snapshot: 1,370 tracks, 88 ordinary album groups and five compilation groups; 37 album artists in the main grid. These are tag-derived groups, not yet MusicBrainz-resolved release identities.
- Favourites XML: 88 tracks; 17 exact metadata/context matches, 53 unmatched and 18 requiring release/duration review. Two compilation groups are segregated. No automatic selection or download.
- Artwork is extracted from existing embedded covers and cached locally. No music files were changed and no stopped containers were started.

## Verification

- Seven backend tests passed, covering compilation rules, album-artist counts, contextual matching, restart persistence, invalid selections/imports, snapshot preservation and cross-origin writes.
- TypeScript checking and Vite production build passed.
- Browser verified artist-to-album navigation, ten saved Funeral tracks, search results, compilation groups and individual migration selection/review/deselection. The temporary test selection was cleared.
- Phone-sized viewport (390 × 844): two-column library cards and bottom navigation; album view had no horizontal overflow. This is browser emulation, not an actual iPhone test.
- No browser console errors in the inspected session.
- Twenty warm requests per endpoint on local loopback: library median 3.0 ms, maximum 4.6 ms; artist detail median 1.7 ms, maximum 2.5 ms. These measure API response time, not end-to-end mobile rendering or NAS scan speed.

## Remaining limits

Matching is deliberately conservative and currently based on names, release context and duration. Punctuation, accents or alternate credits can cause false missing entries (for example Haiti versus Haïti); metadata resolution and duplicate-acquisition checks must precede real downloading. A metadata match is not proof of identical audio/mastering.

The catalogue lookup covers artists only. Full remote release/track browsing, durable acquisition, quality policy, monitoring, approved organisation, trash and settings are subsequent work. Docker packaging is provided but has not been built or deployed in this milestone. Full Apple library coverage, provider downloads and actual iPhone performance remain unverified.
