import { useEffect, useState } from "react";
import { api } from "./api";
import { Cover, catalogueCover } from "./Cover";
import { discoverUrl } from "./navigation";
import { SongRow } from "./SongRow";
import { withLibrary, type Song } from "./songs";
import { warmArtist, whenIdle } from "./prefetch";

function songRows(items: Item[]): Song[] {
  return items.map((item) => ({
    key: "home:" + item.id,
    title: item.name,
    artist: item.artist,
    album: item.album || undefined,
    cover: item.release_id ? catalogueCover("release", item.release_id) : null,
    state: "missing",
    release_id: item.release_id,
    recording_id: item.id,
    artist_id: item.artist_id,
  }));
}
type Item = {
  id: string;
  name: string;
  artist: string;
  artist_id: string;
  release_id?: string;
  album?: string;
  reason?: string;
  kind: string;
};
type Feed = {
  artists: Item[];
  albums: Item[];
  songs: Item[];
  source: string;
  unavailable: boolean;
};
function HomeSection({ kind }: { kind: "popular" | "recommended" }) {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [songs, setSongs] = useState<Song[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void api<Feed>("/v1/home/" + kind, { signal: controller.signal })
      .then((value) => {
        setFeed(value);
        // Every artist here opens instantly; the first two are fully ready.
        whenIdle(() =>
          [
            ...new Set(
              [...value.artists, ...value.albums, ...value.songs].map(
                (item) => item.artist_id,
              ),
            ),
          ]
            .slice(0, 12)
            .forEach((id, i) => warmArtist(id, i < 2)),
        );
        const plain = songRows(value.songs);
        setSongs(plain);
        return withLibrary(plain).then((found) => {
          if (!controller.signal.aborted) setSongs(found);
        });
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [kind]);
  return (
    <section className="home-section">
      <h2>
        {kind === "popular" ? "Popular this week" : "Recommended for you"}
      </h2>
      <p>
        {feed?.source ||
          (kind === "popular"
            ? "ListenBrainz listeners"
            : "Based on artists saved in your library")}
      </p>
      {!feed && <p role="status">{error || "Finding music…"}</p>}
      {feed &&
        ["artists", "albums", "songs"].map((collection) => (
          <section key={collection}>
            <h3>{collection[0].toUpperCase() + collection.slice(1)}</h3>
            {collection === "songs" ? (
              <div className="song-list home-songs">
                {songs.map((song, i) => (
                  <SongRow key={song.key} song={song} queue={songs} index={i} />
                ))}
              </div>
            ) : (
              <div className="home-grid">
                {feed[collection as "artists"].map((item) => (
                  <button
                    className="album-card"
                    key={item.id}
                    onClick={() => {
                      location.hash =
                        discoverUrl(
                          {
                            id: item.artist_id,
                            name: item.artist || item.name,
                          },
                          collection === "songs" ? item.release_id : undefined,
                        ) +
                        (collection === "albums" ? "&group=" + item.id : "");
                    }}
                  >
                    <Cover
                      title={item.name}
                      artist={collection === "artists"}
                      src={
                        collection === "artists"
                          ? `/api/catalogue/artists/${item.id}/artwork`
                          : collection === "albums"
                            ? catalogueCover("release-group", item.id)
                            : item.release_id
                              ? catalogueCover("release", item.release_id)
                              : undefined
                      }
                    />
                    <strong>{item.name}</strong>
                    <p>{collection !== "artists" && item.artist}</p>
                    {item.reason && <small>{item.reason}</small>}
                  </button>
                ))}
              </div>
            )}
            {!feed[collection as "artists"].length && (
              <p className="muted">
                {kind === "recommended"
                  ? "Save artists to your library to find related music. Some artists do not yet have similarity data."
                  : "This feed is temporarily unavailable."}
              </p>
            )}
          </section>
        ))}
      {feed?.unavailable && (
        <p role="status">
          Some discovery feeds are unavailable. Your library is still available.
        </p>
      )}
    </section>
  );
}
type RecentAlbum = {
  id: string;
  title: string;
  artist: string;
  cover_url?: string | null;
};

/** Music this person added lately; hidden until there is some. */
function RecentlyAdded() {
  const [albums, setAlbums] = useState<RecentAlbum[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    void api<{ albums: RecentAlbum[] }>("/v1/home/recent", {
      signal: controller.signal,
    })
      .then((d) => setAlbums(d.albums))
      .catch(() => {});
    return () => controller.abort();
  }, []);
  if (!albums.length) return null;
  return (
    <section className="home-section">
      <h2>Recently added</h2>
      <div className="home-grid">
        {albums.map((album) => (
          <a
            className="album-card"
            key={album.id}
            href={"#/library/album/" + album.id}
          >
            <Cover title={album.title} src={album.cover_url} />
            <strong>{album.title}</strong>
            <p>{album.artist}</p>
          </a>
        ))}
      </div>
    </section>
  );
}

export function Home() {
  return (
    <main className="personal-main home-page">
      <h1>Home</h1>
      <p>Find your next favourite.</p>
      <RecentlyAdded />
      <HomeSection kind="popular" />
      <HomeSection kind="recommended" />
    </main>
  );
}
