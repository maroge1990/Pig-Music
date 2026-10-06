# Audit delivery: artwork responsiveness and library transport

7 October 2026. Implemented; candidate image and live acceptance are recorded below when complete. Branding remains deferred.

Image requests now read local files only, returning a local content-hash redirect or an uncached 404 immediately. Provider work uses two background workers, a 128-item waiting queue, duplicate suppression and bounded retry records. Local album art remains the artist fallback while portraits are fetched. Successful enrichment changes the artwork feed and refreshes library URLs; missing images retry on one shared visible-page clock. Known artist identities are retained and passed to portrait/background providers.

The recurring full-library/discography provider walk is removed. Startup enrichment submits at most one new/changed album and artist per 15-second pass. Visible image demand also submits work. Existing provider positive/negative caches remain authoritative; failures back off. The queue drops excess demand rather than creating unlimited tasks, and later image retries can resubmit it.

Artwork aliases redirect within this server; catalogue artist covers no longer redirect clients to a third party. Published local masters are content-addressed JPEGs up to 1024 pixels. WebP variants at 128/256/512/1024 pixels (plus a 1600 request ceiling that does not upscale) are generated once on local demand, off the event loop, with two request slots and serialised image decoding. The master JPEG remains a fallback for clients that request the base URL. Variant URLs use presentation version 1; change that version if encoder settings change. Portrait decode runs in a worker thread, and backdrop downloads use per-key locks plus a three-slot cap.

Content-hash images and Vite hashed assets use one-year immutable caching. Alias URLs revalidate and missing images are never negatively cached by the browser. The hero uses a phone-sized responsive image and a separate 128px pre-blurred layer. Dominant-colour/brand treatments remain deferred.

Library JSON is compressed, with a strong response-content ETag and conditional 304 support. Validators include playlist count and public media settings. Encoded JSON is reused until its inputs change. The browser retains the last body for 304 responses. Album/artist ID maps replace hot linear lookups; media settings cache respects atomic saves and external filesystem updates. Album/artist cards use content visibility; this avoids offscreen painting but is not full DOM windowing. Phone tabs occupy one horizontally scrollable row. Organisation and removed-music views load separately; a tool error boundary retains collection navigation if an old tab cannot load a new release's chunks.

`GET /api/events` provides a latest-state SSE feed with queue/library/artwork revisions and public connection/storage health. One shared collector serves all subscribers, with a one-message buffer per subscriber, heartbeat, cancellation cleanup and a fresh snapshot on reconnect. Queue changes are observed every two seconds; connection health every fifteen seconds. Hidden web pages disconnect; visible pages reconnect and reconcile. Fifteen-second polling is a fallback when streaming is unavailable. This is an observation feed, not a durable event journal or the future authenticated native sync contract. Existing private deployment access remains unchanged.

## Verification

- Backend: 126 tests pass locally, including blocked-provider HTTP responsiveness, queue bounds/deduplication/backoff, lock ordering, safe derivative pruning, validated additive presentation-cache migration, WebP dimensions, immutable/alias policies, conditional reads, playlist validator changes, settings invalidation and feed reconnect/slow-reader cleanup.
- Frontend: conditional-body reuse regression plus existing discography regressions pass; strict TypeScript/build and formatting pass.
- Disposable HTTP fixture, macOS/Python 3.12, 30 warm conditional requests per size:

| Tracks / albums | JSON bytes | Gzip bytes | Conditional median | Conditional p95 | Process peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 10k / 1k | 381,876 | 45,471 | 1.090 ms | 1.678 ms | 116.62 MB |
| 50k / 5k | 1,917,076 | 223,760 | 1.012 ms | 1.288 ms | 339.00 MB |

Peak RSS is cumulative across the two fixtures, not independent migration memory. Reproduce with `python scripts/benchmark_delivery.py`; the registry workflow repeats it inside a 1 GB candidate container alongside the existing artwork migration gate.

- Local HTTP stream delivered its initial current snapshot immediately without gzip buffering. Browser checks used a disposable 500-track library; the 375px tab row stayed on one line with horizontal overflow contained. Physical iPhone responsiveness, remote/Tailscale transport and device installation remain unverified.

## Audit disposition

| Findings | Disposition |
| --- | --- |
| P0-1, P0-2 | A01 delivered previously; original snapshot and rollback retained |
| P0-3, P1-1, P1-2, P1-6 | A02 implemented in this package |
| P1-7, P2-1, P2-2 | A03 implemented; content visibility chosen before full windowing |
| P2-3 | Responsive/pre-blurred hero implemented; colour metadata deferred with branding |
| P2-4, P2-5 | Server-cached fallback and incremental enrichment implemented |
| P2-8, P2-10 | Scrollable phone tabs and shared SSE observation feed implemented |
| P2-7, P3 lazy views | Image/feed modules and operator views separated; wider monolith restructuring remains opportunistic |
| P1-3/4/5, P2-6/9, F-3 | Branding/type/token/icon/placeholder work deferred until owner confirmation |
| P3 repeated saved ticks | Cosmetic simplification deferred with branding |
| P3 TestClient warning | Existing Starlette/httpx deprecation remains; tests pass, migration is separate dependency work |
| P3 origin protection; F-1/F-2 | Secure accounts, API v1/offline sync and private HTTPS remain the account/native foundation milestones; SSE alone does not complete X01 |
| F-4 feature ideas | Suggestions, not audit defects or additional user instructions |

No library audio/tags are modified by these changes. Source review and stopped-state migration precede any live switch; retain the prior image and matching backup.
