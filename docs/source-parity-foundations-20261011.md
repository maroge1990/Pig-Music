# Source-parity implementation: first foundation increment

11 October 2026, Australia/Melbourne. **Implemented locally; not deployed.**

This increment starts the [source-parity build specification](download-source-parity-assessment-20261011.md). It implements registry and native-audio foundations from SP01/SP02. The YouTube, SoundCloud and Monochrome adapters, extractor network boundary, provider health/cooldowns and live-source acceptance remain subsequent work. They are not registered or enabled by this increment.

## Delivered code

- `server/providers/`: immutable capability registry for the existing four sources. Both settings validation and downloader eligibility use it. Existing source selections/order/defaults remain unchanged; duplicate selected sources are normalised without changing order. Unsupported provider IDs and file extensions are rejected.
- Opt-in `native_standard` system/artist/album preference and lossless fallback. Measured floors are MP3 120, AAC 112, Opus 96 and Vorbis 128 kbps; valid FLAC is eligible. Existing codec-specific profiles and exact MP3 downgrade behaviour remain. New UI controls describe codec retention and player compatibility.
- Native Opus/Vorbis tagging and canonical Vorbis codec names; Pig Music provenance is now readable alongside legacy Music Grabber tags. Published acquisitions record a sanitised provider/quality/codec/container/measurement record without transfer URLs or credentials.
- Read-only bounded audio-packet bitrate measurement when Opus/Vorbis container inspection has no bitrate. Container overhead is excluded; missing measurements remain unknown.
- WebM-to-Ogg Opus stream-copy helper, with a single Opus stream requirement, local-file protocol restriction, temporary output and no overwrite. This helper is ready for the future extractor adapter; existing sources do not need remuxing. The test proves identical compressed packet hashes. WebM millisecond timestamp rounding can change terminal padding by less than 1 ms; decoded sample-count drift is bounded in the test rather than described as bit-identical PCM.
- Bounded/cancellable FFmpeg/FFprobe process runner. POSIX process groups are terminated on cancellation/deadline/output overflow, including descendants whose parent has exited. Final tagged audio is fully decoded before publication/hash computation. No runtime encoder path was added.
- Candidate matching rejects known conflicting recording/release IDs and disjoint ISRCs before name matching. Web-upload title/uploader normalisation remains provider-adapter work.
- Household arbitration gives strict MP3 128 precedence over the flexible native target at the same rank. Higher legacy/lossless targets retain precedence. Unknown-quality scanned files remain protected from automatic replacement; measured native acquisitions can later improve to a requested lossless target.
- Atomic schema migration **0007** extends the personal quality-preference constraint and copies existing rows unchanged. Existing migration ledger entries and foreign keys remain. Interrupted DDL rolls back. Existing defaults and queued payloads are not rewritten.

## Shared workspace / Swift integration

Another agent is developing the Swift app. This increment does not edit any Swift source, package, project or schema copy. Existing web/backend/native changes present at the start of this work were retained.

The server OpenAPI contract now includes `native_standard` as an accepted personal quality preference. `scripts/export_openapi.py` has a new `--server-only` flag to export/check `api/openapi.v1.json` without changing the Swift agent's copy:

```sh
.venv/bin/python -m scripts.export_openapi --server-only
.venv/bin/python -m scripts.export_openapi --check --server-only
```

The Swift agent should account for the new preference in any exhaustive enum handling. A later read-only check found that the concurrently edited Swift schema already contains `native_standard`; this task did not write that file. The default cross-copy contract check still enforces equality; it was not weakened. Both schema copies must remain synchronised for release CI.

Schema 7 state must not be opened with an older schema-6-only release. A future deployment must retain the stopped-state backup and use the existing migration/release procedure for rollback. This work has not touched live state or exercised a production backup.

## Verification

New tests use generated MP3/AAC/Opus/Vorbis/FLAC files in disposable directories. They exercise native validation/tagging/publication/scan/restart, actual packet-preserving remux, container rejection, known identity conflicts, source eligibility/default preservation, shared preferences, unknown-quality protection, migration rollback/row preservation and child-process cancellation/limits.

Verification completed so far:

- Final focused acquisition, native-audio, household, migration, scanner, playback and OpenAPI checks: **69 passed in 82.96 seconds**.
- Full backend rerun against the final code: **268 passed in 363.39 seconds**.
- Web regression suite: **11 passed**; production TypeScript/Vite build passed; Prettier checks passed.
- Black check passed across all 139 Python files in server/tests/scripts; both server-only and default server/Swift OpenAPI freshness checks passed; diff-whitespace and documentation-link checks passed.

No new source transfer, candidate Linux image, browser interaction journey or physical player acceptance was performed. This is local foundation verification, with synthetic media and disposable SQLite state.

## Next implementation boundary

Complete the provider request/context/typed-failure and validated-network layer, then build the extractor adapters and Monochrome HTTP adapter. Reuse this registry and native validation path; add a provider to the registry only with its implemented resolver/transfer and tests. Keep source enablement opt-in and record metadata and actual transfer acceptance separately.
