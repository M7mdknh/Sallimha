import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page } from "@playwright/test";

// Demo accounts are synthetic and local-only (services/api/ops/management/commands/seed_demo.py).
export const SUPERVISOR = { username: "supervisor", password: "sallimha-demo-supervisor" };
export const ACCOUNTS = {
  supervisor: SUPERVISOR,
  manager: { username: "manager", password: "sallimha-demo-manager" },
  admin: { username: "admin", password: "sallimha-demo-admin" },
  owner: { username: "owner", password: "sallimha-demo-owner" },
} as const;
export type Account = keyof typeof ACCOUNTS;

const API_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../services/api");

/** Current code for a synthetic demo account, computed by the local-only `demo_totp` command. */
function demoTotp(username: string): string {
  return execFileSync("uv", ["run", "python", "manage.py", "demo_totp", username],
    { cwd: API_DIR, env: { ...process.env, SALLIMHA_ENV: "test" } }).toString().trim();
}

/** Signs in any console role. Manager and above pass the second factor; a code already used in this
 *  30-second step is refused by replay protection, so on refusal wait for the next step and retry once. */
export async function loginAs(page: Page, account: Account) {
  const who = ACCOUNTS[account];
  await page.goto("/login");
  await page.getByLabel(/اسم المستخدم|Username/).fill(who.username);
  await page.getByLabel(/كلمة المرور|Password/).fill(who.password);
  await page.getByRole("button", { name: /دخول|Sign in/ }).click();
  if (account !== "supervisor") {
    const otp = page.getByLabel(/رمز التحقق|Verification code/);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await otp.fill(demoTotp(who.username));
      await page.getByRole("button", { name: /دخول|Sign in/ }).click();
      const outcome = await Promise.race([
        page.getByRole("navigation").waitFor().then(() => "in"),
        page.getByRole("alert").waitFor().then(() => "refused"),
      ]);
      if (outcome === "in") break;
      await page.waitForTimeout((30 - (Math.floor(Date.now() / 1000) % 30) + 1) * 1000);
    }
  }
  await expect(page.getByRole("navigation")).toBeVisible();
  await page.waitForURL(/\/events\/\d+$/); // a single open event opens its live view
}

export async function login(page: Page, who = SUPERVISOR) {
  await page.goto("/login");
  await page.getByLabel(/اسم المستخدم|Username/).fill(who.username);
  await page.getByLabel(/كلمة المرور|Password/).fill(who.password);
  await page.getByRole("button", { name: /دخول|Sign in/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("ليلة العرض");
}

/** Fails with the page, width and the elements that stick out, so a layout regression is easy to locate. */
export async function noHorizontalOverflow(page: Page, label = "") {
  const culprits = await page.evaluate(() => {
    if (document.documentElement.scrollWidth <= window.innerWidth + 1) return [];
    // Content inside a horizontal scroll container (the narrow nav row, wide tables) is clipped, not overflow.
    const clipped = (el: Element) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        if (["auto", "scroll", "hidden", "clip"].includes(getComputedStyle(p).overflowX)) return true;
      }
      return false;
    };
    return [...document.querySelectorAll("body *")]
      .filter((el) => { const r = el.getBoundingClientRect(); return r.right > window.innerWidth + 1 || r.left < -1; })
      .filter((el) => !clipped(el))
      .slice(0, 5)
      .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join(".")} "${(el.textContent ?? "").trim().slice(0, 40)}"`);
  });
  expect(culprits, `${label} at ${page.viewportSize()?.width}px: ${new URL(page.url()).pathname}`).toEqual([]);
}
