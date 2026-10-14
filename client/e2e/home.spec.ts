import { expect, test } from "@playwright/test";
import { album, mockApi } from "./mock";

const item = (id: string, name: string) => ({
  id,
  name,
  artist: "Someone",
  artist_id: "a-" + id,
});
const feed = (title: string) => ({
  state: "ready",
  title,
  artists: [item("ar1", "Artist one")],
  albums: [item("al1", "Album one")],
  songs: [
    {
      ...item("s1", "Song one"),
      title: "Song one",
      album: "Album one",
      duration: 200,
    },
  ],
});

// Home: what you added lately, then recommendations above popularity.
// Recommendations show artists and albums only, never songs.
test("Home order, with no song recommendations", async ({ page }) => {
  await mockApi(page, {
    answers: {
      "/v1/home/recent": (route) =>
        route.fulfill({
          json: {
            albums: [
              { id: album.id, title: album.title, artist: album.artist },
            ],
          },
        }),
      "/v1/home/recommended": (route) => route.fulfill({ json: feed("") }),
      "/v1/home/popular": (route) =>
        route.fulfill({ json: feed("Popular in Australia") }),
    },
  });
  await page.goto("/#/home");
  const sections = page.locator(".home-page > .home-section > h2");
  await expect(sections).toHaveText([
    "Recently added",
    "Recommended for you",
    "Popular in Australia",
  ]);
  const recommended = page
    .locator(".home-section")
    .filter({ hasText: "Recommended for you" });
  await expect(recommended.locator("h3")).toHaveText(["Artists", "Albums"]);
  await expect(recommended).not.toContainText("Song one");
  const popular = page
    .locator(".home-section")
    .filter({ hasText: "Popular in Australia" });
  await expect(popular.locator("h3")).toHaveText([
    "Artists",
    "Albums",
    "Songs",
  ]);
});
