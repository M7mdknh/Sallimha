import { expect, type Page, test } from "@playwright/test";
import { loginAs, noHorizontalOverflow } from "./helpers";

// AT-53 browser zoom. Playwright cannot press Ctrl+= in Chromium, so two documented equivalents are exercised:
//  1. Page zoom as Chromium applies it: a 1280 x 900 window at 200 % has a 640 x 450 CSS viewport and a device
//     pixel ratio of 2 — emulated exactly with viewport + deviceScaleFactor.
//  2. CSS `zoom: 2` on the document at 1280 px (Chromium's standardised layout zoom), which scales every box
//     and font like page zoom without changing the viewport.
// Neither is the browser's zoom UI itself; that remains a manual check (docs/evidence/review-2026-11-16.md).

const PAGES = ["/dashboard", "/team", "/settings", "/settings/operation", "/settings/delivery", "/outages"];

async function usable(page: Page, path: string) {
  await page.goto(path);
  await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await noHorizontalOverflow(page, `zoom ${path}`);
  const nav = page.getByRole("navigation", { name: /التنقل الرئيسي|Main navigation/ });
  await expect(nav.getByRole("link").first()).toBeVisible();
}

test("200 % page zoom: 640 CSS px at device pixel ratio 2, every management page usable", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "builds its own zoomed browser context");
  test.setTimeout(120_000);
  const context = await browser.newContext({ viewport: { width: 640, height: 450 }, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await loginAs(page, "admin");
  expect(await page.evaluate(() => window.devicePixelRatio)).toBe(2);
  const live = new URL(page.url()).pathname;
  for (const path of [live, ...PAGES]) await usable(page, path);
  await context.close();
});

test("CSS layout zoom 200 % at 1280 px keeps pages usable", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "builds its own browser context");
  test.setTimeout(120_000);
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => { document.documentElement.style.setProperty("zoom", "2"); });
  });
  const page = await context.newPage();
  await loginAs(page, "admin");
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).zoom)).toBe("2");
  const live = new URL(page.url()).pathname;
  for (const path of [live, ...PAGES]) await usable(page, path);
  await context.close();
});
