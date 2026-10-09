# Pig Music platform assessment, 9 October 2026

Scope: Pig Music only. The review covered brand and visual consistency, settings consistency, architecture and integration, and UX and feature gaps. This is a review: no code, settings or live state were changed.

## Owner decisions, 9 October 2026

These decisions were recorded after the first draft. The findings and recommendations below already reflect them.

1. **Two artist pages, by design.** The **library** artist and album pages show what you already have (on the server or the device) and are where you go to *play*. The **Search/catalogue** artist page shows what you *could* have or are missing, and is where you go to *find* music. Recommendations improve each page for its purpose and the link between them; they do not merge the pages.
2. **Favourites is just a special playlist.** The 89-song "Favourites" under Playlists is an imported Apple playlist that happens to share the name. No title-based special-casing should be added.
3. **Members set their own quality.** Per-person, per-artist and per-album quality stays available to members.
4. **Cloudflare Web Analytics:** use whichever option is more efficient and gives the better experience. Recommendation: turn it off (see D4).
5. **Home order and locality:** recommendations should sit above global popularity, and popularity should be local where possible (for example, Australia).
6. **Artist identity fallback:** a one-time owner picker is acceptable when tags and album overlap can't decide (R2 step 3).
7. **Popularity source and scope:** use Apple only, and show **Popular in Australia** alone on Home for now (no worldwide row), then review. Remove ListenBrainz where Apple can replace it; see "ListenBrainz scope" below.

## Method and evidence

- **Live, read-only:** `https://music.markrogers.au`, signed in as the owner. Every member route and all six Admin tabs were checked at 1366 px in light and dark, and Library, Home and Admin at 375 px. The console and network log were captured. Read-only GETs were made against `/api/v1/home/recommended`, `/api/v1/library` and `/api/artists/{id}/catalogue`. Nothing was saved, requested, cleared or scanned.
- **Source:** `main` at `b3b6b5f`.
- **Brand:** the Pig-Branding 1.5.1 guide (§4–§9), `docs/integration.md` and the product assets.
- **External checks:** ListenBrainz LB Radio, MusicBrainz artist search and the Apple Music AU chart feed, all called directly and read-only.
- **Not covered:** playback and the mini player, submitting a request, a member-role session (member gating was read from code, `AppShell.tsx:188,218`), physical iPhone (V01) and the Swift spike.

## What is working well

- **Brand fidelity is high.** Every shipped brand file matches the Pig-Branding `pig-music` product files byte for byte. `pig-radiance.css` is identical to the kit and `.pig-canvas-bloom` sits on `body`. Tokens are generated from the 1.5.1 JSON. The dark theme is clean.
- **The structure is clear.** Navigation is Home · Search · Library · Downloads · Account · Admin. Admin is last and hidden for members, and owner extras sit at the bottom of shared views.
- **Accessibility basics are in place.** Icon-only states carry labels, song buttons are named, and there is no horizontal scroll at 375 px.
- **Engineering discipline is strong.** The OpenAPI contracts for Swift and the server are byte-identical. The project has migrations, a reproducible deployment with rollback and a substantial backend test suite.

## Findings

Severity: **High** means it misleads the user or breaks a core journey. **Medium** means a visible inconsistency or a maintainability risk. **Low** means polish.

### A. UX and feature gaps

