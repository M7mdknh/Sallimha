import { expect, test } from "@playwright/test";

test("Arabic is the default and all four brand faces load without overflow", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  // Request every self-hosted face explicitly: proves each file is served and parses, whatever the page uses.
  const faces = await page.evaluate(async () => {
    for (const spec of ['400 16px "Noto Sans Arabic"', '700 16px "Noto Sans Arabic"', '400 16px "Noto Sans"',
      '700 16px "Noto Sans"']) {
      await document.fonts.load(spec, "سلّمها Sallimha");
    }
    return [...document.fonts].map((f) => `${f.family}|${f.weight}|${f.status}`).sort();
  });
  expect(faces).toEqual([
    "Noto Sans Arabic|400|loaded",
    "Noto Sans Arabic|700|loaded",
    "Noto Sans|400|loaded",
    "Noto Sans|700|loaded",
  ]);
  const bodyFont = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(bodyFont.startsWith('"Noto Sans Arabic"')).toBe(true);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
});

test("switching to English sets ltr and the English stack", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  const bodyFont = await page.evaluate(() => getComputedStyle(document.body).fontFamily);
  expect(bodyFont.startsWith('"Noto Sans"')).toBe(true);
  await page.getByRole("button", { name: "العربية" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
});
