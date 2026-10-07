import { apiFetch } from "./api";
import { useState } from "react";

/** Owner-only: move the server's files to recoverable trash for everyone. */
export function RemoveFromServer({
  kind,
  id,
  title,
  removed,
}: {
  kind: "tracks" | "albums" | "artists";
  id: string;
  title: string;
  removed?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function remove() {
    if (
      !confirm(
        `Move ${title} to recoverable trash on the server? It is removed for everyone.${kind === "artists" ? " Artist monitoring will stop." : ""}`,
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      const r = await apiFetch(`/api/${kind}/${id}/remove`, { method: "POST" });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || "Removal stopped.");
      window.dispatchEvent(new Event("music-library-changed"));
      removed?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        className="danger-text-button"
        disabled={busy}
        onClick={() => void remove()}
      >
        Remove from server…
      </button>
      {error && <span role="alert">{error}</span>}
    </>
  );
}
