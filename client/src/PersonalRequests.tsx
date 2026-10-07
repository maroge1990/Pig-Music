import { useEffect, useState } from "react";
import { api } from "./api";

type Request = {
  id: string;
  title: string;
  artist?: string;
  album?: string;
  status: string;
  request_progress: number | null;
  error?: string | null;
};
type RequestPage = {
  items: Request[];
  total: number;
  next_offset: number | null;
};

// Plain-language request states; the server keeps its technical names.
const labels: Record<
  string,
  [string, "waiting" | "active" | "done" | "failed"]
> = {
  waiting_for_sources: ["Waiting for a source", "waiting"],
  searching: ["Looking for a copy", "active"],
  downloading: ["Downloading to the server", "active"],
  validating: ["Checking the file", "active"],
  importing: ["Adding to the library", "active"],
  completed: ["In your library", "done"],
  downloaded: ["In your library", "done"],
  cancelled: ["Cancelled", "failed"],
  failed: ["Couldn't get this song", "failed"],
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
      {page && !page.total && (
        <p className="muted">
          Songs you request from Search or an artist page appear here until they
          reach your library.
        </p>
      )}
      {page && page.total > 0 && (
        <>
          {(offset > 0 || page.next_offset !== null) && (
            <nav className="collection-pages" aria-label="Request pages">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 100, page.total)} of{" "}
                {page.total}
              </span>
              <button
                disabled={page.next_offset === null}
                onClick={() => setOffset(page.next_offset!)}
              >
                Next
              </button>
            </nav>
          )}
          {page.items.map((r) => {
            const [label, tone] = labels[r.status] || [
              r.status.replaceAll("_", " "),
              "waiting",
            ];
            return (
              <article className="personal-track request-row" key={r.id}>
                <div>
                  <strong>{r.title}</strong>
                  {(r.artist || r.album) && (
                    <p>{[r.artist, r.album].filter(Boolean).join(" · ")}</p>
                  )}
                  {r.request_progress !== null && tone === "active" && (
                    <progress
                      max={1}
                      value={r.request_progress}
                      aria-label={`Downloading ${r.title} to the server, ${Math.round(r.request_progress * 100)} percent`}
                    />
                  )}
                  {tone === "failed" && r.error && (
                    <p className="request-error">{r.error}</p>
                  )}
                </div>
                <span className={`request-status ${tone}`}>{label}</span>
              </article>
            );
          })}
        </>
      )}
    </section>
  );
}
