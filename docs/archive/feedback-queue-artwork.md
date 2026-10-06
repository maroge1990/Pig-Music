> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Queue, imports and artwork feedback — 6 October 2026

Deployed at http://192.168.1.203:8765, image `pig-music:preview-20261006-feedback-queue-v2`, ID `sha256:44c9206f05b94840983b5eab86da30a73931addbaab65fc8e585cab4a0ee40f3`. Queue retained all 24 completed requests; all 24 files are published to SMB. Plex playlist sync remains connected. The configured Fanart key was preserved.

## Delivered

- Queue navigation badges on desktop and phone count all requests except completed/cancelled, including failed requests that still need attention.
- Clear all cancels unfinished claims and clears history without deleting acquired metadata, files or playlists. Active clearing asks for confirmation in the UI. Live history was not cleared for verification. A claim token prevents a cancelled transfer or stale recovery journal from publishing into a new submission with the same request ID; transfer filenames and journals are claim-specific.
- Import library replaces Bring your music; the navigation selection badge is removed. The import page starts empty on app load instead of showing the previously supplied XML. Explicit upload or Add missing songs on an existing playlist opens review. Stored playlists and review data remain durable; hiding the old review does not delete them.
- Promotional headings and sidebar slogans removed, along with player provider/source notes. Playback errors and loading feedback remain visible.
- Settings cards have spacing, controls align centrally, and stale preview/appdata-storage wording is corrected. Mobile layout checked at 390 by 844 with no horizontal overflow.
- Background preloading uses the persistent metadata cache and shared MusicBrainz rate limiter. It resolves unambiguous saved artists and paginates Albums, Singles, EPs and Other releases up to the existing 10,000-result guard. It preloads portraits and the first 12 recent covers per release type, plus missing saved-album artwork. Other covers remain lazy. Checks repeat every 15 minutes against a 24-hour metadata cache; cold preloading is gradual and browsing remains usable. Artist ambiguity is not guessed. Preloaded library portraits use the same name-based cache key as the library artwork endpoint. Configuring/replacing Fanart keys invalidates the old portrait cache, so earlier ArtistGrid portraits do not indefinitely conceal Fanart enrichment.

## Validation and proposed artist-page additions

77 backend tests passed locally and in the Linux feedback-queue image, including queue clearing, retaining files/playlists, stale-claim publication refusal and updated claim-aware recovery. The final v2 image rebuilt with the library portrait-cache alignment and text cleanup. The deployed import, queue and mobile settings screens were checked. Live queue/files and Plex state remained intact.

Fanart live key check for Bruce Springsteen returned six artist thumbnails, 14 backgrounds, nine HD logos, two banners and album artwork. Proposed addition: one responsive artist background with readable text, rather than logos or an image gallery. Not added yet.

MusicBrainz search scores measure query match, not listening popularity. ListenBrainz documents artist top recordings and top release groups by listen count, with MusicBrainz IDs. The actual unauthenticated top-recordings request returned HTTP 401, so a ListenBrainz token is needed before validating that route. Proposed compact Popular songs / Popular albums above the full discography; no popularity feature has been shipped and no additional key has been requested yet. Rankings would reflect ListenBrainz listeners, not worldwide charts.

Concurrency already supports 1 through 6, default 3. Soulseek searches are serialized and each peer permits one transfer at a time, so extra slots help most across different peers/providers. Four is a reasonable next trial before six; bandwidth, large-file memory and provider limits should be observed. This update did not change the user's concurrency setting.

## Recovery

Backups `backups/pre-feedback-queue-20261006/data` and `backups/pre-feedback-queue-v2-20261006/data`; stopped containers `pig-music-preview-before-feedback-queue` and `pig-music-preview-before-feedback-queue-v2`. Keep current SMB and database state authoritative; stop/disconnect the active br0 endpoint before reconnecting a rollback at 192.168.1.203. Compose saves both networks and direct SMB storage. Legacy four containers remain retained.
