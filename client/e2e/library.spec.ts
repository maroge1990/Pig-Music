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
  await expect(page).toHaveURL(/#\/search\/artist\/mb-1\?/);
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
