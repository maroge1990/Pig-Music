import { PlaylistPicker } from "./PlaylistPicker";
import { apiFetch } from "./api";
import { useEffect, useState } from "react";
import { subscribeSong, updateFavourite } from "./membership";
import { Star } from "lucide-react";
export type SongReference = {
  playlist_id?: string;
  position?: number;
  saved_id?: string;
  release_id?: string;
  track_id?: string;
};
async function call(path: string, body: unknown) {
  const r = await apiFetch("/api/" + path, {
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
  hidePlaylist = false,
}: {
  song: SongReference;
  title: string;
  hidePlaylist?: boolean;
}) {
  const [favourite, setFavourite] = useState(false);
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
  return (
    <>
      {!hidePlaylist && (
        <PlaylistPicker
          title={title}
          load={async () => {
            const r = await apiFetch("/api/playlists");
            if (!r.ok) throw new Error("Playlists unavailable");
            return (await r.json()).filter(
              (p: { favourites?: boolean }) => !p.favourites,
            );
          }}
          create={(name) => call("playlists", { name })}
          add={(id) => call("playlists/" + id + "/songs", song)}
        />
      )}
      <button
        className={`round-action ${favourite ? "is-favourite" : ""}`}
        aria-label={`Favourite ${title}`}
        aria-pressed={favourite}
        disabled={busy}
        onClick={() => void toggle()}
      >
        <Star size={16} fill={favourite ? "currentColor" : "none"} />
      </button>
      {error && (
        <span role="alert" className="inline-error">
          {error}
        </span>
      )}
    </>
  );
}
