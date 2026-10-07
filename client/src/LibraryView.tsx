import type { ReactNode } from "react";
import {
  LoaderCircle,
  ArrowLeft,
  CircleCheck,
  Play,
  Disc3,
  ChevronRight,
  ChevronDown,
} from "lucide-react";
import type { Library, Album, Artist, Track } from "./types";
import { Cover } from "./Cover";
import { MusicLink } from "./MusicLink";
import { AlbumQuality } from "./AlbumQuality";
import { RemoveCollection } from "./Recovery";
import { ArtistHero } from "./ArtistHero";
import { ArtistDiscography } from "./ArtistDiscography";
import { Playlists } from "./Playlists";
import { CollectionPages } from "./CollectionPages";
import { ArtistCards } from "./LibraryCards";
import { Empty } from "./EmptyState";
import type { usePlayer } from "./Player";
const plural = (count: number, noun: string) =>
  `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;
type Props = {
  library: Library | null;
  detailLoading: boolean;
  albumDetail: Album | null;
  artistDetail: Artist | null;
  navigate: (page: "library") => void;
  openArtist: (id: string) => void;
  openAlbum: (id: string) => void;
  player: ReturnType<typeof usePlayer>;
  albumCards: (albums: Album[]) => ReactNode;
  savedTracks: (tracks: Track[]) => ReactNode;
  libraryTab: string;
  setLibraryTab: (value: string) => void;
  sort: string;
  setSort: (value: string) => void;
  setToast: (message: string) => void;
  playlist?: string;
  busy: boolean;
  changeCategory: (category: string) => Promise<void>;
  reviewPlaylist: (id: string) => Promise<void>;
  prefetchArtist: (id: string) => void;
};
export function LibraryView({
  library,
  detailLoading,
  albumDetail,
  artistDetail,
  navigate,
  openArtist,
  openAlbum,
  player,
  albumCards,
  savedTracks,
  libraryTab,
  setLibraryTab,
  sort,
  setSort,
  setToast,
  playlist,
  busy,
  changeCategory,
  reviewPlaylist,
  prefetchArtist,
}: Props) {
  if (!library) return null;

  if (detailLoading)
    return (
      <div className="loading-block">
        <LoaderCircle className="spin" />
        Opening your music…
      </div>
    );

  if (albumDetail)
    return (
      <>
        <button
          className="back-button"
          onClick={() =>
            albumDetail.category !== "album"
              ? navigate("library")
              : openArtist(albumDetail.artist_id!)
          }
        >
          <ArrowLeft size={16} />{" "}
          {albumDetail.category !== "album"
            ? "Your library"
            : albumDetail.artist}
        </button>

        <div className="detail-hero album-hero">
          <Cover
            title={albumDetail.title}
            src={albumDetail.cover_url}
            sizes="(max-width: 600px) 190px, (max-width: 800px) 130px, (max-width: 1200px) 170px, 210px"
          />
          <div>
            <div className="eyebrow">
              {albumDetail.compilation
                ? "MULTI-ARTIST COMPILATION"
                : "IN YOUR LIBRARY"}
            </div>
            <h1>{albumDetail.title}</h1>
            <p>
              <MusicLink artist={albumDetail.artist} />
              <span>·</span> {albumDetail.year || "Unknown year"} <span>·</span>{" "}
              {plural(albumDetail.track_count, "saved track")}
            </p>
            <span className="status-pill">
              <CircleCheck size={14} /> Downloaded
            </span>
          </div>
        </div>

        <div className="section-title">
          <h2>Tracks</h2>
          <button
            className="small-button"
            disabled={!albumDetail.tracks?.length}
            onClick={() =>
              player.playSaved(
                {
                  ...albumDetail.tracks![0],
                  cover_url: albumDetail.cover_url,
                },
                albumDetail.tracks!.map((t) => ({
                  ...t,
                  cover_url: albumDetail.cover_url,
                  album_id: albumDetail.id,
                })),
              )
            }
          >
            <Play size={14} /> Play album
          </button>
        </div>
        {savedTracks(
          (albumDetail.tracks || []).map((t) => ({
            ...t,
            cover_url: albumDetail.cover_url,
            album_id: albumDetail.id,
          })),
        )}

        <details className="album-quality">
          <summary>Album settings</summary>
          <div className="appearance-control">
            <label htmlFor="album-category">Library section</label>
            <select
              id="album-category"
              value={albumDetail.category}
              disabled={busy}
              onChange={(e) => void changeCategory(e.target.value)}
            >
              <option value="album">Artists &amp; albums</option>
              <option value="compilation">Compilations</option>
              <option value="soundtrack">Soundtracks</option>
              <option value="musical">Musicals</option>
              <option value="auto">Automatic</option>
            </select>
            <span>
              This changes app grouping; it does not change your music files.
            </span>
          </div>
          <AlbumQuality
            key={albumDetail.id}
            id={albumDetail.id}
            notify={setToast}
            embedded
          />
          <RemoveCollection
            kind="albums"
            id={albumDetail.id}
            title={albumDetail.title}
          />
        </details>
      </>
    );

  if (artistDetail)
    return (
      <>
        <button className="back-button" onClick={() => navigate("library")}>
          <ArrowLeft size={16} /> Your library
        </button>

        <ArtistHero key={artistDetail.id} artist={artistDetail} />

        {!!artistDetail.albums?.length && (
          <>
            <div className="section-title">
              <h2>Albums & releases</h2>
              <span>{plural(artistDetail.albums.length, "release")}</span>
            </div>
            {albumCards(
              [...artistDetail.albums].sort(
                (a, b) =>
                  (b.year || 0) - (a.year || 0) ||
                  a.title.localeCompare(b.title),
              ),
            )}
          </>
        )}

        <ArtistDiscography
          key={"discography:" + artistDetail.id}
          id={artistDetail.id}
          notify={setToast}
        />
        {!!artistDetail.compilation_tracks?.length && (
          <>
            <div className="section-title">
              <h2>On soundtracks & compilations</h2>
              <span>
                {plural(artistDetail.compilation_tracks.length, "track")}
              </span>
            </div>
            {artistDetail.compilation_tracks.map((t) => (
              <button
                className="result-row"
                key={t.id}
                onClick={() => openAlbum(t.album_id!)}
              >
                <Disc3 />
                <div>
                  <strong>{t.title}</strong>
                  <span>{t.album}</span>
                </div>
                <ChevronRight size={16} />
              </button>
            ))}
          </>
        )}

        <AlbumQuality
          key={"quality:" + artistDetail.id}
          kind="artist"
          id={artistDetail.id}
          notify={setToast}
        />
      </>
    );

  const artists = library.artists.filter((a) => !a.compilation_only);

  const albums = library.albums.filter(
    (a) =>
      a.category ===
      (libraryTab === "compilations"
        ? "compilation"
        : libraryTab === "soundtracks"
          ? "soundtrack"
          : libraryTab === "musicals"
            ? "musical"
            : "album"),
  );

  const sortedArtists = [...artists].sort((a, b) =>
    sort === "tracks"
      ? b.track_count - a.track_count
      : a.name.localeCompare(b.name),
  );

  const sortedAlbums = [...albums].sort((a, b) =>
    sort === "year" ? b.year - a.year : a.title.localeCompare(b.title),
  );

  return (
    <>
      <div className="library-controls">
        <div className="tab-list" role="tablist" aria-label="Library views">
          {[
            ["artists", "Artists"],
            ["albums", "Albums"],
            ["compilations", "Compilations"],
            ["soundtracks", "Soundtracks"],
            ["musicals", "Musicals"],
            ["playlists", "Playlists"],
            ["favourites", "Favourites"],
          ]
            .filter(
              ([id]) =>
                !["compilations", "soundtracks", "musicals"].includes(id) ||
                library.stats[
                  id as "compilations" | "soundtracks" | "musicals"
                ] > 0,
            )
            .map(([id, label]) => (
              <button
                role="tab"
                aria-selected={libraryTab === id}
                key={id}
                className={libraryTab === id ? "active" : ""}
                onClick={() => {
                  if (playlist) navigate("library");
                  setLibraryTab(id);
                  setSort("az");
                }}
              >
                {label}
                {id === "compilations" && (
                  <span>{library.stats.compilations}</span>
                )}
                {id === "soundtracks" && (
                  <span>{library.stats.soundtracks}</span>
                )}
                {id === "musicals" && <span>{library.stats.musicals}</span>}
              </button>
            ))}
        </div>
        <label className="sort-control" hidden={libraryTab === "playlists"}>
          <span className="sr-only">Sort collection</span>
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="az">A–Z</option>
            <option value={libraryTab === "artists" ? "tracks" : "year"}>
              {libraryTab === "artists" ? "Most tracks" : "Newest release"}
            </option>
          </select>
          <ChevronDown size={13} />
        </label>
      </div>

      {["playlists", "favourites"].includes(libraryTab) ? (
        <Playlists
          initialId={playlist}
          favourites={libraryTab === "favourites"}
          notify={setToast}
          review={reviewPlaylist}
        />
      ) : (
        <>
          <div className="section-title collection-heading">
            <h2>
              {libraryTab === "artists"
                ? "Your artists"
                : libraryTab === "albums"
                  ? "Albums & releases"
                  : libraryTab === "soundtracks"
                    ? "Soundtracks"
                    : libraryTab === "musicals"
                      ? "Musicals"
                      : "Compilations"}
            </h2>
            <span>
              {libraryTab === "artists"
                ? plural(artists.length, "artist")
                : plural(albums.length, "release")}
            </span>
          </div>

          {libraryTab === "compilations" && (
            <p className="section-description">
              Multi-artist collections, kept together. Single-artist best-of
              albums live with their artist.
            </p>
          )}

          {libraryTab === "artists" ? (
            <CollectionPages
              key={`artists:${sort}`}
              items={sortedArtists}
              label="Artists"
            >
              {(visibleArtists) => (
                <ArtistCards
                  artists={visibleArtists}
                  open={openArtist}
                  prefetch={prefetchArtist}
                />
              )}
            </CollectionPages>
          ) : (
            <CollectionPages
              key={`${libraryTab}:${sort}`}
              items={sortedAlbums}
              label="Releases"
            >
              {albumCards}
            </CollectionPages>
          )}

          {!(libraryTab === "artists" ? artists : albums).length && (
            <Empty
              title="Nothing here yet"
              description="This section will fill as your library is indexed."
            />
          )}
        </>
      )}
    </>
  );
}
