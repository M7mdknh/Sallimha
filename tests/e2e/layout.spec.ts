import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { expect, type Page, test } from "@playwright/test";

import {
  PHONE, customerRequests, device, loginAs, loginValet, noHorizontalOverflow, openTicket, registerAndPark, taskStep,
} from "./helpers";

// Phone and tablet review (ADR-0011): every main screen of the three roles in Arabic and English at 360, 390, 768
// (tablet portrait) and 1024 (tablet landscape). Each screen must fit without sideways scrolling; the screenshots
// are saved as evidence for visual review (docs/evidence/screens). Customer messages are SIMULATED.

const SIZES = [
  { width: 360, height: 780 }, { width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1024, height: 768 },
];
const OUT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../docs/evidence/screens");

async function setLang(page: Page, lang: "ar" | "en") {
  await page.evaluate((l) => window.localStorage.setItem("sallimha.lang", l), lang);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", lang);
}

async function capture(page: Page, lang: string, name: string) {
  const size = page.viewportSize()!;
  await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
  await noHorizontalOverflow(page, `${lang} ${name}`);
  fs.mkdirSync(path.join(OUT, lang), { recursive: true });
  await page.screenshot({ path: path.join(OUT, lang, `${size.width}-${name}.png`), fullPage: true });
}

/** Admin timings through the API (same rules and audit as Settings → Timings). */
async function setOfferTimings(p: Page, window: number, hard: number) {
  const csrf = (await p.context().cookies()).find((c) => c.name === "csrftoken")?.value ?? "";
  const { version } = await (await p.request.get("/api/config")).json();
  const changed = await p.request.post("/api/config/timings", {
    data: { version, timings: { offer_window_s: window, hard_limit_s: hard } },
    headers: { "X-CSRFToken": csrf, "Content-Type": "application/json", "Idempotency-Key": `timings-${Date.now()}` } });
  expect(changed.status()).toBe(200);
}

test("every main screen fits phones and tablets in Arabic and English", async ({ page, browser }, info) => {
  test.skip(info.project.name !== "desktop", "sizes are set explicitly; runs once");
  test.setTimeout(420_000);

  // The screenshots take minutes; an offer correctly lapses after its window, so this test lengthens the window for
  // itself (admin timings, audited) and restores the defaults at the end.
  const admin = await device(browser, { width: 1024, height: 768 });
  await loginAs(admin.page, "admin");
  await setOfferTimings(admin.page, 600, 1200);

  // A car the customer has asked for: an offer on the valet's phone and a waiting car in Operations.
  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "majed");
  await registerAndPark(valet.page, { guest: "0501239901", vehicle: "LAY 1000 تاهو سوداء", zone: "B", spot: "9",
    hook: "199" });
  await loginAs(page, "supervisor");
  await customerRequests(page, "+966501239901");
  await taskStep(valet.page, "offer");
  const panel = await openTicket(page, "LAY 1000");
  const ticketUrl = page.url();
  await expect(panel).toBeVisible();

  const registering = await device(browser, PHONE);
  await loginValet(registering.page, "sara");
  await registering.page.getByRole("link", { name: "تسجيل سيارة" }).click();
  await registering.page.getByLabel("رقم جوال العميل").fill("0501239902");

  for (const lang of ["ar", "en"] as const) {
    for (const p of [valet.page, registering.page, page, admin.page]) await setLang(p, lang);
    for (const size of SIZES) {
      for (const p of [valet.page, registering.page, page, admin.page]) await p.setViewportSize(size);
      await valet.page.goto("/work");
      await taskStep(valet.page, "offer");
      await capture(valet.page, lang, "valet-offer");
      await registering.page.goto("/register");
      await capture(registering.page, lang, "valet-register");
      await page.goto(ticketUrl);
      await expect(page.locator(".ticket-panel")).toBeVisible();
      await capture(page, lang, "supervisor-ticket");
      await page.goto(ticketUrl.replace(/\/tickets\/\d+$/, ""));
      await expect(page.getByTestId("list-waiting")).toBeVisible();
      await capture(page, lang, "supervisor-operations");
      await page.goto("/team");
      await expect(page.getByTestId("tonights-team")).toBeVisible();
      await capture(page, lang, "supervisor-team");
      await admin.page.goto("/dashboard");
      await expect(admin.page.getByTestId("request-to-ready")).toBeVisible();
      await capture(admin.page, lang, "admin-dashboard");
    }
  }

  // Leave nothing open for the next tests: the supervisor withdraws the request.
  await setLang(page, "ar");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(ticketUrl);
  const ticket = page.locator(".ticket-panel");
  await ticket.locator(".more-actions > summary").click();
  await ticket.getByRole("button", { name: "سحب طلب الإحضار", exact: true }).click();
  await ticket.locator(".action-form").getByLabel("السبب").fill("انتهاء مراجعة التصميم (تجريبي)");
  await ticket.locator(".action-form").getByRole("button", { name: "سحب طلب الإحضار", exact: true }).click();
  await taskStep(valet.page, "none");
  await setOfferTimings(admin.page, 30, 60);
  for (const c of [valet.context, registering.context, admin.context]) await c.close();
});
