import { expect, test } from "@playwright/test";
import { VALETS, loginAs, mainNav, openSimulator, parkViaSimulator, say, tapButton, thread } from "./helpers";

// Whole journey through the development simulator, on desktop and at 360 px. Every message here is SIMULATED.
test("registration to verified delivery via the simulator", async ({ page }, info) => {
  test.setTimeout(240_000);
  const n = info.project.name === "desktop" ? "1" : "2";
  const guest = `+9665012345${n}7`;
  await loginAs(page, "supervisor");
  const eventPath = new URL(page.url()).pathname;
  const delivered = Number(await page.getByTestId("count-DELIVERED").locator(".count-n").textContent());

  await parkViaSimulator(page, { valet: VALETS["ماجد (تجريبي)"], guest: `05012345${n}7`,
    plate: `ABC ${n}234 كامري بيضاء`, location: "A 12", hook: `1${n}` });
  await thread(page, guest);
  await page.getByRole("log").getByRole("button", { name: "اطلب سيارتي" }).last().click(); // on the ticket message

  // The dispatcher chooses the valet; read its choice from the live view rather than assuming it.
  await page.goto(eventPath);
  const row = page.getByRole("region", { name: /الطلبات المفتوحة/ }).getByRole("button", { name: new RegExp(`ABC ${n}234`) });
  await expect(row).toContainText(/\(تجريبي\)/, { timeout: 30_000 });
  const rowText = (await row.textContent()) ?? "";
  const offered = Object.keys(VALETS).find((name) => rowText.includes(name))!;

  await openSimulator(page);
  await thread(page, VALETS[offered]);
  await tapButton(page, "قبول");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/تم إسنادها إليك/);
  await tapButton(page, "السيارة جاهزة");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/رمز الاستلام/);
  await thread(page, guest);
  const ready = page.getByRole("log").locator(".bubble-out").filter({ hasText: /رمز الاستلام \d{6}/ }).last();
  await expect(ready).toBeVisible();
  const code = ((await ready.textContent()) ?? "").match(/\b\d{6}\b/)?.[0];
  expect(code).toBeTruthy();
  await thread(page, VALETS[offered]);
  await say(page, code!, /الرمز صحيح/);
  await tapButton(page, "تم التسليم");
  await expect(page.getByRole("log")).toContainText(/تم التسليم لتذكرة/);

  await mainNav(page).getByRole("link", { name: /التشغيل المباشر/ }).click();
  await expect(page.getByTestId("count-DELIVERED").locator(".count-n")).toHaveText(String(delivered + 1));
});