| # | Sev | Finding | Evidence |
|---|---|---|---|
| A1 | Medium | **The library → catalogue link is hidden, and some artists dead-end.** *Corrected after verification:* the library page uses the strong resolver (`GET /api/v1/catalogue/library-artists/{id}`, which uses release credits and then album overlap). It resolves Pink Floyd, The Killers, Coldplay and Arcade Fire live. Only the legacy `GET /api/artists/{id}/catalogue` (used by the warmer) and Home use the weak exact-name rule, which returns 409 for Pink Floyd and The Killers. Two problems remain: the link is hidden ("Select the artist name for the full catalogue"), and unresolved artists (for example Persona 5) get a 409 with no way to choose. | `routes/discover.py:92`, `routes/catalogue.py:167`, live checks |
| A2 | High | **Home recommendations never populate.** Root cause below. Recommended also sits *below* global Popular, and three empty sub-sections render with copy that tells a 178-artist library to "Save artists to your library", which breaks the blueprint's "empty headings stay hidden" rule. | `server/home.py:137-260`, `Home.tsx:131-136` |
| A3 | High | **The library album page lacks cover art and an artist link.** It also gives no year or summary. This is the *play* page, so it should be the richest view of what you own. A related artwork request (`/api/library-artwork/albums/…`) returns 404 and is retried every 60 s. | Neon Bible, library view |
| A4 | Medium | **The two artist pages are hard to tell apart and to move between.** Opening an artist from Library and following its catalogue link moves the nav highlight to **Search**. The library page has no hero, play or shuffle for the artist, or dates. The catalogue page doesn't show which releases you already own, and "Download album" is disabled without a reason ("Arcade Fire ·" has an empty trailing field). | Arcade Fire, both views |
| A5 | Medium | **Search results are uneven.** Library songs show monogram placeholders instead of album covers. "Discover" is a plain text list with no artwork or type, and no marker for the artist already in your library. The search field has no accessible name. | `#/search?q=Radiohead` |
| A6 | Medium | **Downloads reads as a raw log.** It shows one row per track (13 rows for one Meteora request), with no artwork, time or grouping. "Clear downloads" (member) and "Clear all" (admin) are worded and scoped differently. | `#/downloads`, `#/admin/downloads` |
| A7 | Medium | **Account › Your devices** lists six identical "Browser · web" rows, with no last-used time, no agent and no "this device" marker. | `#/account` |
| A8 | Low | **The Favourites hint mentions a heart that rows don't show.** The empty state says "Tap the heart", but song rows have no heart; Favourite is only in the "…" menu. | Library › Favourites |
| A9 | Low | **Library albums show "N songs" but no artist.** There is no sort or filter on any library tab, and no Songs tab. | `#/library/albums` |

### Root cause: empty recommendations (A1, A2)

`HomeDiscovery.recommended` seeds only from the **top 3 library artists by track count**. Here those are Pink Floyd, Persona 5 and The Killers. Each seed is resolved by a MusicBrainz name search that accepts only a single exact match:

| Seed | Exact-name matches | Result |
|---|---:|---|
| Pink Floyd | 2 (the band, plus an "online collective") | rejected |
| Persona 5 | 0 (a game soundtrack, not an artist) | rejected |
| The Killers | 7 (the American band, a UK punk band, …) | rejected |

With zero seeds, the feed returns empty lists *without* setting `unavailable`, so the UI shows the "save artists" message. ListenBrainz itself works: LB Radio returned The Shins, Interpol and The Strokes for Arcade Fire without a token. `home.py` has its own weak copy of the resolver.

**A stronger resolver already exists** in `routes/discover.py` (`saved_identity`). It uses the `musicbrainz_release_id` that scanned and downloaded tracks carry, then album-title overlap, and it is what the library page calls. Home and the legacy warmer route should use it too.

### B. Settings consistency

| # | Sev | Finding | Evidence |
|---|---|---|---|
| B1 | High | **Quality has five different vocabularies.** The one quality model is presented through 5 components with 3 label sets, 2 orderings and 2 "inherit" phrasings. Examples: "MP3 128 / MP3 320 / AAC 256 / Lossless" (Account, artist, album), "MP3 320 kbps / MP3 128 kbps / AAC 256 kbps or better / FLAC lossless (Soulseek)" (Admin system), and "FLAC lossless / AAC 256 kbps / MP3 128 kbps" (Admin album). "Use household default" (Account) sits beside "Use my general preference" (artist and album). Member menus list AAC 256 between MP3 320 and Lossless, though the fallback rule ranks it lowest. Members keep these controls (decision 3), so the vocabulary matters more. | `AccountSettings.tsx:182`, `PersonalQuality.tsx:55`, `AlbumQuality.tsx:88`, `SystemView.tsx:153`, `QualitySettings.tsx:32` |
| B2 | Medium | **Settings are scattered across tabs.** Download settings sit below a 40+ row queue on Admin › Downloads. The Plex account is in Account, not Integrations. Source IDs appear in raw lowercase (`soulseek`, `freemp3cloud`, `zvu4no`, `jiosaavn`). On Integrations, the remote-playback explanation and the "Get a … key" links sit under the next field rather than their own. | Admin tabs |
| B3 | Medium | **Status tiles disagree with reality.** Overview shows "Remote access: Existing Tailscale connection" while the app is used through the Cloudflare tunnel. Indexed counts disagree too: 1,408 tracks (Overview, Library) and "1395 files indexed" (Server library). | `#/admin`, `#/admin/library` |
| B4 | Low | **The quality card sits at the top of every library artist and album page.** Keep it (decision 3), but present it as a compact control near the title rather than a full-width card above the music. | Library artist and album pages |
| B5 | Low | **Apple XML import has two entry points with different UI:** Library › Playlists and Admin › Library migration. | — |

