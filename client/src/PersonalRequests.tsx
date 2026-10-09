import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { friendlyRequestError } from "./requestError";

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
  const readSerial = useRef(0);
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<RequestPage | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  async function clear() {
    ++readSerial.current;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ cleared: number }>("/v1/requests", {
        method: "DELETE",
      });
      setOffset(0);
      setPage(await api<RequestPage>("/v1/requests?offset=0&limit=100"));
      setNotice(
        `Cleared ${result.cleared} finished downloads. Your music files are unchanged.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function retry(id: string) {
    ++readSerial.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/v1/requests/" + encodeURIComponent(id) + "/retry", {
        method: "POST",
      });
      window.dispatchEvent(new Event("music-requests-changed"));
      setPage(
        await api<RequestPage>(`/v1/requests?offset=${offset}&limit=100`),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const load = () => {
      const serial = ++readSerial.current;
      void api<RequestPage>(`/v1/requests?offset=${offset}&limit=100`)
        .then((data) => {
          if (serial === readSerial.current) setPage(data);
        })
        .catch((e) => {
          if (serial === readSerial.current) setError(e.message);
        });
    };
    load();
    window.addEventListener("music-requests-changed", load);
    return () => {
      ++readSerial.current;
      window.removeEventListener("music-requests-changed", load);
    };
  }, [offset]);
  return (
    <section>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {!!page?.total && (
        <div className="release-actions">
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => void clear()}
          >
            Clear downloads
          </button>
          <p className="muted">
            Clears finished, failed and cancelled entries. Active downloads and
            music files are kept.
          </p>
        </div>
      )}
      {page && !page.total && (
        <p className="muted">
          Songs you download from Search or an artist page appear here until
          they reach your library.
        </p>
      )}
      {page && page.total > 0 && (
        <>
          {(offset > 0 || page.next_offset !== null) && (
            <nav className="collection-pages" aria-label="Request pages">
              <button
                disabled={busy || offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 100))}
              >
                Previous
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 100, page.total)} of{" "}
                {page.total}
              </span>
              <button
                disabled={busy || page.next_offset === null}
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
                    <p className="request-error">
                      {friendlyRequestError(r.error)}
                    </p>
                  )}
                </div>
                <span className={`request-status ${tone}`}>{label}</span>
                {(r.status === "failed" || r.status === "cancelled") && (
                  <button
                    className="small-button"
                    disabled={busy}
                    aria-label={`Retry ${r.title}`}
                    onClick={() => void retry(r.id)}
                  >
                    Retry
                  </button>
                )}
              </article>
            );
          })}
        </>
      )}
    </section>
  );
}
