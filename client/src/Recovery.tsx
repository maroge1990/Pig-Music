import { apiFetch as fetch } from "./api";
import { useEffect, useState } from "react";
import { Ellipsis } from "lucide-react";
export function RemovedMusic({ notify }: { notify: (s: string) => void }) {
  const [items, setItems] = useState<
    { id: string; track: { title: string; artist: string }; status: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const refresh = () =>
    fetch("/api/library/trash")
      .then((r) => r.json())
      .then(setItems);
  useEffect(() => {
    void refresh();
  }, []);
  async function restore(id: string) {
    setBusy(true);
    try {
      const r = await fetch("/api/library/trash/" + id + "/restore", {
        method: "POST",
      });
      if (!r.ok) throw new Error("Restore stopped. Check the library folder.");
      await refresh();
      window.dispatchEvent(new Event("music-library-changed"));
      notify("Song restored.");
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="system-panel">
      <h2>Removed music</h2>
      {!items.length ? (
        <p>No removed music.</p>
      ) : (
        items.map((item) => (
          <div className="result-row" key={item.id}>
            <div>
              <strong>{item.track.title}</strong>
              <span>{item.track.artist}</span>
            </div>
            <button
              className="secondary-button"
              disabled={busy}
              onClick={() => void restore(item.id)}
            >
              Restore
            </button>
          </div>
        ))
      )}
    </section>
  );
}
export function RemoveSong({ id, title }: { id: string; title: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      <details className="song-menu">
        <summary aria-label={`More options for ${title}`}>
          <Ellipsis size={16} />
        </summary>
        <button
          className="text-button"
          disabled={busy}
          onClick={() => {
            if (!window.confirm(`Move ${title} to recoverable trash?`)) return;
            setBusy(true);
            void fetch("/api/tracks/" + id + "/remove", { method: "POST" })
              .then(async (r) => {
                if (!r.ok)
                  throw new Error("Removal stopped. Check the library folder.");
                window.dispatchEvent(new Event("music-library-changed"));
              })
              .catch((e) => setError(e.message))
              .finally(() => setBusy(false));
          }}
        >
          Move to trash
        </button>
      </details>
      {error && <span role="alert">{error}</span>}
    </>
  );
}

export function RemoveCollection({
  kind,
  id,
  title,
}: {
  kind: "albums" | "artists";
  id: string;
  title: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    if (
      !confirm(
        `Move ${title} to recoverable trash?${kind === "artists" ? " Artist monitoring will stop." : ""}`,
      )
    )
      return;
    setBusy(true);
    try {
      const r = await fetch(`/api/${kind}/${id}/remove`, { method: "POST" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Removal stopped.");
      window.dispatchEvent(new Event("music-library-changed"));
      location.hash = "/library";
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => void remove()}
      >
        Remove {kind === "artists" ? "artist" : "album"}
      </button>
      {error && <p role="alert">{error}</p>}
    </>
  );
}
