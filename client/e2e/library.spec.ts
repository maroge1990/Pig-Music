import { expect, test, type Route } from "@playwright/test";
import { album, artist, mockApi } from "./mock";

test("album cover loads, and a missing cover shows its lettered placeholder", async ({
  page,
}) => {
  await mockApi(page, {
    answers: {
      "/v1/albums/album-2": (route) =>
        route.fulfill({
          json: {
            ...album,
            id: "album-2",
            title: "Sucker",
            cover_url: "/api/v1/artwork/missing",
          },
        }),
    },
  });
  await page.goto(`/#/library/album/${album.id}`);
  const cover = page.locator("main .cover img").first();
  await expect(cover).toBeVisible();
  await expect
    .poll(() => cover.evaluate((img: HTMLImageElement) => img.naturalWidth))
    .toBeGreaterThan(0);

  await page.goto("/#/library/album/album-2");
  await expect(page.getByText("Von dutch").first()).toBeVisible();
  // No broken-image icon: the image is replaced by the title's placeholder.
  await expect(page.locator("main .cover").first().locator("img")).toHaveCount(
    0,
  );
  await expect(page.locator("main .cover").first()).toContainText("S");
});

const candidates = [
  { id: "mb-1", name: artist.name, disambiguation: "English singer" },
  { id: "mb-2", name: artist.name, disambiguation: "Tribute act" },
];
const ambiguous = {
  [`/v1/catalogue/library-artists/${artist.id}`]: (route: Route) =>
    route.request().method() === "PUT"
      ? route.fulfill({ json: { id: "mb-1", name: artist.name } })
      : route.fulfill({
          status: 409,
          json: {
            detail: "Several artists share this name",
            code: "conflict",
            candidates,
          },
        }),
};

test("the owner chooses which artist an ambiguous name means, once", async ({
  page,
}) => {
  await mockApi(page, { role: "owner", answers: ambiguous });
  await page.goto(`/#/library/artist/${artist.id}`);
  await page
    .getByRole("button", { name: `Find more by ${artist.name}` })
    .click();
  const choice = page.getByRole("group", { name: "Choose artist" });
  await expect(choice).toBeVisible();
  await expect(choice.getByRole("listitem")).toHaveCount(2);
  await expect(choice).toContainText("English singer");
  await expect(choice).toContainText("Tribute act");
  const put = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().includes("/library-artists/"),
  );
  await choice.getByRole("button", { name: "Choose" }).first().click();
  expect((await put).postDataJSON()).toEqual({ id: "mb-1" });
  // The catalogue page opened from the library stays under Library.
  await expect(page).toHaveURL(/#\/library\/discography\/mb-1\?/);
  await expect(page.locator(".nav-library").first()).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("library and catalogue artist pages each link to the other", async ({
  page,
}) => {
  const owned = album.tracks.map((t) => ({ ...t, cover_url: album.cover_url }));
  await mockApi(page, {
    answers: {
      [`/v1/artists/${artist.id}`]: (route) =>
        route.fulfill({
          json: {
            ...artist,
            albums: [{ ...album, year: 2024 }],
            tracks: owned,
            compilation_tracks: [],
          },
        }),
      [`/v1/catalogue/library-artists/${artist.id}`]: (route) =>
        route.fulfill({ json: { id: "mb-1", name: artist.name } }),
      "/v1/catalogue/artists/mb-1/releases": (route) =>
        route.fulfill({
          json: {
            total: 2,
            offset: 0,
            releases: [
              {
                id: "g1",
                title: "Brat",
                date: "2024-06-07",
                type: "Album",
                saved_album_id: album.id,
                saved_songs: 2,
              },
              { id: "g2", title: "Crash", date: "2022-03-18", type: "Album" },
            ],
          },
        }),
      "/v1/catalogue/groups/g1/editions": (route) =>
        route.fulfill({
          json: {
            total: 1,
            offset: 0,
            editions: [
              {
                id: "r1",
                title: "Brat",
                date: "2024-06-07",
                country: "",
                description: "",
                status: "Official",
                formats: ["Digital Media"],
                track_count: 2,
              },
            ],
          },
        }),
      "/v1/library/lookup": (route) =>
        route.fulfill({ json: { tracks: owned } }),
      "/v1/catalogue/releases/r1": (route) =>
        route.fulfill({
          json: {
            id: "r1",
            title: "Brat",
            artist: artist.name,
            artist_id: "mb-1",
            tracks: owned.map((t) => ({
              ...t,
              saved_track: t,
              server_state: "in_library",
            })),
          },
        }),
    },
  });
  // Library page: play what you have.
  await page.goto(`/#/library/artist/${artist.id}`);
  await expect(
    page.locator(".release-actions").getByRole("button", { name: "Play" }),
  ).toBeEnabled();
  await expect(page.getByRole("heading", { name: "Albums" })).toBeVisible();
  await expect(page.locator(".personal-grid")).toContainText("2024 · 2 songs");
  await expect(page.getByRole("heading", { name: "Songs" })).toBeVisible();
  await expect(page.getByText("Von dutch").first()).toBeVisible();
  // Catalogue page: find what you could have, with your copies marked.
  await page
    .getByRole("button", { name: `Find more by ${artist.name}` })
    .click();
  await expect(page).toHaveURL(/#\/library\/discography\/mb-1\?/);
  const brat = page.getByRole("button", { name: /Brat/ });
  await expect(brat).toContainText("In library");
  await expect(page.getByRole("button", { name: /Crash/ })).not.toContainText(
    "In library",
  );
  await brat.click();
  await expect(
    page.getByText("Already in your library: nothing to download."),
  ).toBeVisible();
  await page.getByRole("link", { name: "Open in your library" }).click();
  await expect(page).toHaveURL(new RegExp(`#/library/album/${album.id}$`));
});

test("a member is told the owner links an ambiguous artist", async ({
  page,
}) => {
  await mockApi(page, { role: "member", answers: ambiguous });
  await page.goto(`/#/library/artist/${artist.id}`);
  await page
    .getByRole("button", { name: `Find more by ${artist.name}` })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "The owner can link it" }),
  ).toBeVisible();
  await expect(page.getByRole("group", { name: "Choose artist" })).toHaveCount(
    0,
  );
});
