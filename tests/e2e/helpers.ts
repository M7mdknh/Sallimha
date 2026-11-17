import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { type Browser, type BrowserContext, expect, type Page } from "@playwright/test";

// Demo accounts are synthetic and local-only (services/api/ops/management/commands/seed_demo.py).
// Valets sign in with their mobile number; supervisors and admins with a username.
export const VALETS = {
  majed: { name: "ماجد (تجريبي)", phone: "+966550000101", password: "sallimha-demo-valet-101" },
  sara: { name: "سارة (تجريبي)", phone: "+966550000102", password: "sallimha-demo-valet-102" },
  fahad: { name: "فهد (تجريبي)", phone: "+966550000103", password: "sallimha-demo-valet-103" },
} as const;
export type ValetKey = keyof typeof VALETS;
export const SUPERVISOR = { username: "supervisor", password: "sallimha-demo-supervisor" };
export const ADMIN = { username: "admin", password: "sallimha-demo-admin" };

const API_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../services/api");

/** Current code for the synthetic demo admin, computed by the local-only `demo_totp` command. */
function demoTotp(username: string): string {
  return execFileSync("uv", ["run", "python", "manage.py", "demo_totp", username],
    { cwd: API_DIR, env: { ...process.env, SALLIMHA_ENV: "test" } }).toString().trim();
}

async function fillSignIn(page: Page, username: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/رقم الجوال أو اسم المستخدم|Mobile number or username/).fill(username);
  await page.getByLabel(/^(كلمة المرور|Password)$/).fill(password);
  await page.getByRole("button", { name: /^(دخول|Sign in)$/ }).click();
}

/** Signs in a supervisor or the admin (who passes the second factor; a code already used in this 30-second step
 *  is refused by replay protection, so on refusal wait for the next step and retry once). */
export async function loginAs(page: Page, account: "supervisor" | "admin") {
  const who = account === "admin" ? ADMIN : SUPERVISOR;
  await fillSignIn(page, who.username, who.password);
  if (account === "admin") {
    const otp = page.getByLabel(/رمز التحقق|Verification code/);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await otp.fill(demoTotp(who.username));
      await page.getByRole("button", { name: /^(دخول|Sign in)$/ }).click();
      const outcome = await Promise.race([
        page.getByRole("navigation", { name: /التنقل الرئيسي|Main navigation/ }).waitFor().then(() => "in"),
        page.getByRole("alert").waitFor().then(() => "refused"),
      ]);
      if (outcome === "in") break;
      await page.waitForTimeout((30 - (Math.floor(Date.now() / 1000) % 30) + 1) * 1000);
    }
  }
  await expect(mainNav(page)).toBeVisible();
}

export async function loginValet(page: Page, valet: ValetKey) {
  const v = VALETS[valet];
  await fillSignIn(page, `0${v.phone.slice(4)}`, v.password); // typed the local way: 05…
  await page.waitForURL(/\/work$/);
  await expect(page.getByTestId("connection")).toBeVisible();
}

/** A separate browser (own cookies) per person, sized like their device. */
export async function device(browser: Browser, size: { width: number; height: number }, lang: "ar" | "en" = "ar"):
  Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ viewport: size, hasTouch: size.width < 768,
    isMobile: size.width < 768, locale: lang === "ar" ? "ar-SA" : "en-GB" });
  if (lang === "en") await context.addInitScript(() => window.localStorage.setItem("sallimha.lang", "en"));
  return { context, page: await context.newPage() };
}

export const PHONE = { width: 390, height: 844 };
export const SMALL_PHONE = { width: 360, height: 780 };
export const TABLET = { width: 768, height: 1024 };
export const TABLET_LANDSCAPE = { width: 1024, height: 768 };

export const mainNav = (page: Page) => page.getByRole("navigation", { name: /التنقل الرئيسي|Main navigation/ });

/** A real JPEG made by the browser's own canvas, so the app's resize step runs as it does on a phone. */
export async function cameraPhoto(page: Page, label: string): Promise<{ name: string; mimeType: string; buffer: Buffer }> {
  const base64 = await page.evaluate(async (text) => {
    const canvas = document.createElement("canvas");
    canvas.width = 2400;
    canvas.height = 1600;
    const g = canvas.getContext("2d")!;
    g.fillStyle = "#62429B";
    g.fillRect(0, 0, canvas.width, canvas.height);
    g.fillStyle = "#C6A15B";
    g.font = "bold 160px sans-serif";
    g.fillText(text, 120, 800);
    const blob: Blob = await new Promise((resolve) => canvas.toBlob((b) => resolve(b!), "image/jpeg", 0.9));
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return btoa(binary);
  }, label);
  return { name: `${label}.jpg`, mimeType: "image/jpeg", buffer: Buffer.from(base64, "base64") };
}

