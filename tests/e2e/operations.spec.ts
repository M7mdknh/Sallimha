import { expect, type Locator, type Page, test } from "@playwright/test";

import {
  cameraPhoto, customerRequests, customerSays, customerThread, device, enterCar, loginAs, loginValet, mainNav, openTicket, PHONE, registerAndPark, taskStep, VALETS,
} from "./helpers";

// Supervisor and admin work around the staff app (ADR-0011). Customer messages are SIMULATED.

/** Venue wall-clock time (Asia/Riyadh) `minutes` from now, as a datetime-local value. */
function riyadh(minutes: number) {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Riyadh", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(Date.now() + minutes * 60_000)).replace(" ", "T");
}

/** Runs a ticket action (primary, or under More actions) and waits for its form to close. */
async function ticketAction(panel: Locator, label: string, fill: (form: Locator) => Promise<void>) {
  const button = panel.getByRole("button", { name: label, exact: true }).first();
  if (!(await button.isVisible())) await panel.locator(".more-actions > summary").click();
  await button.click();
  const form = panel.locator(".action-form");
  await fill(form);
  await form.getByRole("button", { name: label, exact: true }).click();
  await expect(form).toHaveCount(0);
}

async function setSimulatedOutage(page: Page, down: boolean) {
  await page.goto("/dev/simulator");
  const start = page.getByRole("button", { name: "محاكاة انقطاع واتساب" });
  const end = page.getByRole("button", { name: "إنهاء الانقطاع المحاكى" });
  await expect(start.or(end)).toBeVisible(); // the switch shows once the simulator has read the provider's state
  if (await (down ? start : end).isVisible()) await (down ? start : end).click();
  await expect(down ? end : start).toBeVisible();
}

test.afterEach(async ({ page }) => {
  // Never leave the simulated provider down for the next test (or the next project), whatever happened above.
  const csrf = (await page.context().cookies()).find((c) => c.name === "csrftoken")?.value;
  if (!csrf) return;
  const reset = await page.request.post("/api/dev/sim/outage", { data: { down: false },
    headers: { "X-CSRFToken": csrf, "Content-Type": "application/json" } });
  expect([200, 403]).toContain(reset.status()); // 403: this page was never signed in as a console user
});

test("device not working: the supervisor registers and parks a car for that valet, and only for them", async (
  { page }, info) => {
  test.setTimeout(180_000);
  const n = info.project.name === "desktop" ? "5" : "6";
  await loginAs(page, "supervisor");
  await mainNav(page).getByRole("link", { name: "الفريق" }).click();
  const fahad = page.getByTestId("tonights-team").locator(".row", { hasText: VALETS.fahad.name });
  await expect(page.getByRole("heading", { name: /تسجيل سيارة عن فاليه/ })).toHaveCount(0); // nobody marked yet
  await fahad.getByRole("button", { name: "جهازه لا يعمل" }).click();
  await fahad.getByLabel("ما المشكلة؟").fill("نفدت بطارية الجوال (تجريبي)");
  await fahad.getByRole("button", { name: "جهازه لا يعمل" }).last().click();
  await expect(fahad).toContainText("المشرف يسجّل عنه");

  const form = page.locator("section", { hasText: "تسجيل سيارة عن فاليه جهازه لا يعمل" });
  await form.getByLabel("الموظف").selectOption({ label: VALETS.fahad.name });
  await enterCar(form, `05012399${n}1`, `DEV ${n}500`);
  await form.getByLabel("طريقة التأكد").selectOption("radio");
  await form.getByLabel("السبب").fill("جهاز الفاليه لا يعمل");
  await form.getByRole("button", { name: "تسجيل الاستلام" }).click();
  const panel = page.locator(".ticket-panel");
  await expect(panel).toContainText(`DEV ${n}500`);

  // Until the four photos are in, adding one is the primary action; its form stays open between photos.
  await expect(panel.getByRole("button", { name: "إضافة صورة استلام", exact: true }).first()).toHaveClass(/btn-primary/);
  await panel.getByRole("button", { name: "إضافة صورة استلام", exact: true }).first().click();
  for (let i = 1; i <= 4; i += 1) {
    const photoForm = panel.locator(".action-form");
    await photoForm.locator("input[type=file]").setInputFiles(await cameraPhoto(page, `relay-${i}`));
    await photoForm.getByLabel("طريقة التأكد").selectOption("in_person");
    await photoForm.getByRole("button", { name: "إضافة صورة استلام" }).click();
    await expect(photoForm).toContainText(`(${["الصور", "Photos"][0]}: ${i})`, { timeout: 15_000 });
  }
  await ticketAction(panel, "تسجيل الركن عن الفاليه", async (f) => {
    await f.getByLabel("الموظف المسؤول").selectOption({ label: VALETS.fahad.name });
    await f.getByLabel("المنطقة", { exact: true }).fill("B");
    await f.getByLabel("الموقع داخل المنطقة").fill("8");
    await f.getByLabel("رقم الخطاف").fill(`26${n}`);
    await f.getByLabel("طريقة التأكد").selectOption("radio");
  });
  await expect(panel.locator(".pill").first()).toContainText("مركونة");

  await mainNav(page).getByRole("link", { name: "الفريق" }).click();
  await fahad.getByRole("button", { name: "عاد جهازه للعمل" }).click();
  await expect(fahad).not.toContainText("المشرف يسجّل عنه");
  await expect(page.getByRole("heading", { name: /تسجيل سيارة عن فاليه/ })).toHaveCount(0);
});

