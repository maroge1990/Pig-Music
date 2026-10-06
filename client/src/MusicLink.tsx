import { apiFetch as fetch, cachedLibrary } from "./api";
import { discoverUrl } from "./navigation";
export function MusicLink({
  artist,
  album,
  releaseId,
}: {
  artist: string;
  album?: string;
  releaseId?: string;
}) {
  async function open() {
    const library = await cachedLibrary<{
      albums: {
        id: string;
        title: string;
        artist: string;
        musicbrainz_release_id?: string;
      }[];
      artists: { id: string; name: string }[];
    }>();
    if (album) {
      const matches = library.albums.filter(
        (a) =>
          a.title.toLocaleLowerCase() === album.toLocaleLowerCase() &&
          a.artist.toLocaleLowerCase() === artist.toLocaleLowerCase() &&
          (!releaseId ||
            !a.musicbrainz_release_id ||
            a.musicbrainz_release_id === releaseId),
      );
      if (matches.length === 1) {
        location.hash = `/library/album/${matches[0].id}`;
        return;
      }
    }
    const matches = library.artists.filter(
      (a: { name: string }) =>
        a.name.toLocaleLowerCase() === artist.toLocaleLowerCase(),
    );
    if (!album && matches.length === 1) {
      location.hash = `/library/artist/${matches[0].id}`;
      return;
    }
    const results = await fetch(
      "/api/catalogue/artists?q=" + encodeURIComponent(artist),
    ).then((r) => r.json());
    const exact = results.artists.filter(
      (a: { name: string }) =>
        a.name.toLocaleLowerCase() === artist.toLocaleLowerCase(),
    );
    if (exact.length === 1)
      location.hash = discoverUrl(exact[0], album ? releaseId : undefined);
    else location.hash = "/search";
  }
  return (
    <button
      className="music-text-link"
      onClick={() =>
        void open().catch(() => {
          location.hash = "/search";
        })
      }
    >
      {album || artist}
    </button>
  );
}
