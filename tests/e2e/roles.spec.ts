import { expect, test } from "@playwright/test";

import { PHONE, device, loginAs, loginValet, mainNav, noHorizontalOverflow } from "./helpers";

// Three roles (ADR-0011): what each one sees, and what the server refuses whatever the screen shows.

test("a valet has My work and Register car only; console pages and APIs are refused", async ({ browser }, info) => {
  test.skip(info.project.name !== "desktop", "sizes are explicit");
  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "majed");
  await expect(mainNav(valet.page).getByRole("link")).toHaveText([/مهامي/, /تسجيل سيارة/]);
  for (const path of ["/operations", "/team", "/dashboard", "/settings", "/dev/simulator"]) {
    await valet.page.goto(path);
    await valet.page.waitForURL(/\/work$/); // the valet app has no such page
  }
  for (const url of ["/api/events/", "/api/staff", "/api/dashboard", "/api/outages", "/api/dev/sim/phones"]) {
    expect((await valet.page.request.get(url)).status(), url).toBe(403);
  }
  await valet.context.close();
});

test("a supervisor has Operations and Team; admin pages are refused", async ({ page }) => {
  await loginAs(page, "supervisor");
  await expect(mainNav(page).getByRole("link")).toHaveText(["التشغيل", "الفريق"]);
  await expect(page).toHaveURL(/\/events\/\d+$/); // the open operation opens directly
  for (const path of ["/dashboard", "/settings", "/settings/delivery", "/carryover"]) {
    await page.goto(path);
    await expect(page.getByTestId("forbidden")).toBeVisible();
  }
  for (const url of ["/api/staff", "/api/dashboard", "/api/config", "/api/integrations/whatsapp"]) {
    expect((await page.request.get(url)).status(), url).toBe(403);
  }
  expect((await page.request.get("/api/valet/work")).status()).toBe(403); // nor can they act as a valet
  await noHorizontalOverflow(page, "supervisor");
});

test("an admin has Dashboard, Operations, Team and Settings, with technical tools under Advanced", async ({ page }) => {
  await loginAs(page, "admin");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(mainNav(page).getByRole("link")).toHaveText(["لوحة المتابعة", "التشغيل", "الفريق", "الإعدادات"]);
  await expect(page.getByTestId("request-to-ready-def")).toContainText(/من طلب العميل حتى يبلّغ الفاليه/);
  await mainNav(page).getByRole("link", { name: "الإعدادات" }).click();
  const tabs = page.getByRole("navigation", { name: "الإعدادات" });
  await expect(tabs).toContainText("متقدم");
  await tabs.getByRole("link", { name: "حالة واتساب" }).click();
  await expect(page.locator("main")).not.toContainText(/token|secret=/i);
  await tabs.getByRole("link", { name: "تسليم الرسائل" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("تسليم الرسائل");
  await noHorizontalOverflow(page, "admin settings");
});

test("an admin adds a valet, who sets their own password with the one-time code and starts in the app", async (
  { page, browser }, info) => {
  test.setTimeout(150_000);
  const n = info.project.name === "desktop" ? "1" : "2";
  const mobile = `055990000${n}`;
  await loginAs(page, "admin");
  await mainNav(page).getByRole("link", { name: "الفريق" }).click();
  const add = page.getByTestId("add-person");
  await add.locator("summary").click();
  await add.getByLabel("الاسم الكامل").fill(`نواف ${n} (تجريبي)`);
  await add.getByLabel("رقم الجوال").fill(mobile);
  await add.getByLabel("أضِفه إلى فريق هذه العملية").check();
  await add.getByRole("button", { name: "إضافة" }).click();
  const row = page.locator(".staff-row", { hasText: `نواف ${n} (تجريبي)` });
  await expect(row).toContainText("لم يُعِدّ كلمة المرور");
  await expect(row).toContainText("ضمن الفريق");
  await row.getByRole("button", { name: "رمز الإعداد" }).click();
  const code = (await row.getByTestId("setup-code").locator(".setup-code").textContent())!.trim();
  expect(code).toMatch(/^\d{8}$/);

  const person = await device(browser, PHONE);
  await person.page.goto("/login");
  await person.page.getByRole("button", { name: "أول دخول أو نسيت كلمة المرور؟" }).click();
  await person.page.getByLabel("رقم الجوال أو اسم المستخدم").fill(mobile);
  await person.page.getByLabel(/رمز الإعداد/).fill(code);
  await person.page.getByLabel("كلمة المرور الجديدة").fill("short");
  await person.page.getByRole("button", { name: "حفظ كلمة المرور" }).click();
  await expect(person.page.getByRole("alert")).toContainText(/قصيرة أو شائعة/);
  await person.page.getByLabel("كلمة المرور الجديدة").fill(`harbour-${n}-lamp`);
  await person.page.getByRole("button", { name: "حفظ كلمة المرور" }).click();
  await expect(person.page.getByText("تم حفظ كلمة المرور. سجّل الدخول الآن.")).toBeVisible();
  await person.page.getByLabel(/^كلمة المرور$/).fill(`harbour-${n}-lamp`);
  await person.page.getByRole("button", { name: /^دخول$/ }).click();
  await person.page.waitForURL(/\/work$/);
  await expect(person.page.getByTestId("no-shift")).toContainText("ليلة العرض (تجريبي)"); // on the team, no shift yet
  await person.context.close();

  await page.reload();
  await expect(row).toContainText("يستطيع الدخول");

  // Made an admin, the person's sign-in is no longer reset from the app (ADR-0012): no setup code, the note instead.
  await row.getByLabel(`تغيير الدور: نواف ${n} (تجريبي)`).selectOption("ADMIN");
  await row.getByRole("button", { name: "تغيير الدور" }).click();
  await expect(row).toContainText("مسؤول النظام");
  await expect(row.getByRole("button", { name: "رمز الإعداد" })).toHaveCount(0);
  await expect(row.getByTestId(/^admin-access-/)).toContainText("يجريه المسؤول التقني على الخادم بشخصين");
  await expect(row).toContainText("بلا تحقق ثنائي");
});
