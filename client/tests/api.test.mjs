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
  assert.equal((await (await apiFetch("/api/library")).json()).revision, "one");
  assert.equal((await (await apiFetch("/api/library")).json()).revision, "one");
  assert.equal(calls[1].options.headers.get("If-None-Match"), '"one"');
  assert.equal((await (await apiFetch("/api/library")).json()).revision, "two");
});
