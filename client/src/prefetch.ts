/** Pre-caching: the service worker keeps artwork and catalogue pages, and
 * these helpers ask it to fetch what the person is likely to open next. */
import { apiFetch } from "./api";
import { catalogueCover, coverUrl } from "./Cover";

export function registerCache() {
  if (!("serviceWorker" in navigator)) return;
  void navigator.serviceWorker.register("/sw.js").catch(() => {
    /* The app works without a cache. */
  });
}

function warm(urls: string[]) {
  const worker = navigator.serviceWorker?.controller;
  if (worker && urls.length) worker.postMessage({ type: "warm", urls });
}

/** The image width the browser will choose for a slot this wide. */
function width(cssPixels: number) {
  const needed = cssPixels * (window.devicePixelRatio || 1);
  return [128, 256, 512, 1024].find((w) => w >= needed) || 1024;
}
const card = () => width(Math.min(window.innerWidth / 2, 200));
const row = () => width(48);

/** Artwork for a set of covers at the size their cards will request. */
export function warmCovers(
  sources: (string | null | undefined)[],
  small = false,
) {
  const size = small ? row() : card();
  warm(sources.flatMap((src) => (src ? [coverUrl(src, size)] : [])));
}

type Popular = {
  songs: { release_id: string }[];
  albums: { id: string }[];
};
type Releases = { releases: { id: string }[] };

/**
 * Get an artist page ready. "Essential" is the photograph, logo, portrait and
 * popular list; "full" adds the album list and every visible cover.
 */
export function warmArtist(id: string, full = false, name = "") {
  const base = `/api/catalogue/artists/${id}`;
  warm([
    `${base}/background?r=0&w=1024`,
    `${base}/background?r=0&w=512`,
    `${base}/background?r=0&w=128&soft=true`,
    `${base}/logo?r=0`,
    coverUrl(`${base}/artwork`, width(160)),
  ]);
  void apiFetch(`/api/v1/catalogue/artists/${id}/popularity`)
    .then((r) => (r.ok ? (r.json() as Promise<Popular>) : null))
    .then((popular) => {
      if (!popular || !full) return;
      warmCovers(
        popular.songs
          .slice(0, 5)
          .map((s) => catalogueCover("release", s.release_id)),
        true,
      );
    })
    .catch(() => {});
  if (!full) return;
  // The same address the artist page asks for, so it opens from this answer.
  void apiFetch(
    `/api/v1/catalogue/artists/${id}/releases?kind=album&offset=0&name=${encodeURIComponent(name)}`,
  )
    .then((r) => (r.ok ? (r.json() as Promise<Releases>) : null))
    .then((data) => {
      if (data)
        warmCovers(
          data.releases
            .slice(0, 24)
            .map((g) => catalogueCover("release-group", g.id)),
        );
    })
    .catch(() => {});
}

/** Run after the current screen has settled, so it never competes with it. */
export function whenIdle(task: () => void) {
  const idle = (window as { requestIdleCallback?: (fn: () => void) => number })
    .requestIdleCallback;
  if (idle) idle(task);
  else setTimeout(task, 400);
}
