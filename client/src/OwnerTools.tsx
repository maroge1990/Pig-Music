import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { api } from "./api";
import { AlbumQuality } from "./AlbumQuality";
import { RemoveFromServer } from "./Recovery";
import { go } from "./routes";

/* Administrator additions always render after everything a member sees,
 * so the owner's screens match a member's from the top down. */

export function OwnerPanel({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <details className="owner-tools">
      <summary>
        <ShieldCheck size={18} aria-hidden="true" />
        Admin · {label}
      </summary>
      <div className="owner-tools-body">{children}</div>
    </details>
  );
}

export function OwnerAlbumTools({ id, title }: { id: string; title: string }) {
  const [category, setCategory] = useState("");
  const [message, setMessage] = useState("");
  useEffect(() => {
    void api<{ category: string }>("/albums/" + id)
      .then((a) => setCategory(a.category))
      .catch(() => setCategory(""));
  }, [id]);
  return (
    <OwnerPanel label="server settings for this album">
      {category && (
        <label>
          Library section
          <select
            value={category}
            onChange={(e) => {
              const value = e.target.value;
              void api("/albums/" + id + "/category", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ category: value }),
              })
                .then(() => {
                  setCategory(value);
                  setMessage("Library section saved");
                  window.dispatchEvent(new Event("music-library-changed"));
                })
                .catch((error) => setMessage((error as Error).message));
            }}
          >
            <option value="album">Artists &amp; albums</option>
            <option value="compilation">Compilations</option>
            <option value="soundtrack">Soundtracks</option>
            <option value="musical">Musicals</option>
            <option value="auto">Automatic</option>
          </select>
          <small>
            Changes grouping for everyone. Music files are unchanged.
          </small>
        </label>
      )}
      <AlbumQuality id={id} notify={setMessage} embedded />
      <RemoveFromServer
        kind="albums"
        id={id}
        title={title}
        removed={() => go("/library/albums")}
      />
      {message && <p role="status">{message}</p>}
    </OwnerPanel>
  );
}

export function OwnerArtistTools({ id, title }: { id: string; title: string }) {
  const [message, setMessage] = useState("");
  return (
    <OwnerPanel label="server settings for this artist">
      <AlbumQuality kind="artist" id={id} notify={setMessage} />
      <RemoveFromServer
        kind="artists"
        id={id}
        title={title}
        removed={() => go("/library/artists")}
      />
      {message && <p role="status">{message}</p>}
    </OwnerPanel>
  );
}

export function OwnerLibraryLinks() {
  return (
    <section className="owner-links" aria-label="Admin shortcuts">
      <h2>
        <ShieldCheck size={18} aria-hidden="true" /> Admin
      </h2>
      <p>
        <a href="#/admin/library">Scan and maintain the server library</a>
        <a href="#/admin/library">Unassigned music</a>
        <a href="#/admin/downloads">Download queue</a>
      </p>
    </section>
  );
}
