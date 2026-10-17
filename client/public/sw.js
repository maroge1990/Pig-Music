/* PigMusic offline cache: artwork and slow catalogue pages only.
 *
 * Artwork is cache-first: an image address never changes meaning (revisions
 * and sizes are in the query). Shared catalogue lists are served from cache at
 * once and refreshed in the background for next time. Pages that carry this
 * person's saved/requested state or recommendations always ask the server
 * first and fall back to the cache only offline, so a change made elsewhere is
 * never hidden behind an old copy. Nothing from the library, playback or
 * account endpoints is stored. Everything is cleared when the person signs
 * out. Storage stays under BUDGET, oldest entries first.
 */
const IMAGES = "pig-images-v1";
// v2: personal pages from v1 were served stale; start them afresh.
const DATA = "pig-data-v2";
const BUDGET = 500 * 1024 * 1024;
const LEDGER = "/__pig-cache-ledger";

const artwork = [
  /^\/api\/artwork\/[^/]+$/,
  /^\/api\/v1\/artwork\/[^/]+$/,
  /^\/api\/library-artwork\/(albums|artists)\/[^/]+$/,
  /^\/api\/catalogue\/artwork\/(release|release-group)\/[^/]+$/,
  /^\/api\/catalogue\/artists\/[^/]+\/(artwork|background|logo)$/,
  /^\/api\/artists\/[^/]+\/(background|logo)$/,
];
/** Shared catalogue lists: the same for everyone. */
const pages = [
  /^\/api\/v1\/catalogue\/artists$/,
  /^\/api\/v1\/catalogue\/artists\/[^/]+\/(popularity|releases)$/,
];
/** Include this person's library state or recommendations. */
const personal = [
  /^\/api\/v1\/home\/(popular|recommended)$/,
  /^\/api\/v1\/catalogue\/groups\/[^/]+\/editions$/,
  /^\/api\/v1\/catalogue\/releases\/[^/]+$/,
];

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((n) => n.startsWith("pig-") && ![IMAGES, DATA].includes(n))
            .map((n) => caches.delete(n)),
        ),
      )
      .then(() => self.clients.claim()),
  ),
);

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== location.origin) return;
  if (artwork.some((p) => p.test(url.pathname)))
    event.respondWith(cacheFirst(request));
  else if (pages.some((p) => p.test(url.pathname)))
    event.respondWith(staleWhileRevalidate(request, event));
  else if (personal.some((p) => p.test(url.pathname)))
    event.respondWith(networkFirst(request));
});

self.addEventListener("message", (event) => {
  const message = event.data || {};
  if (message.type === "clear")
    event.waitUntil(
      Promise.all([caches.delete(IMAGES), caches.delete(DATA)]).then(() => {
        ledger = null;
      }),
    );
  else if (message.type === "warm" && Array.isArray(message.urls))
    event.waitUntil(warm(message.urls));
});

async function cacheFirst(request) {
  const cache = await caches.open(IMAGES);
  const hit = await cache.match(request, { ignoreVary: true });
  if (hit) return hit;
  const response = await fetch(request);
  if (
    response.ok &&
    (response.headers.get("content-type") || "").startsWith("image/")
  )
    await store(cache, request, response.clone());
  return response;
}

async function staleWhileRevalidate(request, event) {
  const cache = await caches.open(DATA);
  const hit = await cache.match(request, { ignoreVary: true });
  const fresh = fetch(request).then(async (response) => {
    if (
      response.ok &&
      (response.headers.get("content-type") || "").includes("json")
    )
      await store(cache, request, response.clone());
    return response;
  });
  if (hit) {
    event.waitUntil(fresh.catch(() => {}));
    return hit;
  }
  return fresh;
}

/** The server's answer, or the last one when offline. */
async function networkFirst(request) {
  const cache = await caches.open(DATA);
  try {
    const response = await fetch(request);
    if (
      response.ok &&
      (response.headers.get("content-type") || "").includes("json")
    )
      await store(cache, request, response.clone());
    return response;
  } catch (error) {
    const hit = await cache.match(request, { ignoreVary: true });
    if (hit) return hit;
    throw error;
  }
}

/** Fetch a list of addresses into the cache, a few at a time, quietly. */
async function warm(urls) {
  const queue = urls.filter((u) => typeof u === "string").slice(0, 400);
  const worker = async () => {
    while (queue.length) {
      const url = new URL(queue.shift(), location.origin);
      if (url.origin !== location.origin) continue;
      const request = new Request(url, { credentials: "same-origin" });
      try {
        if (artwork.some((p) => p.test(url.pathname)))
          await cacheFirst(request);
        else if (
          pages.some((p) => p.test(url.pathname)) ||
          personal.some((p) => p.test(url.pathname))
        ) {
          const cache = await caches.open(DATA);
          if (!(await cache.match(request, { ignoreVary: true })))
            await staleWhileRevalidate(request, { waitUntil() {} });
        }
      } catch {
        /* Warming is best effort. */
      }
    }
  };
  await Promise.all([worker(), worker(), worker()]);
}

// Approximate sizes by address, oldest first, persisted beside the images.
let ledger = null;
async function readLedger() {
  if (ledger) return ledger;
  const saved = await (await caches.open(DATA)).match(LEDGER);
  ledger = saved ? await saved.json() : { entries: [], total: 0 };
  return ledger;
}
let saving = null;
function saveLedger() {
  saving ||= new Promise((resolve) =>
    setTimeout(async () => {
      saving = null;
      const cache = await caches.open(DATA);
      await cache.put(LEDGER, new Response(JSON.stringify(ledger)));
      resolve();
    }, 2000),
  );
  return saving;
}
async function store(cache, request, response) {
  const body = await response.clone().arrayBuffer();
  await cache.put(request, response);
  const book = await readLedger();
  const name = request.url;
  book.entries = book.entries.filter(([url]) => url !== name);
  book.entries.push([name, body.byteLength]);
  book.total = book.entries.reduce((sum, [, size]) => sum + size, 0);
  while (book.total > BUDGET && book.entries.length) {
    const [oldest, size] = book.entries.shift();
    book.total -= size;
    await Promise.all([
      caches.open(IMAGES).then((c) => c.delete(oldest)),
      caches.open(DATA).then((c) => c.delete(oldest)),
    ]);
  }
  void saveLedger();
}
