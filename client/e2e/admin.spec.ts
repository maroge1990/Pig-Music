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
});

test("members have no Admin section, even by address", async ({ page }) => {
  await mockApi(page, { role: "member" });
  await page.goto("/#/admin");
  await expect(
    page.getByRole("heading", { name: "Home", level: 1 }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
});
