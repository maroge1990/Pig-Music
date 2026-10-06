import { apiFetch as fetch } from "./api";
import { useEffect, useRef, useState } from "react";
import { subscribeSong, updateFavourite } from "./membership";
import { Plus, Star, X } from "lucide-react";
export type SongReference = {
  playlist_id?: string;
  position?: number;
  saved_id?: string;
  release_id?: string;
  track_id?: string;
};
async function call(path: string, body: unknown) {
  const r = await fetch("/api/" + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok)
    throw new Error(
      typeof d.detail === "string" ? d.detail : "Could not update this song.",
    );
  window.dispatchEvent(new Event("music-membership"));
  return d;
}
export function SongActions({
  song,
  title,
}: {
  song: SongReference;
  title: string;
}) {
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        return;
      }
      if (e.key !== "Tab") return;
      const nodes = Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]),input:not([disabled])",
        ) || [],
      );
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      previous?.focus();
    };
  }, [open]);
  const [favourite, setFavourite] = useState(false);
  const [items, setItems] = useState<{ id: string; name: string }[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const key = JSON.stringify(song);
  useEffect(
    () => subscribeSong(song, (value) => setFavourite(value.favourited)),
    [key],
  );
  async function toggle() {
    setBusy(true);
    setError("");
    try {
      const d = await call("favourites", { ...song, favourite: !favourite });
      setFavourite(d.favourited);
      updateFavourite(song, d.favourited);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function picker() {
    setOpen(true);
    setError("");
    try {
      const r = await fetch("/api/playlists");
      setItems(
        (await r.json()).filter((p: { favourites?: boolean }) => !p.favourites),
      );
    } catch {
      setError("Playlists unavailable.");
    }
  }
  async function add(id?: string) {
    setBusy(true);
    setError("");
    try {
      if (!id) {
        const p = await call("playlists", { name });
        id = p.id;
      }
      await call("playlists/" + id + "/songs", song);
      setOpen(false);
      setName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="round-action"
        aria-label={`Add ${title} to playlist`}
        onClick={() => void picker()}
      >
        <Plus size={16} />
      </button>
      <button
        className={`round-action ${favourite ? "is-favourite" : ""}`}
        aria-label={`Favourite ${title}`}
        aria-pressed={favourite}
        disabled={busy}
        onClick={() => void toggle()}
      >
        <Star size={16} fill={favourite ? "currentColor" : "none"} />
      </button>
      {!open && error && (
        <span role="alert" className="inline-error">
          {error}
        </span>
      )}
      {open && (
        <div className="modal-backdrop" onClick={() => setOpen(false)}>
          <section
            ref={dialog}
            className="review-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Add to playlist"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-heading">
              <h2>Add to playlist</h2>
              <button
                className="icon-button"
                aria-label="Close playlist picker"
                onClick={() => setOpen(false)}
              >
                <X />
              </button>
            </div>
            <p>{title}</p>
            {items.map((p) => (
              <button
                className="result-row"
                key={p.id}
                disabled={busy}
                onClick={() => void add(p.id)}
              >
                {p.name}
              </button>
            ))}
            <label>
              New playlist
              <input
                autoFocus
                aria-label="New playlist name"
                value={name}
                maxLength={100}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <button
              className="primary-button"
              disabled={busy || !name.trim()}
              onClick={() => void add()}
            >
              Create &amp; add song
            </button>
            {error && (
              <p role="alert" className="inline-error">
                {error}
              </p>
            )}
          </section>
        </div>
      )}
    </>
  );
}