### C. Brand and visual consistency

| # | Sev | Finding | Evidence |
|---|---|---|---|
| C1 | Medium | **The interface font varies by device.** `Base.css` lists `Inter` first but never ships it (no `@font-face`). Guide §5 says system sans or a licensed web font, so choose one deliberately. | `Base.css:5` |
| C2 | Medium | **Page header and card rhythm is inconsistent.** Titles sit tight against their subtitle and first label on sign-in, Search, Library and the Account cards, but are spaced well on Home and Admin. There is no shared PageHeader or Card pattern. | Screens |
| C3 | Medium | **The same state has three treatments.** "In your library" is a cloud-check icon in song rows, a green pill in Downloads, and an eyebrow on artist pages. A cloud suggests "online only" for files that live on the NAS. Admin uses the rose action colour for a status chip, against guide §4. | Song rows, Downloads, Admin |
| C4 | Medium | **Dates and numbers use three formats.** Release dates are ISO (`2010-07-03`), admin times are `06/10/2026, 15:22:42`, and other times are relative ("26 min ago"). Numbers show both `1395` and `1,408`. | Various |
| C5 | Low | **Tab strips show a visible scrollbar track at phone width.** *Corrected:* the side gutter is the conventional 16 px (computed `padding-left` on `.personal-main`). The earlier 10 px reading came from a scaled screenshot. | 375 px |
| C6 | Low | **Installed app and tab title issues.** The manifest hard-codes dark `background_color` and `theme_color`, so a light-mode installed launch flashes dark. There is no maskable icon. `document.title` is "Pig Music · Your library" on every route. | `manifest.webmanifest` |
| C7 | Low | **The splash and mascot are used inconsistently.** The animated `.pig-splash` covers the whole sign-in page (guide §8 intends it for loading surfaces). The mascot appears in only one empty state. | `AppShell.tsx:161` |

### D. Architecture and integration

| # | Sev | Finding | Evidence |
|---|---|---|---|
| D1 | High | **Two API generations are called at once.** A single library album view calls both `/api/v1/albums/{id}` and `/api/albums/{id}`. The artist page calls two acquisition endpoints and fetches popularity twice. Library loads `/api/library` and `/api/v1/library`. Admin is entirely unversioned (`/api/queue`, `/api/settings/*`), so the Swift contract can't cover it. This is roadmap U01-4. | Network log |
| D2 | High | **Artist identity is resolved in three places with two different rules.** `routes/discover.py:92` is strong (release credits, then album overlap). `routes/catalogue.py:167` (warmer) and `home.py:149` use exact-name uniqueness only. This is the root of A2 and part of A1. | — |
| D3 | Medium | **Two live-update streams plus polling.** The shell opens `/api/v1/events`. Admin opens a second `/api/events`, and its effect is keyed on `[section]`, so it reconnects on every Admin tab change. On top of that there is 15 s fallback polling and several other intervals. | `AppShell.tsx:315`, `AdminTools.tsx:168,195` |
| D4 | Low | **Console errors appear on every load.** The CSP (`script-src 'self'`) blocks the beacon that Cloudflare Web Analytics injects, so analytics already collects nothing and only adds a request and an error. **Recommended: turn off Web Analytics for `music.markrogers.au` in Cloudflare** rather than loosening the CSP. This is a dashboard change for the owner. | Console |
| D5 | Low | **Dead legacy code.** `POST /api/membership` still reads the pre-migration `pig-favourites` ID, so it would always report "not favourited". The client no longer calls it; remove it. | `app.py:626` |
| D6 | Low | **Two token naming schemes.** `tokens.css` uses unprefixed names while the kit uses `--pig-*`. `docs/brand-integration-reference.md` still says 1.4.0. | — |
| D7 | Medium | **The documentation no longer matches the live state.** The blueprint header says "Updated 7 October" but contains 9 October entries, and its "not deployed" status lines conflict with what is live. There are 25+ dated delivery documents. Playwright smoke tests (Q02) are still outstanding. | `blueprint.md`, `docs/` |

