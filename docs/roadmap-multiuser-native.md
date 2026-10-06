# Pig Music delivery roadmap: multi-user security, iOS and Apple Watch

Prepared 6 October 2026 (Australia/Sydney). Status: **proposed, awaiting owner approval of the gates in §2**. This expands the roadmap in [blueprint.md](../blueprint.md) (H01–H03, P01, P02) and builds on [audit-20261006.md](audit-20261006.md). Once it is approved, the blueprint roadmap table points here for the detailed instructions. The blueprint stays the single source of status.

The document is written for a **delivery agent** (human or AI) picking up one work package at a time. Each package is self-contained: goal, dependencies, specific instructions, acceptance criteria, required tests, and things not to do.

---

## 1. Rules for every delivery agent

Read these before starting any package. They restate the blueprint invariants that this work is most likely to break.

1. **Start-of-task checklist:** read `blueprint.md`, this document and the package's dependencies. Run `git status`, then the full backend suite, `npm test` and `npm run build`, and record the baseline. Never start on a dirty tree that you didn't create.
2. **One package per branch and PR** (`feature/<ID>-short-name`). Don't combine packages unless this document says they ship together.
3. **No live deployment without explicit owner authorisation for that release.** Use `scripts/deploy_unraid.py` without `--deploy` for candidate verification. Never touch `/library` or live appdata from tests.
4. **The library files on the NAS are the source of truth.** Never delete, move, retag or transcode library files as a side effect. The device copies in M10 are a separate, disposable cache outside `/library`.
5. **Migrations are additive and reversible.** Every schema change ships with: a migration in `server/migrations/` (see M00), a fixture-based test, an extension to `scripts/verify_state_migration.py`, and a backup of the stopped state before deployment. Existing tracks, album links, queue rows, playlists, favourites and preferences must survive unchanged, re-attributed to the owner account.
6. **Secrets:** no passwords, tokens, hashes or keys in Git, logs, API responses, screenshots or handover notes. Redact the `Authorization` and `Cookie` headers in every log path.
7. **No public exposure.** Access remains LAN and Tailscale only. Adding app accounts does *not* authorise port forwarding, public DNS or reverse proxies on the internet.
8. **Brand:** all UI (web and Swift) uses the generated tokens from B01 and the assets from B02. Follow the standard: playback stays on a protected dark surface with rose accent #EF7AAE, no ticks for selection, focus is a separate ring, and text uses Dynamic Type (Swift) or rem (web).
9. **Handover at the end of every package:** update the blueprint roadmap table and the decision dialogue. State what changed, which checks actually ran (with output), which checks didn't run, the open risks, and the next package. "Planned" is not "delivered".
10. **Stop and ask the owner** if a package's instructions conflict with observed code or behaviour, or if a gate in §2 is still open for the package you're about to start.

---

## 2. Owner decisions and gates

