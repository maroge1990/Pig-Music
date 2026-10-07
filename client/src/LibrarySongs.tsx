import { useEffect, useState, type ReactNode } from "react";
import { Play, Shuffle } from "lucide-react";
import { api } from "./api";
import { usePlayer } from "./Player";
import { shuffled } from "./shuffle";
import type { Track } from "./types";

type Page = {
  items: Track[];
  total: number;
  offset: number;
  next_offset: number | null;
};
const PAGE = 100;
const SAMPLE_PAGES = 5;
const SAMPLE_SIZE = 200;

/** Every song in the person's library, paged by the server so large
 * libraries never load whole into the browser. */
export function LibrarySongs({
  render,
}: {
  render: (tracks: Track[]) => ReactNode;
}) {
  const player = usePlayer();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void api<Page>(`/v1/library-pages/tracks?offset=${offset}&limit=${PAGE}`, {
      signal: controller.signal,
    })
      .then(setPage)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [offset]);

  async function shuffleAll() {
    if (!page?.total) return;
    setBusy(true);
    try {
      // Sample a few random windows instead of downloading a 50k-song list.
      const starts = new Set<number>();
      const windows = Math.ceil(page.total / SAMPLE_SIZE);
      while (starts.size < Math.min(SAMPLE_PAGES, windows))
        starts.add(Math.floor(Math.random() * windows) * SAMPLE_SIZE);
      const pages = await Promise.all(
        [...starts].map((start) =>
          api<Page>(
            `/v1/library-pages/tracks?offset=${start}&limit=${SAMPLE_SIZE}`,
          ),
        ),
      );
      const queue = shuffled(
        pages.flatMap((p) => p.items).filter((t) => t.available !== false),
      );
      if (queue.length) player.playSaved(queue[0], queue, 0);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <p role="alert">{error}</p>;
  if (!page) return <p role="status">Loading songs…</p>;
  const playable = page.items.filter((t) => t.available !== false);
  return (
    <>
      <div className="release-actions">
        <button
          className="primary-button"
          disabled={!playable.length}
          onClick={() => player.playSaved(playable[0], playable, 0)}
        >
          <Play size={18} /> Play
        </button>
        <button
          className="secondary-button"
          disabled={!page.total || busy}
          onClick={() => void shuffleAll()}
        >
          <Shuffle size={18} /> Shuffle all
        </button>
      </div>
      {page.total > PAGE && (
        <nav className="collection-pages" aria-label="Songs pages">
          <button
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE))}
          >
            Previous
          </button>
          <span role="status" aria-live="polite">
            {offset + 1}–{Math.min(offset + PAGE, page.total)} of {page.total}
          </span>
          <button
            disabled={page.next_offset === null}
            onClick={() => setOffset(page.next_offset || 0)}
          >
            Next
          </button>
        </nav>
      )}
      {page.items.length ? render(page.items) : <p>No songs yet.</p>}
    </>
  );
}