test("a customer's help message reaches the team, and Contact customer opens the number on request", async (
  { page, browser }, info) => {
  test.setTimeout(180_000);
  const n = info.project.name === "desktop" ? "7" : "8";
  const guestE164 = `+96650123488${n}`;
  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "majed");
  const ticket = await registerAndPark(valet.page, { guest: `050123488${n}`, vehicle: `HLP ${n}800`, zone: "A",
    spot: "2", hook: `28${n}` });
  await valet.context.close();

  await loginAs(page, "supervisor");
  await customerSays(page, guestE164, "وين سيارتي؟ (تجريبي)");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/وصلت رسالتك إلى فريق الخدمة/, { timeout: 30_000 });

  await mainNav(page).getByRole("link", { name: "التشغيل" }).click();
  const problem = page.getByTestId("problems").locator(".row", { hasText: "عميل يطلب المساعدة" })
    .filter({ hasText: ticket });
  await expect(problem).toBeVisible({ timeout: 15_000 });
  await problem.getByRole("button", { name: "فتح" }).click();
  const panel = page.locator(".ticket-panel");
  await expect(panel.locator(".guest-messages")).toContainText("وين سيارتي؟ (تجريبي)");
  await expect(panel).not.toContainText(guestE164); // masked until opened
  await panel.getByRole("button", { name: "تواصل مع العميل" }).click();
  await expect(panel.locator(".contact-open")).toContainText(guestE164);
  await expect(panel.locator(".contact-open a[href^='tel:']").first()).toHaveAttribute("href", `tel:${guestE164}`);
  await expect(panel.locator(".contact-open")).toContainText(/خارج سلّمها/);
});

test("customer WhatsApp down: staff keep working in the app; nothing stale is sent when it returns", async (
  { page, browser }, info) => {
  test.skip(info.project.name !== "desktop", "one simulated provider; runs once");
  test.setTimeout(420_000);
  await loginAs(page, "supervisor");
  await setSimulatedOutage(page, true);

  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "sara");
  await registerAndPark(valet.page, { guest: "0501230991", vehicle: "OUT 9100", zone: "C", spot: "1", hook: "291" });
  await expect(valet.page.getByText(/رسائل العملاء متأخرة الآن/)).toBeVisible({ timeout: 30_000 });

  await mainNav(page).getByRole("link", { name: "التشغيل" }).click();
  await expect(page.locator(".outage-banner")).toContainText(/رسائل العملاء لا تصل/, { timeout: 30_000 });
  const panel = await openTicket(page, "OUT 9100");
  await ticketAction(panel, "طلب إحضار بمساعدة المشرف", async (f) => {
    await f.getByLabel("السبب", { exact: true }).fill("العميل عند المنصة ولم تصله التذكرة");
  });

  const offer = await taskStep(valet.page, "offer");
  await offer.getByRole("button", { name: "قبول" }).click();
  (await taskStep(valet.page, "bring")).getByRole("button", { name: "السيارة جاهزة" }).click();
  await taskStep(valet.page, "code");

  await ticketAction(panel, "تسليم بمساعدة المشرف", async (f) => {
    await f.getByLabel("طريقة التحقق").selectOption("in_person_check");
    await f.getByLabel("السبب", { exact: true }).fill("واتساب متوقف؛ تحققت من استمارة السيارة");
  });
  await taskStep(valet.page, "none");
  await valet.context.close();

  await setSimulatedOutage(page, false);
  // Messages that failed during the outage are retried with a capped backoff (ADR-0010), so allow a few minutes.
  await customerThread(page, "+966501230991", 240_000);
  const log = page.getByRole("log");
  await expect(log.getByRole("button", { name: "ممتازة" })).toBeVisible(); // the thank-you and rating still arrive
  await expect(log).not.toContainText(/\b\d{6}\b/); // the code for a car already handed over is never sent
  await expect(log).not.toContainText(/تم ركن مركبتك|جارٍ إحضار مركبتك/); // nor any status that is no longer true
});

