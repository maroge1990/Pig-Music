> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Inline popular-song actions — 6 October 2026

Current image: `pig-music:preview-20261006-popular-controls-v2`; backup `/mnt/user/appdata/pig-music-preview/backups/pre-popular-controls-v2-20261006/data`; stopped rollback `pig-music-preview-before-popular-controls-v2`. Queue preserved (24 entries).

Popular-song rows now use the album track play/download controls without opening a release view. Each action resolves the exact ListenBrainz recording MBID against the supplied release, then uses the existing catalogue playback or single-track request endpoint with the matched edition track ID. No title-only fallback and no entire-album request. Preferred quality continues through existing album/artist/system inheritance. The five visible rows refresh saved/download status every three seconds; requests abort when paging or unmounting, and refreshes do not overlap. Saved songs show a disabled tick; queued, in-progress, selection and failed states follow album controls. Popular albums still open their release view.

Frontend build passed locally and in the image. Mobile browser verified inline buttons and opening the existing player without changing the artist route. Artwork remains 40px (cover flex overridden for the new catalogue row). No new live acquisition was submitted during verification. Existing backend tests are unchanged (84 passed in preceding deployment).

---

# Popularity paging and mobile scroll follow-up — 6 October 2026

Current image: `pig-music:preview-20261006-popular-paging`. Backup: `/mnt/user/appdata/pig-music-preview/backups/pre-popular-paging-20261006/data`. Stopped rollback: `pig-music-preview-before-popular-paging` with br0 disconnected. All 24 queue entries and 1,394 tracks retained.

Popularity returns up to 20 recordings and 10 album release groups ranked by listen count. Independently controlled song pages show five rows; album pages show three tiles. Right-aligned controls include accessible names, visible ranges and disabled boundary buttons. Full discography now follows the popular sections. Both remain hidden without a token or results.

Live verification: Chappell Roan returned 20 songs / 3 albums, Coldplay 20 / 10, Arcade Fire 20 / 10. Earlier Chappell and Arcade Fire responses were empty, but fresh authenticated provider requests and a direct provider run succeeded; the exact earlier failure could not be reproduced. Previously one failed endpoint hid both sections for five minutes. Endpoint failures are now isolated, unsuccessful responses retry after one minute, malformed entries are skipped, timeouts allow 25 seconds, and cached artist results bypass the global request lock. The cache namespace changed for the expanded result counts.

Mobile scrolling crossfades a sharp photo over a fixed pre-blurred layer and fades their shared container. It no longer changes a blur filter or parallax transform on each mobile scroll frame. Geometry is measured outside the scroll loop. Desktop retains its progressive blur/parallax, and reduced-motion preferences retain a simple fade. Browser verification confirmed mobile parent filter/transform `none`, fixed soft-layer blur 12px and changing opacity; physical iPhone smoothness still needs user confirmation.

84 backend tests passed in the exact deployed Linux image and frontend build passed. New regressions cover 20/10 limits, rank ordering, malformed entries and partial failure. Phone browser checked 1–5, 6–10, 11–15, 16–20 song pages and 1–3, 4–6, 7–9, 10 album pages, disabled end controls, backward paging and no horizontal overflow. Heading order was Popular songs, Popular albums, Full discography. Temporary viewport restored and test tab closed.

---

# Artist scroll artwork update — 6 October 2026

Current image: `pig-music:preview-20261006-artist-scroll`. Authoritative data, 24 queue entries and 1,394 tracks retained. Backup: `/mnt/user/appdata/pig-music-preview/backups/pre-artist-scroll-20261006/data`. Stopped rollback container: `pig-music-preview-before-artist-scroll` (br0 disconnected).

The user's Apple Music screenshots informed a larger artist photograph, a gradient into the current theme canvas, and progressive scroll blur/fade. Existing Pig typography, identity and semantic palette remain in place. Desktop photo height is at least 460px; phone uses 420px with full content width. Missing Fanart images retain the existing portrait layout. Scrolling uses passive listeners and requestAnimationFrame; listeners and pending frames are cleaned up on unmount. Reduced-motion preferences disable blur and parallax. Text remains independent of the fading image.

82 tests passed in the exact Linux image; frontend TypeScript/Vite build passed. Live 390×844 phone verification showed no horizontal overflow. At scroll 380px the image had opacity 0.403 and blur 10.75px; further scrolling produced opacity 0. Popular-song navigation loaded the real Born in the U.S.A. release. Desktop layout also inspected. Temporary viewport reset and agent tab closed. New physical iPhone and reduced-motion device testing remain with the user.

