import { SavedArtistHeading } from "./SavedArtistHeading";
import { CatalogueBrowser } from "./CatalogueBrowser";
import { Shuffle } from "lucide-react";
import { shuffled } from "./shuffle";
import { useEffect, useRef, useState } from "react";
import { Play, ArrowLeft, ListMusic } from "lucide-react";
import { api } from "./api";
import { PersonalQuality } from "./PersonalQuality";
import { SearchPage } from "./SearchPage";
import { Cover } from "./Cover";
import { CollectionPages } from "./CollectionPages";
import { ShuffleLibrary } from "./ShuffleLibrary";
import { SongRow } from "./SongRow";
import { fromTrack, playlistSongs, type Song } from "./songs";
import { warmCovers, whenIdle } from "./prefetch";
import { usePlayer } from "./Player";
import type { Album, Artist, Library, Track } from "./types";
import type { Person } from "./AppShell";
import { go, type Route } from "./routes";
import {
  OwnerAlbumTools,
  OwnerArtistTools,
  OwnerLibraryLinks,
} from "./OwnerTools";

type Entry = Track & {
  entry_id: string;
  position: number;
  saved_track?: Track | null;
  household_available?: boolean;
};
type Playlist = {
  id: string;
  name: string;
  revision: number;
  favourites?: boolean;
  entries: Entry[];
};
type PlaylistSummary = {
  id: string;
  name: string;
  track_count?: number;
  available_count?: number;
};
type Preview = {
  confirmation: string;
  delete_count: number;
  keep_count: number;
  items: { track_id: string; delete_file: boolean; kept_for: string[] }[];
};
const libraryTabs = [
  "artists",
  "albums",
  "musicals",
  "soundtracks",
  "compilations",
  "playlists",
  "favourites",
] as const;
// Each album section shows one category; empty sections stay hidden.
const sectionCategory = {
  albums: "album",
  musicals: "musical",
  soundtracks: "soundtrack",
  compilations: "compilation",
} as const;
type Section = keyof typeof sectionCategory;
type LibraryTab = (typeof libraryTabs)[number];
const tabLabel = (id: string) => id[0].toUpperCase() + id.slice(1);

