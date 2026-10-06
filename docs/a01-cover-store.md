# A01: content-addressed artwork foundation

Implemented 6 October; delivered on Unraid 7 October 2026. Linux container and production-state acceptance passed. Branding remains deferred until the owner confirms completion.

The scanner writes normalised JPEG artwork into appdata `covers/<sha256>.jpg`. Schema 3 snapshots contain track metadata and `cover_sha`, never an image-byte map. Album IDs and edition anchors are unchanged. Each edition selects its own track artwork. Quality replacements retain scanned art from the same edition.

Startup migrates legacy snapshots with image maps one entry at a time using a pinned streaming parser. Images are written and flushed before the replacement snapshot is atomically installed. The original is retained as `library-snapshot.pre-v3.json`; failed parsing, image decoding or snapshot replacement leaves the original active snapshot unchanged. The next scan re-inspects legacy artwork because the old map could not identify its source edition.

Embedded art changes follow audio size/mtime. Folder art has an independent path/size/mtime signature, so changes and removal appear even with unchanged audio. Invalid new artwork produces a scan warning while keeping the audio visible. Both signatures rely on the filesystem reporting modification times; changing bytes while preserving both size and mtime requires a forced rescan strategy outside this package.

Pruning runs weekly after service startup. It serialises with scans, preserves artwork referenced by missing tracks and acquired records, and removes only full 64-character hash filenames after a seven-day grace. Legacy provider cache filenames and rollback backups remain untouched. Expired `missing-artwork:*` and `catalogue:*` documents are pruned with compare-and-delete so a concurrent refresh wins. No music file is edited, moved or deleted.

For explicit maintenance, stop the service first and run:

```sh
python scripts/prune_artwork.py --data /path/to/appdata
```

For rollback to a pre-v3 image, stop all writers and use the matching stopped-state backup through the existing release rollback procedure. Restoring just the legacy snapshot after subsequent library changes can discard new state; compare changes first.

## Local verification

Baseline: 106 backend tests, 2 frontend regression tests and production frontend build passed. Candidate: migration, rollback-failure, edition separation, embedded/folder artwork update/removal, invalid-art and safe-prune regression tests pass. The full candidate count is recorded in the blueprint.

Disposable macOS / Python 3.12 benchmark, 10 tracks per album, distinct noisy 512px JPEG artwork for every album, independent child-process peak RSS. No live NAS/appdata/provider access. These fixtures have larger cover bytes than the original audit, so timings are not a like-for-like comparison.

| Tracks / covers | Legacy snapshot | Schema 3 snapshot | Migration + first refresh | Warm refresh | Peak RSS |
| --- | --- | --- | --- | --- | --- |
| 10,000 / 1,000 | 491.43 MB | 3.01 MB | 6.684 s | 0.169 s | 90.9 MB |
| 50,000 / 5,000 | 2,457.47 MB | 15.37 MB | 34.318 s | 1.209 s | 362.1 MB |

Reproduce with `python scripts/benchmark_cover_store.py`. The Linux image workflow must repeat both sizes under `--memory=1g`; 10k additionally asserts snapshot <25 MB and peak RSS <400 MB. The production-state verifier streams original track metadata and compares it after migration, checks artwork files, and retains its durable-row/album-link checks.

Release acceptance completed on 7 October 2026. The exact image passed 117 backend tests and both benchmark sizes under 1 GB in GitHub Linux and again on Unraid. Final Unraid 10k/50k peak RSS was 88.14/307.04 MB; migration plus first refresh took 35.032/168.943 seconds and warm refresh 0.450/3.163 seconds. A disposable stopped-state migration retained all 1,395 tracks, album links and durable rows before the authorised live switch.

Live schema 3 snapshot is 927,914 bytes with 81 referenced covers, none missing; the original snapshot remains retained. All 1,395 NAS files opened without errors and all 25 managed hashes matched. Five live artwork responses matched their hashes. Existing 98 albums and 27 completed queue entries remain. Exact release and rollback references are in the blueprint. A02 (non-blocking external artwork, derivatives and cache headers) and A03 (payload/grid performance) remain separate planned work.
