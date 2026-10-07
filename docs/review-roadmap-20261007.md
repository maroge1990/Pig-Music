# Pig Music: audit verification, independent review and combined roadmap

7 October 2026. The review itself changed no code. A first implementation pass followed on `main`; see [Delivery status](#6-delivery-status-first-implementation-pass). No live service or Unraid state was changed.

> **Correction (implementation pass).** N01 was wrong and is withdrawn. The four files it named import `apiFetch as fetch`, so their writes already carried the session header. A live fixture confirmed that settings writes succeed. The alias has been renamed to `apiFetch` and a test now forbids bare `fetch` outside `api.ts`.

**What was reviewed.** The live release is `first-run-20261007-v1` (runtime `131e464`), built from the unmerged branch `origin/feature/M11-home-and-unraid`. The local checkout (`feature/audit-followup`) is 53 commits behind that branch, so this review reads the M11 tip directly. It also compares Pig-Branding `main` (brand 1.5.1).

**What was run.**
- Frontend `npm ci`, `npm test` (4/4 passed) and the strict production build (passed; main bundle 302 KB, 91 KB gzip, with LegacyTools lazy at 58 KB).
- The backend suite was **not** re-run: this Mac only has Python 3.9. Backend results below are the recorded CI/Unraid evidence (211 tests), not a fresh run.
- No browser session against a live or fixture server was possible for the same reason. UX findings come from source and were cross-checked line by line.

**Which audit is which.**
- **Audit 1** is the cleanup review (`docs/cleanup-review-20261006.md`), actioned as C01 / `cleanup-20261006-v3`.
- **Audit 2** is the brand, artwork and scale audit (`docs/audit-20261006.md`), actioned through A01–A03, B01/B02, audit-followup and the household/native continuation.

---

## 1. Audit 1: were the findings correctly actioned?

**Verdict: yes for the original scope, but two areas have since regressed.** The household/accounts work reintroduced the duplication and raw requests the cleanup removed.

| Finding | Status in live code | Evidence |
| --- | --- | --- |
| Fresh Import had no file input | ✅ Fixed | Input is mounted unconditionally (`LegacyTools.tsx` ~L1170); the personal Import tab has its own input |
| Edition merging | ✅ Fixed | Release-ID edition groups with persisted anchors (`server/library.py` L50–75) |
| Import vs discovery disagreement | ✅ Fixed | Shared `server/matching.py` used by import, catalogue, playlists and recovery |
| Removal cancelled another edition | ✅ Fixed | Recovery uses edition-aware `exclusion_key` / `same_song` |
| Repeated 20.6 MB snapshot reads; playlist cards at 830 ms | ✅ Fixed | `saved_track` uses the in-memory `snapshot_tracks` index; measured 22.5 ms median after delivery |
| Overlapping polling | ✅ Mostly fixed | SSE plus a 15 s fallback that pauses when the tab is hidden. Remaining 3 s loops (popular songs) only run while work is active |
| One typed API client (about 36 raw fetches) | ✅ Fixed | Every request goes through `apiFetch`. Some files hid it behind an `apiFetch as fetch` alias, now renamed and enforced by a test (N01 withdrawn) |
| One interface for saved and discovered content; shared song row | ⚠️ **Regressed** | Two library views (`LibraryView` vs `PersonalLibrary`), two action sets (`SongActions` vs `PersonalSongActions`), two Home mounts and two Appearance controls |
| Durable URLs and back navigation | ⚠️ Works in each shell but **collides between shells** (see N02) | |
| Protected playback branding | ✅ Fixed | Media tokens, protected dark player |
| Dead code / unused TS checks | ✅ Fixed | `noUnusedLocals`/`noUnusedParameters` on; Monochrome prototype removed (`remote.py` now holds only `RemoteAudio`) |
| Artist-job cancellation race | ✅ Fixed | Generation guard (`artist_jobs.py`) |
| NAS-unavailable degraded mode | ✅ Fixed | Marker-gated writes, cached browsing |
| Single deploy/rollback path | ✅ Partly superseded | GHCR, Docker Manager template and `deploy_first_run_unraid.py`. Several generations of helper scripts now coexist (see N08) |

---

## 2. Audit 2: are the findings confirmed?

**Verdict: the findings were accurate.** I re-checked the evidence at the audit commit `6fdccb6` and every sampled claim reproduced:

- base64 `covers` map (`scanner.py` L234)
- edition-blind `cover_key` (`library.py` L139)
- `_cache_covers` skipping existing files
- `no-cache` on artist artwork (`app.py` L464)
- the single global backdrop lock
- 9 px ×27 and 8 px ×13 type
- the `mem_limit: 1g` container limit
- no manifest or touch icon

Nearly all are now actioned. Three are only partial.

| Finding | Confirmed? | Status now |
| --- | --- | --- |
| P0-1/2 snapshot covers and cover identity | ✅ | Done. Content-addressed store; snapshot 928 KB, schema 3, no image map |
| P0-3 cold artwork blocks the UI | ✅ | Done. Local-only image responses; bounded background enrichment |
| P1-1/2 sizes and cache headers | ✅ | Done. WebP 128–1024 px, immutable hashed URLs |
| P1-3 small px type | ✅ | ⚠️ **Partial.** All text is rem with a 0.75 rem floor, but the old 8–11 px sizes were floored rather than mapped to a scale. **130 rules now use 0.75 rem**, with about 20 distinct sizes, including six near-identical display sizes between 2.125 and 2.6875 rem. The recommended 7-role scale aligned to iOS text styles was not adopted |
| P1-4 wordmark, icons, manifest | ✅ | Done for brand 1.4.0. ⚠️ **Now stale:** Pig-Branding is 1.5.1 (haloed square icons, splash motion, single-corner bloom). Pig-Music still ships 1.4.0 tokens and icons |
| P1-5 hand-copied tokens and unapproved colours | ✅ | Done. `generate_brand_tokens.py` plus a drift test; raw hex only in generated `tokens.css`. The drift test compares against a copied 1.4.0 file, so it did not catch the 1.5.x release |
| P1-6 blocking image work | ✅ | Done |
| P1-7 payload and grids | ✅ | Done. gzip with ETag/304; paging at 100 cards instead of windowing (a reasonable, documented deviation) |
| P2-1/2/4/5/8/10 | ✅ | Done |
| P2-3 hero cost / dominant colour | ✅ | Done (pre-blurred layer and colour sidecars) |
| P2-6 radius and spacing drift | ✅ | Done for radius (one px radius left). Spacing left where changing it would alter density, as the audit allowed |
| P2-7 monoliths | ✅ | ⚠️ **Partial.** `main.tsx` is now tiny, but the old app moved wholesale into `LegacyTools.tsx` (1,489 lines). `app.py` (1,091) and `store.py` (1,242) are still large |
| P2-9 branded placeholders | ✅ | Done |
| P3 items | ✅ | Done. The Origin-only protection was replaced by sessions and the `X-Pig-Request` header, which every client write sends |
| F-1 / F-2 native and household foundations | n/a | v1 OpenAPI, cursors, scoped SSE, Swift client package, household accounts. Device gates still open |

---

## 3. Independent review: new findings

Severity: **High** means broken today or a security/data risk; **Med** means notable UX/perf/maintainability cost; **Low** means polish.

| ID | Sev | Finding |
| --- | --- | --- |
| ~~N01~~ | Withdrawn | Raw `fetch` writes looked unauthenticated, but they were `apiFetch` behind an import alias. Alias renamed; a test forbids bare `fetch` |
| **N02** | High (UX) | **System tools hijacks its own navigation.** `AccountsShell` and `LegacyTools` both listen to `hashchange` on `#/library…`, `#/search…` and `#/home`. Inside System tools, clicking an album, artist, "Your library", "Search & discover", Home or a discovered artist writes one of those hashes. The outer shell then switches to the *personal* Library, unmounts System tools and tries to open a household ID in the personal library. Only Import, Queue and Settings stay inside |
| **N03** | High (UX) | **Two complete apps for the administrator** (see section 4) |
| N04 | Med | **Main is not the source of truth.** Thirteen stacked draft PRs (#1–#13) are unmerged; `main` has only the initial build and the first audit. The live image is built from a feature branch, which makes rollback, review and onboarding fragile |
| N05 | Med | **Member artwork authorization costs O(library) per image.** For every member image request, `security.py` L135–160 calls `projection()`. That takes `library_lock`, opens SQLite and JSON-serialises settings, then linearly scans every artist, album and track URL. A 100-tile page means 100 scans, and tiles stall while a refresh holds the lock. Precompute an allowed-path set per projection signature |
| N06 | Med | **The brand drift gate compares against a stale copy.** Pig-Music pins 1.4.0 while Pig-Branding moved to 1.5.1 the same day. Pin a Pig-Branding version or commit, and make the check report "newer approved version available" |
| N07 | Med | **The personal shell's navigation is weak.** It is a wrapping row of text buttons (Home, Library, Account, System tools, Sign out) with no icons, no active state (`aria-current` is absent everywhere) and no phone bottom bar. Search, Requests and Import are hidden as tabs inside Library. Playlist rename/delete forms always show on the playlist page |
| N08 | Med | **Release tooling and recovery artifacts accumulate.** There are `deploy_unraid.py`, `deploy_first_run_unraid.py`, `adopt_unraid_template.py` and `package_unraid_preview.py`, plus seven generations of rollback containers and backups on Unraid. Define one current release path and a retention policy |
| N09 | Low | Stale code and labels: the comment "Personal media/library projection lands in M03" and the error code `personal_libraries_pending` (`security.py` L123, L168). The legacy breadcrumb says "Pig Music"; the product is "PigMusic" |
| N10 | Low | Personal library has no **Songs** view (Artists, Albums, Playlists, Favourites only), so there's no "shuffle my library" |
| N11 | Low | The local dev environment can't run the backend (Python 3.9 only). Add a pinned `uv`/`.python-version` bootstrap so local verification matches CI |
| **N13** | High | *Found during implementation.* **The personal library ETag wasn't bound to the person.** `user_library.projection` hashed library revision, membership revision and settings, so two people with equal membership counters got identical ETags. On a shared browser the second person's revalidation returned 304 and showed the previous person's library. This was reproduced in a fixture (member saw the owner's 12 songs instead of 4), fixed by adding the user to the signature, and covered by a regression test |
| **N14** | Med | *Found during implementation.* FastAPI 0.142 wraps included routers lazily, so `app.routes` omits them. The startup `audit_routes` guard check and `test_every_api_route_is_anonymous_denied…` covered only 52 of 132 API routes. The routes were still guarded at runtime, but nothing proved it. Fixed with `api_routes()` |
| **N15** | High | *Found during implementation.* **Following an artist downloaded its whole back catalogue.** Turning monitoring on without a request let the background loop treat the artist as due and run a full request. Members' "Follow new albums" and the owner's "Monitor new releases" both queued every existing album, and each daily check reset the done list. Following now records existing release groups as a baseline, periodic checks keep the done list, and an explicit request still fetches everything. Reproduced in a fixture (a member got 11 unwanted requests); covered by two tests |
| N12 | Gate | Owner account creation through the first-run form was still outstanding at the last handover. Physical iPhone/Watch, cellular Tailscale and VoiceOver gates (V01/S00) remain open |

---

## 4. Admin vs member experience: what's wrong and the proposed structure

### Today

```
Member:  [Home] [Library] [Account] [Sign out]
           Library tabs: Artists · Albums · Playlists · Favourites · Search · Requests · Import

Owner:   [Home] [Library] [Account] [System tools] [Sign out]
           Account  → also People · Unassigned music · Account activity (admin-only)
           System tools → the ENTIRE pre-accounts app, nested inside the header:
               own sidebar + top bar + search box + phone bottom nav
               Home · Your library · Search & discover · Import library · Download queue · System & settings
```

The owner therefore sees:
- **two** Homes and **two** libraries, where "Your library" means *personal* in one shell and *entire server* in the other
- **two** search boxes, **two** imports (personal playlists vs whole-library Apple XML migration) and **two** request/queue views
- **two** Appearance settings and **two** settings areas, with admin functions split between Account and System tools
- **two** sets of navigation chrome stacked on each other

Because of N02, half the inner app bounces back to the outer one. This happened because the accounts work wrapped the legacy single-user app (`LegacyTools`) instead of migrating its owner-only functions.

### Target: one app; the owner gets one extra section

```
Everyone:  Home · Search · Library · Account          (+ Admin, owner only, always last)
Phone:     bottom tab bar with the same 4 (5 for the owner) items, icons and active state
```

| Section | Contents |
| --- | --- |
| **Home** | Popular this week, Recommended for you, Recently added (F-4), Continue listening |
| **Search** | One search: In your library → On the server (add instantly) → Discover (catalogue, request). Artist/release pages as today |
| **Library** | Artists · Albums · Songs (new) · Playlists · Favourites. "Import playlist" is a button on Playlists, not a tab. "My requests" is a small status chip/panel (Library header or Account), not a peer tab |
| **Account** | Appearance (the only one), password, devices, my quality, my Plex |
| **Admin** (owner) | **Overview**: health, storage, Soulseek, Plex server, recent activity · **Downloads**: full queue and download settings · **People**: members, setup codes, activity · **Server library**: scan, Unassigned inbox, files needing attention, organisation review, removed music/restore · **Integrations**: Fanart, ListenBrainz, remote playback, Soulseek connection · **Library migration**: whole-library Apple XML inventory import |

**Design rules**
1. The owner browses music exactly like a member. Owner-only actions appear **in context**, in the same album/artist/song overflow menu, gated by role: "Remove from server…", "Server quality…", "Re-categorise", "Fix artwork". There is no separate "household library" browser. Search's "On the server" section and Admin › Unassigned cover discovery of files outside the owner's own library.
   - **Admin additions always go at the bottom.** Within any base section (Home, Search, Library, Account) and any menu, owner-only options come after everything a member sees, under a divider or "Admin" label. They never interleave, reorder or replace member items. The owner's screens should match a member's from the top down, with the extras only at the end:
     - an album or song menu ends with the server actions
     - a Library page ends with an "Admin: server library" panel (scan, Unassigned count)
     - Account ends with links into the Admin section
   - The navigation follows the same rule: Admin is the last item in the bar, after Account. People, Unassigned music and Account activity already sit at the bottom of Account, which fits this rule. Move them into Admin and leave a link at the bottom of Account.
2. One router with namespaced hashes (`#/home`, `#/search/...`, `#/library/...`, `#/account`, `#/admin/<section>`). One navigation component sets `aria-current`.
3. Retire `LegacyTools`, `LibraryView`, `SongActions`, the second `Home` mount and the Appearance control in `SystemView`. Move `SystemView`, `QueueView`, `Organisation`, `Recovery`, `RemovedMusic`, `LibraryScan` and `MediaSettings` under `#/admin/*`, lazy-loaded, using `api()` only.
4. Server: expose owner routes as `/api/v1/admin/*` in the OpenAPI contract, so the Swift app can later host an Admin tab. Keep the legacy routes as aliases for one release, then remove them.

---

## 5. Combined roadmap

IDs continue the blueprint's scheme; new ones are prefixed **U** (UX), **Q** (quality) and **R** (release). Fold this table into `blueprint.md` and retire it here, since the blueprint is the single running roadmap.

### Now: fix before members are invited

| ID | Work | Source | Gate |
| --- | --- | --- | --- |
| **Q01** | Rename the `apiFetch as fetch` aliases; test-ban bare `fetch` outside `api.ts` | N01 (withdrawn), Audit 1 §3 | Structure test passes |
| **Q02** | Authenticated test harness: make the default fixture sign in as owner and as member, and keep `LEGACY_API` only for a few legacy-route tests. Add a Playwright smoke run (owner and member) to CI | N01, N02 | CI fails on a 403 from any UI action |
| **Q03** | Interim navigation fix if U01 can't land quickly: namespace legacy routes under `#/admin/…` so System tools stops ejecting the admin | N02 | Album/artist/search clicks stay inside tools |
| **R01** | Owner completes first-run setup. Then run the authenticated production acceptance (owner + one member) | N12 | Recorded in the blueprint |

### Next: one experience

| ID | Work | Source | Gate |
| --- | --- | --- | --- |
| **U01** | Unified IA per section 4: shared shell, bottom tab bar, Admin section, contextual owner actions, retire `LegacyTools`. Move owner APIs to `/api/v1/admin` | N03, N07, Audit 1 §4, Audit 2 P2-7 | Owner and member journeys (desktop, 390 px, 320 px, 200% text); no duplicate views; bundle check. Owner screens are a member's screens plus extras at the end: compare owner and member side by side for each base section and menu; admin options appear only after the member items |
| **U02** | Library: add a Songs view and shuffle-all; put playlist rename/delete in an overflow menu; turn requests into a status panel | N07, N10 | Phone review |
| **U03** | Type scale: replace about 20 sizes and 130 × 0.75 rem with the 7 iOS-aligned roles as tokens. Generate the same roles for Swift | Audit 2 P1-3 | 200% text and VoiceOver on a physical iPhone (V01) |
| **B03** | Adopt Pig family 1.5.1: haloed icons, manifest and touch icons, splash halo (reduced-motion static), single top-leading corner bloom on canvases. Pin the brand version in the drift gate | N06, Audit 2 P1-4/F-3 | Contrast ≥ 4.5:1 checked in both themes |
| **Q04** | Member artwork authorization via a precomputed path set per projection signature, without `library_lock` on image requests | N05 | 50k-track member grid benchmark; tiles don't stall during refresh |
| **R02** | Merge the stacked PRs into `main` in order, then tag releases from `main`. Point the Docker Manager template at tags/digests from `main` | N04 | `main` equals the live runtime source |
| **R03** | One release script, plus a retention policy for rollback containers and backups (for example the last two releases plus the pre-account baseline) | N08 | Documented in `operations.md` |

### Then: household depth and devices (existing roadmap, re-ordered)

| ID | Work | Status / gate |
| --- | --- | --- |
| V01 / S00 | Physical iPhone (HTTPS over cellular Tailscale, VoiceOver, revocation during playback), plus Sideloadly iPhone/Watch install and refresh | Owner's devices required |
| H03 | Overlapping editions/qualities across members: confirm the "highest requested quality" UX in the Admin › Downloads view | Mostly built in M04; needs owner UX review |
| F-4 | Recently added shelf; artwork fix-up tool (display-only, per edition) under the owner's contextual actions; per-user listening history powering Home | After U01 |
| F-3 | Now-playing accent from the dominant colour, constrained to the protected player | Needs brand approval |
| P01 | Production iPhone app on the v1 contract (generated client exists). Mirror the IA: Home/Search/Library/Account (+Admin) | After U01 freezes the IA and `/v1/admin` |
| M10 / P02 | Device copies and Watch offline playback | After P01 and the Watch feasibility proof |
| S01 / S02 | Shazam inbox, then direct recognition | Phase 2 investigation |
| R01-remote | Remote playback: keep, replace or remove based on measured reliability | Owner decision |
| Q05 | Continue splitting `app.py` and `store.py` into routers/services as U01 and P01 touch them (not as a standalone rewrite) | Opportunistic |
| Q06 | Local dev bootstrap (`uv`, Python ≥ 3.12) so backend tests run on the Mac | N11 |

---

## 6. Delivery status: first implementation pass

On `main` (fast-forwarded to the live M11 source first, which delivers R02's "main equals live source" for this checkout). Not pushed or deployed.

| ID | Status | Notes |
| --- | --- | --- |
| R02 | ✅ Locally | Local `main` fast-forwarded to `origin/feature/M11-home-and-unraid`. Pushing `main` triggers the GHCR image workflow; it needs owner approval |
| Q01 | ✅ | Alias renamed in 15 files; `client/tests/structure.test.mjs` forbids bare `fetch` and `apiFetch` aliases |
| N13 | ✅ | Per-person library validators; `test_library_validators_are_bound_to_the_person` |
| Q03 / U01 | ✅ | One hash router in `AppShell` (a test forbids `hashchange` listeners elsewhere). Nav: Home · Search · Library · Account, then Admin for the owner, with an icon bar at the bottom on phones. `LegacyTools`, `LibraryView`, `SearchPanel`, `LibraryCards`, legacy `Playlists` and `ArtistDiscography` removed. Admin has Overview, Downloads, People, Server library, Integrations and Library migration (lazy 29 KB chunk, down from 58 KB). Owner additions sit at the bottom: album/artist "Admin · server settings" panels, an "Admin" group at the end of the song menu, and Admin shortcuts at the end of Library and Account. Sign out moved to the bottom of Account. Old `#/queue`, `#/system` and `#/migration` links redirect into Admin |
| U02 | ✅ Partly | Songs tab (server-paged, Play, Shuffle all sampled from up to 1,000 songs); playlist rename/delete in a collapsed "Playlist options"; Import moved to the bottom of Playlists; search layout and empty headings tidied |
| Q04 | ✅ | `UserLibrary.artwork_access` indexes allowed artwork once per projection revision; both the guard and the image route use dictionary/set lookups instead of scanning |
| B03 | ✅ | Pig family 1.5.1: haloed web and Apple icons, tokens, vendored `pig-radiance.css` (hash-verified in provenance and by test), top-left corner bloom on the app canvas, splash halo on the loading screen |
| N09 | ✅ | Stale M03 comment and `personal_libraries_pending` code replaced (`owner_only`) |
| Q02 | ✅ Mostly | `api_routes()` expands FastAPI 0.142's lazy included routers. The startup guard audit and the anonymous-denial sweep had silently covered only 52 of 132 API routes (N14). `test_ui_contract.py` checks that all 61 API paths the browser calls exist, and drives the Admin and shared sections through real web sessions for the owner and a member. Remaining: a Playwright browser smoke run, which needs a browser download |
| U03 | ✅ | Seven roles for web (rem tokens) and Swift (`PigType`, Dynamic Type styles), with a test against literal sizes. 51 legacy-only selectors pruned (CSS 55.6 KB to 49.0 KB). Personal and admin headings use the roles. "System" appearance follows the device live again |
| SongActions vs PersonalSongActions | ✅ | Legacy `SongActions`, `SongControls` and `membership.ts` removed with the dead non-personal catalogue mode. Owner artist monitoring is an Admin panel at the bottom of discovered artists. Favourite probes no longer clear the read cache |
| R03 | ✅ | `scripts/deploy_release.py`: routine Docker Manager account release (preflight, quiesce via SQLite, stopped backup, old-image baseline, new-image migration check, recreate, verify, full rollback). `--retention N` reports and never deletes. Tested against a fake host. Image tests read source files through `/source` in CI and on Unraid |
| F-4 / U02 | ✅ | "Recently added" Home shelf (`/api/v1/home/recent`, excluding bootstrap attribution); album Play/Shuffle; heading focus on navigation; Home spacing |
| Q06 | ✅ | uv bootstrap documented; `.python-version` pins 3.14 |
| U01 step 4 | ◻ Next | Owner APIs under `/api/v1/admin` in the OpenAPI contract, ahead of a native Admin tab |
| R01, V01/S00 | Owner | Require the owner, devices or Unraid access |

Verification (first pass): 213 backend tests (Python 3.14, local), 6 frontend tests, strict build, Prettier and Black checks. Browser fixture with synthetic music and generated credentials, owner and member, desktop and 375 px:
- navigation and the Admin sections
- album, song and library owner extras appear only for the owner, at the bottom
- the member sees no Admin, and `#/admin` falls back to Home
- download and media settings saves succeed through the real security guard
- a shared-browser account switch now shows the correct library

Second pass: 221 backend tests, 7 frontend tests, strict build, Black, Prettier, brand and OpenAPI drift checks, and a Swift `PigBrand` build. Browser fixture re-checked:
- owner and member in light and dark, at desktop and 375 px
- Admin pages after the CSS prune
- the Songs tab, album Play (audio actually played through a signed URL) and Recently added

Third pass:
- **One Search:** the query lives in the URL. Results run library artists, albums and songs, then music on the server (add instantly), then the catalogue, and the catalogue degrades gracefully when unavailable. The drill-down explorer is gone, and following is a toggle on every discovered artist page.
- **N15 follow fix.**
- **Library polish:** playlist rows with counts, Favourites shown inline, plain-language request statuses with progress and errors, consistent form buttons, and a full-height canvas bloom.
- **Admin overview:** an at-a-glance row (queued, failed, awaiting an owner, files needing attention, people).

223 backend and 7 frontend tests pass.
