import { apiFetch as fetch } from "./api";
import { useEffect, useRef, useState } from "react";
import { Search, X, ArrowRight, LoaderCircle, CircleCheck } from "lucide-react";
import { Cover } from "./Cover";
import type { Artist, Album, Track } from "./types";
type Discovered = {
  id: string;
  name: string;
  description?: string;
  saved_artist_id?: string | null;
};
type Results = {
  artists: Artist[];
  albums: Album[];
  tracks: Track[];
  available: Track[];
};
export function SearchPanel({
  compact = false,
  onArtist,
  onAlbum,
  onDiscover,
  onMigration,
}: {
  compact?: boolean;
  onArtist: (id: string) => void;
  onAlbum: (id: string) => void;
  onDiscover: (artist: Discovered) => void;
  onMigration: () => void;
}) {
  const [query, setQuery] = useState("");
  const [local, setLocal] = useState<Results | null>(null);
  const [external, setExternal] = useState<Discovered[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    setLocal(null);
    setExternal([]);
    setError("");
    if (query.trim().length < 2) {
      setBusy(false);
      return;
    }
    setBusy(true);
    async function get(path: string) {
      const response = await fetch("/api/" + path, {
        signal: controller.signal,
      });
      if (!response.ok)
        throw new Error(
          "Discovery is temporarily unavailable. Your collection is still searchable.",
        );
      return response.json();
    }
    const timer = setTimeout(() => {
      void get("search?q=" + encodeURIComponent(query))
        .then((data) => {
          if (!controller.signal.aborted) setLocal(data);
        })
        .catch(() => {});
      void get("catalogue/artists?q=" + encodeURIComponent(query))
        .then((data) => {
          if (!controller.signal.aborted) setExternal(data.artists);
        })
        .catch((e) => {
          if (!controller.signal.aborted) setError(e.message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setBusy(false);
        });
    }, 350);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);
  useEffect(() => {
    function dismiss(e: MouseEvent) {
      if (!wrapper.current?.contains(e.target as Node)) setOpen(false);
    }
    function escape(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  function choose(action: () => void) {
    setOpen(false);
    setQuery("");
    action();
  }
  const outside = external.filter((a) => !a.saved_artist_id);
  const results = (
    <>
      <div className="search-divider">Your collection</div>
      {local?.artists.slice(0, compact ? 5 : 20).map((a) => (
        <button
          className="result-row"
          key={a.id}
          onClick={() => choose(() => onArtist(a.id))}
        >
          <Cover title={a.name} src={a.cover_url} artist />
          <div>
            <strong>{a.name}</strong>
            <span>{a.album_count} releases</span>
          </div>
          <CircleCheck size={16} className="saved-icon" />
        </button>
      ))}
      {local?.albums.slice(0, compact ? 3 : 12).map((a) => (
        <button
          className="result-row"
          key={a.id}
          onClick={() => choose(() => onAlbum(a.id))}
        >
          <Cover title={a.title} src={a.cover_url} />
          <div>
            <strong>{a.title}</strong>
            <span>{a.artist}</span>
          </div>
          <CircleCheck size={16} className="saved-icon" />
        </button>
      ))}
      {local?.tracks.slice(0, compact ? 3 : 12).map((t) => (
        <button
          className="result-row"
          key={t.id}
          onClick={() => choose(() => onAlbum(t.album_id!))}
        >
          <div>
            <strong>{t.title}</strong>
            <span>
              {t.artist} · {t.album}
            </span>
          </div>
          <CircleCheck size={16} className="saved-icon" />
        </button>
      ))}
      {local &&
        !local.artists.length &&
        !local.albums.length &&
        !local.tracks.length && (
          <p className="search-empty">No saved matches.</p>
        )}
      {!!local?.available.length && (
        <button className="result-row" onClick={() => choose(onMigration)}>
          <div>
            <strong>From your import</strong>
            <span>{local.available.length} songs not yet saved</span>
          </div>
          <ArrowRight size={16} />
        </button>
      )}
      <div className="search-divider">Find artists outside your collection</div>
      {busy && (
        <p className="subtle-loading">
          <LoaderCircle className="spin" size={15} /> Finding artists…
        </p>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {outside.map((a) => (
        <button
          className="result-row"
          key={a.id}
          onClick={() => choose(() => onDiscover(a))}
        >
          <Cover
            title={a.name}
            artist
            src={`/api/catalogue/artists/${a.id}/artwork`}
          />
          <div>
            <strong>{a.name}</strong>
            <span>{a.description}</span>
          </div>
          <ArrowRight size={16} />
        </button>
      ))}
      {!busy && !error && !outside.length && query.trim().length >= 2 && (
        <p className="search-empty">No additional artists matched.</p>
      )}
    </>
  );
  return (
    <div
      ref={wrapper}
      className={compact ? "header-search" : "discovery-search"}
    >
      <div className={compact ? "header-search-input" : "search-large"}>
        <Search size={compact ? 16 : 22} />
        <input
          aria-label={
            compact
              ? "Search your collection and discover artists"
              : "Search artists, albums and tracks"
          }
          placeholder={compact ? "Find music…" : "An artist, an album, a song…"}
          value={query}
          autoFocus={!compact}
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
        />
        {query && (
          <button
            className="icon-button"
            aria-label="Clear search"
            onClick={() => setQuery("")}
          >
            <X size={16} />
          </button>
        )}
      </div>
      {query.trim().length >= 2 && (!compact || open) && (
        <div
          className={compact ? "header-search-dropdown" : "discovery-results"}
          aria-label="Search results"
        >
          {results}
        </div>
      )}
      {!compact && query.trim().length < 2 && (
        <p className="section-description">
          Search your collection and find artists to add.
        </p>
      )}
    </div>
  );
}
