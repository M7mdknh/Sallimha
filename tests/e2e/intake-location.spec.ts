// ADR-0013 in the browser. Positions come from Playwright's emulated geolocation or a scripted stub, and the map
// is not configured here: every location result in this file is SIMULATED, not a real-device Google Maps rehearsal.
import { type Browser, expect, type Page, test } from "@playwright/test";

import {
  cameraPhoto, customerCode, customerRequests, enterCar, loginAs, loginValet, openTicket, parkHere, PHONE, taskStep,
} from "./helpers";

async function valetDevice(browser: Browser, lang: "ar" | "en", geo?: { latitude: number; longitude: number; accuracy: number }) {
  const context = await browser.newContext({ viewport: PHONE, hasTouch: true, isMobile: true,
    locale: lang === "ar" ? "ar-SA" : "en-GB", ...(geo ? { geolocation: geo, permissions: ["geolocation"] } : {}) });
  if (lang === "en") await context.addInitScript(() => window.localStorage.setItem("sallimha.lang", "en"));
  return { context, page: await context.newPage() };
}

async function photosAndStart(page: Page) {
  const flow = page.getByTestId("register");
  for (let i = 1; i <= 4; i += 1) {
    await flow.locator("input[type=file]").setInputFiles(await cameraPhoto(page, `p-${i}`));
    await expect(flow.locator(".photo-count")).toContainText(`${i}`);
  }
  await flow.getByRole("button", { name: /بدء الركن|Start parking/ }).click();
  await expect(flow).toHaveAttribute("data-step", "park");
  return flow;
}

const letterXs = (page: Page) => page.getByTestId("plate-preview").locator(".plate-letter")
  .evaluateAll((els) => els.map((e) => [e.textContent, e.getBoundingClientRect().x] as [string, number]));

test("phone and Saudi plate entry; a denied location still parks with the description (SIMULATED)", async (
  { browser }, info) => {
  test.skip(info.project.name !== "desktop", "explicit device sizes");
  test.setTimeout(150_000);
  const valet = await valetDevice(browser, "ar");
  await loginValet(valet.page, "majed");
  await valet.page.getByRole("link", { name: "تسجيل سيارة" }).click();
  const flow = valet.page.getByTestId("register");
  const phone = flow.getByLabel("رقم جوال العميل");

  await phone.fill("0501");
  await flow.getByLabel("الحروف").fill("أ ب ح");
  await flow.getByLabel("الأرقام").fill("٧٧١٢");
  await flow.getByLabel("النوع واللون").fill("كامري بيضاء");
  await flow.getByRole("button", { name: "إرسال التذكرة" }).click();
  await expect(flow.getByRole("alert")).toContainText("أقصر من المعتاد");
  await expect(phone).toHaveValue("0501"); // kept after the refusal
  await expect(flow).toHaveAttribute("data-step", "customer");

  // Arabic letters keep their reading order right to left; keyboard alef is read as the plate letter.
  const arabic = await letterXs(valet.page);
  expect(arabic.map(([c]) => c)).toEqual(["ا", "ب", "ح"]);
  expect(arabic[0][1]).toBeGreaterThan(arabic[1][1]);
  await expect(valet.page.getByTestId("plate-preview")).toContainText("7712");

  await phone.fill("٠٥٠ ١٢٣-٩٨٨١"); // Arabic digits, a space and a hyphen
  await expect(flow.locator(".phone-read")).toContainText("+966 50 123 9881");
  await expect(flow.locator(".send-to .phone-confirm")).toContainText("+966 50 123 9881");
  await flow.getByRole("button", { name: "إرسال التذكرة" }).click();
  await expect(flow).toHaveAttribute("data-step", "photos");
  await expect(flow.getByTestId("message-status")).toBeVisible();

  await photosAndStart(valet.page);
  await flow.getByRole("button", { name: /استخدم موقعي/ }).click();
  await expect(flow.getByText(/إذن الموقع متوقف/)).toBeVisible(); // no permission granted in this browser
  await expect(flow.getByTestId("map-state")).toContainText("غير مُعدّة");
  await expect(flow.getByTestId("pin-block")).toHaveAttribute("data-pin", "none");
  await parkHere(flow, { zone: "B", spot: "7", note: "B1، بجانب العمود 12", hook: "171" });
  await expect(valet.page.getByTestId("parked-done")).toBeVisible();
  await valet.context.close();
});

