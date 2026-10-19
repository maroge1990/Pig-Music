import assert from "node:assert/strict";
import test from "node:test";

test("library conditional reads reuse the body on 304 and replace it on change", async () => {
  globalThis.window = { addEventListener() {}, dispatchEvent() {} };
  globalThis.document = { hidden: true };
  const originalInterval = globalThis.setInterval;
  globalThis.setInterval = () => 0;
  const calls = [];
  globalThis.fetch = async (path, options) => {
    calls.push({ path, options });
    if (calls.length === 1)
      return new Response('{"revision":"one"}', { headers: { etag: '"one"' } });
    if (calls.length === 2) return new Response(null, { status: 304 });
    return new Response('{"revision":"two"}', { headers: { etag: '"two"' } });
  };
  const { apiFetch } = await import("../src/api.ts");
  globalThis.setInterval = originalInterval;
  assert.equal(
    (await (await apiFetch("/api/v1/library")).json()).revision,
    "one",
  );
  assert.equal(
    (await (await apiFetch("/api/v1/library")).json()).revision,
    "one",
  );
  assert.equal(calls[1].options.headers.get("If-None-Match"), '"one"');
  assert.equal(
    (await (await apiFetch("/api/v1/library")).json()).revision,
    "two",
  );
});

test("a previous account's delayed library response cannot enter the next account cache", async () => {
  const events = [];
  window.dispatchEvent = (event) => events.push(event.type);
  const { apiFetch, clearSessionReads } = await import("../src/api.ts");
  clearSessionReads();
  let complete;
  globalThis.fetch = () =>
    new Promise((resolve) => {
      complete = resolve;
    });
  const old = apiFetch("/api/v1/library");
  clearSessionReads();
  complete(
    new Response('{"revision":"old-person"}', {
      headers: { etag: '"old-person"' },
    }),
  );
  await old;
  let conditional;
  globalThis.fetch = async (path, options) => {
    conditional = options.headers.get("If-None-Match");
    return new Response('{"revision":"new-person"}');
  };
  assert.equal(
    (await (await apiFetch("/api/v1/library")).json()).revision,
    "new-person",
  );
  assert.equal(conditional, null);
  globalThis.fetch = () =>
    new Promise((resolve) => {
      complete = resolve;
    });
  const late = apiFetch("/api/v1/me");
  clearSessionReads();
  complete(new Response("{}", { status: 401 }));
  await late;
  // Only the session changes themselves were announced; no late 401.
  assert.deepEqual(
    events.filter((type) => type !== "music-session-cleared"),
    [],
  );
});

test("warmed catalogue data is immediately readable and isolated across sessions", async () => {
  const { apiFetch, peekCatalogue, clearSessionReads } = await import(
    "../src/api.ts"
  );
  clearSessionReads();
  let calls = 0;
  const path = "/api/v1/catalogue/artists/fixture/popularity";
  globalThis.fetch = async () => {
    calls++;
    return Response.json({ songs: [{ id: "one" }], albums: [] });
  };
  await apiFetch(path);
  assert.equal(peekCatalogue(path).songs[0].id, "one");
  await apiFetch(path, { signal: new AbortController().signal });
  assert.equal(calls, 1);
  clearSessionReads();
  assert.equal(peekCatalogue(path), undefined);
  let complete;
  globalThis.fetch = () =>
    new Promise((resolve) => {
      complete = resolve;
    });
  const late = apiFetch(path);
  clearSessionReads();
  complete(Response.json({ songs: [], albums: [] }));
  await late;
  assert.equal(peekCatalogue(path), undefined);
});

test("the transport refuses an unversioned API path", async () => {
  const { apiFetch } = await import("../src/api.ts");
  await assert.rejects(() => apiFetch("/api/queue"), /unversioned/i);
  await assert.rejects(() => apiFetch("/api/library"), /unversioned/i);
});
