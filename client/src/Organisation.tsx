import { apiFetch } from "./api";
import { useEffect, useState } from "react";
export function Organisation({ notify }: { notify: (s: string) => void }) {
  const [history, setHistory] = useState<{ id: string; title: string }[]>([]);
  useEffect(() => {
    void apiFetch("/api/library/organisation/history")
      .then((r) => r.json())
      .then(setHistory);
  }, []);
  const [items, setItems] = useState<
    {
      id: string;
      from: string;
      to: string;
      rename: boolean;
      conflict: boolean;
      tag_supported: boolean;
    }[]
  >([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [tags, setTags] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function review() {
    setBusy(true);
    try {
      const r = await apiFetch("/api/library/organisation");
      const d = await r.json();
      if (!r.ok) throw new Error("Library review unavailable.");
      setItems(d.items);
      setSelected([]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (
      !confirm(
        `Apply the reviewed naming${tags ? " and tagging" : ""} changes to ${selected.length} songs? Originals will be preserved.`,
      )
    )
      return;
    setBusy(true);
    try {
      const r = await apiFetch("/api/library/organisation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_ids: selected, tags }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Organisation stopped.");
      notify(`${d.applied} songs organised.`);
      window.dispatchEvent(new Event("music-library-changed"));
      await review();
      setHistory(
        await apiFetch("/api/library/organisation/history").then((r) =>
          r.json(),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="system-panel">
      <h2>Organise existing music</h2>
      <p>
        Review naming changes before applying them. Album folders are retained.
        Originals are preserved.
      </p>
      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => void review()}
      >
        Review library
      </button>
      {!!items.length && (
        <>
          <label className="download-option">
            <input
              type="checkbox"
              checked={tags}
              onChange={(e) => setTags(e.target.checked)}
            />
            Apply consistent tags from current library metadata
          </label>
          <button
            className="text-button"
            onClick={() =>
              setSelected(
                items
                  .filter(
                    (i) =>
                      !i.conflict && (i.rename || (tags && i.tag_supported)),
                  )
                  .map((i) => i.id),
              )
            }
          >
            Select eligible changes
          </button>
          <div className="organisation-list">
            {items
              .filter((i) => i.rename || tags)
              .map((i) => (
                <label className="result-row" key={i.id}>
                  <input
                    type="checkbox"
                    disabled={busy || i.conflict || (tags && !i.tag_supported)}
                    checked={selected.includes(i.id)}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, i.id]
                          : selected.filter((id) => id !== i.id),
                      )
                    }
                  />
                  <div>
                    <strong>{i.from}</strong>
                    <span>
                      {i.conflict ? "Destination needs review" : i.to}
                    </span>
                  </div>
                </label>
              ))}
          </div>
          <button
            className="primary-button"
            disabled={busy || !selected.length}
            onClick={() => void apply()}
          >
            Apply reviewed changes · {selected.length}
          </button>
        </>
      )}
      {history.map((item) => (
        <div className="result-row" key={item.id}>
          <strong>{item.title}</strong>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void apiFetch("/api/library/organisation/" + item.id + "/undo", {
                method: "POST",
              })
                .then((r) => {
                  if (!r.ok)
                    throw new Error("Undo stopped; original retained.");
                  setHistory((old) => old.filter((v) => v.id !== item.id));
                  window.dispatchEvent(new Event("music-library-changed"));
                })
                .catch((e) => setError(e.message))
                .finally(() => setBusy(false));
            }}
          >
            Undo organisation
          </button>
        </div>
      ))}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
