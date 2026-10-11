import assert from "node:assert/strict";
import test from "node:test";
import { registerHooks } from "node:module";
registerHooks({
  resolve(specifier, context, next) {
    try {
      return next(specifier, context);
    } catch (error) {
      if (specifier.startsWith(".") && !/\.[a-z]+$/.test(specifier))
        return next(specifier + ".ts", context);
      throw error;
    }
  },
});
const { mergeAlbumTracks, albumSummary } = await import(
  "../src/albumTracks.ts"
);

const track = (id, title, n, extra = {}) => ({
  id,
  title,
  artist: "A",
  album: "Al",
  album_artist: "A",
  disc_number: 1,
  track_number: n,
  duration: 100,
  ...extra,
});

test("release order is used and missing songs are filled in", () => {
  const release = [
    track("r1", "One", 1, { server_state: "not_in_library" }),
    track("r2", "Two", 2, { server_state: "household_available" }),
    track("r3", "Three", 3, { server_state: "requested" }),
  ];
  const two = track("local2", "Two", 2);
  const rows = mergeAlbumTracks([two], release);
  assert.deepEqual(
    rows.map((r) => r.id),
    ["r1", "local2", "r3"],
  );
  assert.equal(rows[1], two);
  assert.equal(albumSummary(rows, [two]), "1 of 3 songs in your library");
});

test("matches by recording, then position, then title; keeps strays", () => {
  const release = [
    track("r1", "Intro", 1, { musicbrainz_recording_id: "x" }),
    track("r2", "Second", 2),
    track("r3", "Third", 3),
  ];
  const byRecording = track("a", "Renamed", 1, {
    musicbrainz_recording_id: "x",
  });
  const byTitle = track("b", "third!", 9);
  const stray = track("c", "Bonus", 12);
  const rows = mergeAlbumTracks([stray, byTitle, byRecording], release);
  assert.deepEqual(
    rows.map((r) => r.id),
    ["a", "r2", "b", "c"],
  );
});

test("a different recording in the same slot is not the same song", () => {
  const release = [track("r1", "Live", 1, { musicbrainz_recording_id: "x" })];
  const other = track("o", "Studio", 1, { musicbrainz_recording_id: "y" });
  assert.deepEqual(
    mergeAlbumTracks([other], release).map((r) => r.id),
    ["r1", "o"],
  );
});
