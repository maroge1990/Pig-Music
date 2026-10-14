import { defineConfig, devices } from "@playwright/test";

// Smoke tests run the built client against a mocked API (e2e/mock.ts), so
// they need no server, account or music. Build first: npm run build.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  fullyParallel: true,
  reporter: process.env.CI ? "github" : "list",
  // The service worker would answer some API calls itself, out of the mock's reach.
  use: { baseURL: "http://127.0.0.1:4179", serviceWorkers: "block" },
  // An explicit IPv4 host: on Linux "localhost" can bind to ::1 only, and the
  // readiness check below would never connect.
  webServer: {
    command: "npx vite preview --host 127.0.0.1 --port 4179 --strictPort",
    url: "http://127.0.0.1:4179",
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: "desktop",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1366, height: 900 },
      },
    },
    {
      name: "phone",
      use: { ...devices["Pixel 7"], viewport: { width: 375, height: 812 } },
    },
  ],
});
