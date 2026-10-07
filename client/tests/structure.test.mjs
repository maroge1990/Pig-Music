import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import test from "node:test";

const source = new URL("../src/", import.meta.url);
const files = readdirSync(source).filter((f) => /\.(ts|tsx)$/.test(f));
const read = (file) => readFileSync(new URL(file, source), "utf8");

test("only the shared transport calls the browser fetch API", () => {
  // apiFetch adds the session write header and same-origin credentials.
  for (const file of files.filter((f) => f !== "api.ts")) {
    const text = read(file);
    assert.doesNotMatch(text, /(?<![\w.])fetch\(/, `${file} calls fetch()`);
    assert.doesNotMatch(text, /apiFetch as /, `${file} renames apiFetch`);
  }
});

test("only the app shell listens to route changes", () => {
  // A second hash router caused nested views to replace each other.
  for (const file of files.filter((f) => f !== "AppShell.tsx"))
    assert.doesNotMatch(read(file), /hashchange/, `${file} reads hashchange`);
});
