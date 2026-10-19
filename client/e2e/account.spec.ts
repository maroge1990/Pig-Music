import { expect, test } from "@playwright/test";
import { mockApi } from "./mock";

test("Your devices names each session and can sign out the others", async ({
  page,
}) => {
  const now = Date.now() / 1000;
  let signedOut = false;
  const sessions = () => [
    {
      id: "web-1",
      kind: "web",
      device_name: "Safari on Mac",
      platform: "web",
      created_at: now - 9000,
      last_seen_at: now - 60,
      expires_at: now + 9000,
      revoked_at: null,
      current: true,
    },
    ...(signedOut
      ? []
      : [
          {
            id: "phone-1",
            kind: "device",
            device_name: "iPhone",
            platform: "ios",
            created_at: now - 90000,
            last_seen_at: now - 7200,
            expires_at: now + 90000,
            revoked_at: null,
          },
        ]),
  ];
  await mockApi(page, {
    answers: {
      "/v1/me/sessions": (route) => {
        if (route.request().method() === "DELETE") {
          signedOut = true;
          return route.fulfill({ json: { revoked: 1 } });
        }
        return route.fulfill({ json: { sessions: sessions() } });
      },
      "/v1/quality": (route) =>
        route.fulfill({
          json: { preferences: [], options: [], household_default: "" },
        }),
    },
  });
  await page.goto("/#/account");
  const devices = page.locator(".session-list li");
  await expect(devices).toHaveCount(2);
  await expect(devices.first()).toContainText("Safari on Mac · This device");
  await expect(devices.first()).toContainText("Web · In use now");
  await expect(devices.first().getByRole("button")).toHaveCount(0);
  await expect(devices.nth(1)).toContainText(
    "iPhone or iPad app · Last used 2 h ago",
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Sign out other devices" }).click();
  await expect(page.getByText("Signed out 1 other device.")).toBeVisible();
  await expect(devices).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Sign out other devices" }),
  ).toHaveCount(0);
});
