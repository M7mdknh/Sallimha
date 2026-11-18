import { expect, test } from "@playwright/test";

import {
  cameraPhoto, customerCode, customerRequests, device, enterCar, loginAs, loginValet, mainNav, noHorizontalOverflow, openTicket, PHONE, registerAndPark, SMALL_PHONE, taskStep, VALETS,
} from "./helpers";

// The valet app (ADR-0011): the valet works on a phone; the customer's WhatsApp is the development simulator
// (every customer message here is SIMULATED). The supervisor's page plays the customer through the simulator.

test("a valet registers, parks and delivers a car in the app; the customer is served on WhatsApp", async (
  { page, browser }, info) => {
  test.setTimeout(240_000);
  const desktop = info.project.name === "desktop";
  const n = desktop ? "1" : "2";
  const guest = `05012345${n}7`;
  const guestE164 = `+9665012345${n}7`;
  const valet = await device(browser, desktop ? PHONE : SMALL_PHONE);
  await loginValet(valet.page, "majed");
  await taskStep(valet.page, "none");
  await noHorizontalOverflow(valet.page, "my work");

  const ticket = await registerAndPark(valet.page, { guest, vehicle: `ABC ${n}234 كامري بيضاء`, zone: "A",
    spot: "12", hook: `1${n}1` });
  await taskStep(valet.page, "none");
  await expect(valet.page.locator(".recent")).toContainText(ticket);

  await loginAs(page, "supervisor");
  await customerRequests(page, guestE164);

  // The dispatcher offers it to the valet who parked it; the app shows the offer with a countdown.
  const offer = await taskStep(valet.page, "offer");
  await expect(offer).toContainText(ticket);
  await expect(offer.getByRole("timer")).toBeVisible();
  await expect(offer).toContainText("A · 12");
  await expect(offer).toContainText(`1${n}1`);
  await offer.getByRole("button", { name: "قبول" }).click();
  const bring = await taskStep(valet.page, "bring");
  await bring.getByRole("button", { name: "السيارة جاهزة" }).click();
  const codeStep = await taskStep(valet.page, "code");

  const code = await customerCode(page, guestE164);
  await codeStep.getByLabel(/رمز الاستلام/).fill(code);
  await codeStep.getByRole("button", { name: "تحقق" }).click();
  const deliver = await taskStep(valet.page, "deliver");
  await deliver.getByRole("button", { name: "تم التسليم" }).click();
  await taskStep(valet.page, "none");
  await expect(valet.page.locator(".recent").locator("li").first()).toContainText(/سُلّمت/);

  // The customer gets the rating buttons; nothing was ever sent to the valet's WhatsApp.
  await expect(page.getByRole("log").getByRole("button", { name: "ممتازة" }).last()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("button", { name: new RegExp(VALETS.majed.phone.replace("+", "\\+")) })).toHaveCount(0);
  await valet.context.close();
});

test("double taps and a second tab never repeat a registration, and the flow resumes where the server is", async (
  { browser }, info) => {
  test.skip(info.project.name !== "desktop", "one valet, two tabs; sizes are explicit");
  test.setTimeout(180_000);
  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "sara");
  await valet.page.getByRole("link", { name: "تسجيل سيارة" }).click();
  const flow = valet.page.getByTestId("register");
  await enterCar(flow, "0501230077", "DUP 7007");
  // Moving away and back keeps what was typed (in memory only).
  await valet.page.getByRole("link", { name: "مهامي" }).click();
  await valet.page.getByRole("link", { name: "تسجيل سيارة" }).click();
  await expect(flow.getByLabel("رقم جوال العميل")).toHaveValue("0501230077");
  expect(await valet.page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage })))
    .not.toContain("0501230077"); // never written to the device
  await flow.getByRole("button", { name: "إرسال التذكرة" }).dblclick();
  await expect(flow).toHaveAttribute("data-step", "photos");
  const number = (await flow.locator(".ticket-no").textContent())!.trim();

  const second = await valet.context.newPage();
  await second.goto("/register");
  await expect(second.getByTestId("register")).toHaveAttribute("data-step", "photos");
  await expect(second.getByTestId("register").locator(".ticket-no")).toHaveText(number); // the same, single ticket

  for (let i = 1; i <= 4; i += 1) {
    await second.getByTestId("register").locator("input[type=file]").setInputFiles(await cameraPhoto(second, `dup-${i}`));
    await expect(second.getByTestId("register").locator(".photo-count")).toContainText(`${i}`);
  }
  await expect(flow).toHaveAttribute("data-step", "start_parking", { timeout: 15_000 }); // the first tab follows
  await flow.getByRole("button", { name: "بدء الركن" }).click();
  await flow.locator(".choice", { hasText: "B" }).click();
  await flow.getByLabel("الموقف").fill("7");
  await flow.getByLabel("رقم خطاف المفتاح").fill("177");
  await flow.getByRole("button", { name: "تم الركن" }).dblclick();
  await expect(valet.page.getByTestId("parked-done")).toBeVisible();
  await second.goto("/work");
  await taskStep(second, "none");
  await expect(second.locator(".recent li", { hasText: number })).toHaveCount(1); // parked once, not twice
  await valet.context.close();
});

