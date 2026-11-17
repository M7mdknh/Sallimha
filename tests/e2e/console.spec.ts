import { expect, test } from "@playwright/test";

import { loginAs, mainNav, noHorizontalOverflow } from "./helpers";

test("a supervisor signs in and sees Operations problems-first in Arabic", async ({ page }) => {
  await loginAs(page, "supervisor");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  // Wait for Operations to render (the first read used to race a cold server): the first section is the problems.
  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/تحتاج تدخلك/);
  await expect(page.getByTestId("list-waiting")).toBeVisible();
  await expect(page.getByTestId("list-retrieving")).toBeVisible();
  await expect(page.getByTestId("list-ready")).toBeVisible();
  await noHorizontalOverflow(page);
});

test("a wrong password shows a generic error and stays on sign-in", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/رقم الجوال أو اسم المستخدم/).fill("supervisor");
  await page.getByLabel(/^كلمة المرور$/).fill("not-the-password");
  await page.getByRole("button", { name: /^دخول$/ }).click();
  await expect(page.getByRole("alert")).toContainText(/غير صحيحة/);
  await expect(page).toHaveURL(/\/login$/);
});

test("English switches the console to LTR", async ({ page }) => {
  await loginAs(page, "supervisor");
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(mainNav(page).getByRole("link")).toHaveText(["Operations", "Team"]);
  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Needs you/);
  await page.getByRole("button", { name: "العربية" }).click();
});

test("a lost connection shows the stale banner and disables actions until it returns", async ({ page }) => {
  await loginAs(page, "supervisor");
  await page.route("**/api/events/*/live", (route) => route.abort());
  await expect(page.getByRole("status").filter({ hasText: /غير محدّثة/ })).toBeVisible({ timeout: 20_000 });
  for (const button of await page.locator("main button[data-mutation]").all()) {
    await expect(button).toBeDisabled();
  }
  await page.unroute("**/api/events/*/live");
  await expect(page.getByRole("status").filter({ hasText: /غير محدّثة/ })).toBeHidden({ timeout: 20_000 });
});

test("signed-out requests are refused", async ({ page }) => {
  await page.goto("/login");
  for (const url of ["/api/events/", "/api/valet/work", "/api/dashboard"]) {
    expect([401, 403]).toContain((await page.request.get(url)).status());
  }
});
