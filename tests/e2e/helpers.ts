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

// --- development simulator (every message here is SIMULATED) ---------------------------------------------
export const VALETS: Record<string, string> = {
  "ماجد (تجريبي)": "+966550000101", "سارة (تجريبي)": "+966550000102", "فهد (تجريبي)": "+966550000103",
};

export const mainNav = (page: Page) => page.getByRole("navigation", { name: /التنقل الرئيسي|Main navigation/ });

export async function openSimulator(page: Page) {
  await mainNav(page).getByRole("link", { name: "المحاكي", exact: true }).click();
  await expect(page.getByText(/محاكاة — لا تصل أي رسالة إلى هاتف حقيقي/)).toBeVisible();
}

export async function thread(page: Page, phone: string) {
  await page.getByRole("button", { name: new RegExp(phone.replace("+", "\\+")) }).click();
  await expect(page.getByRole("heading", { level: 2, name: phone })).toBeVisible();
}

export async function say(page: Page, text: string, reply: RegExp) {
  await page.getByLabel(/رسالة|Message/).fill(text);
  await page.getByRole("button", { name: /إرسال|Send/ }).click();
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(reply);
}

/** Taps a button in the newest message only, so an older message's button is never pressed by mistake. */
export async function tapButton(page: Page, title: string) {
  const button = page.getByRole("log").locator(".bubble-out").last().getByRole("button", { name: title });
  await expect(button).toBeVisible();
  await button.click();
}

/** Registers and parks a car through a valet's simulated WhatsApp thread. */
export async function parkViaSimulator(page: Page, car: { valet: string; guest: string; plate: string;
  location: string; hook: string }) {
  await openSimulator(page);
  await thread(page, car.valet);
  await say(page, "مركبة جديدة", /أرسل رقم جوال الضيف/);
  await say(page, car.guest, /هل الرقم/);
  await tapButton(page, "تأكيد الرقم");
  await tapButton(page, "نعم، استلمها");
  await say(page, car.plate, /صور للمركبة/);
  for (let i = 1; i <= 4; i += 1) {
    await page.getByRole("button", { name: /صورة|Photo/ }).click();
    await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(i < 4 ? `${i} من` : /اكتملت الصور/);
  }
  await tapButton(page, "بدء الركن");
  await say(page, car.location, /خطاف المفتاح/);
  await say(page, car.hook, /تم الركن/);
}

/** Opens a ticket's panel from the live view's ticket finder. */
export async function findTicket(page: Page, eventPath: string, query: string, rowName: RegExp) {
  await page.goto(eventPath);
  const finder = page.getByRole("search");
  await finder.getByLabel(/رقم التذكرة أو جزء من اللوحة|Ticket number or part of the plate/).fill(query);
  await finder.getByRole("button", { name: /^(بحث|Find)$/ }).click();
  await page.getByRole("button", { name: rowName }).click();
  await expect(page.locator(".ticket-panel")).toBeVisible();
}
