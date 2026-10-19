import { expect, test, type Page } from "@playwright/test";
import { mockApi } from "./mock";

// The other specs block the worker; this one checks what it really caches.
test.use({ serviceWorkers: "allow" });

const sha = "a".repeat(64);
const image = `<svg xmlns="http://www.w3.org/2000/svg" width="8" height="8"><rect width="8" height="8"/></svg>`;
const cached = (page: Page, name: string) =>
  page.evaluate(
    async (name) =>
      (await (await caches.open(name)).keys()).map((r) => {
        const url = new URL(r.url);
        return url.pathname;
      }),
    name,
  );

test("the service worker caches versioned artwork and keeps release lists personal", async ({
  page,
  context,
}) => {
  let releaseReads = 0;
  const picture = (route: import("@playwright/test").Route) =>
    route.fulfill({ contentType: "image/svg+xml", body: image });
  await mockApi(context, {
    answers: {
      [`/v1/covers/${sha}.jpg`]: picture,
      "/v1/catalogue/artwork/release-group/group-1": picture,
      "/v1/catalogue/artists/mb-1/background": picture,
      "/v1/catalogue/artists/mb-1/releases": (route) => {
        releaseReads += 1;
        return route.fulfill({
          json: {
            total: 1,
            offset: 0,
            releases: [
              {
                id: "group-1",
                title: "Brat",
                date: "2024",
                type: "Album",
                saved_album_id: releaseReads > 1 ? "album-1" : null,
                saved_songs: releaseReads > 1 ? 2 : 0,
              },
            ],
          },
        });
      },
    },
  });
  await page.goto("/#/home");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);

  // An ordinary web cover: /api/v1/covers/<sha>.jpg.
  await page.evaluate(
    (url) => fetch(url).then((r) => r.blob()),
    `/api/v1/covers/${sha}.jpg?w=256&v=1`,
  );
  await expect
    .poll(() => cached(page, "pig-images-v1"))
    .toContain(`/api/v1/covers/${sha}.jpg`);

  // Warming messages for versioned catalogue images are honoured.
  await page.evaluate(() =>
    navigator.serviceWorker.controller!.postMessage({
      type: "warm",
      urls: [
        "/api/v1/catalogue/artwork/release-group/group-1?w=256&v=1&r=0",
        "/api/v1/catalogue/artists/mb-1/background?r=0&w=512",
      ],
    }),
  );
  await expect
    .poll(() => cached(page, "pig-images-v1"))
    .toEqual(
      expect.arrayContaining([
        "/api/v1/catalogue/artwork/release-group/group-1",
        "/api/v1/catalogue/artists/mb-1/background",
      ]),
    );

  // Release lists carry ownership: always the server's current answer.
  const owned = () =>
    page.evaluate(() =>
      fetch("/api/v1/catalogue/artists/mb-1/releases?kind=album")
        .then((r) => r.json())
        .then((body) => body.releases[0].saved_album_id),
    );
  expect(await owned()).toBeNull();
  expect(await owned()).toBe("album-1");
  expect(releaseReads).toBe(2);
  await expect
    .poll(() => cached(page, "pig-data-v3"))
    .toContain("/api/v1/catalogue/artists/mb-1/releases");

  // Signing out clears everything the worker kept.
  await page.evaluate(() =>
    navigator.serviceWorker.controller!.postMessage({ type: "clear" }),
  );
  await expect.poll(() => cached(page, "pig-images-v1")).toEqual([]);
});
