import { PlaylistPicker } from "./PlaylistPicker";
import { useEffect, useState } from "react";
import { Heart } from "lucide-react";
import { api } from "./api";
import type { Track } from "./types";
export function PersonalSongActions({
  track,
  hidePlaylist = false,
}: {
  track: Track;
  hidePlaylist?: boolean;
}) {
  const [favourite, setFavourite] = useState(false);
  const playlists: { id: string; name: string }[] = [];
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
      {!hidePlaylist && (
        <PlaylistPicker
          title={track.title}
          load={async () =>
            (
              await api<{ playlists: typeof playlists }>("/v1/playlists")
            ).playlists.filter((p) => !p.id.startsWith("pig-favourites:"))
          }
          create={(name) =>
            api("/v1/playlists", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name }),
            })
          }
          add={(id) =>
            api(`/v1/playlists/${id}/songs`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
            }).then(() =>
              window.dispatchEvent(new Event("music-library-changed")),
            )
          }
        />
      )}
      {error && <span role="alert">{error}</span>}
    </>
  );
}