## Home discovery: proposed design

**Order:** Recently added → **Recommended for you** → **Popular in Australia** (decision 7: no worldwide row for now).

**Recommendations (fixes A2):**

1. Resolve seed artists through the shared resolver (R6), not a name search.
2. Pick seeds from the whole library, not the top 3. Skip compilation-only and soundtrack "artists" such as Persona 5. Weight by track count but rotate daily, so the feed changes and isn't always Pink Floyd. Collect 5–8 seeds.
3. Keep LB Radio (it works without a token), plus "Because you saved X". Exclude artists already in the library by MBID, not only by name.
4. Distinguish three states: *no seeds resolved* (explain, and link to Admin to resolve artists), *provider unavailable* (retry later), and *ready*. Hide empty sub-sections.

**Local popularity:**

| Source | Region support | Key | IDs | Assessment |
|---|---|---|---|---|
| **Apple Music charts feed** (`rss.marketingtools.apple.com/api/v2/au/music/most-played/{n}/songs.json` and `/albums.json`) | Per storefront (`au`, `nz`, `gb`…) | None | Apple IDs plus title and artist, with artwork | **Recommended primary.** Verified live today: AU Top Songs and Top Albums updated 9 Oct 2026. Needs title + artist → MusicBrainz matching, cached daily. It is Apple's marketing feed, so link-outs aren't required for private use, but check the terms if usage widens. |
| Last.fm `geo.getTopArtists` / `geo.getTopTracks` | Per country | Free API key | Often includes MBIDs | Good optional second source. Better for *artists*, and its MBIDs reduce matching work. |
| ListenBrainz sitewide stats (current) | Global only | Optional | MBIDs | Keep as the "worldwide" row or the fallback. |
| Spotify charts or playlists | Per country | OAuth app; editorial playlists restricted since late 2024 | — | Not recommended. |

Make the region an Admin › Integrations setting (default `au`), with the source shown as the section caption, for example "Apple Music · Australia · today".

**Decided (decision 7):** Apple only, Australia only. Home order is Recently added → Recommended for you → Popular in Australia. Apple's feed has **no worldwide chart**: `global`, `world` and `ww` return HTTP 500, and only country storefronts such as `au`, `us` and `gb` exist. A worldwide row would need another source, so leave it out unless the review asks for it.

### ListenBrainz scope

ListenBrainz is used for three things today, and Apple can replace only one of them:

| Use | Where | Token | Apple replacement? | Action |
|---|---|---|---|---|
| Sitewide weekly Popular | Home "Popular this week" (`home.py` `popular`) | Optional | **Yes**, Apple AU charts | **Remove** |
| Similar artists (LB Radio) | Home recommendations (`home.py` `recommended`) | Not needed (verified) | No: the Apple feed has no similarity data | **Keep**; it is the only recommendation source |
| Per-artist popular songs and albums | Catalogue artist page "Popular songs" and "Popular first" album order (`popularity.py`) | **Required** (401 without one, verified) | No: the Apple feed has no per-artist data | **Keep** the token setting in Integrations |

Removing ListenBrainz entirely would lose recommendations and the artist page's popularity ordering. Recommended: remove only the Home sitewide feed and its code path. Update the Integrations help text to say the token powers per-artist popularity, and that recommendations work without it.

## Prioritised recommendations

### Priority 1: fix what misleads (about 2–4 days)

1. **R1 · Fix the library album page:** add the cover, the artist link (to the *library* artist page) and a year or track summary. Fix the `library-artwork` 404s (A3).
2. **R2 · Add a shared artist identity resolver** (D2, unblocks A2 and fixes A1). Extract the strong `discover.py` resolver (release credits, then album overlap) into one module. Use it from Home and the legacy warmer route. Add a one-time owner picker, stored in the existing `library-artist:` document, for the cases it can't decide. Replace the hidden name-link with a visible "Find more by {artist}" action.
3. **R3 · Rebuild Home discovery as designed above:** Recommended above Popular, wider rotating seeds, explicit states and hidden empty sections (A2).
4. **R4 · Make the admin status truthful:** report remote access from the actual configuration and use one indexed-count source and format (B3, C4).
5. **R5 · Quick wins:** add a search field label, per-route `document.title`, a light/dark-aware `theme-color` and a maskable icon, "Tap the heart" copy that matches the UI or a heart on rows, and removal of `/api/membership`. **Owner:** turn off Cloudflare Web Analytics (A5, A8, C6, D4, D5).

