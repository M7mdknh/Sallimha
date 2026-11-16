import { expect, test } from "@playwright/test";
import { VALETS, findTicket, loginAs, openSimulator, parkViaSimulator, say, tapButton, thread } from "./helpers";

// ADR-0007: a move is an offer; the location changes only after the valet accepts and reports it. SIMULATED.
test("supervisor starts a move, the valet accepts and reports it, the console shows the new location", async (
  { page }, info) => {
  test.setTimeout(240_000);
  const n = info.project.name === "desktop" ? "1" : "2";
  const plate = `MOV ${n}100`;
  await loginAs(page, "supervisor");
  const eventPath = new URL(page.url()).pathname;
  await parkViaSimulator(page, { valet: VALETS["فهد (تجريبي)"], guest: `05012300${n}1`, plate: `${plate} لكزس`,
    location: "B 4", hook: `8${n}` });

  await findTicket(page, eventPath, plate, new RegExp(plate));
  const panel = page.locator(".ticket-panel");
  await panel.getByRole("button", { name: "نقل المركبة", exact: true }).click();
  const form = panel.locator(".action-form");
  const select = form.getByLabel("الموظف المستلم");
  const valetName = (await select.locator("option").nth(1).textContent())!.trim();
  await select.selectOption({ index: 1 });
  await form.getByLabel("السبب").fill("تفريغ مسار الطوارئ (تجريبي)");
  await form.getByRole("button", { name: "نقل المركبة", exact: true }).click();
  await expect(panel.getByText(/نقل بانتظار القبول/)).toBeVisible();
  await expect(panel.getByRole("button", { name: "تسجيل الموقع الجديد" })).toHaveCount(0); // not accepted yet
  await expect(panel).toContainText("B 4");

  await openSimulator(page);
  await thread(page, VALETS[valetName]);
  await tapButton(page, "قبول");
  await expect(page.getByRole("log").locator(".bubble-out").last()).toContainText(/النقل مسند إليك/);
  await tapButton(page, "تم النقل");
  await say(page, "C 3", /خطاف المفتاح/);
  await say(page, `9${n}`, /تم تسجيل النقل/);

  await findTicket(page, eventPath, plate, new RegExp(plate));
  await expect(panel).toContainText("C 3");
  await expect(panel).toContainText(`9${n}`);
  await expect(panel.getByText(/قيد النقل|نقل بانتظار القبول/)).toHaveCount(0);
});
