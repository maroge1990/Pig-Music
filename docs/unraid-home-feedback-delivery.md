# Native Unraid management and testing feedback

7 October 2026. Pig Music is now **PigMusic**, managed by Unraid Docker Manager with `/boot/config/plugins/dockerMan/templates-user/my-PigMusic.xml`. The repository is `ghcr.io/maroge1990/pig-music`; Support and Project link to the correct private GitHub repository. The approved mark is installed locally because anonymous GitHub image URLs cannot read a private repository. The original Compose file is retired, so it does not compete with Docker Manager. The source template is `unraid/PigMusic.xml`.

## Live management conversion

This conversion did not upgrade the application. It uses the exact existing verified image under `sha-1f21118b0448f7dce0cedb694a3067da132fd7ab` (digest `17f42b85b47f4404988f849c26005a66a2c3051b85671c821dffcb3f01e7a439`). Docker Manager ownership, installed template, autostart, UID 99:100, read-only root, capability restrictions, 1 GB memory, existing appdata/NAS mounts and both fixed network addresses passed acceptance. Private HTTPS has a valid certificate and reports 1,395 tracks, no read failures, available storage and enabled downloads.

Rollback container: `pig-music-preview-before-dockerman-20261007-v1`. Stopped appdata/Compose/autostart backup: `/mnt/user/appdata/pig-music-preview/backups/pre-dockerman-20261007-v1`. Conversion preflight and execution are in `scripts/adopt_unraid_template.py`; this narrowly allows the existing image only and is not an account-migration tool. It refuses active transfers and keeps original download settings. Advanced parameters encode both existing networks. The repository tag stays pinned while real owner setup is pending; this avoids an automatic update to an account release that cannot yet accept sign-in. Do not run the retired Compose file.

## Requested interface changes in the candidate

- Player transport and custom actions share the desktop control row. The seek slider spans below, with responsive phone placement and protected media colours retained.
- Playlist selection uses a native top-layer popover placed beside its icon, with existing playlists and New playlist at the bottom. New playlist opens a centred naming dialog; creating it also adds the selected song. Favourites remain immediate toggles. Both personal and administrator views use the picker.
- Playlist pages have Play and Fisher–Yates Shuffle, album artwork, artist and album navigation, and no add-to-playlist control inside the playlist. Existing playlist management and requesting unavailable songs remain supported.
- Saved artist pages contain only the personal/server library projection, use the circle portrait and link the artist name to full discovery. Full artist pages retain the hero, popular songs and the complete paged album catalogue. Album cards scale across web width. Known ListenBrainz ranks come first; remaining albums are chronological. If ListenBrainz is unavailable, all albums are chronological. Singles/EPs/other releases are a subsequent screen opened from below the album list, with no Albums tab there.
- Search identifies saved results as Artist and omits imported-but-unsaved hints. Members retain playlist imports in their Import section.
- Home has distinct weekly popular and recommended artist/album/song shelves. Public ListenBrainz weekly statistics supply popularity; ListenBrainz radio supplies similar artists seeded only from the signed-in person's saved artists, and MusicBrainz resolves recommended albums/recordings. The current seed budget is three saved artists and up to four related artists. Similar-artist recommendations do not require a separate ListenBrainz user account and do not submit private listening events. Recommendations are based on artist similarity, not album audio analysis.

## Providers and fallbacks

Provider replies are bounded, cached for an hour, and errors retry after a minute. Existing stale feeds remain labelled unavailable. Popular and recommended shelves load independently; discovery failure cannot block the saved library. Recommendations have a 25-second request ceiling and reuse public catalogue caches. Empty feeds have explicit text rather than fabricated charts or unrelated recommendations.

Actual responses were checked from Unraid for weekly artists, release groups, recordings and artist radio. This exposed two differences that were fixed: statistics use `track_name` for songs, and artist radio requires `pop_begin`/`pop_end`. Reference APIs: [ListenBrainz statistics](https://listenbrainz.readthedocs.io/en/latest/users/api/statistics.html), [ListenBrainz radio](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html#get--1-lb-radio-artist-(seed_artist_mbid)), [MusicBrainz API](https://musicbrainz.org/doc/MusicBrainz_API).

## Acceptance and remaining gates

The local suite passed **208 backend tests**; four frontend regressions and the strict production build passed. Backend checks include feed ID validation/caching, stale failure handling and use of personal recommendation seeds without submitting listens, alongside the existing isolation and migration suite. The v1 OpenAPI and Swift schema copies are regenerated. The published candidate also passed GitHub dependency, container-image and native-client checks at revision `2a2e0ae`.

Normal in-app browser access recovered on the owner-requested retry after the earlier policy lookup failure. No browser security settings were weakened. Local visual verification used disposable member accounts and controlled provider data, not the production library:

- Desktop and 390/320-pixel layouts: compact song artwork, full-width personal player, aligned transport/actions and no horizontal overflow at 320 pixels.
- Icon-anchored picker: existing playlist selection, New playlist centred overlay, create-and-add success, initial text-field focus and Escape/close focus restoration.
- Playlist detail: Play/Shuffle, artwork placeholders, no row-level playlist picker. The separate player still allows adding its current song.
- Two-minute silent WAV fixture: playback progressed, next-track navigation, pause, mute and favourite state updates worked. The contract fixture now writes valid disposable WAV files rather than missing MP3 paths.
- Saved artist: circle presentation and artist-name navigation to the full catalogue. Full artist: twelve albums in supplied popularity order, compact desktop cards and a separate Singles/EPs/Other screen; Singles and EP filters verified.
- Home: populated artist/album/song shelves and artist navigation using explicitly synthetic provider responses. Earlier normal-provider loading/unavailable states were observed. This does not claim end-to-end real-provider discovery acceptance or real artwork availability on this Mac.

Visual testing found and corrected growing personal row covers, inherited sidebar/mobile offsets on the personal player, naming-dialog focus, and album title/date text running together. Screenshots are retained in `.localdata/browser-proof/` (desktop-player, phone-player, phone-player-picker, saved-artist, home and album-grid). Four frontend regressions, strict production build and formatting passed after these corrections. The preview also logged duplicate Home keys from repeated provider IDs; feeds now deduplicate by catalogue identity, and all three Home backend tests pass with duplicate coverage. Physical-device tests, full administrator-view visual acceptance and real-provider production acceptance remain separate gates.

The interface/Home candidate is not live yet. Mark's private interactive owner setup and a fresh-state authenticated migration remain prerequisites for upgrading from the legacy live image. The prepared offline helper remains `pig-music-household-setup`; its password command is unchanged. The future cutover must target **PigMusic**, preserve fresh live data, retain complete appdata rollback and leave the native Unraid template as the sole management source. Physical iPhone/Watch feasibility gates are unchanged.
