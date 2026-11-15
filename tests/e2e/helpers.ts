import { expect, type Page } from "@playwright/test";

// Demo accounts are synthetic and local-only (services/api/ops/management/commands/seed_demo.py).
export const SUPERVISOR = { username: "supervisor", password: "sallimha-demo-supervisor" };

export async function login(page: Page, who = SUPERVISOR) {
  await page.goto("/login");
  await page.getByLabel(/اسم المستخدم|Username/).fill(who.username);
  await page.getByLabel(/كلمة المرور|Password/).fill(who.password);
  await page.getByRole("button", { name: /دخول|Sign in/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("ليلة العرض");
}

export async function noHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  expect(overflow).toBe(false);
}
