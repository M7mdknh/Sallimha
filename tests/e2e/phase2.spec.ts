import { expect, type Page, test } from "@playwright/test";
import { type Account, loginAs, noHorizontalOverflow } from "./helpers";

// Phase 2: role-based navigation (AT-59), exception handling from the console, and design QA (AT-53).
// Every WhatsApp message here goes through the development simulator and is SIMULATED.

const NAV = {
  live: "التشغيل المباشر", incidents: "البلاغات", events: "المناسبات", staff: "الموظفون",
  carryover: "المركبات المتبقية", settings: "الإعدادات", operations: "التشغيل الفني", integrations: "التكاملات",
  simulator: "المحاكي",
} as const;
type Link = keyof typeof NAV;

const ROLES: Record<Account, { links: Link[]; forbidden?: string }> = {
  supervisor: { links: ["live", "incidents", "simulator"], forbidden: "/staff" },
  manager: { links: ["live", "incidents", "events", "staff", "carryover", "simulator"], forbidden: "/settings" },
  admin: { links: ["live", "incidents", "events", "staff", "carryover", "settings", "operations", "simulator"],
    forbidden: "/integrations" },
  owner: { links: Object.keys(NAV) as Link[] },
};

const nav = (page: Page) => page.getByRole("navigation", { name: /التنقل الرئيسي|Main navigation/ });

async function expectReady(page: Page) {
  await expect(page.locator("[aria-busy='true']")).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
}

for (const [account, spec] of Object.entries(ROLES) as [Account, (typeof ROLES)[Account]][]) {
  test(`${account} sees only the links for their role, and the server refuses the rest`, async ({ page }) => {
    await loginAs(page, account);
    for (const link of Object.keys(NAV) as Link[]) {
      const locator = nav(page).getByRole("link", { name: NAV[link], exact: true });
      if (spec.links.includes(link)) await expect(locator).toBeVisible();
      else await expect(locator).toHaveCount(0);
    }
    if (spec.forbidden) {
      await page.goto(spec.forbidden);
      await expect(page.getByTestId("forbidden")).toBeVisible();
      await expect(page.getByRole("button", { name: /إعادة المحاولة/ })).toHaveCount(0); // no futile retry
    } else {
      await page.goto("/integrations");
      await expect(page.getByText(/محاكاة — لا تصل أي رسالة إلى هاتف حقيقي/)).toBeVisible();
      await expect(page.locator("main")).not.toContainText(/token|secret=/i);
    }
    await noHorizontalOverflow(page);
  });
}

async function simulator(page: Page) {
  await nav(page).getByRole("link", { name: NAV.simulator, exact: true }).click();
  await expect(page.getByText(/محاكاة — لا تصل أي رسالة إلى هاتف حقيقي/)).toBeVisible();
}

async function thread(page: Page, phone: string) {
  await page.getByRole("button", { name: new RegExp(phone.replace("+", "\\+")) }).click();
  await expect(page.getByRole("heading", { level: 2, name: phone })).toBeVisible();
}

async function say(page: Page, text: string, reply: RegExp) {
  await page.getByLabel(/رسالة|Message/).fill(text);
  await page.getByRole("button", { name: /إرسال|Send/ }).click();
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(reply);
}

async function tap(page: Page, title: string) {
  const button = page.getByRole("log").getByRole("button", { name: title }).last();
  await expect(button).toBeVisible();
  await button.click();
}

async function action(page: Page, label: string, fill: (form: ReturnType<Page["locator"]>) => Promise<void>) {
  const panel = page.locator(".ticket-panel");
  await panel.getByRole("button", { name: label, exact: true }).first().click();
  const form = panel.locator(".action-form");
  await fill(form);
  await form.getByRole("button", { name: label, exact: true }).click();
  await expect(form).toHaveCount(0);
}

