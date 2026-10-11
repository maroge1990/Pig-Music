# Native review, artwork and source fixes — 12 October 2026

Owner-requested review of the iPhone and Watch apps, confirmation of the YouTube, SoundCloud and Monochrome download clients, and the missing Passion Pit artwork on the web client. Owner layout feedback received during the review is applied to both the web and native clients. Committed locally to main; not pushed or deployed.

## Artwork (web and native)

- **Cause:** Passion Pit's MP3s carry no embedded art and are tagged with a GB pressing of *Manners* (`12b93d10…`). Cover Art Archive has no scan for that release, but has one for its release group (`cdaae438…`). The library album path fetched only the exact release and then marked the album missing for 24 hours. The web cover retried twice, then showed the placeholder. The catalogue path already fell back to the release group; the library path now shares that fallback. Missing-cover markers move to `v4`, so previously failed albums retry immediately.
- The personal library projection replaced household artist portraits with album art. Portraits are kept now, and the artist alias falls back to the album's lazily fetched cover.
- Native clients address artwork by hash only. Personal and native track/album DTOs now carry `album_id` and the hash of server-fetched covers. Without this, albums without embedded art could never show a cover on iPhone.
- The native artwork transport refused every redirect, so catalogue portraits (`/api/catalogue/artists/{id}/artwork`) could never load. It now follows one same-origin redirect to `/api/artwork/<sha>.jpg` and loads that hash through `/api/v1/artwork`. Catalogue release and release-group covers use the same path.

## Download clients

Metadata-only checks were run with the isolated harness on this Mac. No audio was transferred.

| Source | Before | After | Notes |
| --- | --- | --- | --- |
| Monochrome | 1 match (Passion Pit / Little Secrets) | unchanged | Live API shape matches the adapter; FLAC served from the configured host. |
| YouTube | 0 matches | 2 format choices of the official track (also Bastille / Pompeii) | Plain `ytsearch` returns music videos, which correctly fail the duration check. Search now uses YouTube Music song results (official "Topic" audio with structured credits) first, and falls back to video search only when no song result matches. `(Audio)`, `(Lyrics)` and visualiser suffixes are stripped from verified-channel credits. |
| SoundCloud | 0 matches | unchanged (by design) | The official upload has no structured artist credit, only the account name, and the 30-second Go+ preview is correctly rejected. Accepting uploader names as artists would admit fan uploads; left for an owner decision. |

Also fixed: a remuxed WebM/HLS stream with an unhandled codec was hard-linked into a mismatched container; it is now rejected. A non-transient failure during an expired circuit-breaker probe left the source half-blocked for concurrent operations; an answered probe now clears the cooldown.

## iPhone

- **Crash:** the Now Playing artwork handler was main-actor isolated, but MediaPlayer calls it on its own queue. Swift 6 isolation checks terminated the app as soon as a song with artwork played. Reproduced in the simulator (crash report: `closure in PlayerController.refreshArtwork()` on MediaPlayer's access queue) and fixed. AVFoundation notification sinks on iPhone and Watch now receive on the main queue.
- Changing the playback mode no longer clears the queue. Retrying with streaming keeps artwork. Headphone and AirPods play/pause is handled. Now Playing seeks once per drag instead of on every slider tick.
- Artwork no longer blanks to a placeholder on every sync. Pushed pages had lost the branded canvas (plain black); every pushed page and sheet now uses it. The Watch bridge no longer polls every two seconds in the background or without a paired Watch app.
- **Experience aligned with the web app:** Home, Library, Downloads and Search tabs, with Account opened from the avatar. Web-style artwork cards with initials placeholders, collection chips and grids. Home shows recommended artists and albums only. Album, artist, playlist and catalogue pages use a compact header, one action row (Play capsule plus round icons) and settings below the music. On iOS 26.1+ the mini player is the tab bar accessory, as in Apple Music; older systems dock it above the tab bar inside each tab.

## Watch

Starting a song where earlier songs were still waiting for transfer started the wrong song. Audio-session activation used a main-actor completion closure. Headphone toggle and Now Playing scrubbing commands are handled. One tap now plays a song; swipe removes its download. Times show as m:ss, and the current song appears on the Watch home list.

## Web (owner feedback)

On phones, the player and the tab bar form one integrated dock with equal row heights, and no longer overlap. The fold-on-scroll tab bar is removed. Album, artist and playlist pages have a small back link, one compact action row, and quality, playlist options and "follow new albums" below the songs; owner tools stay last. Home recommendations show artists and albums only.

## Verification

- Backend: full suite passes (372 tests), including new regressions for release-group cover fallback, native cover hashes, the YouTube song-first search, title suffixes and breaker probes.
- Web: 38 tests, production build and Prettier pass.
- Native: PigKit Swift Testing 65 + 13 (including the alias transport test) and XCTest 17 (2 skipped, as before) pass. iPhone simulator Debug build (iOS 26.5 simulator, Xcode 27) and the Watch simulator build pass. Project generation check passes. Demo-mode screens were captured headlessly, and demo playback ran through a gapless queue with no crash.
- The simulator panel needs `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer` (owner action). Builds used `DEVELOPER_DIR` instead.

## Still open

Physical iPhone and Watch acceptance from the [build handoff](native-phone-watch-build-20261012.md); real audio transfers for the three new sources from the Unraid network; and the SoundCloud uploader-identity decision. The web changes need a container build and deploy to reach `music.markrogers.au`. Server-fetched covers reach the iPhone after the next library refresh following the fetch.
