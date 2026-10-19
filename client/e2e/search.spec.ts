import { expect, test } from "@playwright/test";
import { artist, mockApi } from "./mock";

test("search types ahead without a request per keystroke", async ({ page }) => {
  const asked: string[] = [];
  await mockApi(page, {
    answers: {
      "/v1/search": (route) => {
        asked.push(
          "library:" + new URL(route.request().url()).searchParams.get("q"),
        );
        return route.fulfill({ json: { tracks: [], household_tracks: [] } });
      },
      "/v1/catalogue/artists": (route) => {
        const q = new URL(route.request().url()).searchParams.get("q") || "";
        asked.push("catalogue:" + q);
        return route.fulfill({
          json: {
            artists: [
              {
                id: "mb-charli",
                name: artist.name,
                description: "English singer",
              },
              { id: "mb-other", name: q + " Band", description: "" },
            ],
            offset: 0,
            total: 2,
            next_offset: null,
          },
        });
      },
    },
  });
  await page.goto("/#/search");
  const box = page.getByRole("searchbox", {
    name: "Search artists, albums or songs",
  });
  await box.pressSequentially("Charli", { delay: 40 });
  const discover = page.locator(".discover-list");
  await expect(discover).toContainText("Charli Band");
  // One pause, one search: nothing was sent for "C", "Ch", "Cha" …
  expect(asked).toEqual(["library:Charli", "catalogue:Charli"]);
  await expect(page).toHaveURL(/#\/search\?q=Charli$/);
  // Discover rows show artwork, type and what you already have.
  const charli = discover.getByRole("link", { name: /English singer/ });
  await expect(charli).toContainText("Artist · English singer");
  await expect(charli).toContainText("In your library");
  await expect(charli.locator(".cover")).toHaveCount(1);
  await expect(
    discover.getByRole("link", { name: /Charli Band/ }),
  ).not.toContainText("In your library");
  // Changing and going back reuses the earlier answers.
  await box.press("Backspace");
  await expect(discover).toContainText("Charl Band");
  await box.press("i");
  await expect(discover).toContainText("Charli Band");
  expect(asked).toEqual([
    "library:Charli",
    "catalogue:Charli",
    "library:Charl",
    "catalogue:Charl",
  ]);
  // One letter searches your library only.
  await box.fill("C");
  await expect(
    page.getByText("Type another letter to search the catalogue."),
  ).toBeVisible();
  expect(asked.filter((a) => a === "catalogue:C")).toEqual([]);
});
