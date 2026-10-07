import { SavedArtistHeading } from "./SavedArtistHeading";
import { CatalogueBrowser } from "./CatalogueBrowser";
import { MusicLink } from "./MusicLink";
import { PlaylistPicker } from "./PlaylistPicker";
import { Shuffle } from "lucide-react";
import { shuffled } from "./shuffle";
import { useEffect, useRef, useState } from "react";
import {
  Cloud,
  CirclePlus,
  Heart,
  Play,
  ArrowLeft,
  Ellipsis,
} from "lucide-react";
import { api } from "./api";
import { PersonalRequests } from "./PersonalRequests";
import { PersonalQuality } from "./PersonalQuality";
import { CatalogueExplorer } from "./CatalogueExplorer";
import { Cover } from "./Cover";
import { CollectionPages } from "./CollectionPages";
import { usePlayer } from "./Player";
import type { Album, Artist, Library, Track } from "./types";
import type { Person } from "./AccountsShell";

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
type Preview = {
  confirmation: string;
  delete_count: number;
  keep_count: number;
  items: { track_id: string; delete_file: boolean; kept_for: string[] }[];
};
const clean = (t: Track) => ({
  year: String(t.year || ""),
  musicbrainz_release_id: t.musicbrainz_release_id,
  musicbrainz_recording_id: t.musicbrainz_recording_id,
  title: t.title,
  artist: t.artist,
  album: t.album,
  album_artist: t.album_artist,
  duration: t.duration,
  track_number: t.track_number,
  disc_number: t.disc_number,
});
export function PersonalLibrary({ user }: { user: Person }) {
  const [catalogue, setCatalogue] = useState<{
    id: string;
    name: string;
    release?: string;
    group?: string;
  } | null>(null);
  const [favourites, setFavourites] = useState<Set<string>>(new Set());
  const [library, setLibrary] = useState<Library | null>(null);
  const [tab, setTab] = useState("artists");
  const [detail, setDetail] = useState<{
    title: string;
    artist?: Artist;
    cover?: string | null;
    quality?: { scope: "artist" | "album"; itemId: string };
    tracks?: Track[];
    albums?: Album[];
    playlist?: Playlist;
  } | null>(null);
  const [playlists, setPlaylists] = useState<{ id: string; name: string }[]>(
    [],
  );
  const [search, setSearch] = useState<{
    tracks: Track[];
    household_tracks: Track[];
  } | null>(null);
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
      api<{ playlists: { id: string; name: string }[] }>("/v1/playlists"),
    ]);
    setLibrary(summary);
    setPlaylists(list.playlists);
    const favouriteList = list.playlists.find((p) =>
      p.id.startsWith("pig-favourites:"),
    );
    if (favouriteList) {
      const values = await api<Playlist>("/v1/playlists/" + favouriteList.id);
      setFavourites(
        new Set(values.entries.map((t) => t.saved_track?.id || t.id)),
      );
    } else setFavourites(new Set());
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
    const changed = () => void refresh().catch((e) => setError(e.message));
    window.addEventListener("music-library-changed", changed);
    const events = new EventSource("/api/v1/events");
    events.addEventListener("revision", changed);
    events.addEventListener("queue", () =>
      window.dispatchEvent(new Event("music-requests-changed")),
    );
    events.addEventListener("revoked", () =>
      window.dispatchEvent(new Event("music-auth-required")),
    );
    let fallback: ReturnType<typeof setInterval> | undefined;
    events.onerror = () => {
      fallback ||= setInterval(() => {
        changed();
        window.dispatchEvent(new Event("music-requests-changed"));
      }, 15000);
    };
    events.onopen = () => {
      clearInterval(fallback);
      fallback = undefined;
    };
    return () => {
      events.close();
      clearInterval(fallback);
      window.removeEventListener("music-library-changed", changed);
    };
  }, []);
  useEffect(() => {
    const route = () => {
      const [path, query] = location.hash.replace(/^#\/?/, "").split("?");
      const [page, kind, id] = path.split("/");
      if (page === "search" && kind === "artist" && id) {
        const params = new URLSearchParams(query);
        setCatalogue({
          id,
          name: params.get("name") || "Artist",
          release: params.get("release") || undefined,
          group: params.get("group") || undefined,
        });
        return;
      }
      setCatalogue(null);
      if (!kind) setDetail(null);
      if (kind === "album" && id) void openAlbum({ id } as Album);
      else if (kind === "artist" && id) void openArtist({ id } as Artist);
      else if (kind === "playlist" && id) void openPlaylist(id);
    };
    route();
    window.addEventListener("hashchange", route);
    return () => window.removeEventListener("hashchange", route);
  }, []);
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
  async function add(t: Track) {
    await action(
      () =>
        api("/v1/requests", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tracks: [clean(t)] }),
        }),
      "Added or requested for your library",
    );
    setSearch(null);
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
    return (
      <CollectionPages key={detail?.title || tab} items={tracks} label="Songs">
        {(items) =>
          items.map((t) => {
            const entry = playlist?.entries[tracks.indexOf(t)];
            const saved = playlist
              ? !!entry?.saved_track
              : t.available !== false;
            return (
              <article className="personal-track" key={entry?.entry_id || t.id}>
                <Cover title={t.title} src={t.cover_url || detail?.cover} />
                <div>
                  <strong>{t.title}</strong>
                  <p>
                    <MusicLink artist={t.artist} /> ·{" "}
                    <MusicLink artist={t.artist} album={t.album} />
                  </p>
                </div>
                <button
                  aria-label={
                    saved ? `Play ${t.title}` : `Add or request ${t.title}`
                  }
                  onClick={() =>
                    saved
                      ? player.playSaved(
                          t,
                          playlist
                            ? playlist.entries.flatMap((e) =>
                                e.saved_track ? [e.saved_track] : [],
                              )
                            : tracks.filter((x) => x.available !== false),
                        )
                      : void add(t)
                  }
                >
                  {saved ? <Play size={20} /> : <CirclePlus size={20} />}
                </button>
                <span
                  aria-label={
                    saved
                      ? "On the server"
                      : entry?.household_available
                        ? "On server. Add to your library"
                        : "Not in your library"
                  }
                >
                  {saved ? <Cloud size={20} /> : null}
                </span>
                <button
                  aria-label={
                    favourites.has(t.id)
                      ? `Remove ${t.title} from favourites`
                      : `Favourite ${t.title}`
                  }
                  onClick={() =>
                    void action(
                      () =>
                        api("/v1/favourites", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            track: clean(t),
                            favourite: !favourites.has(t.id),
                          }),
                        }),
                      favourites.has(t.id)
                        ? "Removed from favourites"
                        : "Added to favourites",
                    )
                  }
                >
                  <Heart
                    size={18}
                    fill={favourites.has(t.id) ? "currentColor" : "none"}
                  />
                </button>
                {!playlist && (
                  <PlaylistPicker
                    title={t.title}
                    load={async () =>
                      (
                        await api<{
                          playlists: { id: string; name: string }[];
                        }>("/v1/playlists")
                      ).playlists.filter(
                        (p) => !p.id.startsWith("pig-favourites:"),
                      )
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
                        body: JSON.stringify(clean(t)),
                      }).then(() =>
                        window.dispatchEvent(
                          new Event("music-library-changed"),
                        ),
                      )
                    }
                  />
                )}
                <details>
                  <summary aria-label={`More options for ${t.title}`}>
                    <Ellipsis size={20} />
                  </summary>
                  {saved && (
                    <button onClick={() => void preview([t.id])}>
                      Remove from my library
                    </button>
                  )}
                  {playlist && !playlist.favourites && entry && (
                    <>
                      <button
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
                                  .map((i) =>
                                    i === entry.position
                                      ? i - 1
                                      : i === entry.position - 1
                                        ? i + 1
                                        : i,
                                  ),
                              }),
                            });
                            await openPlaylist(playlist.id);
                          })
                        }
                      >
                        Move up
                      </button>
                      <button
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
                        Remove from playlist
                      </button>
                    </>
                  )}
                </details>
              </article>
            );
          })
        }
      </CollectionPages>
    );
  }
  if (catalogue)
    return (
      <main className="personal-main">
        <CatalogueBrowser
          key={catalogue.id + (catalogue.release || "")}
          artist={catalogue}
          close={() => {
            location.hash = "/library";
          }}
          notify={setNotice}
          initialRelease={catalogue.release}
          initialGroup={catalogue.group}
          personal
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
  return (
    <main className="personal-main">
      {detail?.artist ? (
        <SavedArtistHeading artist={detail.artist} personal />
      ) : (
        <h1>{detail?.title || "Your library"}</h1>
      )}
      <p>
        {user.display_name} · {library.stats.tracks} songs
      </p>
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
                setDetail(null);
              }, "Restored")
            }
          >
            Undo
          </button>
        </p>
      )}
      {detail ? (
        <>
          <button className="text-button" onClick={() => setDetail(null)}>
            <ArrowLeft size={18} /> Back to library
          </button>
          {detail.playlist && (
            <div className="release-actions">
              {[false, true].map((shuffle) => (
                <button
                  key={String(shuffle)}
                  className={shuffle ? "secondary-button" : "primary-button"}
                  disabled={
                    !detail.playlist!.entries.some((e) => e.saved_track)
                  }
                  onClick={() => {
                    const tracks = detail.playlist!.entries.flatMap((e) =>
                      e.saved_track ? [e.saved_track] : [],
                    );
                    const queue = shuffle ? shuffled(tracks) : tracks;
                    player.playSaved(queue[0], queue, 0);
                  }}
                >
                  {shuffle ? <Shuffle size={18} /> : <Play size={18} />}{" "}
                  {shuffle ? "Shuffle" : "Play"}
                </button>
              ))}
            </div>
          )}
          {detail.quality && (
            <PersonalQuality key={detail.quality.itemId} {...detail.quality} />
          )}
          {detail.playlist && !detail.playlist.favourites && (
            <div>
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
                      setDetail(null);
                    }, "Playlist deleted");
                }}
              >
                Delete playlist
              </button>
            </div>
          )}
          {detail.albums && (
            <div className="personal-grid">
              {detail.albums.map((a) => (
                <button key={a.id} onClick={() => void openAlbum(a)}>
                  <Cover title={a.title} src={a.cover_url} />
                  <h3>{a.title}</h3>
                </button>
              ))}
            </div>
          )}
          {detail.tracks && songs(detail.tracks, detail.playlist)}
        </>
      ) : (
        <>
          <nav className="personal-tabs" aria-label="Library collections">
            {[
              "artists",
              "albums",
              "playlists",
              "favourites",
              "search",
              "requests",
              "import",
            ].map((id) => (
              <button
                key={id}
                aria-pressed={tab === id}
                onClick={() => {
                  setTab(id);
                  setSearch(null);
                }}
              >
                {id[0].toUpperCase() + id.slice(1)}
              </button>
            ))}
          </nav>
          {(tab === "artists" || tab === "albums") && (
            <CollectionPages<Artist | Album>
              key={tab}
              items={tab === "artists" ? library.artists : library.albums}
              label={tab}
            >
              {(items) => (
                <div className="personal-grid">
                  {items.map((item) => {
                    const artist = "name" in item;
                    return (
                      <button
                        key={item.id}
                        onClick={() =>
                          artist
                            ? void openArtist(item as Artist)
                            : void openAlbum(item as Album)
                        }
                      >
                        <Cover
                          title={
                            artist
                              ? (item as Artist).name
                              : (item as Album).title
                          }
                          src={item.cover_url}
                          artist={artist}
                        />
                        <h3>
                          {artist
                            ? (item as Artist).name
                            : (item as Album).title}
                        </h3>
                        <p>
                          {artist
                            ? (item as Artist).album_count + " albums"
                            : (item as Album).track_count + " songs"}
                        </p>
                      </button>
                    );
                  })}
                </div>
              )}
            </CollectionPages>
          )}
          {(tab === "playlists" || tab === "favourites") && (
            <>
              <form
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
                <button type="submit">Create</button>
              </form>
              {playlists
                .filter(
                  (p) =>
                    tab !== "favourites" || p.id.startsWith("pig-favourites:"),
                )
                .map((p) => (
                  <p key={p.id}>
                    <button onClick={() => void openPlaylist(p.id)}>
                      {p.name}
                    </button>
                  </p>
                ))}
            </>
          )}
          {tab === "search" && (
            <>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const q = new FormData(e.currentTarget).get("q");
                  void api<{ tracks: Track[]; household_tracks: Track[] }>(
                    "/v1/search?q=" + encodeURIComponent(String(q)),
                  )
                    .then(setSearch)
                    .catch((e) => setError(e.message));
                }}
              >
                <label>
                  Search music on the server
                  <input name="q" type="search" required maxLength={150} />
                </label>
                <button type="submit">Search</button>
              </form>
              {search && (
                <>
                  <h2>In your library</h2>
                  {songs(search.tracks)}
                  <h2>Available in the household</h2>
                  {search.household_tracks.map((t) => (
                    <article className="personal-track" key={t.id}>
                      <div>
                        <strong>{t.title}</strong>
                        <p>{t.artist} · On server</p>
                      </div>
                      <button
                        onClick={() => void add(t)}
                        aria-label={`Add ${t.title} to your library`}
                      >
                        <CirclePlus size={20} /> Add to my library
                      </button>
                    </article>
                  ))}
                </>
              )}
            </>
          )}
          {tab === "search" && <CatalogueExplorer />}
          {tab === "requests" && <PersonalRequests />}
          {tab === "import" && (
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