export function PersonalLibrary({
  user,
  route,
}: {
  user: Person;
  route: Route;
}) {
  const owner = user.role === "owner";
  const searching = route.section === "search";
  const [catalogue, setCatalogue] = useState<{
    id: string;
    name: string;
    release?: string;
    group?: string;
  } | null>(null);
  const [library, setLibrary] = useState<Library | null>(null);
  const [tab, setTab] = useState<LibraryTab>("artists");
  const [detail, setDetail] = useState<{
    title: string;
    artist?: Artist;
    cover?: string | null;
    quality?: { scope: "artist" | "album"; itemId: string };
    tracks?: Track[];
    albums?: Album[];
    playlist?: Playlist;
  } | null>(null);
  const [playlists, setPlaylists] = useState<PlaylistSummary[]>([]);
  const [favouriteList, setFavouriteList] = useState<Playlist | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [removal, setRemoval] = useState<{
    preview: Preview;
    ids: string[];
  } | null>(null);
  const [undo, setUndo] = useState<{ id: string; undo_until: number } | null>(
    null,
  );
  const dialog = useRef<HTMLDialogElement>(null);
  const player = usePlayer();
  async function refresh() {
    const [summary, list] = await Promise.all([
      api<Library>("/v1/library"),
      api<{ playlists: PlaylistSummary[] }>("/v1/playlists"),
    ]);
    setLibrary(summary);
    setPlaylists(list.playlists);
    // Library artwork is always ready, whichever tab opens next.
    whenIdle(() =>
      warmCovers([
        ...summary.artists
          .filter((a) => !a.compilation_only)
          .map((a) => a.cover_url),
        ...summary.albums.map((a) => a.cover_url),
      ]),
    );
    const favouriteList = list.playlists.find((p) =>
      p.id.startsWith("pig-favourites:"),
    );
    setFavouriteList(
      favouriteList
        ? await api<Playlist>("/v1/playlists/" + favouriteList.id)
        : null,
    );
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
    const changed = () => void refresh().catch((e) => setError(e.message));
    window.addEventListener("music-library-changed", changed);
    return () => window.removeEventListener("music-library-changed", changed);
  }, []);
  const [kind, id] = route.parts;
  const routeKey = `${route.section}/${route.parts.join("/")}?${route.params}`;
  useEffect(() => {
    if (searching && kind === "artist" && id) {
      setCatalogue({
        id,
        name: route.params.get("name") || "Artist",
        release: route.params.get("release") || undefined,
        group: route.params.get("group") || undefined,
      });
      return;
    }
    setCatalogue(null);
    if (searching) return setDetail(null);
    if (libraryTabs.includes(kind as LibraryTab)) setTab(kind as LibraryTab);
    if (kind === "album" && id) void openAlbum({ id } as Album);
    else if (kind === "artist" && id) void openArtist({ id } as Artist);
    else if (kind === "playlist" && id) void openPlaylist(id);
    else setDetail(null);
  }, [routeKey]);
  const backToLibrary = () => go("/library/" + tab);
  useEffect(() => {
    // Keep the chosen collection visible in the sideways tab strip.
    document
      .querySelector(".personal-tabs [aria-current]")
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [tab, !!library]);
  useEffect(() => {
    if (removal) dialog.current?.showModal();
  }, [removal]);
  useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(
      () => setUndo(null),
      Math.max(0, undo.undo_until * 1000 - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [undo]);
  async function action(fn: () => Promise<unknown>, message = "Saved") {
    setError("");
    try {
      await fn();
      setNotice(message);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function openAlbum(album: Album) {
    try {
      const data = await api<Album & { tracks: Track[] }>(
        "/v1/albums/" + album.id,
      );
      setDetail({
        title: data.title,
        cover: data.cover_url,
        tracks: data.tracks,
        quality: { scope: "album", itemId: data.id },
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function openArtist(artist: Artist) {
    try {
      const data = await api<
        Artist & { albums: Album[]; compilation_tracks?: Track[] }
      >("/v1/artists/" + artist.id);
      setDetail({
        title: data.name,
        artist: data,
        quality: { scope: "artist", itemId: data.id },
        albums: data.albums,
        tracks: data.compilation_tracks,
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function openPlaylist(id: string) {
    try {
      const data = await api<Playlist>("/v1/playlists/" + id);
      setDetail({
        title: data.name,
        tracks: data.entries.map((t) => t.saved_track || t),
        playlist: data,
      });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function preview(ids: string[]) {
    try {
      const data = await api<Preview>("/v1/library/removal-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_ids: ids }),
      });
      setRemoval({ preview: data, ids });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function songs(tracks: Track[], playlist?: Playlist) {
    const albumArtist =
      detail?.quality?.scope === "album" && tracks[0]?.album_artist;
    const artistName = detail?.artist?.name;
    const list: Song[] = playlist
      ? playlistSongs(playlist.entries, detail?.cover)
      : tracks.map((t) => fromTrack(t, detail?.cover));
    return (
      <CollectionPages key={detail?.title || tab} items={list} label="Songs">
        {(items) => (
          <div className="song-list">
            {items.map((song) => {
              const i = list.indexOf(song);
              const t = tracks[i];
              const entry = playlist?.entries[i];
              return (
                <SongRow
                  key={song.key}
                  song={song}
                  queue={list}
                  index={i}
                  numbered={!!albumArtist}
                  onAlbum={!!albumArtist}
                  onArtist={
                    !!(albumArtist || artistName) &&
                    t.artist.toLocaleLowerCase() ===
                      String(albumArtist || artistName).toLocaleLowerCase()
                  }
                  onRemove={playlist ? undefined : () => void preview([t.id])}
                  menu={
                    playlist &&
                    !playlist.favourites &&
                    entry && (
                      <>
                        <button
                          role="menuitem"
                          disabled={entry.position === 0}
                          onClick={() =>
                            void action(async () => {
                              await api(`/v1/playlists/${playlist.id}`, {
                                method: "PATCH",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                  revision: playlist.revision,
                                  order: playlist.entries
                                    .map((e) => e.position)
                                    .map((p) =>
                                      p === entry.position
                                        ? p - 1
                                        : p === entry.position - 1
                                          ? p + 1
                                          : p,
                                    ),
                                }),
                              });
                              await openPlaylist(playlist.id);
                            })
                          }
                        >
                          <span>Move up</span>
                        </button>
                        <button
                          role="menuitem"
                          className="danger"
                          onClick={() =>
                            void action(async () => {
                              await api(
                                `/v1/playlists/${playlist.id}/songs/${entry.position}?revision=${playlist.revision}`,
                                { method: "DELETE" },
                              );
                              await openPlaylist(playlist.id);
                            })
                          }
                        >
                          <span>Remove from playlist</span>
                        </button>
                      </>
                    )
                  }
                />
              );
            })}
          </div>
        )}
      </CollectionPages>
    );
  }
  if (catalogue)
    return (
      <main className="personal-main">
        <CatalogueBrowser
          key={catalogue.id + (catalogue.release || "")}
          artist={catalogue}
          close={() =>
            // Return to the results that opened this artist, query included.
            history.length > 1 ? history.back() : go("/search")
          }
          notify={setNotice}
          initialRelease={catalogue.release}
          initialGroup={catalogue.group}
          owner={owner}
        />
        {notice && <p role="status">{notice}</p>}
      </main>
    );
  if (!library)
    return (
      <main className="personal-main">
        <p role={error ? "alert" : "status"}>
          {error || "Loading your library…"}
        </p>
      </main>
    );
  const counts: Record<string, number> = {
    musicals: library.stats.musicals,
    soundtracks: library.stats.soundtracks,
    compilations: library.stats.compilations,
  };
  const visibleTabs = libraryTabs.filter((id) => counts[id] !== 0);
  return (
    <main className="personal-main">
      {searching ? (
        <h1>Search</h1>
      ) : detail?.artist ? (
        <SavedArtistHeading artist={detail.artist} personal />
      ) : (
        <h1>{detail?.title || "Your library"}</h1>
      )}
      {!searching && !detail && (
        <p>
          {user.display_name} · {library.stats.tracks} songs
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {undo && (
        <p className="personal-status" role="status">
          Removed from your library.{" "}
          <button
            onClick={() =>
              void action(async () => {
                await api(`/v1/library/removals/${undo.id}/undo`, {
                  method: "POST",
                });
                setUndo(null);
                backToLibrary();
              }, "Restored")
            }
          >
            Undo
          </button>
        </p>
      )}
      {searching ? (
        <SearchPage
          query={route.params.get("q") || ""}
          library={library}
          songs={(tracks) => songs(tracks)}
        />
      ) : detail ? (
        <>
          <button className="text-button" onClick={backToLibrary}>
            <ArrowLeft size={18} /> Back to library
          </button>
          {(detail.playlist || detail.quality?.scope === "album") && (
            <div className="release-actions">
              {[false, true].map((shuffle) => {
                const playable = detail.playlist
                  ? playlistSongs(detail.playlist.entries, detail.cover)
                  : (detail.tracks || [])
                      .filter((t) => t.available !== false)
                      .map((t) => fromTrack(t, detail.cover));
                return (
                  <button
                    key={String(shuffle)}
                    className={shuffle ? "secondary-button" : "primary-button"}
                    disabled={!playable.length}
                    onClick={() => {
                      const queue = shuffle ? shuffled(playable) : playable;
                      player.play(queue, 0);
                    }}
                  >
                    {shuffle ? <Shuffle size={18} /> : <Play size={18} />}{" "}
                    {shuffle ? "Shuffle" : "Play"}
                  </button>
                );
              })}
            </div>
          )}
          {detail.quality && (
            <PersonalQuality key={detail.quality.itemId} {...detail.quality} />
          )}
          {detail.playlist && !detail.playlist.favourites && (
            <details className="playlist-options">
              <summary>Playlist options</summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const name = new FormData(e.currentTarget).get("name");
                  void action(async () => {
                    const p = detail.playlist!;
                    await api(`/v1/playlists/${p.id}`, {
                      method: "PATCH",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ revision: p.revision, name }),
                    });
                    await openPlaylist(p.id);
                  });
                }}
              >
                <label>
                  Playlist name
                  <input
                    name="name"
                    defaultValue={detail.playlist.name}
                    required
                    maxLength={100}
                  />
                </label>
                <button type="submit">Rename</button>
              </form>
              <button
                onClick={() => {
                  if (
                    confirm(
                      "Delete this playlist? Music files stay in your library.",
                    )
                  )
                    void action(async () => {
                      await api(
                        `/v1/playlists/${detail.playlist!.id}?revision=${detail.playlist!.revision}`,
                        { method: "DELETE" },
                      );
                      backToLibrary();
                    }, "Playlist deleted");
                }}
              >
                Delete playlist
              </button>
            </details>
          )}
          {detail.albums && (
            <div className="personal-grid">
              {detail.albums.map((a) => (
                <button key={a.id} onClick={() => go("/library/album/" + a.id)}>
                  <Cover title={a.title} src={a.cover_url} />
                  <h3>{a.title}</h3>
                </button>
              ))}
            </div>
          )}
          {detail.tracks && songs(detail.tracks, detail.playlist)}
          {owner && detail.quality?.scope === "album" && (
            <OwnerAlbumTools id={detail.quality.itemId} title={detail.title} />
          )}
          {owner && detail.quality?.scope === "artist" && (
            <OwnerArtistTools id={detail.quality.itemId} title={detail.title} />
          )}
        </>
      ) : (
        <>
          <div className="library-toolbar">
            <nav className="personal-tabs" aria-label="Library collections">
              {visibleTabs.map((id) => (
                <a
                  key={id}
                  href={"#/library/" + id}
                  aria-current={tab === id ? "page" : undefined}
                >
                  {tabLabel(id)}
                </a>
              ))}
            </nav>
            <ShuffleLibrary total={library.stats.tracks} />
          </div>
          {tab === "artists" && (
            <CollectionPages<Artist>
              key={tab}
              items={library.artists.filter((a) => !a.compilation_only)}
              label="artists"
            >
              {(items) => (
                <div className="personal-grid">
                  {items.map((artist) => (
                    <a
                      key={artist.id}
                      className="album-card"
                      href={"#/library/artist/" + artist.id}
                    >
                      <Cover
                        title={artist.name}
                        src={artist.cover_url}
                        artist
                      />
                      <h3>{artist.name}</h3>
                      <p>
                        {artist.album_count} album
                        {artist.album_count === 1 ? "" : "s"}
                      </p>
                    </a>
                  ))}
                </div>
              )}
            </CollectionPages>
          )}
          {tab in sectionCategory && (
            <CollectionPages<Album>
              key={tab}
              items={library.albums.filter(
                (a) => a.category === sectionCategory[tab as Section],
              )}
              label={tab}
            >
              {(items) => (
                <div className="personal-grid">
                  {items.map((album) => (
                    <a
                      key={album.id}
                      className="album-card"
                      href={"#/library/album/" + album.id}
                    >
                      <Cover title={album.title} src={album.cover_url} />
                      <h3>{album.title}</h3>
                      <p>
                        {tab === "albums"
                          ? `${album.track_count} songs`
                          : album.artist}
                      </p>
                    </a>
                  ))}
                </div>
              )}
            </CollectionPages>
          )}
          {tab === "favourites" &&
            (favouriteList?.entries.length ? (
              songs(
                favouriteList.entries.map((e) => e.saved_track || e),
                favouriteList,
              )
            ) : (
              <p className="muted">
                Tap the heart on any song to keep it here. Favourites never
                download anything by themselves.
              </p>
            ))}
          {tab === "playlists" && (
            <>
              <form
                className="search-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  void action(
                    () =>
                      api("/v1/playlists", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                          name: new FormData(form).get("name"),
                        }),
                      }),
                    "Playlist created",
                  ).then(() => form.reset());
                }}
              >
                <label>
                  New playlist
                  <input name="name" required maxLength={100} />
                </label>
                <button type="submit" className="secondary-button">
                  Create
                </button>
              </form>
              <ul className="playlist-list">
                {playlists
                  .filter((p) => !p.id.startsWith("pig-favourites:"))
                  .map((p) => (
                    <li key={p.id}>
                      <a href={"#/library/playlist/" + p.id}>
                        <ListMusic size={22} aria-hidden="true" />
                        <strong>{p.name}</strong>
                        <span>
                          {p.track_count ?? 0} song
                          {p.track_count === 1 ? "" : "s"}
                          {p.track_count &&
                          p.available_count !== undefined &&
                          p.available_count < p.track_count
                            ? ` · ${p.available_count} available`
                            : ""}
                        </span>
                      </a>
                    </li>
                  ))}
              </ul>
              {tab === "playlists" && (
                <section className="account-section">
                  <h2>Import your playlists</h2>
                  <p>
                    Choose an Apple Music XML export. This saves your playlists
                    without requesting downloads.
                  </p>
                  <label>
                    Apple Music XML
                    <input
                      type="file"
                      accept=".xml"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file)
                          void action(
                            () =>
                              api("/v1/imports/apple", {
                                method: "POST",
                                headers: { "Content-Type": "application/xml" },
                                body: file,
                              }),
                            "Your playlists were imported",
                          );
                      }}
                    />
                  </label>
                </section>
              )}
            </>
          )}
          {owner && <OwnerLibraryLinks />}
        </>
      )}
      {removal && (
        <dialog ref={dialog} onCancel={() => setRemoval(null)}>
          <h2>Remove from your library?</h2>
          <p>
            {removal.preview.delete_count
              ? `${removal.preview.delete_count} music files will move to recoverable trash on the server.`
              : "The music files will stay on the server."}
          </p>
          {removal.preview.items
            .filter((i) => !i.delete_file)
            .map((i) => (
              <p key={i.track_id}>
                Kept for {i.kept_for.join(", ") || "another pending request"}.
              </p>
            ))}
          <button onClick={() => setRemoval(null)}>Cancel</button>
          <button
            onClick={() =>
              void action(async () => {
                const r = await api<{ id: string; undo_until: number }>(
                  "/v1/library/remove",
                  {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      track_ids: removal.ids,
                      confirmation: removal.preview.confirmation,
                    }),
                  },
                );
                setUndo(r);
                setRemoval(null);
                setDetail(null);
              }, "Removed from your library")
            }
          >
            Remove
          </button>
        </dialog>
      )}
    </main>
  );
}
