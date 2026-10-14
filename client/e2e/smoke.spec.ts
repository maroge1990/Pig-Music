import { expect, test } from "@playwright/test";
import { album, artist, mockApi } from "./mock";

// R19 smoke journeys at 1366 px and 375 px (projects), in both themes.
for (const appearance of ["light", "dark"] as const) {
  test(`home, library album and account render (${appearance})`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await mockApi(page, { appearance });
    await page.goto("/#/home");
    await expect(page.locator("html")).toHaveAttribute(
      "data-theme",
      appearance,
    );
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
    await page.goto(`/#/library/album/${album.id}`);
    await expect(page.getByText("Von dutch").first()).toBeVisible();
    await page.goto("/#/account");
    await expect(
      page.getByRole("heading", { name: "Your account" }),
    ).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test("the page never scrolls sideways", async ({ page }) => {
  await mockApi(page);
  for (const route of [
    "/#/home",
    `/#/library/album/${album.id}`,
    `/#/search/artist/${artist.id}?name=Charli%20xcx`,
  ]) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow, route).toBeLessThanOrEqual(1);
  }
});