test("supervisor finds a parked car, places and clears a hold, and opens an incident", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the exception flow runs once, on desktop");
  test.setTimeout(240_000);
  await loginAs(page, "supervisor");
  const eventPath = new URL(page.url()).pathname;

  await simulator(page);
  await thread(page, "+966550000103");
  await say(page, "مركبة جديدة", /أرسل رقم جوال الضيف/);
  await say(page, "0501234599", /هل الرقم/);
  await tap(page, "تأكيد الرقم");
  await tap(page, "نعم، استلمها");
  await say(page, "PLT 7788 لكزس رمادية", /صور للمركبة/);
  for (let i = 1; i <= 4; i += 1) {
    await page.getByRole("button", { name: /صورة|Photo/ }).click();
    await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(i < 4 ? `${i} من` : /اكتملت الصور/);
  }
  await tap(page, "بدء الركن");
  await say(page, "B 7", /خطاف المفتاح/);
  await say(page, "77", /تم الركن/);

  await page.goto(eventPath);
  const finder = page.getByRole("search");
  await finder.getByLabel(/رقم التذكرة أو جزء من اللوحة/).fill("PLT");
  await finder.getByRole("button", { name: "بحث" }).click();
  await page.getByRole("button", { name: /PLT 7788/ }).click();
  const panel = page.locator(".ticket-panel");
  await expect(panel).toContainText("77");

  await action(page, "إيقاف سلامة", async (form) => {
    await form.getByLabel("السبب").fill("المفتاح يحتاج تحققًا");
  });
  await expect(panel.getByRole("list", { name: "إيقافات السلامة" })).toContainText("المفتاح يحتاج تحققًا");

  await action(page, "رفع الإيقاف", async (form) => {
    await form.getByLabel("الإيقاف").selectOption({ label: "المفتاح يحتاج تحققًا" });
    await form.getByLabel("السبب").fill("تم التحقق من المفتاح");
  });
  await expect(panel.getByRole("list", { name: "إيقافات السلامة" })).toHaveCount(0);

  await action(page, "فتح بلاغ", async (form) => {
    await form.getByLabel("التصنيف").selectOption("damage");
    await form.getByLabel("الوصف").fill("خدش في الباب الخلفي (تجريبي)");
  });
  await panel.getByRole("list", { name: "البلاغات" }).getByRole("link").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("البلاغات");
  await expect(page.locator(".ticket-panel")).toContainText("خدش في الباب الخلفي");
  await page.locator(".ticket-panel").getByLabel("ملاحظة").fill("طُلبت صور إضافية");
  await page.locator(".ticket-panel").getByRole("button", { name: "إضافة ملاحظة" }).click();
  await expect(page.locator(".notes")).toContainText("طُلبت صور إضافية");
  // Supervisors annotate; only a manager resolves (server-enforced; the control is not offered).
  await expect(page.getByRole("button", { name: "إغلاق البلاغ" })).toHaveCount(0);

  // End of night: the car was not collected. The supervisor proposes; a manager approves (next test).
  await page.goto(eventPath);
  await page.getByRole("search").getByLabel(/رقم التذكرة أو جزء من اللوحة/).fill("PLT");
  await page.getByRole("search").getByRole("button", { name: "بحث" }).click();
  await page.getByRole("button", { name: /PLT 7788/ }).click();
  await action(page, "اقتراح غير مُستلمة", async (form) => {
    await form.getByLabel("الجهة المسؤولة").fill("أمن المكان (تجريبي)");
    await form.getByLabel("الخطة").fill("تبقى المركبة حتى الصباح ويُتواصل مع الضيف");
  });
  await expect(page.locator(".ticket-panel").getByRole("button", { name: "اعتماد غير مُستلمة" })).toHaveCount(0);
});

