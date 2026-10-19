import { expect, test } from "@playwright/test";
import { mockApi } from "./mock";

const queue = {
  library_revision: "1",
  downloads_enabled: false,
  items: [
    { id: "q1", status: "downloading", title: "One", artist: "A", album: "X" },
    {
      id: "q2",
      status: "waiting_for_sources",
      title: "Two",
      artist: "A",
      album: "X",
    },
    { id: "q3", status: "failed", title: "Three", artist: "A", album: "X" },
  ],
};

test("the owner's Admin overview shows the numbers to act on", async ({
  page,
}) => {
  await mockApi(page, {
    role: "owner",
    answers: {
      "/queue": (route) => route.fulfill({ json: queue }),
      "/v1/people": (route) =>
        route.fulfill({
          json: {
            people: [{ id: "1" }, { id: "2" }, { id: "3", disabled: true }],
          },
        }),
      "/v1/admin/unassigned": (route) =>
        route.fulfill({ json: { albums: [{}, {}], next_offset: null } }),
      "/v1/admin/mixes": (route) =>
        route.fulfill({
          json: {
            budget_bytes: 50000000000,
            reserve_bytes: 2000000000,
            profile: "mp3_320",
            timezone: "Australia/Melbourne",
            files: 10,
            used_bytes: 100000000,
            ready: 4,
            preparing: 1,
            retrying: 1,
            failed: 2,
            reclaimable_bytes: 12000000,
            issues: [{ mix: "Daily blend", message: "Downloads are paused" }],
            people: [
              { id: "u1", name: "Mark", ready: 3, preparing: 1 },
              { id: "u2", name: "Sam", ready: 1, preparing: 0 },
            ],
          },
        }),
      "/v1/admin/mixes/people/u1": (route) =>
        route.fulfill({
          json: {
            person: "Mark",
            editions: [
              {
                id: "e1",
                kind: "daily",
                day: "2026-10-18",
                title: "Daily blend",
                reason: "Discoveries inspired by your library",
                state: "preparing",
                active: false,
                attempts: 1,
                retry_at: null,
                worked_at: null,
                blocked: "Downloads are paused",
                published: null,
                songs: [
                  { title: "Ready One", artist: "A", status: "cached" },
                  {
                    title: "Missing Two",
                    artist: "B",
                    status: "failed",
                    detail: "No matching recording available",
                  },
                  { title: "Next Three", artist: "C", status: "next" },
                ],
              },
            ],
          },
        }),
      "/v1/admin/mixes/people/u2": (route) =>
        route.fulfill({ json: { person: "Sam", editions: [] } }),
      "/warmer": (route) =>
        route.fulfill({
          json: {
            artists_ready: 12,
            covers_prepared: 40,
            queued: 0,
            last_pass_finished: null,
          },
        }),
    },
  });
  await page.goto("/#/home");
  await expect(
    page.getByRole("link", { name: "Admin" }).first(),
  ).toBeAttached();
  await page.goto("/#/admin");
  const tile = (label: string) =>
    page
      .locator("a, div")
      .filter({ has: page.getByText(label, { exact: true }) })
      .last();
  await expect(tile("Queued or downloading")).toContainText("2");
  await expect(tile("Queued or downloading")).toContainText(
    "Downloads are paused",
  );
  await expect(tile("Failed requests")).toContainText("1");
  await expect(tile("Albums awaiting an owner")).toContainText("2");
  await expect(tile("People")).toContainText("2");
  await expect(tile("Artist pages ready")).toContainText("12");
  const mixes = page
    .locator(".system-panel")
    .filter({ has: page.getByRole("heading", { name: "Mix preparation" }) });
  await expect(mixes).toContainText("2 unavailable candidates");
  await expect(mixes).toContainText("12 MB can be reclaimed");
  await mixes.getByText("Preparation issues", { exact: true }).click();
  await expect(mixes).toContainText("Daily blend: Downloads are paused");
  await expect(mixes).toContainText("1/3 songs ready · 1 unavailable");
  await expect(mixes).toContainText("Waiting: Downloads are paused");
  await expect(mixes.locator("li[data-status=failed]")).toContainText(
    "No matching recording available",
  );
  await expect(mixes.locator("li[data-status=next]")).toContainText("Up next");
  await mixes.getByRole("button", { name: /Sam/ }).click();
  await expect(mixes).toContainText("No mixes are planned for Sam yet.");
  const budget = mixes.getByLabel("Cache budget (GB)");
  await budget.fill("55");
  await mixes.getByRole("button", { name: "Refresh mix status" }).click();
  await expect(
    mixes.getByRole("button", { name: "Refresh mix status" }),
  ).toBeEnabled();
  await expect(budget).toHaveValue("55");
});

test("members have no Admin section, even by address", async ({ page }) => {
  await mockApi(page, { role: "member" });
  await page.goto("/#/admin");
  await expect(
    page.getByRole("heading", { name: "Home", level: 1 }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
});

test("Admin follows the shell's event stream without a timer", async ({
  page,
}) => {
  // Frozen timers: nothing polls, so only the pushed `admin` event can move
  // the numbers after the first load.
  await page.clock.install();
  let queueAsked: () => void = () => {};
  const asked = new Promise<void>((resolve) => (queueAsked = resolve));
  let queueCalls = 0;
  const pushed = {
    library_revision: "1",
    downloads_enabled: true,
    items: [
      ...["a", "b", "c", "d"].map((id) => ({
        id,
        status: "downloading",
        title: id,
        artist: "A",
        album: "X",
      })),
      { id: "e", status: "failed", title: "e", artist: "A", album: "X" },
      { id: "f", status: "failed", title: "f", artist: "A", album: "X" },
    ],
  };
  await mockApi(page, {
    role: "owner",
    answers: {
      "/queue": (route) => {
        queueCalls += 1;
        queueAsked();
        return route.fulfill({ json: queue });
      },
      "/v1/events": async (route) => {
        await asked;
        await route.fulfill({
          contentType: "text/event-stream",
          body: `event: admin\ndata: ${JSON.stringify({
            queue: pushed,
            scan: { status: "completed" },
            soulseek: { configured: true, connected: true },
          })}\n\n`,
        });
      },
      "/v1/people": (route) => route.fulfill({ json: { people: [] } }),
      "/v1/admin/unassigned": (route) =>
        route.fulfill({ json: { albums: [], next_offset: null } }),
      "/warmer": (route) =>
        route.fulfill({
          json: { artists_ready: 0, covers_prepared: 0, queued: 0 },
        }),
    },
  });
  await page.goto("/#/admin");
  const tile = (label: string) =>
    page
      .locator("a, div")
      .filter({ has: page.getByText(label, { exact: true }) })
      .last();
  await expect(tile("Queued or downloading")).toContainText("4");
  await expect(tile("Queued or downloading")).not.toContainText(
    "Downloads are paused",
  );
  await expect(tile("Failed requests")).toContainText("2");
  expect(queueCalls).toBe(1);
});
