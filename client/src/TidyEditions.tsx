import { apiFetch } from "./api";
import { useState } from "react";

type Song = {
  id: string;
  title: string;
  album: string;
  quality: string;
};
type Album = {
  id: string;
  artist: string;
  keep: { title: string; songs: number };
  editions: { album_id: string; title: string; songs: number }[];
  remove: (Song & { kept: Song })[];
  replace: (Song & { replaces: Song })[];
  leftovers: Song[];
  fingerprint: string;
};
type Done = {
  id: string;
  artist: string;
  title: string;
  status: string;
  error?: string | null;
};

/** Albums the library has on several editions, tidied to the fullest. */
export function TidyEditions({ notify }: { notify: (s: string) => void }) {
  const [albums, setAlbums] = useState<Album[] | null>(null);
  const [history, setHistory] = useState<Done[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  /** Refresh the review; a tidy-up or Undo that just failed keeps its
   * `failure` on screen. */
  async function review(failure = "") {
    setBusy(true);
    setError(failure);
    try {
      const r = await apiFetch("/api/v1/admin/library/tidy");
      if (!r.ok) throw new Error("Edition review unavailable.");
      const d: { albums: Album[]; history: Done[] } = await r.json();
      setAlbums(d.albums);
      setHistory(d.history);
    } catch (e) {
      setError([failure, (e as Error).message].filter(Boolean).join(" "));
    } finally {
      setBusy(false);
    }
  }
  async function post(path: string, body?: object) {
    const r = await apiFetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      throw new Error(d.detail || "Stopped. Check the library folder.");
    }
  }
  async function tidy(album: Album) {
    const moved = album.remove.length + album.replace.length * 2;
    if (
      !confirm(
        `Keep ${album.keep.title} and move ${moved} files to Removed music? Listeners keep the kept copies, and you can undo this.`,
      )
    )
      return;
    setBusy(true);
    setError("");
    let failure = "";
    try {
      await post("/api/v1/admin/library/tidy/" + album.id, {
        fingerprint: album.fingerprint,
      });
      notify(`${album.artist} · ${album.keep.title} tidied.`);
    } catch (e) {
      failure = (e as Error).message;
    }
    // A stopped tidy-up may still have changed files.
    window.dispatchEvent(new Event("music-library-changed"));
    await review(failure);
  }
  async function undo(done: Done) {
    setBusy(true);
    setError("");
    let failure = "";
    try {
      await post(`/api/v1/admin/library/tidy/history/${done.id}/undo`);
      notify(`${done.artist} · ${done.title} put back.`);
    } catch (e) {
      failure = (e as Error).message;
    }
    window.dispatchEvent(new Event("music-library-changed"));
    await review(failure);
  }
  return (
    <section className="system-panel">
      <h2>Album editions</h2>
      <p>
        Albums you have on more than one edition, such as an album and its
        deluxe edition. The fullest edition is kept, with the best copy of each
        song. Singles, EPs, live albums and greatest hits stay separate.
      </p>
      <button
        className="secondary-button"
        disabled={busy}
        onClick={() => void review()}
      >
        Find editions
      </button>
      {albums && !albums.length && <p>No albums on several editions.</p>}
      {!!albums?.length && (
        <div className="organisation-list">
          {albums.map((album) => (
            <div key={album.id}>
              <h3>
                {album.artist} · {album.keep.title}
              </h3>
              <p>
                Keep {album.keep.title} ({album.keep.songs} songs); tidy{" "}
                {album.editions
                  .map((e) => `${e.title} (${e.songs} songs)`)
                  .join(", ")}
                .
              </p>
              {album.replace.map((s) => (
                <div className="result-row" key={s.id}>
                  <div>
                    <strong>{s.title}</strong>
                    <span>
                      {s.quality} from {s.album} replaces {s.replaces.quality}
                    </span>
                  </div>
                </div>
              ))}
              {album.remove.map((s) => (
                <div className="result-row" key={s.id}>
                  <div>
                    <strong>{s.title}</strong>
                    <span>
                      Removed from {s.album} · {s.kept.quality} kept
                    </span>
                  </div>
                </div>
              ))}
              {album.leftovers.map((s) => (
                <div className="result-row" key={s.id}>
                  <div>
                    <strong>{s.title}</strong>
                    <span>Stays on {s.album}: review it yourself</span>
                  </div>
                </div>
              ))}
              <button
                className="primary-button"
                disabled={busy || !(album.remove.length + album.replace.length)}
                onClick={() => void tidy(album)}
              >
                Tidy {album.keep.title}
              </button>
            </div>
          ))}
        </div>
      )}
      {!!history.length && (
        <>
          <h3>Tidied albums</h3>
          {history.map((done) => (
            <div className="result-row" key={done.id}>
              <div>
                <strong>{done.title}</strong>
                <span>
                  {done.artist}
                  {done.status === "applied" ? "" : " · stopped part-way"}
                  {done.error ? `: ${done.error}` : ""}
                </span>
              </div>
              <button
                className="secondary-button"
                disabled={busy}
                onClick={() => void undo(done)}
              >
                Undo
              </button>
            </div>
          ))}
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
