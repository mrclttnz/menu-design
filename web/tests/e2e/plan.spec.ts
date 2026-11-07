// SL-06a: il piano della settimana nel browser vero, contro l'app collegata a un database di prova
// e al provider OIDC finto (08 §2, §4.2). US-001 AC-001.1 end-to-end (login con Google -> piano
// della settimana corrente della propria famiglia), US-008 AC-008.1/.4/.5, AC-024.1 (il Membro
// legge), NFR-008 (360 px, axe: zero violazioni serious/critical). Ogni test gira a 360 px e su
// desktop; ogni contesto ha un IP proprio (`actAs` -> `isolateIp`).
//
// L'orologio dello stack è quello vero: la settimana attesa si calcola qui, nel fuso della
// famiglia (Europe/Rome, il predefinito). I testi sono quelli del catalogo `it` (docs/03-ux.md §7.3).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import { expectNoSeriousA11y } from "./support/a11y";
import { observe } from "./support/browser";
import { actAs, seedMember, STUB_AVAILABLE, STUB_MISSING_REASON, unique } from "./support/stub";

test.skip(!STUB_AVAILABLE, STUB_MISSING_REASON);

const LOGIN = /Continua con Google/;
const DAY_MS = 86_400_000;

function romeToday(): Date {
  const iso = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(new Date());
  return new Date(`${iso}T00:00:00Z`);
}

function weekOf(today: Date): Date[] {
  const monday = new Date(today.getTime() - ((today.getUTCDay() + 6) % 7) * DAY_MS);
  return Array.from({ length: 7 }, (_, n) => new Date(monday.getTime() + n * DAY_MS));
}

