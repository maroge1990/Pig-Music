# Testing and delivery checks

Use disposable data and music fixtures. Never point automated tests at live appdata or the real NAS. See [blueprint.md](../blueprint.md) for status and product invariants.

```powershell
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
.venv/Scripts/python.exe -m black --check server tests scripts --workers 1
Set-Location client
npm ci
npm run format:check
npm test
npm run build
```

The build includes strict TypeScript unused-declaration checks. Python formatting excludes vendor source and private work directories. Provider tests use mocked HTTP responses; FFmpeg tests decode real disposable audio. Windows sandbox restrictions may prevent test subprocesses or access to pytest-created temporary directories; use an authorised accessible execution context rather than changing library permissions. The deployment tool repeats backend tests in the actual Linux image with no network/live mounts.

Essential coverage:

- Known edition/recording conflicts, ambiguous matches, compilation/live context and identical-byte memberships.
- Legacy album-ID anchors/preferences after scan-order changes and restart; edition-specific removal cancellation/exclusions/restore.
- Persistent/idempotent queue submission, claim cancellation/clear, interrupted publication, full decoding and quality replacement/fallback semantics.
- Favourite membership without acquisition, batch membership reads without snapshot reparsing, playlist order/duplicates/missing files and Plex ownership/order handling.
- Artist cancellation during awaited metadata cannot submit work or overwrite cancelled state.
- Unavailable/wrong NAS marker permits UI reads but creates no workspace or media paths; the correct marker permits recovery.

Browser checks are required as well: fresh Import opens a chooser; synthetic XML import starts a review without auto-downloading; replacement import works; saved/discovered artist and playlist links survive reload/back; playlist picker focus/Escape work; player artist/album labels remain readable and actionable; saved/queued/downloading/failed states are distinguishable. Use local disposable browser fixtures for mutations. Inspect desktop and phone, light/dark/system appearance, keyboard focus and reduced motion. Physical iPhone scrolling and off-site Tailscale need real-device checks.

For response measurements, record dataset size, sample count and network location. Report warm cached reads separately from cold metadata/image/source resolution. Use at least thirty samples for a p95 claim. Proposed current-dataset gates: cached local browsing p95 under 100 ms and playlist cards under 150 ms. Test indexed matching with 1k/10k/50k metadata fixtures; don't trade matching/validation guarantees for throughput. Check request counts so idle views do not poll every song indefinitely.

```powershell
.venv/Scripts/python.exe scripts/benchmark_library.py
.venv/Scripts/python.exe scripts/benchmark_api.py --url http://192.168.1.203:8765 --samples 30 --output .localdata/api-performance.json
```

The API benchmark uses the current household artist ID by default; supply `--artist` for a different fixture/deployment. It only performs GET requests, including explicit organisation review. It does not prove cold metadata/provider performance. Private raw delivery samples are retained under `.localdata/review-20261006/`; the portable summary and deployed image are in the blueprint.

`deploy_unraid.py` also runs `verify_state_migration.py` against a read-only stopped-state backup copied into temporary container storage, without NAS/network access. It checks existing track counts, album links and durable database rows, allowing only the new edition-anchor document. A migration failure aborts deployment and restores the prior container; inspect the result before reporting success.

Each handover must state which checks actually ran, the image tested/deployed, rollback location and remaining checks. Prior passing milestones are historical evidence, not substitutes for candidate verification.

## Artwork scaling

Run `python scripts/benchmark_cover_store.py` against disposable fixtures. It tests legacy migration and warm refresh with distinct artwork at 10k and 50k, records per-process peak RSS, and asserts the A01 10k limits. Repeat in the candidate Linux image with a 1 GB memory limit before release. See [A01 evidence](a01-cover-store.md).
