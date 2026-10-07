import { apiFetch } from "./api";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Cover, catalogueCover } from "./Cover";
type Group = { id: string; title: string; date: string; type: string };
type Song = {
  id: string;
  title: string;
  artist: string;
  album: string;
  release_id: string;
};
export function ArtistPopular({
  id,
  openAlbum,
  songsOnly = false,
}: {
  id: string;
  openAlbum: (album: Group) => void;
  songsOnly?: boolean;
}) {
  const [data, setData] = useState<{ songs: Song[]; albums: Group[] } | null>(
    null,
  );
  const [songPage, setSongPage] = useState(0);
  const [albumPage, setAlbumPage] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setSongPage(0);
    setAlbumPage(0);
    void (async () => {
      try {
        const response = await apiFetch(
          `/api/v1/catalogue/artists/${id}/popularity`,
          { signal: controller.signal },
        );
        if (response.ok) {
          const body = await response.json();
          if (!controller.signal.aborted) setData(body);
        }
      } catch {
        /* Optional enrichment never blocks discography. */
      }
    })();
    return () => controller.abort();
  }, [id]);
  if (!data || (!data.songs.length && !data.albums.length)) return null;
  const pager = (
    label: string,
    page: number,
    size: number,
    total: number,
    setPage: (n: number) => void,
  ) => (
    <div className="popular-pager">
      <span aria-live="polite">
        {page * size + 1}–{Math.min((page + 1) * size, total)} of {total}
      </span>
      <button
        className="icon-button"
        aria-label={`Previous popular ${label}`}
        disabled={page === 0}
        onClick={() => setPage(page - 1)}
      >
        <ChevronLeft size={18} />
      </button>
      <button
        className="icon-button"
        aria-label={`Next popular ${label}`}
        disabled={(page + 1) * size >= total}
        onClick={() => setPage(page + 1)}
      >
        <ChevronRight size={18} />
      </button>
    </div>
  );
  return (
    <section className="artist-popular" aria-label="Popular music">
      {!!data.songs.length && (
        <>
          <div className="section-title">
            <h2>Popular songs</h2>
            {pager("songs", songPage, 5, data.songs.length, setSongPage)}
          </div>
          {data.songs.slice(songPage * 5, songPage * 5 + 5).map((song) => {
            return (
              <div
                className="result-row catalogue-song popular-song"
                key={song.id}
              >
                <Cover
                  title={song.album}
                  src={catalogueCover("release", song.release_id)}
                />
                <div>
                  <strong>{song.title}</strong>
                  <span>{song.album}</span>
                </div>
                <button
                  className="text-button"
                  onClick={() => {
                    location.hash = `/search/artist/${id}?name=${encodeURIComponent(song.artist)}&release=${song.release_id}`;
                  }}
                >
                  View song
                </button>
              </div>
            );
          })}
        </>
      )}
      {!songsOnly && !!data.albums.length && (
        <>
          <div className="section-title">
            <h2>Popular albums</h2>
            {pager("albums", albumPage, 3, data.albums.length, setAlbumPage)}
          </div>
          <div className="popular-albums">
            {data.albums
              .slice(albumPage * 3, albumPage * 3 + 3)
              .map((album) => (
                <button
                  className="album-card"
                  key={album.id}
                  onClick={() => openAlbum(album)}
                >
                  <Cover
                    title={album.title}
                    src={catalogueCover("release-group", album.id)}
                  />
                  <div className="card-name">{album.title}</div>
                  <div className="card-caption">{album.date.slice(0, 4)}</div>
                </button>
              ))}
          </div>
        </>
      )}
    </section>
  );
}
