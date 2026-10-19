import { useEffect, useRef, useState, type ReactNode } from "react";
import { CircleCheck } from "lucide-react";
import { api } from "./api";
import { Cover, catalogueArtistCover } from "./Cover";
import { discoverUrl } from "./navigation";
import { go } from "./routes";
import { SongRow } from "./SongRow";
import { fromTrack } from "./songs";
import { warmArtist, whenIdle } from "./prefetch";
import type { Album, Artist, Library, Track } from "./types";

type CatalogueArtist = { id: string; name: string; description?: string };
type Local = { tracks: Track[]; household: Track[] };
const fold = (value: string) => value.toLocaleLowerCase().normalize("NFKD");
const clean = (value: string) => value.trim().slice(0, 150);

/** Type-ahead waits this long after the last keystroke (at least 300 ms, so
 * typing adds no catalogue load). */
export const SEARCH_DEBOUNCE_MS = 350;
const CATALOGUE_MINIMUM = 2;
const ANSWER_LIFETIME_MS = 5 * 60_000;

/** Answers by query, reused while fresh so backspacing or retyping sends no
 * request. Library answers are dropped when the library changes. */
const answers = new Map<
  string,
  { time: number; local?: Local; catalogue?: CatalogueArtist[] }
>();
window.addEventListener("music-library-changed", () => {
  for (const answer of answers.values()) delete answer.local;
});
function answer(key: string) {
  const found = answers.get(key);
  if (found && Date.now() - found.time > ANSWER_LIFETIME_MS) {
    answers.delete(key);
    return undefined;
  }
  return found;
}
function remember(
  key: string,
  update: (entry: {
    time: number;
    local?: Local;
    catalogue?: CatalogueArtist[];
  }) => void,
) {
  if (!answers.has(key) && answers.size >= 60)
    answers.delete(answers.keys().next().value!);
  const entry = answers.get(key) || { time: Date.now() };
  update(entry);
  answers.set(key, entry);
}

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
  const [text, setText] = useState(query);
  // The query being searched: the address's, then what is typed, once
  // typing pauses.
  const [active, setActive] = useState(clean(query));
  const typed = useRef(false);
  useEffect(() => {
    // Arriving from elsewhere (a link, back): the address wins.
    if (clean(query) === active) return;
    typed.current = false;
    setText(query);
    setActive(clean(query));
  }, [query]);
  useEffect(() => {
    if (!typed.current) return;
    const next = clean(text);
    const timer = setTimeout(() => {
      setActive(next);
      // Keep the address in step without a history entry per keystroke.
      history.replaceState(
        null,
        "",
        next ? "#/search?q=" + encodeURIComponent(next) : "#/search",
      );
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [text]);
  const [local, setLocal] = useState<Local | null>(null);
  const [catalogue, setCatalogue] = useState<CatalogueArtist[] | null>(null);
  const [catalogueFailed, setCatalogueFailed] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setCatalogueFailed(false);
    setError("");
    const key = fold(active);
    const saved = answer(key);
    setLocal(saved?.local ?? null);
    setCatalogue(
      active.length < CATALOGUE_MINIMUM ? [] : (saved?.catalogue ?? null),
    );
    if (!active) return;
    // A newer query aborts this one's requests.
    const controller = new AbortController();
    const signal = controller.signal;
    // Local results arrive first; the catalogue can be slower or unavailable.
    if (!saved?.local)
      void api<{ tracks: Track[]; household_tracks: Track[] }>(
        "/v1/search?q=" + encodeURIComponent(active),
        { signal },
      )
        .then((found) => {
          const value = {
            tracks: found.tracks,
            household: found.household_tracks,
          };
          remember(key, (entry) => (entry.local = value));
          if (!signal.aborted) setLocal(value);
        })
        .catch((e) => {
          if (!signal.aborted) setError(e.message);
        });
    if (active.length >= CATALOGUE_MINIMUM && !saved?.catalogue)
      void api<{ artists: CatalogueArtist[] }>(
        "/v1/catalogue/artists?q=" + encodeURIComponent(active),
        { signal },
      )
        .then((found) => {
          remember(key, (entry) => (entry.catalogue = found.artists));
          if (signal.aborted) return;
          setCatalogue(found.artists);
          // The likely next tap: essentials for three, everything for two.
          whenIdle(() =>
            found.artists
              .slice(0, 3)
              .forEach((a, i) => warmArtist(a.id, i < 2, a.name)),
          );
        })
        .catch(() => {
          if (!signal.aborted) {
            setCatalogue([]);
            setCatalogueFailed(true);
          }
        });
    return () => controller.abort();
  }, [active]);

  const needle = fold(active);
  const artists = active
    ? library.artists.filter((a: Artist) => fold(a.name).includes(needle))
    : [];
  const owned = new Set(library.artists.map((a) => fold(a.name)));
  const albums = active
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
          // Enter searches at once and keeps a history entry.
          const q = clean(text);
          typed.current = false;
          setActive(q);
          if (q) go("/search?q=" + encodeURIComponent(q));
        }}
      >
        <label>
          Artists, albums or songs
          <input
            name="q"
            type="search"
            aria-label="Search artists, albums or songs"
            value={text}
            onChange={(e) => {
              typed.current = true;
              setText(e.target.value);
            }}
            required
            maxLength={150}
            autoFocus={!query}
            autoComplete="off"
          />
        </label>
        <button type="submit" className="primary-button">
          Search
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {active && !local && !error && <p role="status">Searching…</p>}
      {active && (
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
                      <Cover
                        title={artist.name}
                        src={catalogueArtistCover(artist.id)}
                        artist
                        sizes="48px"
                      />
                      <span className="discover-text">
                        <strong>{artist.name}</strong>
                        <span>
                          {["Artist", artist.description]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      {owned.has(fold(artist.name)) && (
                        <span className="discover-owned">
                          <CircleCheck size={14} aria-hidden="true" /> In your
                          library
                        </span>
                      )}
                    </a>
                  </li>
                ))}
              </ul>
            ) : active.length < CATALOGUE_MINIMUM ? (
              <p className="muted">
                Type another letter to search the catalogue.
              </p>
            ) : (
              <p className="muted">No catalogue artists match “{active}”.</p>
            )}
          </section>
        </>
      )}
    </>
  );
}
