import type { Track } from "./types";

const clean = (s: string) =>
  s
    .toLocaleLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();

/**
 * Lay a release's full tracklist over the songs this person owns.
 *
 * Owned songs keep their own Track (so play and remove still work); release
 * songs that are not owned appear with the release's server_state. Owned
 * songs that match nothing on the release are kept, after the release songs.
 */
export function mergeAlbumTracks(owned: Track[], release: Track[]): Track[] {
  const matches = new Map<number, Track>();
  const used = new Set<Track>();
  const pass = (
    same: (o: Track, r: Track) => boolean,
    // Later passes only take songs the earlier ones left alone.
  ) => {
    release.forEach((r, i) => {
      if (matches.has(i)) return;
      const found = owned.find((o) => !used.has(o) && same(o, r));
      if (found) {
        matches.set(i, found);
        used.add(found);
      }
    });
  };
  const place = (o: Track, r: Track) =>
    o.disc_number === r.disc_number && o.track_number === r.track_number;
  const recording = (o: Track, r: Track) =>
    !!o.musicbrainz_recording_id &&
    o.musicbrainz_recording_id === r.musicbrainz_recording_id;
  pass((o, r) => recording(o, r) && place(o, r));
  pass(
    (o, r) =>
      place(o, r) &&
      // A different recording in the same slot is only the same song if the
      // title agrees (another edition may order its tracks differently).
      (!o.musicbrainz_recording_id ||
        !r.musicbrainz_recording_id ||
        clean(o.title) === clean(r.title)),
  );
  pass((o, r) => clean(o.title) === clean(r.title));
  const rows = release.map((r, i) => matches.get(i) || r);
  return [...rows, ...owned.filter((o) => !used.has(o))];
}

/** "8 of 12 songs in your library", counting only songs on the release. */
export function albumSummary(rows: Track[], owned: Track[]) {
  const have = rows.filter((r) => owned.includes(r)).length;
  const total = rows.length;
  return `${have} of ${total} songs in your library`;
}