/** The valet registers a car through the app: number and vehicle, confirm, four photos, receipt, park. */
export async function registerAndPark(page: Page, car: { guest: string; vehicle: string; zone: string; spot: string;
  hook: string; receipt?: boolean }) {
  await page.getByRole("navigation", { name: /التنقل الرئيسي|Main navigation/ }).getByRole("link", { name: /تسجيل سيارة|Register car/ }).click();
  const flow = page.getByTestId("register");
  await flow.getByLabel(/رقم جوال العميل|Customer's mobile number/).fill(car.guest);
  await flow.getByLabel(/اللوحة أو وصف قصير|Plate or a short description/).fill(car.vehicle);
  await flow.getByRole("button", { name: /التالي|Next/ }).click();
  await expect(flow.locator(".phone-confirm")).toHaveText(car.guest);
  await flow.getByRole("button", { name: /إرسال التذكرة|Send ticket/ }).click();
  await expect(flow).toHaveAttribute("data-step", "photos");
  for (let i = 1; i <= 4; i += 1) {
    await flow.locator("input[type=file]").setInputFiles(await cameraPhoto(page, `car-${i}`));
    await expect(flow.locator(".photo-count")).toContainText(`${i}`);
  }
  await expect(flow).toHaveAttribute("data-step", "receipt");
  await flow.getByRole("button", { name: car.receipt === false ? /لم تصل|Not received/ : /نعم، وصلت|Yes, received/ }).click();
  await expect(flow).toHaveAttribute("data-step", "start_parking");
  await flow.getByRole("button", { name: /بدء الركن|Start parking/ }).click();
  await expect(flow).toHaveAttribute("data-step", "park");
  await flow.locator(".choice", { hasText: car.zone }).click();
  await flow.getByLabel(/^(الموقف|Spot)$/).fill(car.spot);
  await flow.getByLabel(/رقم خطاف المفتاح|Key hook number/).fill(car.hook);
  await flow.getByRole("button", { name: /^(تم الركن|Parked)$/ }).click();
  await expect(page.getByTestId("parked-done")).toBeVisible();
  const ticket = (await page.getByTestId("parked-done").locator("bdi").textContent())!.trim();
  await page.getByTestId("parked-done").getByRole("button", { name: /مهامي|My work/ }).click();
  return ticket;
}

/** The valet's current task card (waits for the server's step). */
export async function taskStep(page: Page, step: string) {
  await expect(page.getByTestId("task-card")).toHaveAttribute("data-step", step, { timeout: 30_000 });
  return page.getByTestId("task-card");
}

// --- the customer, through the development simulator (every message here is SIMULATED) -------------------

export async function customerThread(page: Page, phone: string, timeout = 30_000) {
  await page.goto("/dev/simulator");
  await expect(page.getByText(/محاكاة — لا تصل أي رسالة إلى هاتف حقيقي|SIMULATED/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: new RegExp(phone.replace("+", "\\+")) })).toBeVisible({ timeout });
  await page.getByRole("button", { name: new RegExp(phone.replace("+", "\\+")) }).click();
  await expect(page.getByRole("heading", { level: 2, name: phone })).toBeVisible();
}

/** The customer taps "Request my car" on their WhatsApp ticket. */
export async function customerRequests(page: Page, phone: string) {
  await customerThread(page, phone);
  await page.getByRole("log").getByRole("button", { name: "اطلب سيارتي" }).last().click();
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/استلمنا طلبك|طلبك/, { timeout: 30_000 });
}

/** The six-digit code from the customer's "car ready" message. */
export async function customerCode(page: Page, phone: string): Promise<string> {
  await customerThread(page, phone);
  const ready = page.getByRole("log").locator(".bubble-out").filter({ hasText: /\b\d{6}\b/ }).last();
  await expect(ready).toBeVisible({ timeout: 30_000 });
  return ((await ready.textContent()) ?? "").match(/\b\d{6}\b/)![0];
}

export async function customerSays(page: Page, phone: string, text: string) {
  await customerThread(page, phone);
  await page.getByLabel(/رسالة|Message/).fill(text);
  await page.getByRole("button", { name: /إرسال|Send/ }).click();
}

/** Opens a ticket's detail from Operations' search. */
export async function openTicket(page: Page, query: string) {
  await mainNav(page).getByRole("link", { name: /التشغيل|Operations/ }).click();
  const finder = page.getByRole("search");
  await finder.getByLabel(/رقم التذكرة أو جزء من اللوحة|Ticket number or part of the plate/).fill(query);
  await finder.getByRole("button", { name: /^(بحث|Find)$/ }).click();
  await page.locator(".rows").getByRole("button", { name: new RegExp(query) }).first().click();
  await expect(page.locator(".ticket-panel")).toBeVisible();
  return page.locator(".ticket-panel");
}

/** Fails with the page, width and the elements that stick out, so a layout regression is easy to locate. */
export async function noHorizontalOverflow(page: Page, label = "") {
  const culprits = await page.evaluate(() => {
    if (document.documentElement.scrollWidth <= window.innerWidth + 1) return [];
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
