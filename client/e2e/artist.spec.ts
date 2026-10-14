import { expect, test } from "@playwright/test";
import { artist, mockApi } from "./mock";

// The photograph fades into the page as part of the photograph itself (a mask),
// so the fade moves with it instead of a separate overlay scrolling at another speed.
test("artist photo fades with a mask that travels with it", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/#/search/artist/${artist.id}?name=Charli%20xcx`);
  const backdrop = page.locator(".has-background .artist-backdrop");
  await expect(backdrop).toBeVisible();
  await expect(page.locator(".artist-photo-sharp")).toHaveJSProperty(
    "complete",
    true,
  );
  const mask = await backdrop.evaluate((el) => {
    const style = getComputedStyle(el);
    return style.maskImage || style.getPropertyValue("-webkit-mask-image");
  });
  expect(mask).toContain("linear-gradient");
  // No separate gradient overlay sits on the scene any more.
  const overlay = await page
    .locator(".artist-scene")
    .evaluate((el) => getComputedStyle(el, "::after").backgroundImage);
  expect(overlay).toBe("none");

  const before = await backdrop.evaluate((el) =>
    Number(getComputedStyle(el).opacity),
  );
  await page.mouse.wheel(0, 320);
  await expect
    .poll(() => backdrop.evaluate((el) => Number(getComputedStyle(el).opacity)))
    .toBeLessThan(before);
  // Still masked while it fades and drifts.
  expect(
    await backdrop.evaluate(
      (el) =>
        getComputedStyle(el).maskImage ||
        getComputedStyle(el).getPropertyValue("-webkit-mask-image"),
    ),
  ).toContain("linear-gradient");
});
