// THR-070 (base di SL-01): l'input che arriva dall'indirizzo non diventa mai markup né script.
// THR-005 / SR-037: la SPA non scrive nulla di persistente nel browser (token, dati) in questa
// slice; il service worker e la cache offline arrivano in M2.
import { expect, test } from "@playwright/test";
import { observe } from "./support/browser";

// `spa`: l'indirizzo non ha punti nell'ultimo segmento, quindi il server deve servire la SPA e
// la prova ha senso nel browser. Gli altri sono «file» per il server (404 JSON): niente da eseguire.
const PAYLOADS = [
  { url: "/%3Cimg%20src%3Dx%20onerror%3Dwindow.__xss%3D1%3E", spa: false },
  { url: "/%22%3E%3Cscript%3Ewindow.__xss%3D1%3C%2Fscript%3E", spa: false },
  {
    url: "/accedi?x=%3Csvg%20onload%3Dwindow.__xss%3D1%3E&return_to=javascript:window.__xss=1",
    spa: true,
  },
  { url: "/accedi#%22%3E%3Cimg%20src%3Dx%20onerror%3Dwindow.__xss%3D1%3E", spa: true },
  { url: "/piano/%3Cimg%20src%3Dx%20onerror%3Dwindow.__xss%3D1%3E/cena", spa: true },
];

for (const payload of PAYLOADS) {
  test(`indirizzo ostile non esegue nulla: ${payload.url.slice(0, 48)}`, async ({ page }) => {
    const dialogs: string[] = [];
    page.on("dialog", async (dialog) => {
      dialogs.push(dialog.message());
      await dialog.dismiss();
    });
    const seen = await observe(page);
    const response = await page.goto(payload.url);
    const isHtml = (response?.headers()["content-type"] ?? "").includes("text/html");
    if (payload.spa) {
      expect(response?.status(), "la SPA deve rispondere a questo indirizzo").toBe(200);
      expect(isHtml).toBe(true);
    }
    if (isHtml) await page.getByRole("heading", { level: 1 }).waitFor();
    await page.waitForLoadState("networkidle");
    expect(
      await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
    ).toBeUndefined();
    expect(dialogs).toEqual([]);
    expect(await page.locator('img[src="x"], svg[onload], script:not([src])').count()).toBe(0);
    expect(await page.locator("body").innerHTML()).not.toMatch(/onerror=|onload=/);
    expect(await seen.cspViolations()).toEqual([]);
  });
}

test("SR-037 / THR-005: nessun dato in localStorage, sessionStorage, cookie, IndexedDB, cache", async ({
  page,
  context,
}) => {
  await page.goto("/accedi");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await page.goto("/questa-rotta-non-esiste");
  await page.getByRole("heading", { level: 1 }).waitFor();
  const state = await page.evaluate(async () => ({
    local: localStorage.length,
    session: sessionStorage.length,
    cookie: document.cookie,
    databases: (await indexedDB.databases()).length,
    caches: (await caches.keys()).length,
  }));
  expect({ ...state, cookie: "" }).toEqual({
    local: 0,
    session: 0,
    cookie: "",
    databases: 0,
    caches: 0,
  });
  // SL-03a (ADR-0004 rev. 3): l'unico cookie di una visita anonima è il token CSRF `__Host-csrf`,
  // letto dalla SPA (non HttpOnly); la sessione, quando c'è, è HttpOnly e non compare qui.
  expect(state.cookie.split("; ").map((c) => c.split("=")[0])).toEqual(["__Host-csrf"]);
  expect((await context.cookies()).map((c) => c.name)).toEqual(["__Host-csrf"]);
});

test("M0: nessun service worker registrato (la PWA offline arriva in M2, THR-073)", async ({
  page,
}) => {
  await page.goto("/accedi");
  await page.getByRole("heading", { level: 1 }).waitFor();
  const registrations = await page.evaluate(
    async () => (await navigator.serviceWorker.getRegistrations()).length,
  );
  expect(registrations).toBe(0);
});
