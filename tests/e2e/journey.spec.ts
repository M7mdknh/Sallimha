import { expect, type Page, test } from "@playwright/test";
import { login } from "./helpers";

// Whole journey through the development simulator. Every message here is SIMULATED.
const VALET = "+966550000101";

async function openThread(page: Page, phone: string) {
  await page.getByRole("button", { name: new RegExp(phone.replace("+", "\\+")) }).click();
  await expect(page.getByRole("heading", { level: 2, name: phone })).toBeVisible();
}

async function send(page: Page, text: string, expectReply?: RegExp) {
  await page.getByLabel(/رسالة|Message/).fill(text);
  await page.getByRole("button", { name: /إرسال|Send/ }).click();
  if (expectReply) await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(expectReply);
}

async function tap(page: Page, title: string | RegExp) {
  const button = page.getByRole("log").getByRole("button", { name: title }).last();
  await expect(button).toBeVisible();
  await button.click();
}

test("registration to verified delivery via the simulator", async ({ page }, info) => {
  test.skip(info.project.name !== "desktop", "the full journey runs once, on desktop");
  test.setTimeout(240_000);
  await login(page);
  await page.getByRole("link", { name: /المحاكي/ }).click();
  await expect(page.getByText(/محاكاة — لا تصل أي رسالة إلى هاتف حقيقي/)).toBeVisible();
  await openThread(page, VALET);
  await send(page, "مركبة جديدة", /أرسل رقم جوال الضيف/);
  await send(page, "0501234567", /هل الرقم/);
  await tap(page, "تأكيد الرقم");
  await tap(page, "نعم، استلمها");
  await send(page, "ABC 1234 كامري بيضاء", /صور للمركبة/);
  for (let i = 1; i <= 4; i += 1) {
    await page.getByRole("button", { name: /صورة|Photo/ }).click();
    await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(i < 4 ? `${i} من` : /اكتملت الصور/);
  }
  await tap(page, "بدء الركن");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/أين ركنت/);
  await send(page, "A 12", /خطاف المفتاح/);
  await send(page, "15", /تم الركن/);

  await openThread(page, "+966501234567");
  await tap(page, "اطلب سيارتي");
  await openThread(page, VALET);
  await tap(page, "قبول");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/تم إسنادها إليك/);
  await tap(page, "السيارة جاهزة");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/رمز الاستلام/);
  await openThread(page, "+966501234567");
  const ready = page.getByRole("log").locator(".bubble-out").filter({ hasText: /رمز الاستلام \d{6}/ }).last();
  await expect(ready).toBeVisible();
  const readyText = await ready.textContent();
  const code = readyText?.match(/\b\d{6}\b/)?.[0];
  expect(code).toBeTruthy();
  await openThread(page, VALET);
  await send(page, code!, /الرمز صحيح/);
  await tap(page, "تم التسليم");
  await expect(page.getByRole("log")).toContainText(/تم التسليم لتذكرة/);

  await page.getByRole("link", { name: /التشغيل المباشر/ }).click();
  await expect(page.getByTestId("count-DELIVERED")).toContainText("1");
});
