import { SongControls, isPending } from "./SongControls";
import { apiFetch } from "./api";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Cover, catalogueCover } from "./Cover";
import { SongActions } from "./SongActions";
import { usePlayer } from "./Player";
type Group = { id: string; title: string; date: string; type: string };
type Song = {
  id: string;
  title: string;
  artist: string;
  album: string;
  release_id: string;
};
type Track = {
  id: string;
  title: string;
  artist: string;
  duration: number;
  musicbrainz_recording_id: string;
  status: string;
  download_status?: string;
  received_bytes?: number;
  total_bytes?: number;
};
const pending = isPending;
export function ArtistPopular({
  id,
  openAlbum,
  notify,
  songsOnly = false,
  personal = false,
}: {
  id: string;
  openAlbum: (album: Group) => void;
  notify: (message: string) => void;
  songsOnly?: boolean;
  personal?: boolean;
}) {
  const player = usePlayer();
  const [tracks, setTracks] = useState<Record<string, Track>>({});
  const [working, setWorking] = useState<Record<string, boolean>>({});
  async function resolve(song: Song, signal?: AbortSignal) {
    const response = await apiFetch(
      `/api/catalogue/releases/${song.release_id}`,
      {
        signal,
      },
    );
    const body = await response.json();
    if (!response.ok)
      throw new Error(
        typeof body.detail === "string"
          ? body.detail
          : "Song unavailable. Try again.",
      );
    const track = (body.tracks as Track[]).find(
      (t) => t.musicbrainz_recording_id === song.id,
    );
    if (!track)
      throw new Error("This recording is unavailable in the listed release.");
    return track;
  }
  async function act(song: Song, download: boolean) {
    setWorking((old) => ({ ...old, [song.id]: true }));
    try {
      const track = await resolve(song);
      setTracks((old) => ({ ...old, [song.id]: track }));
      if (!download) {
        player.playCatalogue(
          song.release_id,
          track,
          catalogueCover("release", song.release_id),
        );
        return;
      }
      if (track.status === "downloaded" || pending(track)) return;
      const response = await apiFetch(
        `/api/catalogue/releases/${song.release_id}/request`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ track_ids: [track.id] }),
        },
      );
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Could not queue this song.",
        );
      notify(
        `${result.created} songs queued${result.downloads_enabled ? "" : " · downloads paused"}`,
      );
      const updated = await resolve(song);
      setTracks((old) => ({ ...old, [song.id]: updated }));
    } catch (error) {
      notify((error as Error).message);
    } finally {
      setWorking((old) => ({ ...old, [song.id]: false }));
    }
  }
  const [data, setData] = useState<{ songs: Song[]; albums: Group[] } | null>(
    null,
  );
  const [songPage, setSongPage] = useState(0);
  const [albumPage, setAlbumPage] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setTracks({});
    setWorking({});
    setSongPage(0);
    setAlbumPage(0);
    void (async () => {
      try {
        const response = await apiFetch(
          `/api/${personal ? "v1/" : ""}catalogue/artists/${id}/popularity`,
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
  useEffect(() => {
    if (!data || personal) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      if (document.hidden) {
        timer = setTimeout(() => void refresh(), 3000);
        return;
      }
      const found = await Promise.all(
        data.songs.slice(songPage * 5, songPage * 5 + 5).map(async (song) => {
          try {
            const track = await resolve(song, controller.signal);
            if (!controller.signal.aborted)
              setTracks((old) => ({ ...old, [song.id]: track }));
            return pending(track);
          } catch {
            /* Actions report failures; background state refresh stays quiet. */
          }
        }),
      );
      if (!controller.signal.aborted && found.some(Boolean))
        timer = setTimeout(() => void refresh(), 3000);
    };
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [data, songPage, Object.values(tracks).filter(pending).length]);
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
            const track = tracks[song.id];
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
                {personal && (
                  <button
                    className="text-button"
                    onClick={() => {
                      location.hash = `/search/artist/${id}?name=${encodeURIComponent(song.artist)}&release=${song.release_id}`;
                    }}
                  >
                    View song
                  </button>
                )}
                {!personal && (
                  <SongControls
                    song={{ ...track, title: song.title }}
                    busy={working[song.id]}
                    play={() => void act(song, false)}
                    download={() => void act(song, true)}
                  />
                )}
                {!personal && track && (
                  <SongActions
                    song={{ release_id: song.release_id, track_id: track.id }}
                    title={song.title}
                  />
                )}
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
