import { expect, test } from "@playwright/test";
import { login, noHorizontalOverflow } from "./helpers";

test("supervisor signs in and sees the live view attention-first in Arabic", async ({ page }) => {
  await login(page);
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  const headings = await page.getByRole("heading", { level: 2 }).allTextContents();
  expect(headings[0]).toMatch(/يحتاج انتباهك/);
  await expect(page.getByRole("region", { name: /الطلبات المفتوحة/ })).toBeVisible();
  await expect(page.getByRole("region", { name: /الفريق/ })).toBeVisible();
  await expect(page.getByText(/محاكاة/).first()).toBeVisible(); // WhatsApp health is labelled simulated
  await noHorizontalOverflow(page);
});

test("wrong password shows a generic error and stays on login", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel(/اسم المستخدم/).fill("supervisor");
  await page.getByLabel(/كلمة المرور/).fill("not-the-password");
  await page.getByRole("button", { name: /دخول/ }).click();
  await expect(page.getByRole("alert")).toContainText(/اسم المستخدم أو كلمة المرور غير صحيحة/);
});

test("English switches the console to LTR", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "English" }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(page.getByRole("heading", { level: 2 }).first()).toHaveText(/Needs your attention/);
  await page.getByRole("button", { name: "العربية" }).click();
});

test("lost connection shows the stale banner and disables actions", async ({ page }) => {
  await login(page);
  await page.route("**/api/events/*/live", (route) => route.abort());
  await expect(page.getByRole("status").filter({ hasText: /غير محدّثة/ })).toBeVisible({ timeout: 20_000 });
  for (const button of await page.locator("main button[data-mutation]").all()) {
    await expect(button).toBeDisabled();
  }
  await page.unroute("**/api/events/*/live");
  await expect(page.getByRole("status").filter({ hasText: /غير محدّثة/ })).toBeHidden({ timeout: 20_000 });
});

test("valets have no console access", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: /دخول/ })).toBeVisible();
  const response = await page.request.get("/api/events/");
  expect([401, 403]).toContain(response.status());
});