test("a Latin plate keeps its order in English; a possible duplicate is caught; the saved pin guides retrieval (SIMULATED)",
  async ({ browser, page }, info) => {
    test.skip(info.project.name !== "desktop", "explicit device sizes");
    test.setTimeout(240_000);
    const sara = await valetDevice(browser, "en", { latitude: 24.7647, longitude: 46.6403, accuracy: 400 });
    await loginValet(sara.page, "sara");
    await sara.page.getByRole("link", { name: "Register car" }).click();
    const flow = sara.page.getByTestId("register");
    await flow.getByLabel("Customer's mobile number").fill("0501239882");
    await flow.getByLabel("Letters").fill("abj");
    await flow.getByLabel("Numbers").fill("4321");
    await flow.getByLabel("Make and colour").fill("white Tahoe");
    const latin = await letterXs(sara.page);
    expect(latin.map(([c]) => c)).toEqual(["A", "B", "J"]);
    expect(latin[0][1]).toBeLessThan(latin[1][1]);
    await flow.getByRole("button", { name: "Send ticket" }).click();
    const ticket = (await flow.locator(".ticket-no").textContent())!.trim();
    await photosAndStart(sara.page);

    await flow.getByRole("button", { name: /Use my location/ }).click();
    await expect(flow.getByText(/too approximate/)).toBeVisible(); // ±400 m is never saved
    await expect(flow.getByTestId("pin-block")).toHaveAttribute("data-pin", "none");
    await sara.context.setGeolocation({ latitude: 24.764712, longitude: 46.640312, accuracy: 12 });
    await flow.getByRole("button", { name: /Locate me again/ }).click();
    await expect(flow.getByTestId("pin-block")).toHaveAttribute("data-pin", "gps");
    await expect(flow.getByTestId("pin-block")).toContainText("±12 m");
    await parkHere(flow, { zone: "A", spot: "21", note: "level 2, by the lifts", hook: "172" }, /^Parked$/);
    await expect(sara.page.getByTestId("parked-done")).toBeVisible();

    // The same plate typed in Arabic by another valet: shown before anything is registered.
    const fahad = await valetDevice(browser, "ar");
    await loginValet(fahad.page, "fahad");
    await fahad.page.getByRole("link", { name: "تسجيل سيارة" }).click();
    const other = fahad.page.getByTestId("register");
    await other.getByLabel("رقم جوال العميل").fill("0501239883");
    await other.getByLabel("الحروف").fill("ا ب ح");
    await other.getByLabel("الأرقام").fill("4321");
    await other.getByRole("button", { name: "إرسال التذكرة" }).click();
    await expect(other.getByTestId("possible-duplicate")).toContainText(ticket);
    await expect(other.getByRole("button", { name: /سيارة مختلفة/ })).toBeVisible();
    await expect(other).toHaveAttribute("data-step", "customer"); // nothing registered
    await fahad.context.close();

    // Retrieval: the place and the saved pin, with a link out that carries coordinates only.
    await sara.page.getByTestId("parked-done").getByRole("button", { name: "My work" }).click();
    await loginAs(page, "supervisor");
    await customerRequests(page, "+966501239882");
    const card = await taskStep(sara.page, "offer");
    const place = card.getByTestId("place-view");
    await expect(place).toContainText("level 2, by the lifts");
    const href = await place.getByRole("link", { name: "Open in Google Maps" }).getAttribute("href");
    expect(href).toBe("https://www.google.com/maps/search/?api=1&query=24.764712%2C46.640312");
    await card.getByRole("button", { name: "Accept" }).click();
    await taskStep(sara.page, "bring");
    await card.getByRole("button", { name: "Car ready" }).click();
    const code = await customerCode(page, "+966501239882");
    await (await taskStep(sara.page, "code")).getByLabel(/Collection code|code/i).fill(code);
    await card.getByRole("button", { name: "Verify" }).click();
    await (await taskStep(sara.page, "deliver")).getByRole("button", { name: "Delivered" }).click();
    await taskStep(sara.page, "none");
    await sara.context.close();
  });

test("a failed customer ticket is one supervisor issue with resend; the valet sees it and carries on (SIMULATED)", async (
  { browser, page }, info) => {
  test.skip(info.project.name !== "desktop", "explicit device sizes");
  test.setTimeout(150_000);
  await loginAs(page, "supervisor");
  await page.goto("/dev/simulator");
  await page.getByRole("button", { name: /اجعل الرسالة التالية تفشل/ }).click();
  await expect(page.getByText(/الرسالة التالية ستفشل/)).toBeVisible();

  const valet = await valetDevice(browser, "ar");
  // A position the phone reports from a minute ago (a cached fix): shown as stale, never saved.
  await valet.context.addInitScript(() => {
    navigator.geolocation.getCurrentPosition = (ok) => ok({
      coords: { latitude: 24.76, longitude: 46.64, accuracy: 8 }, timestamp: Date.now() - 60_000 } as GeolocationPosition);
  });
  await loginValet(valet.page, "fahad");
  await valet.page.getByRole("link", { name: "تسجيل سيارة" }).click();
  const flow = valet.page.getByTestId("register");
  await enterCar(flow, "0501239884", "MSG 4400 لكزس");
  await flow.getByRole("button", { name: "إرسال التذكرة" }).click();
  await expect(flow).toHaveAttribute("data-step", "photos");
  await expect(flow.getByTestId("message-status")).toHaveAttribute("data-status", "failed", { timeout: 30_000 });
  const ticket = (await flow.locator(".ticket-no").textContent())!.trim();

  const panel = await openTicket(page, ticket.replace("#", ""));
  await expect(panel).toContainText("لم تصل — أُبلغ المشرف");
  await page.goto(page.url().replace(/\/tickets\/\d+$/, ""));
  await expect(page.getByTestId("problems")).toContainText("لم تصل رسالة إلى العميل");
  const again = await openTicket(page, ticket.replace("#", ""));
  await again.getByRole("button", { name: "إعادة إرسال التذكرة" }).first().click(); // the primary action opens
  await again.getByRole("button", { name: "إعادة إرسال التذكرة" }).last().click(); // its form submits
  await expect(again).toContainText(/في الانتظار|أُرسلت|وصلت/, { timeout: 30_000 });

  await photosAndStart(valet.page);
  await flow.getByRole("button", { name: /استخدم موقعي/ }).click();
  await expect(flow.getByText("الموقع قديم. أعد المحاولة.")).toBeVisible();
  await expect(flow.getByTestId("pin-block")).toHaveAttribute("data-pin", "none");
  await parkHere(flow, { zone: "C", spot: "4", hook: "173" });
  await expect(valet.page.getByTestId("parked-done")).toBeVisible();
  await valet.context.close();
});
