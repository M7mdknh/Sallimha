import { defineConfig, devices } from "@playwright/test";

// Local runs may use the installed Chrome (PW_CHANNEL=chrome) to avoid a browser download;
// CI installs Playwright's bundled Chromium. The backend runs with the simulated WhatsApp transport.
const channel = process.env.PW_CHANNEL || undefined;
const webOrigin = "http://127.0.0.1:5180";
const databaseUrl =
  process.env.E2E_DATABASE_URL ?? "postgres://sallimha:sallimha-local-only@127.0.0.1:55432/sallimha_e2e";

export default defineConfig({
  testDir: ".",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: webOrigin, trace: "retain-on-failure", channel },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel, viewport: { width: 1280, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"], channel, viewport: { width: 360, height: 800 } } },
  ],
  webServer: [
    {
      command: "../../scripts/run-local-backend.sh",
      url: "http://127.0.0.1:8100/readyz",
      env: { DATABASE_URL: databaseUrl, SALLIMHA_ENV: "test" },
      reuseExistingServer: process.env.E2E_REUSE === "1",
      timeout: 180_000,
    },
    {
      command: "npm run build && npm run preview",
      cwd: "../../apps/web",
      url: webOrigin,
      reuseExistingServer: process.env.E2E_REUSE === "1",
      timeout: 180_000,
    },
  ],
});
