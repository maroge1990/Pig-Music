import { expect, test } from "@playwright/test";
import { mockApi } from "./mock";

const songs = Array.from({ length: 13 }, (_, i) => ({
  id: `m${i + 1}`,
  title: `Meteora song ${i + 1}`,
  artist: "Linkin Park",
  track_number: i + 1,
  status: i === 0 ? "completed" : i === 1 ? "failed" : "waiting_for_sources",
  request_progress: null,
  error: i === 1 ? "no_source" : null,
  source: i === 0 ? "soulseek" : null,
  quality: i === 0 ? "FLAC" : null,
}));
const groups = {
  total: 2,
  next_offset: null,
  active: 11,
  offset: 0,
  downloads_enabled: true,
  groups: [
    {
      id: "g-meteora",
      kind: "album",
      title: "Meteora",
      artist: "Linkin Park",
      release_id: "r-meteora",
      state: "waiting",
      songs: 13,
      done: 1,
      active: 0,
      waiting: 11,
      failed: 1,
      progress: 1 / 13,
      requested_at: new Date(Date.now() - 600_000).toISOString(),
      updated_at: new Date(Date.now() - 300_000).toISOString(),
      items: songs,
    },
    {
      id: "g-numb",
      kind: "song",
      title: "Numb",
      artist: "Linkin Park",
      release_id: null,
      state: "done",
      songs: 1,
      done: 1,
      active: 0,
      waiting: 0,
      failed: 0,
      progress: 1,
      requested_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z",
      items: [
        {
          id: "n1",
          title: "Numb",
          status: "completed",
          request_progress: null,
          source: "youtube",
          quality: "AAC 256 kbps",
        },
      ],
    },
  ],
};

test("Downloads shows one card per request, with detail inside", async ({
  page,
}) => {
  const posted: string[] = [];
  await mockApi(page, {
    answers: {
      "/v1/requests/groups": (route) => route.fulfill({ json: groups }),
      "/v1/requests/m2/retry": (route) => {
        posted.push("retry m2");
        return route.fulfill({ json: { retried: true } });
      },
      "/v1/requests": (route) => {
        if (route.request().method() === "DELETE") {
          posted.push("clear");
          return route.fulfill({ json: { cleared: 2 } });
        }
        return route.fulfill({
          json: { items: [], next_offset: null, active: 0 },
        });
      },
    },
  });
  await page.goto("/#/downloads");
  const cards = page.locator(".request-group");
  // Thirteen songs from one album request are one card, not thirteen rows.
  await expect(cards).toHaveCount(2);
  const meteora = cards.filter({ hasText: "Meteora" });
  await expect(meteora).toContainText(
    "1 of 13 songs in your library · 11 waiting · 1 failed",
  );
  await expect(meteora).toContainText("5 min ago");
  await expect(meteora.locator("summary .cover")).toHaveCount(1);
  await expect(meteora.getByText("Soulseek")).toBeHidden();
  await meteora.locator("summary").click();
  await expect(meteora).toContainText("In your library · Soulseek · FLAC");
  await meteora.getByRole("button", { name: "Retry Meteora song 2" }).click();
  await expect.poll(() => posted).toContain("retry m2");
  await page.getByRole("button", { name: "Clear finished" }).click();
  await expect.poll(() => posted).toContain("clear");
  await expect(page.getByRole("status").first()).toContainText(
    "Cleared 2 finished songs",
  );
  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
