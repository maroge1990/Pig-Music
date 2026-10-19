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
const listeners = {};
globalThis.window = {
  addEventListener(type, listener) {
    (listeners[type] ||= []).push(listener);
  },
  dispatchEvent(event) {
    for (const listener of listeners[event.type] || []) listener(event);
  },
};
globalThis.document = { hidden: true };
const interval = globalThis.setInterval;
globalThis.setInterval = () => 0;
const { clearSessionReads, currentSession } = await import("../src/api.ts");
const { answer, remember } = await import("../src/searchAnswers.ts");
globalThis.setInterval = interval;

const pats = { tracks: [{ id: "pat-song" }], household: [] };

test("an account change empties search answers", () => {
  const session = currentSession();
  assert.equal(
    remember("charli", session, (e) => (e.local = pats)),
    true,
  );
  assert.equal(answer("charli").local, pats);
  let cleared = 0;
  window.addEventListener("music-session-cleared", () => cleared++);
  clearSessionReads();
  assert.equal(answer("charli"), undefined);
  assert.equal(cleared, 1);
});

test("an answer arriving after sign-out is not kept for the next person", () => {
  const asked = currentSession();
  // Pat signs out and Sam signs in before Pat's search returns.
  clearSessionReads();
  assert.equal(
    remember("charli", asked, (e) => (e.local = pats)),
    false,
  );
  assert.equal(answer("charli"), undefined);
});

test("library changes drop library answers but keep the catalogue's", () => {
  const session = currentSession();
  remember("brat", session, (e) => {
    e.local = pats;
    e.catalogue = [{ id: "a", name: "Charli" }];
  });
  window.dispatchEvent({ type: "music-library-changed" });
  assert.equal(answer("brat").local, undefined);
  assert.equal(answer("brat").catalogue.length, 1);
  // Answers expire.
  assert.equal(answer("brat", Date.now() + 6 * 60_000), undefined);
});
