import { useEffect, useState } from "react";
import { Heart } from "lucide-react";
import { api } from "./api";
import type { Track } from "./types";
export function PersonalSongActions({ track }: { track: Track }) {
  const [favourite, setFavourite] = useState(false);
  const [playlists, setPlaylists] = useState<{ id: string; name: string }[]>(
    [],
  );
  const [error, setError] = useState("");
  const body = {
    title: track.title,
    artist: track.artist,
    album: track.album,
    album_artist: track.album_artist,
    duration: track.duration,
  };
  const key = JSON.stringify(body);
  useEffect(() => {
    void api<{ favourited: boolean }>("/v1/favourites", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ track: body }),
    })
      .then((d) => setFavourite(d.favourited))
      .catch((e) => setError(e.message));
    void api<{ playlists: typeof playlists }>("/v1/playlists")
      .then((d) => setPlaylists(d.playlists))
      .catch((e) => setError(e.message));
  }, [key]);
  return (
    <>
      <button
        aria-label={
          favourite
            ? `Remove ${track.title} from favourites`
            : `Favourite ${track.title}`
        }
        onClick={() =>
          void api<{ favourited: boolean }>("/v1/favourites", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ track: body, favourite: !favourite }),
          })
            .then((d) => {
              setFavourite(d.favourited);
              window.dispatchEvent(new Event("music-library-changed"));
            })
            .catch((e) => setError(e.message))
        }
      >
        <Heart size={18} fill={favourite ? "currentColor" : "none"} />
      </button>
      <label className="player-playlist-picker">
        Add to playlist
        <select
          aria-label={`Add ${track.title} to a playlist`}
          value=""
          onChange={(e) => {
            const id = e.target.value;
            if (id)
              void api(`/v1/playlists/${id}/songs`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
              })
                .then(() =>
                  window.dispatchEvent(new Event("music-library-changed")),
                )
                .catch((e) => setError(e.message));
          }}
        >
          <option value="">Choose playlist</option>
          {playlists
            .filter((p) => !p.id.startsWith("pig-favourites:"))
            .map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
        </select>
      </label>
      {error && <span role="alert">{error}</span>}
    </>
  );
}
