import { Music2 } from "lucide-react";
import type { Library } from "./types";
import { Empty } from "./EmptyState";
import { sourceName } from "./sources";
type QueueItem = {
  id: string;
  title: string;
  artist: string;
  album: string;
  status: string;
  source?: string;
  error?: string;
  received_bytes?: number;
  total_bytes?: number;
};

export type Queue = {
  library_revision: string;
  artwork_revision?: number;
  media?: Library["media"];
  downloads_enabled: boolean;
  items: QueueItem[];
};
export function QueueView({
  queue,
  busy,
  clearQueue,
  queueAction,
}: {
  queue: Queue | null;
  busy: boolean;
  clearQueue: () => void;
  queueAction: (id: string, action: "retry" | "cancel") => void;
}) {
  return (
    <>
      <div className="page-heading queue-heading">
        <div>
          <h2>Download queue</h2>
          <p>
            {queue?.downloads_enabled
              ? "Downloads go directly to your SMB library."
              : "Downloads are paused. Enable them in Download settings below."}
          </p>
        </div>
        <button
          className="secondary-button"
          disabled={busy || !queue?.items.length}
          onClick={clearQueue}
        >
          Clear all
        </button>
      </div>
      {!queue ? (
        <p>Loading requests...</p>
      ) : !queue.items.length ? (
        <Empty
          title="Ready when you are"
          description="Submit music from your migration inventory to add requests here."
        />
      ) : (
        queue.items.map((item) => (
          <div className="result-row" key={item.id}>
            <Music2 size={22} />
            <div>
              <strong>{item.title}</strong>
              <span>
                {item.artist} · {item.album}
              </span>
              <span>
                {(
                  {
                    waiting_for_sources: "Waiting",
                    searching: "Searching sources",
                    downloading: "Downloading",
                    validating: "Checking audio and tags",
                    completed: "Downloaded and imported",
                    failed: "Failed",
                    cancelled: "Cancelled",
                  } as Record<string, string>
                )[item.status] || item.status}
                {item.source && ` · ${sourceName(item.source)}`}
              </span>
              {item.status === "downloading" && (
                <span>
                  {Math.round((item.received_bytes || 0) / 1024)} KB
                  {item.total_bytes
                    ? ` / ${Math.round(item.total_bytes / 1024)} KB`
                    : ""}
                </span>
              )}
              {item.error && item.status === "failed" && (
                <span className="inline-error">{item.error}</span>
              )}
            </div>
            {["failed", "cancelled"].includes(item.status) ? (
              <button
                className="small-button"
                disabled={busy}
                onClick={() => queueAction(item.id, "retry")}
              >
                Retry
              </button>
            ) : (
              item.status !== "completed" && (
                <button
                  className="small-button"
                  disabled={busy}
                  onClick={() => queueAction(item.id, "cancel")}
                >
                  Cancel
                </button>
              )
            )}
          </div>
        ))
      )}
    </>
  );
}