| Gate | Decision | Status |
| --- | --- | --- |
| G-1 Identity | Pig Music **app accounts with passwords**. Web uses a session cookie; iPhone and Watch use per-device revocable tokens obtained by password sign-in. This supersedes the blueprint line "do not add new authentication assumptions". | **Decided 6 Oct 2026** |
| G-2 Sharing | **Files are shared and stored once; libraries are private.** Each person has their own library membership, favourites, playlists, play history and requests. **Deletion follows membership:** if you're the only person who has an album or song, deleting it deletes the files. If both people have it, one person deleting it removes it from their library only and the files stay. When the second person also deletes it, the files are deleted. No owner review step. | **Decided 6 Oct 2026** (deletion rule confirmed by owner) |
| G-3 Device copies | iPhone downloads **original files**. Watch gets **server-made AAC 256 kbps copies** held in a bounded cache outside the library. The library is never converted. | **Decided 6 Oct 2026** |
| G-4 Distribution | **Sideloadly.** Feasibility for the Watch app must be proven in S00 before Watch work starts. | **Decided, pending S00 proof** |
| G-5 Apple account type | **Recommended:** a paid Apple Developer membership (1-year signing; avoids the free account's 7-day expiry and 3-active-app limit, since the iOS app, Watch app and any widget count separately). Free account workable only if S00 proves the bundle fits. | **Open; decide during S00** |
| G-6 Device inventory | iPhone and Watch models and OS versions for both people. **Default:** minimum iOS 18 / watchOS 11. Raise the minimum if all four devices support a newer OS. | **Open; collect in S00** |
| G-7 Shared-file quality conflict (H03) | **Recommended:** a shared file's quality is the *highest* any current member wants. An explicit downgrade replaces the file only when the requester is its sole member; otherwise the downgrade is recorded and applied when that becomes true. | **Open; confirm before M04** |
| G-8 Externally added files | **Recommended:** files found by Scan that Pig Music didn't publish go to an owner-only **Unassigned** inbox. The owner assigns them to one or both libraries. The existing library is assigned to the owner during migration. | **Open; confirm before M04** |
| G-9 Plex | **Recommended:** Plex keeps one shared music section (Plex can't filter a section by Pig Music membership). Only *playlists and favourites* are exported per person, to each person's Plex home user. | **Open; confirm before M05** |
| G-10 HTTPS hostname | **Recommended:** `tailscale serve` HTTPS on the Unraid host (`https://pig-music.<tailnet>.ts.net`) as the only supported client URL, on LAN and off-site alike. Plain `http://192.168.1.203:8765` is retired once T01 ships. Needs Tailscale running on the Unraid host and on both iPhones. | **Open; confirm before T01** |
| G-11 Household admin | **Recommended:** the owner (Mark) holds the `owner` role, and the second person is a `member`. Only `owner` changes system settings, providers, Plex connection, scans, organisation, recovery and the people and devices list. | **Open; confirm before M02** |

---

## 3. Sequence

```
Phase 0  Foundations ─ A01 → A02 → A03 ─┐      B01 → B02 ─────────────┐
                       T01 (HTTPS) ─────┤                              │
Phase 1  Multi-user ── M00 → M01 → M02 → M03 → M04 → M05 → M06 → M07  │
Phase 2  Client API ── X01 → X02 → X03 → M10 (device copies)           │
Phase 3  iOS ───────── S00 (spike; may run from Phase 0) → I01 … I09 ◄┘
Phase 4  Watch ─────── W01 … W06  (needs S00 Watch proof, I05, M10)
Later    S01/S02/R01 as in the blueprint
```

- A01 (cover store) must land before M03: two libraries on the current snapshot design would exceed the 1 GB container limit sooner.
- S00 is a throwaway spike and can run in parallel with Phase 0/1 on the owner's Mac.
- Ship and verify Phase 1 before any iOS sign-in work. The iOS app must never be built against an unauthenticated API.

---

## 4. Phase 0: foundations

These packages come straight from the audit and are summarised here; see the audit for the evidence.

### A01: Content-addressed cover store (audit P0-1, P0-2)
- Write each cover to `covers/<sha256-of-normalised-bytes>.jpg` **at scan time** (`server/scanner.py`). The snapshot keeps only `cover_sha` per track and album edition. Delete the `covers` map from the snapshot schema (bump `schema_version` to 3).
- Add a migration that streams the existing `covers` map out of `library-snapshot.json` into files, then rewrites the snapshot without it. Use a streaming or one-pass approach, and test it at 10k tracks inside a 1 GB memory limit.
- Album edition identity now carries its own `cover_sha`. Fall back across editions only when an edition has no art.
- Prune: an owner-triggered (and weekly) job removes cover files no longer referenced and `missing-artwork:*` and `catalogue:*` documents past expiry.
- **Accept when:** the synthetic benchmark at 10k tracks with covers shows a snapshot under 25 MB and peak RSS under 400 MB; retagged art appears after a rescan; deluxe and standard editions can show different art.

### A02: Artwork delivery (audit P0-3, P1-1, P1-2, P1-6, P2-3, P2-4)
- Derivatives per cover hash: 128, 256, 512 and 1024 px in WebP (and JPEG fallback), plus a stored `dominant_colour` (hex) and a small BlurHash. Route: `GET /api/v1/artwork/{sha}?w=128|256|512|1024&fmt=webp|jpeg`, sent with `Cache-Control: private, max-age=31536000, immutable`.
- Enrichment (CAA, Fanart, ArtistGrid) runs as a background worker. Image routes never wait on the network: they return the best local hash or a 404. Library payloads carry `cover_sha`, `dominant_colour` and `blurhash`.
- Per-key locks in `Backgrounds`; run all PIL work through `asyncio.to_thread`; proxy the catalogue artist-artwork route instead of redirecting.
- **Accept when:** a cold grid of 50 unenriched albums doesn't delay `/api/library` or search requests (test with concurrent requests); tiles fetch the 256 px WebP at 2×.

### A03: Payloads and lookups (audit P1-7, P2-1, P2-2)
- GZip middleware (minimum size 1 KB, excluding audio and images). `ETag` equal to the library revision on library reads, with `If-None-Match` returning 304. Add `albums_by_id`/`artists_by_id` maps. Cache settings in memory, invalidated on save. Use `content-visibility: auto` on grid cards.

### T01: HTTPS via Tailscale serve (G-10)
- On Unraid, run `tailscale serve --bg --https=443 http://127.0.0.1:8765` from the Tailscale plugin or a sidecar container. Leave the existing static LAN address untouched until the owner has confirmed both phones work over HTTPS.
- Set `PIG_MUSIC_PUBLIC_ORIGIN=https://pig-music.<tailnet>.ts.net`. The server uses it for the Origin check, cookie settings and absolute URLs.
- Document the setup in `docs/operations.md` (no secrets). Add a health check that reports whether the request arrived over HTTPS.
- **Accept when:** the web app loads over the ts.net URL on both iPhones on LAN and off-site (this closes blueprint V01's off-site item), and the certificate is valid.

### B01: Tokens and type (audit P1-3, P1-5)
- Write `scripts/generate_brand_tokens.py`. It reads `docs/pig-family-brand-tokens.json` and writes `client/src/tokens.css` (light, dark and `media` roles; radius, space, type and shadow scales) and `swift/PigKit/Sources/PigBrand/Tokens.swift` (colour sets, generated once the Swift package exists). Add a test that fails if the generated files are stale.
- Type scale in rem (minimum 0.75 rem): replace every font-size below 11 px.
- **Owner/brand review:** the three player colours (`#d9d2dd`, `#8c7f95`, `#493d52`). Either get them approved as `media.secondary`, `media.controlBorder` and `media.border`, or replace them with existing roles.

### B02: Pig Music identity assets
- In **Pig-Branding**, extend `Tools/make-brand-assets.swift` to produce: Pig Music light and dark wordmarks; iOS app icon set (light, dark, tinted, 1024 px); watchOS icon; a web `apple-touch-icon` (180 px), a square favicon and a `manifest.webmanifest`. Record the new assets in Pig-Branding's `decisions.md` and asset README, then copy them into Pig-Music `client/public/` and later into the Swift asset catalog.
- **Accept when:** the owner approves the wordmark (a new artwork review is required by the standard), and "Add to Home Screen" on an iPhone shows the pig icon.

---

## 5. Phase 1: secure multi-user server

### M00: Schema migration framework
**Goal:** versioned, tested SQLite migrations. These replace the ad-hoc `CREATE TABLE IF NOT EXISTS` in `Store.__init__` (`server/store.py:38-55`).
- Add a `schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT)` table and a `server/migrations/NNNN_name.py` module per migration, each with an `up(conn)` function. They run in a transaction at startup, before `refresh_library()`.
- Migration 0001 records the current schema as the baseline (no-op on existing databases).
- Turn on `PRAGMA foreign_keys=ON` and `journal_mode=WAL` in `Store.connect()`.
- **Tests:** a fresh database and a copy of a pre-migration fixture database both reach the same final schema. Running migrations twice is a no-op.

### M01: Accounts, passwords and sessions
**Depends:** M00, T01.

**Data (migration 0002):**
```sql
users(id TEXT PK, username TEXT UNIQUE COLLATE NOCASE, display_name TEXT,
      role TEXT CHECK(role IN ('owner','member')), password_hash TEXT,
      password_changed_at TEXT, disabled INTEGER DEFAULT 0, created_at TEXT)
sessions(id TEXT PK,            -- SHA-256 of the opaque token; the raw token is never stored
         user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
         kind TEXT CHECK(kind IN ('web','device')),
         device_name TEXT, platform TEXT,        -- e.g. "Mark's iPhone", "ios" / "watchos" / "web"
         created_at TEXT, last_seen_at TEXT, expires_at TEXT, revoked_at TEXT)
setup_codes(id TEXT PK, user_id TEXT, code_hash TEXT, expires_at TEXT, used_at TEXT)
auth_events(id INTEGER PK, at TEXT, user_id TEXT NULL, event TEXT, ip TEXT, detail TEXT)
login_attempts(key TEXT PK, failures INTEGER, locked_until TEXT)
```

**Instructions:**
- New module `server/auth.py`. Hash passwords with **Argon2id** (`argon2-cffi`; add it to `requirements.txt` and regenerate `requirements.lock.txt`), using the library defaults or stronger. Rehash on login if the parameters have changed. Minimum password length 12, maximum 256. There is no complexity rule, but reject the username itself and an embedded list of the most common passwords.
- Tokens: 32 random bytes from `secrets.token_urlsafe(32)`. Store only `sha256(token)`. Compare in constant time.
- **Web:** `POST /api/v1/auth/login {username, password}` sets the cookie `__Host-pig_session` with `HttpOnly; Secure; SameSite=Strict; Path=/`. Idle expiry 14 days, absolute expiry 60 days.
- **Device:** `POST /api/v1/auth/device {username, password, device_name, platform}` returns `{token, user}`. Sliding expiry of 180 days, refreshed on use (only write `last_seen_at` at most hourly).
- `POST /api/v1/auth/logout` revokes the current session. `GET /api/v1/me`. `GET /api/v1/me/sessions` and `DELETE /api/v1/me/sessions/{id}`. `POST /api/v1/me/password` (requires the current password and revokes every other session).
- **Bootstrap:** `python -m server.admin create-owner --username <name>` prompts for the password twice on a TTY (run via `docker exec -it`). Until an owner exists, every `/api/` route except `/api/health` returns `503 {"detail":"setup_required"}`, and the web app shows "Finish setup on the server". There is **no web self-registration**.
- **Adding the second person:** the owner uses Settings › People › Add person, which creates the user with no password and a one-time **setup code** (8+ characters from an unambiguous alphabet, valid 24 hours, shown once). The person opens `/setup`, enters the code and chooses a password. The owner can reset a forgotten password by issuing a new setup code (this revokes their sessions). `python -m server.admin reset-password <username>` is the fallback when the owner is locked out.
- **Rate limiting:** 5 failures per username and per IP within 15 minutes triggers an exponential lock of 1, 2, 4 … up to 60 minutes. Error messages never reveal whether the username exists. Every failed attempt goes to `auth_events`.
- **Logging:** add a log filter that strips the `Authorization` and `Cookie` headers and any field named `password`, `token` or `code`. Add a test that asserts none of these appear in captured logs during the auth tests.

**Acceptance:**
- An owner created by the CLI can sign in on the web.
- The second person activates with a setup code.
- Wrong passwords lock as specified.
- Revoking a device session makes its next request return 401 within one request.
- No raw token is present anywhere in SQLite.

**Do not:** use JWTs (opaque tokens are easier to revoke and enough for a single server); store passwords reversibly; add OAuth or other providers; expose any route publicly.

### M02: Authorisation on every route
**Depends:** M01, G-11.
- Add two FastAPI dependencies: `current_user` (cookie or `Authorization: Bearer`) and `require_owner`. Apply them at **router level**: split `server/app.py` into routers (`routes/library.py`, `routes/catalogue.py`, `routes/queue.py`, `routes/playback.py`, `routes/settings.py`, `routes/admin.py`, `routes/auth.py`). Mount everything under `/api/v1`, and keep `/api/*` as temporary aliases for the web client until M07 is done.
- **Default deny:** add a startup self-check plus a test that walks `app.routes`. Every `/api/` route must declare `current_user` or `require_owner`, except an explicit allow-list (`/api/health`, `/api/v1/auth/login`, `/api/v1/auth/device`, `/api/v1/setup`).
- **Owner-only:** download, Soulseek, media-provider and Plex settings; scan; organisation; recovery and trash; remove-from-disk; the Unassigned inbox; people and devices administration; queue clear; Apple XML import for *another* user.
- **CSRF:** keep the Origin check (`server/app.py:118-123`), comparing against `PIG_MUSIC_PUBLIC_ORIGIN`. Additionally require the `X-Pig-Request: 1` header on cookie-authenticated mutations. Bearer-authenticated requests are exempt.
- **Media:** `<img>` and `<audio>` tags on the web authenticate by cookie. Native clients send a Bearer token, and for AVPlayer use **signed URLs** (`?exp=<unix>&sig=<HMAC-SHA256(server_secret, user_id|path|exp)>`, valid 6 hours). They are issued by `POST /api/v1/playback/{track_id}/url`. `server_secret` is 32 random bytes generated into appdata `auth-secret` (mode 0600) on first start.
- **Tests:** an anonymous request to every non-allow-listed route returns 401; a member calling every owner route returns 403; an expired or tampered signature returns 403.

### M03: Per-user library, favourites, playlists and history
**Depends:** M02, A01, G-2.

**Data (migration 0003):**
```sql
library_members(user_id, track_id, added_at, source TEXT CHECK(source IN
                ('migration','request','scan-assign','household-add','import')),
                PRIMARY KEY(user_id, track_id))
playlists: ADD COLUMN owner_id TEXT REFERENCES users(id)     -- backfilled to owner
play_events(id INTEGER PK, user_id, track_id, played_at, seconds, device_session_id)
user_preferences(user_id PK, payload TEXT)                    -- appearance, default tab, etc.
queue: payload gains "requested_by": [user_id, ...]
```

**Instructions:**
- **Migration:** every current track ID goes into `library_members` for the owner with source `migration`. Every playlist gets `owner_id = owner`. `pig-favourites` becomes `pig-favourites:<owner_id>`. Queue rows get `requested_by=[owner]`. Extend `scripts/verify_state_migration.py` to assert the counts are unchanged.
- **Projection:** `store.library` stays the household projection, built once. Add `store.library_for(user_id)` to return the filtered summary, with artist and album counts recomputed from that user's members. Cache it per user, keyed by `(library_revision, membership_revision[user])`, and bump `membership_revision` on every membership change.
- Every read route (library, artists, albums, search "saved" presence, membership, playlists) filters by the caller. Search results mark music that is on the server but not in your library as `household_available: true` (no owner names). Offer "Add to my library", which creates membership without downloading.
- **Requests** (`submit_catalogue`, artist jobs, Apple import): if the matched file already exists, add membership and don't enqueue. Otherwise enqueue, or attach the caller to an existing active request for the same recording or edition (append to `requested_by`). When publishing, `publish_request` adds membership for every user in `requested_by`.
- Favourites and playlists are scoped by `owner_id`. Make `/api/membership` use the caller's favourites.
- Record `play_events` from web playback and native clients (`POST /api/v1/play-events`, batched). Rewrite artist monitoring (`server/artist_jobs.py`) per user, with `user_id` stored in its state.
- **Accept when:** in a two-user fixture, A and B see disjoint libraries. B adding an album A already has creates zero queue rows. Concurrent requests for the same album create one queue row with two beneficiaries. Each person's favourites, playlists and history are invisible to the other.

### M04: Shared-file lifecycle (removal, quality, scans)
**Depends:** M03, G-7, G-8.
- **Removal (owner rule, G-2):** "Delete" on a track, album or artist removes the **caller's** `library_members` rows for those tracks, all in one transaction. Then, for each affected track:
  - **Still has another member** → the file stays on disk and nothing else changes. The UI confirms "Removed from your library. Kept for <other person>". Use their display name: the household knows each other, and this is the only place one person's library is revealed to the other.
  - **No members left** → the file is deleted immediately and automatically, through the existing `server/recovery.py` removal path (path and hash guards, Plex exclusion, recoverable trash). There's no owner review and no `orphan_policy` setting. The confirmation dialog says "This deletes the files from the server" *only* in this case, and lists the count. For an album that's partly shared, it says "8 songs will be deleted; 3 are kept because they're also in <name>'s library".
  - Membership is per **track**. If A has the full album and B has 3 of its songs, A deleting the album deletes the other songs and keeps those 3.
- **Things that do *not* keep a file alive:** playlist or favourite references (the entries stay in the playlist as metadata and show as "Missing", as imported playlists already do), play history, device copies, and downloads on iPhone or Watch.
- **Things that *do* count as a member** (so the file is kept): an active queued or in-flight request from the other person for that recording or edition (they're a pending member via `requested_by`).
- **In-flight work on a deleted file:** cancel quality-replacement jobs for it using the existing claim-token cancellation. Purge its M10 device copies, and mark copies on iPhone and Watch stale so clients delete them on next sync. A deletion holds the per-track lock, so a concurrent "add to my library" either lands first (file kept) or sees the file as gone and offers a re-request.
- **Restore:** recovery-trash restore (owner, Settings › Recovery) re-creates the memberships that existed at deletion. A member can undo their own deletion from the toast for 30 s. That re-adds the membership, and restores the file if it had been trashed.
- **Owner "remove from disk"** (existing route `POST /api/tracks/{id}/remove`) is the only way to delete a file that someone else still holds. It stays owner-only and its confirmation names the affected libraries.
- **Quality (G-7):** store per-user quality preferences in `quality_preferences(user_id, scope, item_id, preferred)`. The effective target for a file is the max over its members, using the existing system → artist → album precedence per user. Downgrades apply only when the requester is the sole member. Extend `server/quality.py` and `store.quality_policy` and keep the existing "never transcode" rule.
- **Scan assignment (G-8):** new tracks that weren't published by Pig Music go to `unassigned_tracks`. The owner's Unassigned inbox offers per album: assign to me, to the other person, or to both. Previously known tracks keep their memberships across rescans because track ID is `sha256(relative_path)`. When organisation renames a path, carry memberships to the new ID in the same transaction (`server/organisation.py`, `server/exporter.py`).
- **Tests (deletion rule, all required):**
  - sole member deletes → files trashed;
  - two members, first deletes → files kept and the second still plays;
  - second deletes → files trashed;
  - partial overlap keeps only the shared songs;
  - a playlist reference does **not** keep a file and becomes "Missing";
  - the other person's pending request keeps the file;
  - concurrent delete and add is race-safe;
  - undo restores membership and file;
  - quality jobs cancelled and device copies purged;
  - the removal and restore path, hash and marker safeguards from `tests/test_recovery.py` still pass.
- **Other tests:** G-7 conflicts resolve correctly in both directions; organisation rename keeps memberships; restore re-creates memberships.

### M05: Per-user Plex (blueprint H02)
**Depends:** M03, G-9.
- Change `plex-connection.json` to keep only the server-level fields (`url`, `section_id`, `machine_id`, `library_root`). Store per-user Plex tokens in a new `plex_accounts(user_id, token_encrypted, plex_user_label)` table, encrypted with a key derived from `auth-secret` (AES-GCM via the already-locked `pycryptodome`).
- Export each user's playlists and favourites into *their* Plex account. Keep the existing ownership marker so only Pig Music-owned playlists are edited. Never edit another user's playlists.
- Migrate the existing owner token into `plex_accounts`.
- **Accept when:** in a fixture with two mocked Plex users, each user's playlists appear only for that user; existing owner playlists are unchanged and not duplicated.

### M06: Security hardening and review
**Depends:** M01–M05.
- Security headers on HTML: `Content-Security-Policy: default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'`. Move the inline theme script in `client/index.html` into a hashed file, or add its SHA-256 to the CSP. Also `Strict-Transport-Security` (when the origin is HTTPS), `Permissions-Policy` and `Cross-Origin-Opener-Policy: same-origin`.
- Limit request body sizes (Apple XML: the existing limit; JSON: 1 MB). Validate all path parameters as IDs (some already go through `valid_id`).
- Run `/security-review` (or an equivalent manual review) over the Phase 1 diff. Run `pip-audit` and `npm audit --omit=dev` in CI.
- Security events in Settings › People › Activity (owner only): sign-ins, failures, lockouts, device additions and revocations.
- Document threat-model assumptions in `docs/security.md`: tailnet-only; app accounts protect against other tailnet devices and casual misuse; owner can read all data; backups contain password hashes (protect appdata backups).

### M07: Web client for accounts
**Depends:** M02 (can proceed alongside M03–M05).
- Screens: sign in, `/setup` (code + new password), Settings › Account (change password, my devices with revoke), Settings › People (owner only: add person, setup code, reset, disable), Unassigned inbox (owner), "Add to my library" on household-available results.
- On a 401 from the shared transport, `client/src/api.ts` goes to sign-in and keeps the current hash route. On a 403 it shows a toast.
- Brand: the sign-in screen uses the pig with a **soft halo** behind an opaque form (per the standard's light-effects section), the B02 wordmark, and B01 tokens.
- **Browser journeys to verify:** owner and member sign-in on desktop and phone; light and dark mode; keyboard focus; setup-code expiry; device revoke takes effect.

---

## 6. Phase 2: client API for native apps

### X01: API v1 contract
**Depends:** M02.
- Every native endpoint lives under `/api/v1`, with typed Pydantic response models (not bare dicts) so FastAPI's OpenAPI output is complete. Commit `api/openapi.v1.json`, generated by `scripts/export_openapi.py`, with a test that fails if it's stale.
- **Pagination:** cursor-based (`?cursor=&limit=200`) for tracks, albums and artists.
- Every track, album and playlist entry carries `server_state` from the availability state model in §7, with `request_progress` when the state is `requested`. Album and playlist payloads carry the counts used by the aggregate.
- **Endpoints the Swift app needs** (all scoped to the user):
  - `GET /me`
  - `GET /library/changes?since=<revision>`: returns `{revision, upserts:{artists,albums,tracks}, deletes:{…}}`, or `410` when a full resync is needed
  - `GET /library/{artists|albums|tracks}` and `GET /albums/{id}`, `GET /artists/{id}`, `GET /search?q=`
  - `GET /artwork/{sha}`
  - `GET /playlists`, `GET /playlists/{id}` and playlist edits; `POST /favourites`
  - `POST /requests`, `GET /requests`
  - `POST /playback/{id}/url`
  - `GET /tracks/{id}/file`: original file with Range support
  - `POST /device-copies` and `GET /device-copies/{id}` (from M10)
  - `POST /play-events`
  - `GET /events` (from X02)
- **Change feed:** keep a `changes(revision INTEGER PK, user_id, entity, entity_id, op)` log, written on membership, playlist and favourite changes and on library refresh (as a diff against the previous projection). Keep 30 days; older `since` values get `410`.
- **Errors:** always `{"detail": string, "code": string}`, with stable `code` values the Swift app can switch on.

### X02: Server-sent events
- `GET /api/v1/events` (authenticated) sends `revision` (library or membership changed), `queue` (request state for this user's requests) and `health` events, with a heartbeat every 25 s. Move the web client from 5 s/15 s polling to SSE, falling back to polling. Bound connections to 4 per session.

### X03: Request and download state for clients
- Per-user view of the queue (`requested_by` contains the user), including progress. The owner keeps the full queue view. Push notifications are **out of scope** (they would need a paid account and APNs); clients update via SSE or on foreground.

### M10: Device-copy (AAC) service (G-3)
**Depends:** X01, A01.
- `POST /api/v1/device-copies {track_ids:[...], preset:"aac256"}` queues transcodes. Output goes to appdata `device-copies/<source_sha>-aac256.m4a` (keyed by the **source file hash**, so a library upgrade invalidates the copy). Never write under `/library`, and never record copies as library files.
- FFmpeg command: `ffmpeg -nostdin -i <src> -map 0:a:0 -c:a aac -b:a 256k -movflags +faststart -map_metadata 0 <tmp>`. Embed the 512 px cover. Validate by full decode (reuse the existing probe), then rename atomically.
- Limit to 1 concurrent transcode and pause while acquisitions are active. Cache size cap via the setting `device_copy_cache_gb`, default 20, with LRU eviction. Original MP3/AAC sources at or below 256 kbps are served **as-is** (no conversion needed).
- `GET /api/v1/device-copies/{track_id}?preset=aac256` returns `202 {status}` until ready, then the file with Range support.
- Record in the blueprint decision dialogue that this does *not* breach the "never transcode to obtain library quality" rule.

---

## 7. Phase 3: iOS app (blueprint P01)

### S00: Feasibility spike (run early; throwaway code)
**Goal:** prove installation and networking on the owner's real devices before investing in the app.
1. Collect the G-6 device inventory (models and OS versions for both iPhones and Watches) and the G-5 account decision.
2. Build a minimal Xcode project with an iOS app, an embedded watchOS app and an App Group. Export an IPA (Development signing) and **install it with Sideloadly** on the owner's iPhone. Record:
   - (a) whether the Watch app installs to the paired Watch automatically or needs the Watch app's "Install" switch;
   - (b) whether it survives a Sideloadly refresh;
   - (c) the App ID count and active-app limits on the chosen account;
   - (d) whether App Groups and Keychain sharing survive Sideloadly re-signing.
3. On the iPhone with Tailscale connected, fetch `https://pig-music.<tailnet>.ts.net/api/health` from the spike app, both on LAN and off-site (cellular). Test it as a background `URLSession` download as well.
4. From the Watch app, fetch the same URL: (a) with the iPhone nearby, (b) with the iPhone off or Bluetooth disabled on home Wi-Fi. The expected result, to be confirmed, is that traffic routes through the phone's VPN only when the phone is nearby.
5. Play a local AAC file on the Watch through Bluetooth headphones with a `.longFormAudio` audio session.
6. Write the findings into `docs/native-spike.md` and update gates G-4 to G-6.
- **Fallback if Sideloadly can't install the Watch app:** install the iOS app via Sideloadly and the combined app (including the Watch app) via Xcode direct-run from the owner's Mac. Or reconsider TestFlight with a paid account. Escalate to the owner and do not start W01 until this is resolved.

### Availability state model (shared by API, web, iOS and Watch)
Owner direction, 6 Oct 2026: the app must clearly distinguish music **on the server** from music **on this device**, and both from music not downloaded at all. Every client uses this one model. Don't invent per-screen variants.

**Server state** (from the API, per user, field `server_state` on every track, album and playlist entry):

| `server_state` | Meaning | Symbol (SF Symbol / web lucide) | Primary action | Accessibility label |
| --- | --- | --- | --- | --- |
| `not_in_library` | Catalogue only; not on the server | `plus.circle` / `CirclePlus` | Request (acquire to server) | "Not in your library. Request" |
| `household_available` | File is on the server, in the other person's library | `plus.circle` + caption "On server" | Add to my library (instant, no download) | "On the server. Add to your library" |
| `requested` | Queued or acquiring to the server | `clock` while queued, then `icloud` with determinate ring / `Clock`, `Cloud` + ring | Open request status | "Requested. Downloading to server, 40%" |
| `in_library` | In your library on the server (stream-only on this device) | `icloud`, secondary colour / `Cloud` | (iOS) Download to this device | "On the server" |
| `failed` | Request failed or file unavailable | `exclamationmark.circle`, danger colour + text / `CircleAlert` | Retry | "Request failed. Retry" |

**Device state** (iOS and Watch only, local to the device, layered on top of `in_library`):

| Device state | Symbol | Action | Accessibility label |
| --- | --- | --- | --- |
| none | (shows the server symbol `icloud`) | Download to this device | "On the server. Download to this iPhone" |
| `queued` / `downloading` | determinate progress ring | Cancel | "Downloading to this iPhone, 60%" |
| `downloaded` | `arrow.down.circle.fill`, accent colour | none (remove via swipe or menu) | "On this iPhone" |
| `stale` (server file upgraded) | `arrow.down.circle.fill` + small dot | Update on Wi-Fi (automatic) | "On this iPhone. Update available" |
| `failed` | `exclamationmark.circle` | Retry | "Download to this iPhone failed. Retry" |

**Rules:**
- **The cloud always means "on the server". A down arrow always means "on this device"** and is never used for server acquisition. Getting music onto the server is "Request" with a **plus**. This changes the web: `client/src/SongControls.tsx` currently uses `ArrowDown` to request and `Check` for saved. Move it to `CirclePlus`/`Cloud` in M07. The web never shows device states.
- **One trailing status slot per song row**, which is also the tap target (44 pt minimum). Albums, playlists and artists show an **aggregate** in the header: "12 songs · 8 on this iPhone", plus a single button whose state is "Download all", a progress ring, or `arrow.down.circle.fill` when complete.
- **Colour:** the server symbol uses the secondary text colour; device downloaded uses the accent; failure uses danger. **Always pair a symbol with a label** (VoiceOver, long-press, context menu), because colour alone never carries status (brand standard).
- These are **status** symbols, not selection, so they're allowed alongside the no-ticks selection rule. Don't use a checkmark for any availability state, to avoid confusion with selection.
- Library gets a filter chip, **"On this iPhone"** (on the Watch: everything shown is on the Watch). The Downloads tab lists device downloads and server requests in separate sections, titled "On this iPhone" and "Requests".
- **What's on the Watch** shows only on the iPhone's Settings › Apple Watch and "Send to Watch" screens (`applewatch` symbol), not in every row.
- `PigUI` implements this once as `AvailabilityBadge(server:device:)` and `AvailabilityButton`. The web implements it once in `SongControls.tsx`. Snapshot-test every state in light, dark and at AX5 text size.

### Architecture (applies to I01–I09 and W01–W06)
- New directory `swift/` in this repository, so server, API contract and clients version together:
  - `swift/PigMusic.xcodeproj` with targets: iOS app, watchOS app, and optionally a widget/complication.
  - `swift/PigKit` (a Swift package) with these modules:
    - `PigAPI`: OpenAPI-generated client via `swift-openapi-generator` from `api/openapi.v1.json`, plus auth middleware.
    - `PigStore`: local SQLite via **GRDB**, which handles 50k-row libraries better than SwiftData and supports explicit migrations.
    - `PigSync`: change-feed sync.
    - `PigPlayback`: queue, AVFoundation and Now Playing.
    - `PigDownloads`: background `URLSession` and storage.
    - `PigBrand`: generated tokens, colours, type and shapes.
    - `PigUI`: shared SwiftUI components.
- Swift 6 language mode with strict concurrency; SwiftUI; Observation (`@Observable`); `async/await`. No third-party UI frameworks. Keep dependencies to GRDB, swift-openapi-generator/runtime/URLSession transport, and optionally Nuke for image caching, which can be replaced by a small `ImageCache` keyed by `cover_sha`.
- **Entitlements:** Background Modes → Audio, plus Keychain. App Groups only if S00 proved they survive re-signing. **No** push notifications, iCloud or CarPlay (these need a paid account, APNs or Apple approval).
- **Bundle IDs:** `au.com.pig.music` (iOS) and `au.com.pig.music.watchkitapp` (watchOS). Confirm with the owner and keep the count within the G-5 limits.
- **CI:** GitHub Actions `macos-latest` runs `xcodebuild test` for PigKit and both app targets on simulators. Signing happens only on the owner's Mac.

### I01: Project skeleton and brand
- Create the project, the PigKit modules and an empty tab shell: Library, Search, Downloads, Settings.
- Generate an `Assets.xcassets` colour set from B01 (adaptive light/dark). Import the B02 app icons and wordmark. Launch screen: the cleaned pig centred on its optical anchor (49.9694%, 40.5360%) over the canvas colour, with a soft halo and no added delay.
- Type uses system text styles only (`.body`, `.headline` …), so Dynamic Type works; test the largest accessibility sizes. Shapes follow the standard's touch roles: 14–16 pt cards, 22 pt heroes, capsule chips.
- **Accept when:** a snapshot test in light, dark and at Accessibility XL shows token colours that match the web.

### I02: Sign-in, server and Keychain
- **First run:** enter server URL (default `https://pig-music.<tailnet>.ts.net`, editable) → health check → username and password → `POST /auth/device` with `device_name = UIDevice.current.name`. Store the token in Keychain (`kSecAttrAccessibleAfterFirstUnlock`, so background downloads work while locked).
- Clear errors for: Tailscale not connected ("Can't reach Pig Music. Is Tailscale on?"), wrong password, locked out, revoked (back to sign-in).
- Settings › Account shows the signed-in user, the device name, and sign-out (revokes the session server-side). Settings › Devices is web-only.
- **Never:** store the password; log tokens; allow HTTP except to `localhost` in debug builds.

### I03: Library sync and browsing
- First sync: paginated full download into GRDB. After that: `GET /library/changes?since=` on launch, on foreground, and on an SSE `revision` event; `410` triggers a full resync.
- Screens: Artists (grid with portraits), Albums (grid; sections for Albums, Compilations, Soundtracks and Musicals as on the web), Artist detail (hero backdrop with dominant-colour placeholder, discography), Album detail (tracks, editions), Playlists, Favourites. Search is local-first over GRDB FTS5, then server search for household or catalogue results.
- **Artwork:** request `w=256` for grid tiles and `w=1024` for detail and now-playing, choosing by `displayScale` × point size. Show the BlurHash or dominant colour instantly, and cache by `cover_sha` with no expiry. Use a lazy grid (`LazyVGrid`); don't preload off-screen images.
- **Performance gates on the owner's oldest device:** cold launch to first grid under 1.5 s with a warm cache; scrolling 5k albums at 60 fps with no hitch over 50 ms (Instruments trace attached to the handover).

### I04: Playback
- `PigPlayback` wraps `AVQueuePlayer`:
  - shuffle, repeat, up-next;
  - `MPNowPlayingInfoCenter` with artwork;
  - `MPRemoteCommandCenter` (play, pause, next, previous, seek, like = favourite);
  - an AirPlay route picker;
  - interruption and route-change handling (pause when headphones are unplugged);
  - background audio.
- **Sources, in order:** local downloaded file, then a signed streaming URL (`POST /playback/{id}/url`). Refresh the URL on 403 or at expiry. Experimental remote playback (JioSaavn) is **excluded** from the native app unless the owner asks.
- Batch play events and post them when online, from a persistent outbox.
- **Player UI:** protected dark surface and rose #EF7AAE accent in both appearances (per the standard), with large controls, a scrubber and favourite. Add a mini-player above the tab bar.
- **Accept when:** playback survives locking the screen, backgrounding, a phone call interruption and a Bluetooth disconnect; and an album plays across tracks with no gap over 0.5 s (true gapless is a stretch goal; document the result).

### I05: Offline downloads
- Download the **original file** for a track, album, playlist or favourites, using background `URLSession`. Files go to Application Support/`Downloads/<track_id>.<ext>` with `isExcludedFromBackup`.
- GRDB tracks the state: queued, downloading, downloaded or failed, plus bytes. Settings › Storage shows the total used, lets you remove items, and has "Keep favourites downloaded" (auto-sync on change).
- When the server's file hash changes after a quality replacement, mark the local copy as stale and re-download on Wi-Fi.
- **Formats:** FLAC and ALAC play natively on iOS; Opus/Ogg do **not** play in AVPlayer. For those, request the M10 device copy with `preset=aac256`. Show this in the UI as "converted copy for this device".
- **Accept when:** in airplane mode, downloaded albums play, browse and search; a re-download after a server upgrade works; downloads continue while the app is backgrounded.

### I06: Favourites, playlists and requests
- Favourite (heart) on songs. Favouriting never requests a download (blueprint invariant).
- Playlists: create, rename, add to, reorder and remove, with optimistic updates through an outbox for offline edits. Conflicts resolve server-wins, and the user is told.
- Requests: from Search, request a song or album without choosing a backend, matching the web's "phone use should be quick" principle. Music already on the server is offered as "Add to my library" (instant). Request status comes from SSE; the Requests list lives under Downloads.

### I07: Accessibility and brand pass
- VoiceOver labels on every control; Dynamic Type up to AX5 without truncating key actions; Reduce Motion (no parallax on the hero); Reduce Transparency; minimum 44 pt hit targets.
- Selection uses the 14% accent fill plus a short inset bar, with **no ticks**. Availability symbols follow the availability state model in §7 (status, not selection); snapshot-test all of them.
- Compare against the web side by side in light and dark mode. Capture evidence screenshots into Pig-Branding `evidence/` following its manifest pattern.

### I08: Sideload build pipeline
- `scripts/build_ios_ipa.sh`: run `xcodebuild archive` and `-exportArchive` with `ExportOptions.plist` (method `development`, or `debugging` on newer Xcode). The IPA goes to `swift/build/` (git-ignored).
- Document in `docs/ios-install.md`:
  - Sideloadly steps for each person's device;
  - auto-refresh setup (Sideloadly daemon on the Mac, same Wi-Fi);
  - what happens at signing expiry (the app won't launch; downloads are kept if the bundle ID is unchanged);
  - the S00 Watch install procedure or its fallback.
- Version: `CFBundleShortVersionString` follows the server release, and the build number is the git commit count. The app reports its version in `GET /me` calls (`User-Agent: PigMusic/<ver> iOS/<os>`). The server returns `426` with an upgrade message if the client is below the minimum version.

### I09: Device acceptance
- Run on both people's iPhones: sign in, browse 10k+ library smoothly, play saved and streamed music, download offline, airplane mode, off-site over Tailscale on cellular, revoke device from web.
- Run the 7-day (or 1-year) re-sign cycle once with Sideloadly. Downloads must survive it.
- Record results in the blueprint. This also closes blueprint V01 for the native client.

---

## 8. Phase 4: Apple Watch (blueprint P02)

**Networking principle:** the **iPhone is the Watch's gateway**. A Watch reaches the network through the paired iPhone, and so through Tailscale, only when the phone is nearby. On home Wi-Fi alone it bypasses the phone's VPN and can't resolve or reach the tailnet host. S00 step 4 must confirm this. The design therefore doesn't rely on the Watch reaching the server directly.

### W01: Watch app skeleton and pairing
- An independent watchOS app that also works with its companion (`WKApplication`, SwiftUI) and uses `PigKit` (`PigBrand`, `PigUI` subset, `PigPlayback` watch variant, `PigStore` subset).
- **Pairing:** the iPhone app sends the Watch, via `WCSession` `transferUserInfo`, the server URL and a **separate device token for the Watch**. The phone obtains that token without asking for the password again: add `POST /api/v1/auth/device/child`, which authenticates with the phone's Bearer token and creates a new session with `platform=watchos`. The token lives in the Watch's own Keychain. Revoking the phone does not revoke the Watch, and vice versa.
- Watch brand: black canvas (the `media.canvas` token), rose accent, the pig on the launch screen, system fonts.

### W02: Sending music to the Watch
- On the iPhone, Settings › Apple Watch lets you choose what lives on the Watch: favourites, chosen playlists and chosen albums, with a storage budget (default 4 GB, adjustable to what the Watch reports).
- **Flow:** the iPhone requests M10 `aac256` copies, downloads them on Wi-Fi in the background, then sends each file with `WCSession.transferFile` and metadata (track ID, `cover_sha` 256 px image, source hash). The Watch writes the files to its container and updates its GRDB.
- **Opportunistic direct path:** when the Watch can reach the server (`GET /health` succeeds), it may download copies itself with a background `URLSession`. Gate this behind S00 findings.
- Sync is resumable and idempotent (keyed by track ID and source hash). Remove items from the Watch when they're deselected or when the library file is upgraded.
- **Accept when:** 200 songs (about 1.2 GB) transfer overnight with the Watch on its charger, with no duplicates after the phone restarts mid-transfer.

### W03: Offline playback on the Watch
- `AVAudioSession` category `.playback`, route-sharing policy `.longFormAudio` (requires Bluetooth headphones; the system shows a route picker). Use `AVQueuePlayer` over local files, with Now Playing info and remote commands from headphone buttons.
- **Screens:** Now Playing (protected dark, rose accent, Digital Crown volume), Library (Playlists, Albums, Favourites on the Watch only), and a storage indicator.
- Batch play events and relay them to the iPhone (`transferUserInfo`), which posts them to the server.
- **Accept when:** with the phone left at home, the Watch plays downloaded music to AirPods, shows correct Now Playing on the Watch face, and resumes after interruptions.

### W04: Remote control of iPhone playback
- When the iPhone is playing, the Watch shows a remote: play/pause, skip, favourite and volume. Use the system Now Playing view where possible (no extra code), and add a custom favourite action via `WCSession` `sendMessage`.

### W05: Complication and Smart Stack
- Add a WidgetKit complication that opens Pig Music and shows now playing or the pig mark. It needs its own bundle ID, so **check this against the G-5 app limits first**; skip it if the free-account limit would be exceeded.

### W06: Watch acceptance
- Both people's Watches: pairing, overnight sync, a phone-free run with AirPods, storage cap behaviour, a re-sign cycle via Sideloadly or the fallback, and revocation from the web.

---

## 9. Testing and evidence matrix

| Layer | Required in every relevant package |
| --- | --- |
| Backend | `pytest` (all existing tests plus new ones), migration fixtures, `verify_state_migration.py` on a backup copy, authorisation route-walk test, log-redaction test |
| Web | `npm test`, `npm run build`, Prettier; browser journeys in §5 M07; light/dark, phone/desktop, keyboard |
| API | OpenAPI drift test; contract tests that run the generated Swift client against a test server (CI job starts FastAPI with fixture data) |
| Swift | `xcodebuild test` (PigKit unit tests: sync, outbox, download state, token handling); snapshot tests for brand; UI tests for sign-in and playback start |
| Devices | I09 and W06 checklists on the owner's and second person's real devices, with screen recordings or Instruments traces attached to the handover |
| Performance | The audit's benchmark scale (10k/50k synthetic) for server changes; iOS scroll and launch gates in I03 |
| Security | M06 review, `pip-audit`, `npm audit`, manual test of lockout, revoke and setup-code expiry |

---

## 10. Risk register

| Risk | Mitigation |
| --- | --- |
| Sideloadly can't install or refresh the Watch app | S00 proves it first; fallback is Xcode direct install or a paid account with TestFlight; W-packages are blocked until resolved |
| Free Apple account: 7-day expiry and 3-app limit | G-5 recommends a paid account; keep bundle IDs minimal (complication is optional) |
| Watch can't reach the tailnet without the phone | The phone is the gateway (W02); the direct path is opportunistic only |
| Migration damages the existing single-user state | Additive migrations, fixture tests, stopped-state backup, `verify_state_migration.py`, rollback image retained (existing deployment tool) |
| Lockout of the only owner | CLI `reset-password` via `docker exec`; documented in operations |
| Device-copy cache fills appdata | Size cap, LRU, pause during acquisitions, owner-visible usage |
| Shared-file quality conflicts surprise a user | G-7 rule shown in the UI ("Kept at FLAC because it's also in another library") |
| A sole member deletes something by mistake and the files go | Deletion goes through recoverable trash (existing recovery safeguards); 30 s undo toast; the confirmation states clearly when files will be deleted |
| Opus/Ogg files can't play natively on iOS | Use the M10 device copy automatically for those formats |

---

## 11. Updates to make in blueprint.md once approved

- Roadmap table: add A01–A03, T01, B01–B02 ahead of H01. Replace H01/H02/H03 with M00–M07 (keeping their IDs as aliases). Add X01–X03 and M10. Expand P01 into S00 and I01–I09, and P02 into W01–W06, each linking to this document.
- Product contract: replace "Do not add public exposure or new authentication assumptions" with "No public exposure. Household app accounts (owner/member) with passwords and per-device tokens, per this roadmap."
- Decision dialogue: append the 6 October 2026 owner decisions G-1 to G-4.
