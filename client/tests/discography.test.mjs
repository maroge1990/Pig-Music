import assert from "node:assert/strict";
import test from "node:test";
import { mergePage, newestFirst } from "../src/discography.ts";
const group = (id, date) => ({ id, date, title: id, type: "Album" });
test("late Other releases responses cannot populate the Albums tab", () => {
  const albums = {
    scope: "u2:album",
    groups: [group("album", "2024")],
    total: 1,
    loading: false,
  };
  assert.equal(
    mergePage(albums, "u2:other", [group("live", "2025")], 400),
    albums,
  );
});
test("overlapping pages have unique identities and newest-first order", () => {
  let state = { scope: "u2:other", groups: [], total: 0, loading: true };
  state = mergePage(
    state,
    "u2:other",
    [group("older", "1990"), group("newer", "2024")],
    3,
  );
  state = mergePage(
    state,
    "u2:other",
    [group("newer", "2024"), group("unknown", "")],
    3,
  );
  assert.deepEqual(
    state.groups.map((g) => g.id),
    ["newer", "older", "unknown"],
  );
  assert.deepEqual(
    [group("a", "2020"), group("b", "2024")].sort(newestFirst).map((g) => g.id),
    ["b", "a"],
  );
});