test("a lost connection is shown at once, nothing is pretended, and the app recovers by itself", async (
  { browser }, info) => {
  test.skip(info.project.name !== "desktop", "sizes are explicit");
  const valet = await device(browser, PHONE);
  await loginValet(valet.page, "fahad");
  await valet.context.route("**/api/valet/**", (route) => route.abort());
  await valet.page.getByRole("button", { name: /استراحة/ }).click();
  await expect(valet.page.locator(".offline-banner")).toBeVisible({ timeout: 15_000 });
  await expect(valet.page.getByTestId("connection")).toContainText("لا يوجد اتصال");
  await expect(valet.page.getByRole("button", { name: /متاح/ })).toHaveAttribute("aria-pressed", "true"); // unchanged
  await valet.context.unroute("**/api/valet/**");
  await expect(valet.page.getByTestId("connection")).toContainText("متصل", { timeout: 15_000 });
  await expect(valet.page.locator(".offline-banner")).toHaveCount(0);
  await valet.context.close();
});

test("a supervisor's move is offered, accepted and recorded in the valet's app", async ({ page, browser }, info) => {
  test.setTimeout(240_000);
  const desktop = info.project.name === "desktop";
  const n = desktop ? "3" : "4";
  const parker = await device(browser, PHONE);
  await loginValet(parker.page, "sara");
  await registerAndPark(parker.page, { guest: `05012300${n}1`, vehicle: `MOV ${n}100 لكزس`, zone: "B", spot: "4",
    hook: `2${n}1` });
  await parker.context.close();

  await loginAs(page, "supervisor");
  const panel = await openTicket(page, `MOV ${n}100`);
  await panel.locator(".more-actions > summary").click();
  await panel.getByRole("button", { name: "نقل المركبة", exact: true }).click();
  const form = panel.locator(".action-form");
  await form.getByLabel("الموظف المستلم").selectOption({ label: VALETS.fahad.name });
  await form.getByLabel("السبب").fill("تفريغ مسار الطوارئ (تجريبي)");
  await form.getByRole("button", { name: "نقل المركبة", exact: true }).click();
  await expect(panel.getByText(/نقل بانتظار القبول/)).toBeVisible();

  const mover = await device(browser, desktop ? PHONE : SMALL_PHONE);
  await loginValet(mover.page, "fahad");
  const offer = await taskStep(mover.page, "offer");
  await expect(offer).toContainText("تفريغ مسار الطوارئ");
  await expect(offer).toContainText("B · 4");
  await offer.getByRole("button", { name: "قبول" }).click();
  const move = await taskStep(mover.page, "move");
  await move.locator(".choice", { hasText: "C" }).click();
  await move.getByLabel("الموقف").fill("3");
  await move.getByLabel("رقم خطاف المفتاح").fill(`2${n}9`);
  await move.getByRole("button", { name: "تم النقل" }).click();
  await taskStep(mover.page, "none");
  await mover.context.close();

  await expect(panel).toContainText("C · 3", { timeout: 15_000 });
  await expect(panel).toContainText(`2${n}9`);
  await expect(panel.getByText(/قيد النقل|نقل بانتظار القبول/)).toHaveCount(0);
  await expect(mainNav(page)).toBeVisible();
});
