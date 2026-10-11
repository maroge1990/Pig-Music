import { useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { Cover } from "./Cover";
import { discoverUrl } from "./navigation";
import { go } from "./routes";
import { SongRow } from "./SongRow";
import { fromTrack } from "./songs";
import { warmArtist, whenIdle } from "./prefetch";
import type { Album, Artist, Library, Track } from "./types";

type CatalogueArtist = { id: string; name: string; description?: string };
const fold = (value: string) => value.toLocaleLowerCase().normalize("NFKD");

/** One search: your library first, then the server, then the catalogue. */
export function SearchPage({
  query,
  library,
  songs,
}: {
  query: string;
  library: Library;
  songs: (tracks: Track[]) => ReactNode;
}) {
  const [local, setLocal] = useState<{
    tracks: Track[];
    household: Track[];
  } | null>(null);
  const [catalogue, setCatalogue] = useState<CatalogueArtist[] | null>(null);
  const [catalogueFailed, setCatalogueFailed] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setLocal(null);
    setCatalogue(null);
    setCatalogueFailed(false);
    setError("");
    if (!query) return;
    const controller = new AbortController();
    const signal = controller.signal;
    // Local results arrive first; the catalogue can be slower or unavailable.
    void api<{ tracks: Track[]; household_tracks: Track[] }>(
      "/v1/search?q=" + encodeURIComponent(query),
      { signal },
    )
      .then((found) =>
        setLocal({ tracks: found.tracks, household: found.household_tracks }),
      )
      .catch((e) => {
        if (!signal.aborted) setError(e.message);
      });
    void api<{ artists: CatalogueArtist[] }>(
      "/v1/catalogue/artists?q=" + encodeURIComponent(query),
      { signal },
    )
      .then((found) => {
        setCatalogue(found.artists);
        // The likely next tap: essentials for three, everything for two.
        whenIdle(() =>
          found.artists.slice(0, 3).forEach((a, i) => warmArtist(a.id, i < 2)),
        );
      })
      .catch(() => {
        if (!signal.aborted) {
          setCatalogue([]);
          setCatalogueFailed(true);
        }
      });
    return () => controller.abort();
  }, [query]);

  const needle = fold(query);
  const artists = query
    ? library.artists.filter((a: Artist) => fold(a.name).includes(needle))
    : [];
  const albums = query
    ? library.albums.filter(
        (a: Album) =>
          fold(a.title).includes(needle) || fold(a.artist).includes(needle),
      )
    : [];
  const nothingLocal =
    local && !artists.length && !albums.length && !local.tracks.length;

  return (
    <>
      <form
        className="search-form"
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          const q = String(new FormData(e.currentTarget).get("q") || "").trim();
          if (q) go("/search?q=" + encodeURIComponent(q));
        }}
      >
        <label>
          Artists, albums or songs
          <input
            key={query}
            name="q"
            type="search"
            defaultValue={query}
            required
            maxLength={150}
            autoFocus={!query}
          />
        </label>
        <button type="submit" className="primary-button">
          Search
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {query && !local && !error && <p role="status">Searching…</p>}
      {query && (
        <>
          <section className="search-group" aria-labelledby="search-library">
            <h2 id="search-library">In your library</h2>
            {nothingLocal && (
              <p className="muted">Nothing in your library yet.</p>
            )}
            {(artists.length > 0 || albums.length > 0) && (
              <div className="personal-grid">
                {artists.slice(0, 6).map((a) => (
                  <a
                    key={a.id}
                    className="album-card"
                    href={"#/search?q=" + encodeURIComponent(a.name)}
                    onClick={(event) => {
                      if (
                        event.metaKey ||
                        event.ctrlKey ||
                        event.shiftKey ||
                        event.altKey
                      )
                        return;
                      event.preventDefault();
                      void api<CatalogueArtist>(
                        `/v1/catalogue/library-artists/${a.id}`,
                      )
                        .then((identity) => go(discoverUrl(identity)))
                        .catch((e) => setError(e.message));
                    }}
                  >
                    <Cover title={a.name} src={a.cover_url} artist />
                    <h3>{a.name}</h3>
                    <p>Artist</p>
                  </a>
                ))}
                {albums.slice(0, 12).map((a) => (
                  <a
                    key={a.id}
                    className="album-card"
                    href={"#/library/album/" + a.id}
                  >
                    <Cover title={a.title} src={a.cover_url} />
                    <h3>{a.title}</h3>
                    <p>{a.artist}</p>
                  </a>
                ))}
              </div>
            )}
            {local && local.tracks.length > 0 && songs(local.tracks)}
          </section>
          {local && local.household.length > 0 && (
            <section className="search-group" aria-labelledby="search-server">
              <h2 id="search-server">On the server</h2>
              <p className="muted">
                Already on the server. Tap to play; adding to your library is
                instant.
              </p>
              <div className="song-list">
                {local.household.map((t, i, all) => (
                  <SongRow
                    key={t.id}
                    song={fromTrack(t)}
                    queue={all.map((x) => fromTrack(x))}
                    index={i}
                  />
                ))}
              </div>
            </section>
          )}
          <section className="search-group" aria-labelledby="search-discover">
            <h2 id="search-discover">Discover</h2>
            {catalogue === null ? (
              <p role="status">Searching the music catalogue…</p>
            ) : catalogueFailed ? (
              <p className="muted">
                The music catalogue is unavailable right now. Your library
                results above are unaffected.
              </p>
            ) : catalogue.length ? (
              <ul className="discover-list">
                {catalogue.map((artist) => (
                  <li key={artist.id}>
                    <a href={"#" + discoverUrl(artist)}>
                      <strong>{artist.name}</strong>
                      {artist.description && <span>{artist.description}</span>}
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="muted">No catalogue artists match “{query}”.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
