// SL-01: guscio della SPA servito da FastAPI e pagina S-01 (UX S-01, 8.1; NFR-008, NFR-009,
// NFR-011, NFR-013). Ogni test gira a 360 px e su desktop (progetti di playwright.config.ts).
import { expect, test } from "@playwright/test";
import { observe, VIEWS } from "./support/browser";

test.describe("S-01 Accesso", () => {
  test("si carica con titolo, lingua e testi italiani, senza errori né richieste fallite", async ({
    page,
  }) => {
    const seen = await observe(page);
    const response = await page.goto("/accedi");
    expect(response?.status()).toBe(200);
    await expect(page.locator("html")).toHaveAttribute("lang", "it");
    await expect(page).toHaveTitle(/Menu Design/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).toBeVisible();
    await expect(
      page.getByText("Il piano dei pasti della tua famiglia, sempre in tasca."),
    ).toBeVisible();
    const google = page
      .getByRole("button", { name: /Continua con Google/ })
      .or(page.getByRole("link", { name: /Continua con Google/ }));
    await expect(google).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(seen.consoleErrors).toEqual([]);
    expect(seen.pageErrors).toEqual([]);
    expect(seen.failedResponses.map((r) => `${r.status()} ${r.url()}`)).toEqual([]);
  });

  test("la radice / porta a S-01 (nessuna sessione in questa slice)", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/accedi$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).toBeVisible();
  });

  test("NFR-009: nessuno scorrimento orizzontale a 360 px né a 320 px (WCAG 1.4.10)", async ({
    page,
  }) => {
    for (const width of [360, 320]) {
      await page.setViewportSize({ width, height: 740 });
      await page.goto("/accedi");
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow, `scorrimento orizzontale a ${width}px`).toBeLessThanOrEqual(0);
    }
  });

  test("il comando di accesso ha un bersaglio di almeno 44 x 44 px (UX 9.4, WCAG 2.5.8)", async ({
    page,
  }) => {
    await page.goto("/accedi");
    const google = page
      .getByRole("button", { name: /Continua con Google/ })
      .or(page.getByRole("link", { name: /Continua con Google/ }));
    const box = await google.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    expect(box?.width ?? 0).toBeGreaterThanOrEqual(44);
  });

  test("tastiera: «Vai al contenuto» è il primo elemento, si vede a fuoco e porta nel contenuto (WCAG 2.4.1)", async ({
    page,
  }) => {
    await page.goto("/accedi");
    await page.getByRole("heading", { level: 1 }).waitFor();
    const first = await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      );
      return el?.textContent?.trim() ?? null;
    });
    expect(first, "primo elemento attivabile nel DOM").toBe("Vai al contenuto");
    const skip = page.getByRole("link", { name: "Vai al contenuto" });
    await skip.focus();
    await expect(skip).toBeFocused();
    const box = await skip.boundingBox();
    expect(
      box && box.width > 1 && box.height > 1 && box.x >= 0 && box.y >= 0,
      "visibile quando ha il focus",
    ).toBe(true);
    await page.keyboard.press("Enter");
    const inMain = await page.evaluate(
      () => document.querySelector("main")?.contains(document.activeElement) ?? false,
    );
    expect(inMain, "dopo Invio il focus deve essere dentro <main>").toBe(true);
  });

  test("il focus è visibile: anello di almeno 2 px sul comando focalizzato (WCAG 2.4.7)", async ({
    page,
  }) => {
    await page.goto("/accedi");
    const google = page
      .getByRole("button", { name: /Continua con Google/ })
      .or(page.getByRole("link", { name: /Continua con Google/ }));
    await page.locator("body").click({ position: { x: 1, y: 1 }, force: true });
    for (let i = 0; i < 6; i += 1) {
      await page.keyboard.press("Tab"); // focus da tastiera: attiva :focus-visible
      if (await google.evaluate((el) => el === document.activeElement)) break;
    }
    await expect(google).toBeFocused();
    const ring = await google.evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        outline: Number.parseFloat(style.outlineWidth) * (style.outlineStyle === "none" ? 0 : 1),
        shadow: style.boxShadow,
      };
    });
    expect(ring.outline >= 2 || ring.shadow !== "none", JSON.stringify(ring)).toBe(true);
  });

  test("prefers-reduced-motion: nessuna transizione (UX 8.2)", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/accedi");
    const durations = await page.evaluate(() =>
      [...document.querySelectorAll("button, a, input")].map(
        (el) => getComputedStyle(el).transitionDuration,
      ),
    );
    expect(durations.length, "nessun comando trovato nella pagina").toBeGreaterThan(0);
    for (const d of durations) {
      for (const part of d.split(",")) {
        const seconds = part.trim().endsWith("ms")
          ? Number.parseFloat(part) / 1000
          : Number.parseFloat(part);
        expect(seconds).toBeLessThanOrEqual(0.001);
      }
    }
  });
});

test.describe("rotte e fallback SPA", () => {
  test("una rotta inesistente mostra la vista «non trovato» in italiano (error.notFound)", async ({
    page,
  }) => {
    const response = await page.goto("/questa-rotta-non-esiste");
    expect(response?.status(), "il server serve la SPA e la SPA decide (UX 5.1)").toBe(200);
    await expect(
      page.getByText("Non troviamo quello che cerchi. Potrebbe essere stato eliminato.").first(),
    ).toBeVisible();
    await expect(page.locator('a[href="/accedi"]').first()).toBeVisible();
  });

  test("ricaricare un indirizzo profondo dell app (/piano/2026-10-19/cena) non dà un 404 del server", async ({
    page,
  }) => {
    const response = await page.goto("/piano/2026-10-19/cena");
    expect(response?.status()).toBe(200);
    expect(response?.headers()["content-type"]).toContain("text/html");
    await expect(page.locator("#root")).not.toBeEmpty();
  });

  test("WCAG 2.4.2: il titolo del documento descrive la vista e cambia tra le viste", async ({
    page,
  }) => {
    const titles: string[] = [];
    for (const view of VIEWS.filter((v) => v.path !== "/")) {
      await page.goto(view.path);
      await page.getByRole("heading", { level: 1 }).waitFor();
      titles.push(await page.title());
    }
    for (const title of titles) expect(title).toMatch(/Menu Design/);
    expect(new Set(titles).size, `titoli uguali per viste diverse: ${titles.join(" | ")}`).toBe(
      titles.length,
    );
  });

  test("WCAG 2.4.3: dopo un cambio di rotta il focus va sul titolo h1", async ({ page }) => {
    await page.goto("/questa-rotta-non-esiste");
    await page.locator('a[href="/accedi"]').first().click();
    const h1 = page.getByRole("heading", { level: 1, name: "Accedi a Menu Design" });
    await expect(h1).toBeFocused();
  });

  test("NFR-011: la lingua è sempre l italiano, qualunque sia la lingua del browser", async ({
    browser,
    baseURL,
  }) => {
    const context = await browser.newContext({ locale: "en-US", ...(baseURL ? { baseURL } : {}) });
    const page = await context.newPage();
    await page.goto("/accedi");
    await expect(
      page.getByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("lang", "it");
    await context.close();
  });
});
