import assert from "node:assert/strict";
import test from "node:test";
import { friendlyRequestError } from "../src/requestError.ts";

test("matching failures from every source become one sentence", () => {
  assert.equal(
    friendlyRequestError(
      "soulseek: no candidate passed recording/version matching; freemp3cloud: no candidate passed recording/version matching",
    ),
    "No source had a matching copy of this song.",
  );
});
test("unreachable sources are named with friendly names", () => {
  const text = friendlyRequestError(
    "soulseek: search unavailable; zvu4no: transfer failed",
  );
  assert.match(text, /Soulseek, Zvu4no/);
  assert.match(text, /Try again later/);
});
test("other strings are shown as they are", () => {
  assert.equal(
    friendlyRequestError("Acquisition interrupted by restart"),
    "Acquisition interrupted by restart",
  );
  assert.equal(
    friendlyRequestError("soulseek: odd failure"),
    "soulseek: odd failure",
  );
});
