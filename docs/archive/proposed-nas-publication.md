> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Direct SMB publication — 6 October 2026

The user approved direct SMB storage and corrected the earlier dedicated `Pig Music/` destination. That earlier proposal is superseded.

The deployed image is `pig-music:preview-20261006-direct-smb-v2`, ID `sha256:cda33ec196d235cfa95d5a40c9246fb976f785990ef84ce711423f5b5d816321`. Pig Music remains at http://192.168.1.203:8765.

New transfers use `/library/.pig-music-work/` on the SMB share, with a Plex exclusion file. This contains incomplete source/validation files only; completed music is published into the existing artist/album structure. There is no separate appdata music store. Small database, credentials and recovery journals remain in appdata. The embedded Soulseek engine also downloads onto SMB. Its copied source file is removed after successful transfer into validation.

Folder matching uses album artist, album, year and embedded release identity where available. Exactly one matching folder preserves its existing spelling. Multiple candidates defer publication for a destination decision. New folders follow `Artist/Album (year)/Artist - Album - NN - Title.ext`; subsequent discs use a disc/track number. A same-extension quality replacement may receive a short content suffix to coexist with its original until verification. Unknown different-content destination collisions defer rather than overwrite.

Validated same-filesystem publication uses hard links without another audio copy. Existing appdata downloads were copied, hash-checked and committed before their appdata originals were removed. Publication requests a Plex library refresh, and playlist sync retries as indexing finishes. No transcoding is performed. Explicit quality replacement retains the original until the new source is verified, then puts it in recoverable excluded trash. Existing library folders and tags are not generally rewritten.

## Verified live

- Disposable SMB fixture as user 99:100: write, atomic hard-link publication and original recovery all passed; fixture removed.
- All 13 previously completed downloads published in normal artist folders; every destination hash matches the validated record.
- All 13 destination paths indexed in Plex; zero remaining MP3s in the main appdata audio store or NAS validation-library area.
- Favourites playlist sync remains connected. Per-user Plex ownership and credentials are explicitly deferred until the core flow is complete; the current integration uses the server owner's account.
- All 76 backend tests passed in the final Linux image, including direct SMB storage, preserving existing folder spelling, no second same-NAS audio copy, wrong-mount refusal and replacement recovery.

No additional real source acquisition was submitted during this storage cutover; fresh downloads and real upgrade/downgrade flows remain live acceptance cases. General restore UI and per-user playlists remain outstanding. The legacy four containers have not been removed.

## Recovery

Before the first write cutover: `/mnt/user/appdata/pig-music-preview/backups/pre-direct-smb-20261006/data`; container `pig-music-preview-before-direct-smb` (library-v5). Before the startup-fix image: `backups/pre-direct-smb-v2-20261006/data`; container `pig-music-preview-before-direct-smb-v2`.

Stopped rollback containers have their `br0` attachment disconnected to release the approved static address. Stop/disconnect the active container before reconnecting a rollback at 192.168.1.203. Never run both on shared data. Published destinations are part of authoritative live data; do not restore an older snapshot blindly. Older preview images require their matching storage/engine settings. Current Compose includes the writable SMB mount, `PIG_MUSIC_DOWNLOAD_ROOT=/library/.pig-music-work`, and both network attachments.