test("manager resolves the incident, approves the unclaimed car and releases its key", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "continues the desktop exception flow");
  test.setTimeout(120_000);
  await loginAs(page, "manager");
  await nav(page).getByRole("link", { name: NAV.incidents, exact: true }).click();
  await page.getByRole("button", { name: /ضرر/ }).first().click();
  await page.locator(".ticket-panel").getByLabel("النتيجة").fill("خدش سابق موثّق في صور الاستلام");
  await page.locator(".ticket-panel").getByRole("button", { name: "إغلاق البلاغ" }).click();
  await expect(page.locator(".ticket-panel")).toContainText("خدش سابق موثّق");

  await nav(page).getByRole("link", { name: NAV.carryover, exact: true }).click();
  await page.locator(".rows .row-button").first().click();
  const panel = page.locator(".ticket-panel");
  await expect(panel).toContainText("77");
  await action(page, "اعتماد غير مُستلمة", async () => {});
  await expect(panel.getByText("غير مُستلمة", { exact: true })).toBeVisible();
  await action(page, "تحرير المفتاح والمركبة", async (form) => {
    await form.getByLabel("الطريقة").selectOption("collected_verified");
    await form.getByLabel("ملاحظة").fill("استلمها المالك بعد التحقق من الهوية حضوريًا");
  });
  await nav(page).getByRole("link", { name: NAV.carryover, exact: true }).click();
  await expect(page.getByText("لا توجد مركبات متبقية. المفاتيح كلها محررة.")).toBeVisible();
});

// Design QA (AT-53): every management page at phone, tablet, 200% zoom (640 CSS px) and desktop widths,
// in Arabic and English, without sideways scrolling; keyboard focus is visible.
test("management pages hold their layout at every width in both languages", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "widths are set explicitly; runs once");
  test.setTimeout(240_000);
  await loginAs(page, "admin");
  const eventId = new URL(page.url()).pathname.split("/")[2];
  const pages = ["/manage", "/staff", "/carryover", "/settings", "/operations", `/events/${eventId}/report`,
    `/events/${eventId}/incidents`, `/events/${eventId}`];
  for (const lang of ["ar", "en"]) {
    if (lang === "en") await page.getByRole("button", { name: "English" }).click();
    for (const width of [1280, 768, 640, 360]) {
      await page.setViewportSize({ width, height: 900 });
      for (const path of pages) {
        await page.goto(path);
        await expectReady(page);
        await expect(page.locator("html")).toHaveAttribute("dir", lang === "ar" ? "rtl" : "ltr");
        await noHorizontalOverflow(page, lang);
      }
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/settings");
  await expectReady(page);
  await page.locator("main input").first().focus();
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement as Element);
    return { style: style.outlineStyle, width: parseFloat(style.outlineWidth) };
  });
  expect(outline.style).not.toBe("none");
  expect(outline.width).toBeGreaterThanOrEqual(2);
});

test("manager creates and closes an event, and sees the report without guest phone export", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "runs once");
  await loginAs(page, "manager");
  const eventId = new URL(page.url()).pathname.split("/")[2];
  await nav(page).getByRole("link", { name: NAV.events, exact: true }).click();
  await page.getByText("مناسبة جديدة").click();
  await page.getByLabel("المكان").selectOption({ index: 1 });
  await page.getByLabel("الاسم").fill("ليلة اختبار الإغلاق (تجريبي)");
  await page.getByLabel("موعد البدء").fill("2026-12-01T19:00");
  await page.getByRole("button", { name: "إنشاء" }).click();
  const row = page.locator("li").filter({ hasText: "ليلة اختبار الإغلاق" });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "إغلاق المناسبة" }).click();
  await row.getByRole("button", { name: "تأكيد" }).click();
  await expect(row.getByText("مغلقة")).toBeVisible();

  await page.goto(`/events/${eventId}/report`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("تقرير المناسبة");
  await expect(page.getByRole("link", { name: /تصدير التذاكر/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /أرقام الضيوف/ })).toHaveCount(0);
  const csv = await page.request.get(`/api/events/${eventId}/export/tickets.csv`);
  expect(csv.headers()["content-type"]).toContain("text/csv");
  expect(await csv.text()).not.toMatch(/\+9665/);
});
