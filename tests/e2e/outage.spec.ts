import { expect, type Page, test } from "@playwright/test";
import { VALETS, findTicket, loginAs, mainNav, parkViaSimulator, thread } from "./helpers";

// ADR-0008. Every WhatsApp message here is SIMULATED; the "outage" is declared, not a real provider failure.

/** Venue wall-clock time (Asia/Riyadh) `minutes` from now, as a datetime-local value. */
function riyadh(minutes: number) {
  const parts = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Riyadh", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(Date.now() + minutes * 60_000));
  return parts.replace(" ", "T");
}

async function panelAction(page: Page, label: string, fill: (form: ReturnType<Page["locator"]>) => Promise<void>) {
  const panel = page.locator(".ticket-panel");
  await panel.getByRole("button", { name: label, exact: true }).first().click();
  const form = panel.locator(".action-form");
  await fill(form);
  await form.getByRole("button", { name: label, exact: true }).click();
  await expect(form).toHaveCount(0);
}

test("WhatsApp outage: relayed acceptance and ready, assisted handover, intake on a valet's behalf", async (
  { page }, info) => {
  test.setTimeout(240_000);
  const n = info.project.name === "desktop" ? "3" : "4";
  const guest = `05012300${n}5`;
  await loginAs(page, "supervisor");
  const eventPath = new URL(page.url()).pathname;
  await parkViaSimulator(page, { valet: VALETS["ماجد (تجريبي)"], guest, plate: `OUT ${n}500 سوناتا`,
    location: "A 5", hook: `6${n}` });
  await thread(page, `+9665012300${n}5`);
  await page.getByRole("log").getByRole("button", { name: "اطلب سيارتي" }).last().click(); // on the ticket message

  await mainNav(page).getByRole("link", { name: "الأعطال", exact: true }).click();
  await page.getByLabel("السبب").fill("الرسائل لا تصل (تجريبي)");
  await page.getByRole("button", { name: "إعلان عطل واتساب" }).click();
  await expect(page.getByText("عطل واتساب معلن", { exact: true })).toBeVisible();

  await findTicket(page, eventPath, `OUT ${n}500`, new RegExp(`OUT ${n}500`));
  await expect(page.getByRole("status").filter({ hasText: /عطل واتساب معلن/ })).toBeVisible();
  const panel = page.locator(".ticket-panel");
  await expect(panel.getByText(/العرض لدى/)).toBeVisible({ timeout: 20_000 });
  await panelAction(page, "تسجيل قبول الموظف (مُرحَّل)", (f) => f.getByLabel("طريقة التأكد").selectOption("radio"));
  await panelAction(page, "تسجيل جاهزية السيارة (مُرحَّل)",
    (f) => f.getByLabel("طريقة التأكد").selectOption("in_person"));
  await panelAction(page, "تسليم بمساعدة المشرف", async (f) => {
    await f.getByLabel("طريقة التحقق").selectOption("in_person_check");
    await f.getByLabel("السبب", { exact: true }).fill("تطابقت الصور واللوحة مع الضيف");
  });
  await expect(panel.getByText("سُلّمت", { exact: true })).toBeVisible();

  await mainNav(page).getByRole("link", { name: "الأعطال", exact: true }).click();
  const intake = page.locator("section").filter({ hasText: "استلام مركبة نيابة عن موظف" });
  await intake.getByLabel("الموظف").selectOption({ index: 1 });
  await intake.getByLabel("الجوال").fill(`05012300${n}6`);
  await intake.getByLabel("اللوحة").fill(`INT ${n}600`);
  await intake.getByLabel("المنطقة", { exact: true }).fill("B");
  await intake.getByLabel("رقم الخطاف").fill(`7${n}`);
  await intake.getByLabel("طريقة التأكد").selectOption("in_person");
  await intake.getByLabel("السبب").fill("واتساب متوقف");
  await intake.getByRole("button", { name: "تسجيل الاستلام" }).click();
  await expect(intake.getByText("تم الحفظ.")).toBeVisible();
  await findTicket(page, eventPath, `INT ${n}600`, new RegExp(`INT ${n}600`));
  await expect(panel.getByText("مركونة", { exact: true })).toBeVisible();

  await mainNav(page).getByRole("link", { name: "الأعطال", exact: true }).click();
  await page.getByLabel("سبب الإنهاء").fill("عادت الرسائل");
  await page.getByRole("button", { name: "إنهاء العطل" }).click();
  await expect(page.getByRole("button", { name: "إعلان عطل واتساب" })).toBeVisible();
});

test("whole-system outage: a manager records the window and reconciles an offline intake and handover", async (
  { page }, info) => {
  test.setTimeout(180_000);
  const desktop = info.project.name === "desktop";
  const [start, end] = desktop ? [-300, -200] : [-190, -100];
  const n = desktop ? "7" : "8";
  await loginAs(page, "manager");
  const eventPath = new URL(page.url()).pathname;
  await mainNav(page).getByRole("link", { name: "الأعطال", exact: true }).click();
  const sys = page.locator("section").filter({ hasText: "توقف النظام بالكامل" });
  await sys.getByLabel(/بداية التوقف/).fill(riyadh(start));
  await sys.getByLabel(/نهاية التوقف/).fill(riyadh(end));
  const forms = sys.locator("form");
  await forms.nth(0).getByLabel("السبب").fill(`توقف الاستضافة ${n} (تجريبي)`);
  await forms.nth(0).getByRole("button", { name: "تسجيل فترة التوقف" }).click();
  await expect(page.getByText(`توقف الاستضافة ${n} (تجريبي)`)).toBeVisible();

  const rec = forms.nth(1);
  await rec.getByLabel("الموظف").selectOption({ index: 1 });
  await rec.getByLabel("الجوال").fill(`05012300${n}7`);
  await rec.getByLabel("اللوحة").fill(`OFL ${n}700`);
  await rec.getByLabel("المنطقة", { exact: true }).fill("A");
  await rec.getByLabel("رقم الخطاف").fill(`9${n}`);
  await rec.getByLabel(/وقت الاستلام الفعلي/).fill(riyadh(start + 10));
  await rec.getByLabel(/وقت الركن الفعلي/).fill(riyadh(start + 15));
  await rec.getByLabel(/الدليل/).fill("سجل الهاتف، السطر ٣");
  await rec.getByLabel("السبب").fill("استلام أثناء التوقف");
  await rec.getByRole("button", { name: "تسجيل الاستلام" }).click();
  await expect(rec.getByText("تم الحفظ.")).toBeVisible();

  await findTicket(page, eventPath, `OFL ${n}700`, new RegExp(`OFL ${n}700`));
  const panel = page.locator(".ticket-panel");
  await panelAction(page, "تسوية تسليم تم أثناء التوقف", async (f) => {
    await f.getByLabel("وقت التسليم الفعلي").fill(riyadh(start + 60));
    await f.getByLabel("الموظف الذي سلّم").selectOption({ index: 1 });
    await f.getByLabel("من تحقق من الضيف").selectOption({ label: "مشرفة الليلة (تجريبي)" }); // not the recorder
    await f.getByLabel("طريقة التحقق").selectOption("in_person_check");
    await f.getByLabel(/الدليل/).fill("سجل الهاتف، السطر ٩: تطابقت اللوحة والصور");
    await f.getByLabel("السبب", { exact: true }).fill("سُلّمت أثناء التوقف");
  });
  await expect(panel.getByText("سُلّمت", { exact: true })).toBeVisible();
  await expect(panel.getByRole("button", { name: "تسوية تسليم تم أثناء التوقف" })).toHaveCount(0);
});
