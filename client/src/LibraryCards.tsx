import type { Album, Artist } from "./types";
import { Cover } from "./Cover";

const count = (value: number, label: string) =>
  `${value} ${label}${value === 1 ? "" : "s"}`;

export function AlbumCards({
  albums,
  open,
}: {
  albums: Album[];
  open: (id: string) => void;
}) {
  return (
    <div className="album-grid">
      {albums.map((album) => (
        <button
          className="album-card"
          key={album.id}
          onClick={() => open(album.id)}
        >
          <Cover title={album.title} src={album.cover_url} />
          <div className="card-name">{album.title}</div>
          <div className="card-caption">{album.artist}</div>
          <div className="album-meta">
            {album.year || "Release"}
            <span>·</span>
            {count(album.track_count, "track")}
          </div>
        </button>
      ))}
    </div>
  );
}

export function ArtistCards({
  artists,
  open,
  prefetch,
}: {
  artists: Artist[];
  open: (id: string) => void;
  prefetch: (id: string) => void;
}) {
  return (
    <div className="artist-grid">
      {artists.map((artist) => (
        <button
          className="artist-card"
          key={artist.id}
          onClick={() => open(artist.id)}
          onPointerEnter={() => prefetch(artist.id)}
        >
          <div className="artist-art-wrap">
            <Cover artist title={artist.name} src={artist.cover_url} />
          </div>
          <div className="card-name">{artist.name}</div>
          <div className="card-caption">
            {count(artist.album_count, "release")} <span>·</span>{" "}
            {count(artist.track_count, "track")}
          </div>
        </button>
      ))}
    </div>
  );
}
