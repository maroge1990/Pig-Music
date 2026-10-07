# M04 implementation notes

7 October 2026. Planned next step after M03; no shared-file deletion has been enabled for members.

The existing `Recovery.remove/restore` provides mount, path and SHA-256 checks, durable removal intent, claim cancellation, recoverable trash and Plex refresh. It currently has a controller lock and removes a household track. The personal layer must inspect other active memberships and pending request beneficiaries before invoking that path. Playlist/favourite/history references do not retain files.

Implementation sequence:

1. Add shared per-track coordination and a durable removal/undo record. Apply the same coordination to membership addition, request attachment, publication, recovery and quality replacement. Do not hold `library_lock` and then acquire `covers.lock`: refresh/pruning take them in the opposite order. Record a removal intent before filesystem work so restart recovery cannot silently regrant or delete a newly shared file.
2. Add a personal removal preview and confirmation operation. Recheck the affected tracks and sharing inside the mutation, remove only the caller's memberships, retain other members' files and pending acquisitions, and preserve the existing owner-only physical-removal route. Record the original memberships for restore and bound personal undo to 30 seconds.
3. Add per-user quality preferences and compute the highest required quality for every shared track; scope preferences without changing physical identity. Preserve the existing replacement claim and original-file checks.
4. Add an owner-only Unassigned inbox for newly scanned files and explicit scan assignment. Prevent restart/bootstrap from attributing later external scans automatically. Add assignment to the scoped API before account screens are exposed.

Required acceptance includes a partly shared album, a pending request from another person, playlist-only references, add/remove and publish/remove races, replacement cancellation, stale confirmations, interrupted removal/restore, exact membership restoration, undo expiration and an unavailable/changed NAS mount. Use disposable filesystem fixtures and a stopped production backup. M04 deployment remains part of the later complete account cutover; do not enable this partial branch on the live household service.

Follow-up review from the removal checkpoint: scanner reuse preserves a cached track ID, but a fresh `inspect_file` after organisation can derive an ID from the new relative path. Test both cached and changed-file scans after rename and undo before enabling assignment. Personal quality decisions must include current members and active request beneficiaries, including changes arriving during an in-flight replacement. When preferred formats have equal quality rank, choose deterministically and preserve the validated-source/no-transcode rule.