test("whole-system outage: an admin records the window and reconciles an offline intake and handover", async (
  { page }, info) => {
  test.setTimeout(180_000);
  const desktop = info.project.name === "desktop";
  const [start, end] = desktop ? [-300, -200] : [-190, -100];
  const n = desktop ? "7" : "8";
  await loginAs(page, "admin");
  await page.goto("/outages");
  const sys = page.locator("section").filter({ hasText: "توقف النظام بالكامل" });
  await sys.getByLabel(/بداية التوقف/).fill(riyadh(start));
  await sys.getByLabel(/نهاية التوقف/).fill(riyadh(end));
  const forms = sys.locator("form");
  await forms.nth(0).getByLabel("السبب").fill(`توقف الاستضافة ${n} (تجريبي)`);
  await forms.nth(0).getByRole("button", { name: "تسجيل فترة التوقف" }).click();
  await expect(page.getByText(`توقف الاستضافة ${n} (تجريبي)`)).toBeVisible();

  const rec = forms.nth(1);
  await rec.getByLabel("الموظف").selectOption({ label: VALETS.sara.name });
  await rec.getByLabel("رقم جوال العميل").fill(`05012300${n}7`);
  await rec.getByLabel("اللوحة").fill(`OFL ${n}700`);
  await rec.getByLabel("المنطقة", { exact: true }).fill("A");
  await rec.getByLabel("رقم الخطاف").fill(`9${n}`);
  await rec.getByLabel(/وقت الاستلام الفعلي/).fill(riyadh(start + 10));
  await rec.getByLabel(/وقت الركن الفعلي/).fill(riyadh(start + 15));
  await rec.getByLabel(/الدليل/).fill("سجل الهاتف، السطر ٣");
  await rec.getByLabel("السبب").fill("استلام أثناء التوقف");
  await rec.getByRole("button", { name: "تسجيل الاستلام" }).click();
  await expect(rec.getByText("تم الحفظ.")).toBeVisible();

  const panel = await openTicket(page, `OFL ${n}700`);
  await ticketAction(panel, "تسوية تسليم تم أثناء التوقف", async (f) => {
    await f.getByLabel("وقت التسليم الفعلي").fill(riyadh(start + 60));
    await f.getByLabel("الموظف الذي سلّم").selectOption({ label: VALETS.sara.name });
    await f.getByLabel("من تحقق من الضيف").selectOption({ label: "مشرفة الليلة (تجريبي)" }); // not the recorder
    await f.getByLabel("طريقة التحقق").selectOption("in_person_check");
    await f.getByLabel(/الدليل/).fill("سجل الهاتف، السطر ٩: تطابقت اللوحة والصور");
    await f.getByLabel("السبب", { exact: true }).fill("سُلّمت أثناء التوقف");
  });
  await expect(panel.getByText("سُلّمت", { exact: true })).toBeVisible();
});

test("a customer request made before parking ends waits, and the valet who is parking sees it", async (
  { page, browser }, info) => {
  test.skip(info.project.name !== "desktop", "sizes are explicit");
  test.setTimeout(180_000);
  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "fahad");
  await valet.page.getByRole("link", { name: "تسجيل سيارة" }).click();
  const flow = valet.page.getByTestId("register");
  await enterCar(flow, "0501230555", "EAR 5500");
  await flow.getByRole("button", { name: "إرسال التذكرة" }).click();
  await expect(flow).toHaveAttribute("data-step", "photos");

  await loginAs(page, "supervisor");
  await customerRequests(page, "+966501230555");
  await expect(flow.getByText("العميل طلب السيارة")).toBeVisible({ timeout: 15_000 });
  for (let i = 1; i <= 4; i += 1) {
    await flow.locator("input[type=file]").setInputFiles(await cameraPhoto(valet.page, `early-${i}`));
    await expect(flow.locator(".photo-count")).toContainText(`${i}`);
  }
  await flow.getByRole("button", { name: "بدء الركن" }).click();
  await flow.locator(".choice", { hasText: "A" }).click();
  await flow.getByLabel("رقم خطاف المفتاح").fill("255");
  await flow.getByRole("button", { name: "تم الركن" }).click();
  await valet.page.getByTestId("parked-done").getByRole("button", { name: "مهامي" }).click();
  // The kept request is now dispatched; the valet who parked it gets the offer.
  const offer = await taskStep(valet.page, "offer");
  await expect(offer).toContainText("EAR 5500");
  await offer.getByRole("button", { name: "قبول" }).click();
  (await taskStep(valet.page, "bring")).getByRole("button", { name: "السيارة جاهزة" }).click();
  await taskStep(valet.page, "code");
  const panel = await openTicket(page, "EAR 5500");
  await ticketAction(panel, "تسليم بمساعدة المشرف", async (f) => {
    await f.getByLabel("طريقة التحقق").selectOption("in_person_check");
    await f.getByLabel("السبب", { exact: true }).fill("إنهاء الاختبار (تجريبي)");
  });
  await taskStep(valet.page, "none");
  await valet.context.close();
});