### Priority 2: one vocabulary, one component per concept (about 3–5 days)

6. **R6 · Add a single `QualitySelect` component** driven by server-provided options (value, label, rank, availability), with one order (highest to lowest), one inherit phrase that names what it inherits ("Use household default: MP3 320"), and no source names in labels. Used by Account, artist, album and Admin. Shown as a compact control on library pages (B1, B4).
7. **R7 · Add a state system:** one component each for In library, Requested, Downloading and Failed (icon, label, status token). Drop the cloud metaphor and use status tokens, not rose, for status (C3).
8. **R8 · Add PageHeader and Card primitives** on the 4/8/12/16/24/32 rhythm, and migrate sign-in, Search, Library, Account and Admin (C2).
9. **R9 · Add shared formatters:** `Intl.DateTimeFormat('en-AU')`, relative time and `Intl.NumberFormat` (C4).
10. **R10 · Settle on a typeface:** drop `Inter` for the system stack, or self-host a licensed file (C1).
11. **R11 · Restructure Admin settings:** separate Queue from Download settings, title-case source names with descriptions, move Plex under Integrations (or link to it), and put help text under the right field (B2).

### Priority 3: sharpen each page for its purpose (about 1–2 weeks)

12. **R12 · Make the two-page model explicit** (A4; replaces the earlier "merge" proposal).
    - **Library artist page (play):** add a hero using the same portrait or background as the catalogue page, plus Play all and Shuffle, owned albums with years, and owned songs. Add a clear secondary action, "Find more by {artist}" or "See what's missing", that opens the catalogue page and keeps the **Library** nav highlight when entered from Library.
    - **Catalogue artist page (find):** mark releases you already own (badge or "x of y songs"), link owned releases back to the library album page, and explain disabled actions ("Already in your library").
13. **R13 · Request-centred Downloads:** group by request with artwork, progress and time, show source and quality on expansion, use one Clear behaviour, and collapse duplicates (A6).
14. **R14 · Improve Search:** add type-ahead, album art in song rows, and artwork, type and an "in library" marker on Discover (A5).
15. **R15 · Make device sessions identifiable:** show agent or platform, last used, "This device", and "Sign out other devices" (A7).
16. **R16 · Add local popularity:** Apple Music AU charts replace the ListenBrainz sitewide feed on Home (Popular in Australia only). Add an Admin region setting, defaulting to `au`. Remove the ListenBrainz sitewide code path and keep LB Radio and per-artist popularity (see "ListenBrainz scope"). Because this replaces a live Home section, ship it together with R3.

### Priority 4: platform hygiene (alongside, before the native Admin tab)

17. **R17 · Finish U01-4:** move every client call to `/api/v1`, including Admin. Keep the legacy routes as aliases for one release, then remove them. Add a test that rejects unversioned `/api/` paths in the client (D1).
18. **R18 · One event stream:** Admin consumes the shell's `/api/v1/events`, with no `[section]` reconnect and one visibility-aware fallback poll (D3).
19. **R19 · Add Playwright smoke tests** (Q02 remainder): library album with a cover, library artist → catalogue for an ambiguous name (Pink Floyd), Home with recommendations above popular and no empty headings, and Admin status. Run at 1366 px and 375 px in both themes (D7).
20. **R20 · Documentation truth pass:** fix the blueprint header and deployment status, record which release is live, and archive the dated delivery docs (D7).
21. **R21 · Token alignment:** emit `--pig-*` aliases from `generate_brand_tokens.py` and refresh `brand-integration-reference.md` to 1.5.1 (D6).

### Polish backlog

Phone gutter to 16 px and hidden tab-strip scrollbar (C5). Splash only on loading surfaces, with the mascot used consistently across empty states (C7). A single Apple XML import entry point (B5). Artist names on album tiles, plus sort and a Songs tab in Library (A9).

## Remaining owner decisions

None outstanding. Decisions 1–7 above cover the open questions. Review Home after "Popular in Australia" has been live for a while.
