import { useEffect, useState } from "react";
import { api } from "./api";
type RequestPage = {
  items: {
    id: string;
    title: string;
    status: string;
    request_progress: number | null;
  }[];
  total: number;
  next_offset: number | null;
};
export function PersonalRequests() {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<RequestPage | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const load = () =>
      void api<RequestPage>(`/v1/requests?offset=${offset}&limit=100`)
        .then(setPage)
        .catch((e) => setError(e.message));
    load();
    window.addEventListener("music-requests-changed", load);
    return () => window.removeEventListener("music-requests-changed", load);
  }, [offset]);
  return (
    <section>
      <h2>Your requests</h2>
      {error && <p role="alert">{error}</p>}
      {page && (
        <>
          <nav className="collection-pages" aria-label="Request pages">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              Previous
            </button>
            <span>{page.total} requests</span>
            <button
              disabled={page.next_offset === null}
              onClick={() => setOffset(page.next_offset!)}
            >
              Next
            </button>
          </nav>
          {page.items.map((r) => (
            <article className="personal-track" key={r.id}>
              <div>
                <strong>{r.title}</strong>
                <p>{r.status.replaceAll("_", " ")}</p>
                {r.request_progress !== null && (
                  <progress
                    max={1}
                    value={r.request_progress}
                    aria-label={`Downloading ${r.title} to the server, ${Math.round(r.request_progress * 100)} percent`}
                  />
                )}
              </div>
            </article>
          ))}
        </>
      )}
    </section>
  );
}