---

# Optional ListenBrainz and Fanart artist pages — 6 October 2026

Deployed image `pig-music:preview-20261006-artist-enrichment`, ID `sha256:f1b278e764887985ca207f9006e65dfa8d60cc71ad336c29e6158074b370e5a5`. App: http://192.168.1.203:8765. Current authoritative data retained 24 completed requests and 1,394 tracks. Plex playlist sync remains connected.

## ListenBrainz

Settings → Artwork & playback now accepts a ListenBrainz user token, sourced from https://listenbrainz.org/settings/. It is persisted privately alongside the existing media settings with owner-only file permissions. Public settings return only `listenbrainz_configured`. Blank submission preserves an existing token; the separate Remove ListenBrainz token action clears it and preserves the Fanart key. No token is echoed to the browser or public errors.

Without a configured token, artist popularity makes no provider calls and has no UI heading, placeholder or enable prompt. The live unconfigured API returned `enabled:false` and empty lists; the deployed artist DOM contained no popularity section. Unavailable, invalid-auth and empty responses also produce no panels.

When configured and data is available, the artist discography shows up to five popular songs and three popular albums ahead of the Albums/Single/EP/Other selector. Song rows open their supplied release through the existing catalogue workflow; album tiles open their release group and recommended edition. All acquisition still uses server metadata and existing validation. No automatic downloads or listens submission is added.

The server uses the documented artist popularity GET endpoints with `Authorization: Token ...`, a one-second minimum request spacing, 12-second timeouts, bounded responses, validated MusicBrainz IDs, artist filtering for recordings and deduplication. Positive results cache for 24 hours; unsuccessful results retry after five minutes. Cache identity includes a one-way token fingerprint, so replacing/removing a token cannot surface old account results. Rankings are by ListenBrainz listen count, not worldwide charts.

**Update, 6 October:** Authenticated live requests succeeded after the user entered a token. Bruce Springsteen returns five popular songs and three popular albums. His provider responses contain 3,170 recordings (2.4 MB) and 696 release groups (3.3 MB), exceeding the original 2 MB bound. The bounded limit is now 16 MB, with a versioned cache key to bypass earlier negative results. A regression test covers both large responses. Reference: https://listenbrainz.readthedocs.io/en/latest/users/api/popularity.html and https://listenbrainz.readthedocs.io/en/latest/users/api/index.html.

## Fanart and branding

The saved-artist page gains a static Fanart background above its existing portrait, name and library details. Images retain their natural colours; text is placed on the opaque theme surface. The existing Pig mark, semantic pink controls, typography and light/dark palette are preserved. There are no new colours, slogans, animation, logos or image-selection controls. Missing backgrounds keep the normal artist layout with no placeholder.

Implementation follows `C:/Users/markr/GitHub/Pig-Branding/06-family-brand-standard.md` (approved 2 October 2026): theme CSS variables, opaque readable surfaces, 16px hero framing, established spacing vocabulary, static imagery and no rays. Backgrounds are display-only and never change file tags or Plex artwork. Explicit Fanart configuration and the existing Artist portraits toggle govern use. Highest-liked background is fetched from the trusted Fanart asset host, bounded to 5MB and 20M decoded pixels, saved as a landscape JPEG up to 1600 by 900 and cached privately. Negative requests retry after five minutes; artists with no background retry after one day. Library startup preloads backgrounds alongside portraits.

## Verification and recovery

81 backend tests passed in the exact Linux image as user 99:100 with networking disabled. New tests cover private token preservation/removal, zero provider requests while unconfigured, authenticated header/cache handling, excluding mismatched artist recordings, quiet auth failure, landscape resizing and untrusted asset rejection. Provider tests disable unrelated startup warming so their mock transports cannot race background requests.

The actual Bruce Springsteen Fanart background loaded at 1600 by 900. Desktop and 390 by 844 phone views were inspected in light and dark mode: no horizontal overflow, readable text on the protected surface, no unconfigured popularity panel. The settings token input was verified. Temporary dark appearance and viewport overrides were restored; agent test tab closed.

Backup: `/mnt/user/appdata/pig-music-preview/backups/pre-artist-enrichment-20261006/data`; stopped rollback: `pig-music-preview-before-artist-enrichment`. Current Compose keeps both network attachments and direct SMB storage. Stop/disconnect the active br0 endpoint before reconnecting a rollback to 192.168.1.203; never run both against shared data. Retain authoritative SMB/database state rather than blindly restoring old data.
