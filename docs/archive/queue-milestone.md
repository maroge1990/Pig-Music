> Historical record. This describes an earlier build. For current requirements, deployment and handover, read [blueprint.md](../../blueprint.md). Do not execute old deployment commands without comparing current operations guidance.

# Import queue and appearance milestone

Implemented locally on 5 October 2026.

## Behaviour

Import all includes every unsaved song in the supplied inventory, including compilations; it does not request an artist's full catalogue. Version/release conflicts require a persisted choice: retain the requested release or skip the song. Individual selection remains available. With no unresolved selected conflicts, Import now submits directly.

Submission reads inventory, selection and decisions under a SQLite write transaction. Unresolved conflicts reject the whole batch before any request is inserted. Request identities include artist, track, release, album artist, year, disc/track position and duration; repeated or concurrent submissions reuse existing requests. This is request deduplication, not proof of identical encoded audio or mastering.

Queue entries survive restart and inventory replacement. Waiting requests can be cancelled and explicitly resubmitted later. Existing music files are untouched. Queue entries are not treated as downloaded library music.

All requests currently have `waiting_for_sources` status. No provider worker runs, no transfer has been performed, and no source reliability/quality claim is made. This is the durable submission foundation for acquisition, not complete phase 1. The next work is adapting provider modules, matching/quality validation, bounded retry recovery, staging and approved library export. Existing Music Grabber's acquisition ledger is coupled to its own worker/database; that code has been inspected but not incorporated.

## Appearance

System default follows the device's light/dark preference and changes when that preference changes. Light and Dark override it. The choice is saved per browser/device, independent of shared library settings. Theme initialization happens before the interface renders and updates the browser theme colour. Both themes use approved family tokens. The conflict dialog supports keyboard focus containment and Escape dismissal.

## Verification

- Ten backend tests pass. New cases cover all-or-nothing conflict blocking, skip/request decisions, restart persistence, cancellation/resubmission, simultaneous duplicate submissions and replacement of inventory without loss of queued work.
- TypeScript checking and production bundling pass.
- An isolated browser fixture exercised Import all, one conflict decision and two persisted queue requests. Repeating Import all reused both requests without prompting for the resolved conflict; cancellation changed one request to Cancelled. Real migration selections were not submitted as test downloads.
- Browser checked Light (#FBF8FA canvas), Dark (#15111A canvas), stored appearance after reload and restoration to System default.
- Phone-sized appearance settings and four-item navigation fit without horizontal overflow. Restored System default resolved to Light, matching the browser's reported device preference. No console errors were observed.

Actual provider transfers, Unraid deployment, physical iPhone appearance changes and end-to-end tagging/import remain unverified.
