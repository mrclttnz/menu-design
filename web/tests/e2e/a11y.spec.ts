// NFR-008: zero violazioni serious o critical con axe su ogni vista (08 §15), a 360 px e su
// desktop (progetti), con movimento ridotto e a 320 px. Le viste dello stato vuoto, caricamento
// ed errore delle slice successive aggiungono qui le proprie righe.
import { test } from "@playwright/test";
import { expectNoSeriousA11y } from "./support/a11y";
import { VIEWS } from "./support/browser";

for (const view of VIEWS) {
  test(`axe: ${view.name} (${view.path})`, async ({ page }) => {
    await page.goto(view.path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await expectNoSeriousA11y(page, view.name);
  });
}

test("axe: S-01 con prefers-reduced-motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/accedi");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await expectNoSeriousA11y(page, "movimento ridotto");
});

test("axe: S-01 a 320 px (riflusso)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto("/accedi");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await expectNoSeriousA11y(page, "320 px");
});

test("axe: S-01 con il collegamento «Vai al contenuto» a fuoco", async ({ page }) => {
  await page.goto("/accedi");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await page.locator("body").click({ position: { x: 1, y: 1 }, force: true });
  await page.keyboard.press("Tab");
  await expectNoSeriousA11y(page, "skip link a fuoco");
});
