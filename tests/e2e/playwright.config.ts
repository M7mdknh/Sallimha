import { defineConfig, devices } from "@playwright/test";

// Local runs may use the installed Chrome (PW_CHANNEL=chrome) to avoid a browser
// download; CI installs Playwright's bundled Chromium.
const channel = process.env.PW_CHANNEL || undefined;
const webOrigin = "http://127.0.0.1:5180";

export default defineConfig({
  testDir: ".",
  timeout: 60_000,
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
      command: "npm run build && npm run preview",
      cwd: "../../apps/web",
      url: webOrigin,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
