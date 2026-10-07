import { Cover } from "./Cover";
import { api } from "./api";
import { discoverUrl } from "./navigation";
import type { Artist } from "./types";
import { useState } from "react";
export function SavedArtistHeading({
  artist,
  personal = false,
}: {
  artist: Artist;
  personal?: boolean;
}) {
  const [error, setError] = useState("");
  async function open() {
    try {
      const identity = await api<{ id: string; name: string }>(
        personal
          ? `/v1/catalogue/library-artists/${artist.id}`
          : `/artists/${artist.id}/catalogue`,
      );
      location.hash = discoverUrl(identity);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="saved-artist-heading">
      <Cover title={artist.name} src={artist.cover_url} artist />
      <div>
        <span className="eyebrow">IN YOUR LIBRARY</span>
        <h1>
          <button className="music-text-link" onClick={() => void open()}>
            {artist.name}
          </button>
        </h1>
        <p>Saved music · Select the artist name for the full catalogue</p>
        {error && <p role="alert">{error}</p>}
      </div>
    </div>
  );
}
