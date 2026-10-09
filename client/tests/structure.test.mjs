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

test("text sizes come from the shared type roles", () => {
  // Fluid clamp() display sizes are the only literal exception.
  for (const file of readdirSync(source).filter((f) => f.endsWith(".css"))) {
    if (file === "tokens.css") continue;
    for (const [, value] of read(file).matchAll(/font-size:\s*([^;]+);/g))
      assert.match(
        value,
        /^(var\(--type-[a-z]+\)|clamp\(.*\)|inherit)$/,
        `${file}: ${value}`,
      );
  }
});

test("the library album page shows its cover and a library artist link", () => {
  const text = read("PersonalLibrary.tsx");
  assert.match(text, /IN YOUR LIBRARY/);
  assert.match(text, /<Cover title=\{detail\.title\} src=\{detail\.cover\}/);
  assert.match(text, /"#\/library\/artist\/" \+ info\.artistId/);
});

test("each section sets its own document title", () => {
  const text = read("AppShell.tsx");
  assert.match(text, /document\.title =/);
  assert.match(text, /· Pig Music/);
});

test("quality option labels live only in QualitySelect", () => {
  const labels = /MP3 (128|320)|AAC 256|Lossless \(FLAC\)|FLAC lossless/;
  for (const file of files.filter(
    (f) =>
      !["QualitySelect.tsx", "QualitySettings.tsx", "sources.ts"].includes(f),
  ))
    assert.doesNotMatch(read(file), labels, `${file} hard-codes a label`);
});

test("quality selects share one component and name what they inherit", () => {
  for (const file of [
    "AccountSettings.tsx",
    "PersonalQuality.tsx",
    "AlbumQuality.tsx",
    "SystemView.tsx",
  ]) {
    const text = read(file);
    assert.match(text, /<QualitySelect/, file);
    assert.doesNotMatch(text, /<option value="(mp3|aac|lossless)/, file);
  }
  assert.match(read("AccountSettings.tsx"), /Use household default/);
  assert.match(read("PersonalQuality.tsx"), /Use your default/);
  assert.match(read("PersonalQuality.tsx"), /Use artist or your default/);
  assert.match(read("AlbumQuality.tsx"), /Use artist or household default/);
  assert.doesNotMatch(
    files.map(read).join("\n"),
    /general preference|system preference/,
  );
});

test("download sources render through the shared display-name map", () => {
  for (const file of files.filter((f) => f !== "sources.ts"))
    assert.doesNotMatch(
      read(file),
      /["'](soulseek|freemp3cloud|zvu4no|jiosaavn)["']/,
      `${file} hard-codes a source id`,
    );
  assert.match(read("SystemView.tsx"), /sourceName\(source\)/);
  assert.match(read("QueueView.tsx"), /sourceName\(item\.source\)/);
});

test("admin downloads splits the queue from its settings", () => {
  const text = read("AdminTools.tsx");
  assert.match(text, /#\/admin\/downloads\/settings/);
  assert.match(text, /downloadsView === "queue"/);
  assert.match(text, /downloadsView === "settings"/);
});