function label(day: Date): string {
  const weekday = new Intl.DateTimeFormat("it-IT", { weekday: "long", timeZone: "UTC" }).format(
    day,
  );
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} ${day.getUTCDate()}`;
}

async function enter(
  page: Page,
  context: BrowserContext,
  request: APIRequestContext,
  options: { role?: string; defaultMeals?: string[]; label: string },
): Promise<void> {
  const who = unique(options.label);
  await seedMember(request, {
    ...who,
    role: options.role ?? "planner",
    displayName: "Paola Pianificatrice",
    defaultMeals: options.defaultMeals ?? ["lunch", "dinner"],
  });
  await actAs(context, { ...who, name: "Paola Pianificatrice" });
  await page.goto("/accedi");
  await page
    .getByRole("button", { name: LOGIN })
    .or(page.getByRole("link", { name: LOGIN }))
    .click();
  await page.waitForURL(/\/piano$/);
}

async function noOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    inner: window.innerWidth,
  }));
  expect(widths.scroll, "scorrimento orizzontale (NFR-008, 360 px)").toBeLessThanOrEqual(
    widths.inner,
  );
}

test.describe("AC-001.1: dopo il login si vede il piano della settimana corrente", () => {
  test("login con Google -> settimana da lunedì a domenica con i pasti di default", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "piano" });
    const week = weekOf(romeToday());
    await expect(page.getByRole("heading", { level: 1, name: "Piano" })).toBeVisible();
    for (const day of week) {
      await expect(page.getByRole("heading", { name: new RegExp(label(day)) })).toBeVisible();
    }
    await expect(page.getByText("Pranzo")).toHaveCount(7);
    await expect(page.getByText("Cena")).toHaveCount(7);
    // Il giorno di oggi è evidenziato con il badge (non solo con il colore).
    const today = page
      .getByRole("heading", { name: new RegExp(label(romeToday())) })
      .locator("xpath=ancestor::section[1]");
    await expect(today.getByText("Oggi", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Pagina non trovata" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Accedi a Menu Design" })).toHaveCount(0);
  });

  test("la barra del piano mostra l'intervallo e i comandi di navigazione", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "nav" });
    await expect(page.getByRole("button", { name: "Settimana precedente" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Settimana successiva" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Oggi" })).toBeVisible();
    await page.getByRole("button", { name: "Settimana successiva" }).click();
    await expect(page).toHaveURL(/\/piano\?.*da=\d{4}-\d{2}-\d{2}/);
    await page.getByRole("button", { name: "Oggi" }).click();
    const first = label(weekOf(romeToday())[0] as Date);
    await expect(page.getByRole("heading", { name: new RegExp(first) })).toBeVisible();
  });

  test("senza richieste verso terzi, senza errori di pagina né violazioni della CSP", async ({
    page,
    context,
    request,
  }) => {
    const seen = await observe(page);
    await enter(page, context, request, { label: "pulita" });
    await expect(page.getByText("Pranzo")).toHaveCount(7);
    const origin = new URL(page.url()).origin;
    const foreign = seen.requests
      .map((r) => new URL(r.url()))
      .filter((u) => u.origin !== origin && !u.href.includes("127.0.0.1"));
    expect(foreign.map(String)).toEqual([]);
    expect(seen.pageErrors).toEqual([]);
    expect(await seen.cspViolations()).toEqual([]);
  });
});

test.describe("la vista e i ruoli", () => {
  test("un Membro vede il piano in sola lettura (AC-024.1)", async ({ page, context, request }) => {
    await enter(page, context, request, { role: "member", label: "membro" });
    await expect(page.getByText("Pranzo")).toHaveCount(7);
    await expect(page.getByText("Ancora niente").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /Aggiungi piatto/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Azioni per/ })).toHaveCount(0);
  });

  test("una famiglia senza pasti di default vede lo stato vuoto (AC-003.3)", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "vuoto", defaultMeals: [] });
    await expect(page.getByText("Nessun pasto da pianificare")).toBeVisible();
    await expect(page.getByRole("button", { name: "Aggiungi un pasto a un giorno" })).toBeVisible();
  });

  test("togliere la cena da un giorno la toglie solo da quel giorno (AC-008.4)", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "togli" });
    const section = page
      .getByRole("heading", { name: new RegExp(label(weekOf(romeToday())[6] as Date)) })
      .locator("xpath=ancestor::section[1]");
    await section.getByRole("link", { name: /Cena/ }).click();
    await page.waitForURL(/\/piano\/\d{4}-\d{2}-\d{2}\/cena$/);
    await page.locator("main [aria-haspopup]").first().click();
    await page.getByRole("menuitem", { name: "Togli questo pasto da questo giorno" }).click();
    await page.goto("/piano");
    await expect(page.getByText("Pranzo")).toHaveCount(7);
    await expect(page.getByText("Cena")).toHaveCount(6);
  });
});

test.describe("D-05: intervallo", () => {
  test("oltre 62 giorni l'errore indica il limite e il piano non cambia (AC-008.5)", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "intervallo" });
    await page.locator("main [aria-haspopup]").first().click();
    await page.getByRole("menuitem", { name: "Mostra un altro intervallo…" }).click();
    const dialog = page.getByRole("dialog", { name: "Scegli un intervallo" });
    await dialog.getByLabel("Dal", { exact: true }).fill("2026-10-01");
    await dialog.getByLabel("Al", { exact: true }).fill("2026-12-02");
    await dialog.getByRole("button", { name: "Mostra" }).click();
    await expect(dialog.getByText("Scegli al massimo 62 giorni.")).toBeVisible();
  });

  test("un intervallo di 10 giorni mostra 10 giorni (AC-008.5)", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "dieci" });
    await page.goto("/piano?da=2026-11-01&a=2026-11-10");
    await expect(page.getByText("Pranzo")).toHaveCount(10);
  });
});

test.describe("accessibilità e 360 px (NFR-008)", () => {
  test("il piano non ha violazioni serious/critical né scorrimento orizzontale", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "a11y" });
    await expect(page.getByText("Pranzo")).toHaveCount(7);
    await expectNoSeriousA11y(page, "S-02 piano");
    await noOverflow(page);
  });

  test("il pasto (S-03) non ha violazioni serious/critical", async ({ page, context, request }) => {
    await enter(page, context, request, { label: "a11y-pasto" });
    await page
      .getByRole("link", { name: /Pranzo/ })
      .first()
      .click();
    await expect(page.getByRole("heading", { level: 1, name: /Pranzo/ })).toBeVisible();
    await expectNoSeriousA11y(page, "S-03 pasto");
    await noOverflow(page);
  });
});
