import { apiFetch } from "./api";
import { useEffect, useState } from "react";
export function RemovedMusic({ notify }: { notify: (s: string) => void }) {
  const [items, setItems] = useState<
    { id: string; track: { title: string; artist: string }; status: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const refresh = () =>
    apiFetch("/api/v1/admin/library/trash")
      .then((r) => r.json())
      .then(setItems);
  useEffect(() => {
    void refresh();
  }, []);
  async function restore(id: string) {
    setBusy(true);
    try {
      const r = await apiFetch(
        "/api/v1/admin/library/trash/" + id + "/restore",
        {
          method: "POST",
        },
      );
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
