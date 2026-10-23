// SL-04: archivio piatti nel browser vero, contro l'app collegata a un database di prova e al
// provider OIDC finto (08 §2, §4.2, §4.5). US-004 AC-004.1-.7, US-006 AC-006.1-.5, THR-070
// (XSS memorizzato in nome e note), THR-020 (altra famiglia), SR-024, SR-032, NFR-008 (360 px),
// accessibilità (axe: zero violazioni serious/critical). Ogni test gira a 360 px e su desktop;
// ogni contesto ha un IP proprio (`actAs` → `isolateIp`).
//
// Contratto UI assunto, lo stesso dei test di componenti `tests/unit/dishes/*`: rotte `/piatti`,
// `/piatti/nuovo`, `/piatti/:id`, `/piatti/:id/modifica`; etichette dal catalogo `it` di
// docs/03-ux.md §7.3.
import { randomUUID } from "node:crypto";
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { expectNoSeriousA11y } from "./support/a11y";
import { observe, type Observed } from "./support/browser";
import {
  actAs,
  seedMember,
  STUB_AVAILABLE,
  STUB_MISSING_REASON,
  unique,
  type SeedDish,
} from "./support/stub";
import type { APIRequestContext } from "@playwright/test";

test.skip(!STUB_AVAILABLE, STUB_MISSING_REASON);

const LOGIN = /Continua con Google/;

interface Session {
  who: { sub: string; email: string };
  seen: Observed;
  dialogs: string[];
}

async function enter(
  page: Page,
  context: BrowserContext,
  request: APIRequestContext,
  options: { role?: string; dishes?: SeedDish[]; label: string },
): Promise<Session> {
  const who = unique(options.label);
  await seedMember(request, {
    ...who,
    role: options.role ?? "planner",
    displayName: "Paola Pianificatrice",
    dishes: options.dishes ?? [],
  });
  await actAs(context, { ...who, name: "Paola Pianificatrice" });
  const dialogs: string[] = [];
  page.on("dialog", async (dialog) => {
    dialogs.push(dialog.message());
    await dialog.dismiss();
  });
  const seen = await observe(page);
  await page.goto("/accedi");
  await page
    .getByRole("button", { name: LOGIN })
    .or(page.getByRole("link", { name: LOGIN }))
    .click();
  await page.waitForURL(/\/piano$/);
  return { who, seen, dialogs };
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

async function xssFired(page: Page): Promise<unknown> {
  return page.evaluate(() => (window as unknown as { __xss?: number }).__xss);
}

async function fillAndSave(
  page: Page,
  dish: { name: string; courses: string[]; notes?: string; source?: string },
): Promise<void> {
  await page.getByLabel("Nome del piatto").fill(dish.name);
  for (const course of dish.courses) await page.getByRole("checkbox", { name: course }).check();
  if (dish.notes !== undefined) await page.getByRole("textbox", { name: /^Note/ }).fill(dish.notes);
  if (dish.source !== undefined) {
    await page.getByRole("button", { name: "Aggiungi una fonte" }).click();
    await page.getByLabel("Indirizzo (https://…)").fill(dish.source);
  }
  await page.getByRole("button", { name: "Salva" }).click();
}

const PASTA: SeedDish = { name: "Pasta e ceci", courses: ["first"], status: "tested" };
const PURE: SeedDish = { name: "Purè di patate", courses: ["side"] };
const SPECIAL: SeedDish[] = [
  { name: "50% sugo", courses: ["first"] },
  { name: "a_b", courses: ["first"] },
  { name: "L'insalata di Nonna", courses: ["side"] },
];

test.describe("US-004: creare e consultare", () => {
  test("AC-004.7 + AC-004.1 + AC-004.2: dall'archivio vuoto al primo piatto con fonti", async ({
    page,
    context,
    request,
  }) => {
    const { seen, dialogs } = await enter(page, context, request, { label: "primo" });
    await page.getByRole("navigation").getByRole("link", { name: "Piatti" }).click();
    await page.waitForURL(/\/piatti$/);
    await expect(page.getByRole("heading", { level: 1, name: "Piatti" })).toBeVisible();
    await expect(page.getByText("Il tuo archivio è vuoto")).toBeVisible();
    await noOverflow(page);
    await expectNoSeriousA11y(page, "S-05 vuoto");

    await page.getByRole("link", { name: "Aggiungi il primo piatto" }).click();
    await page.waitForURL(/\/piatti\/nuovo$/);
    await expect(page.getByRole("navigation")).toHaveCount(0);
    await noOverflow(page);
    await expectNoSeriousA11y(page, "S-07 nuovo");

    await page.getByLabel("Nome del piatto").fill("Frittata di zucchine");
    await page.getByRole("checkbox", { name: "Secondo" }).check();
    await page.getByRole("checkbox", { name: "Piatto unico" }).check();
    await page.getByRole("radio", { name: "Collaudato" }).check();
    await page.getByLabel("Tempo di preparazione").selectOption({ label: "Meno di 30 minuti" });
    await page.getByRole("button", { name: "Aggiungi una fonte" }).click();
    await page.getByLabel("Indirizzo (https://…)").fill("https://ricette.example.test/frittata");
    await page.getByRole("button", { name: "Aggiungi una fonte" }).click();
    await page.getByRole("combobox", { name: "Tipo" }).nth(1).selectOption({ label: "Libro" });
    await page.getByLabel("Titolo").fill("Il cucchiaio");
    await page.getByLabel("Pagina").fill("142");
    await page.getByRole("button", { name: "Salva" }).click();

    await page.waitForURL(/\/piatti\/[0-9a-f-]{36}$/);
    await expect(page.getByText("Piatto salvato")).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 1, name: "Frittata di zucchine" }),
    ).toBeVisible();
    const main = page.getByRole("main");
    for (const text of ["Secondo", "Piatto unico", "Collaudato", "Meno di 30 minuti"]) {
      await expect(main).toContainText(text);
    }
    await expect(main).toContainText("Il cucchiaio");
    await expect(main).toContainText("142");
    const recipe = page.getByRole("link", { name: /Apri la ricetta/ });
    await expect(recipe).toHaveAttribute("href", "https://ricette.example.test/frittata");
    await expect(recipe).toHaveAttribute("target", "_blank");
    expect((await recipe.getAttribute("rel")) ?? "").toMatch(/noopener/);
    expect((await recipe.getAttribute("rel")) ?? "").toMatch(/noreferrer/);
    await noOverflow(page);
    await expectNoSeriousA11y(page, "S-06 scheda");

    // compare nell'archivio con tutti i dati
    await page.getByRole("navigation").getByRole("link", { name: "Piatti" }).click();
    const row = page.getByRole("link", { name: /Frittata di zucchine/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Collaudato");
    expect(dialogs).toEqual([]);
    expect(seen.pageErrors).toEqual([]);
    expect(await seen.cspViolations()).toEqual([]);
  });

  test("AC-004.3 + AC-004.4 + AC-004.5: il modulo indica cosa non va e non perde il testo", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "errori" });
    await page.goto("/piatti/nuovo");
    await page.getByRole("button", { name: "Salva" }).click();
    await expect(page.getByText("Compila questo campo.").first()).toBeVisible();
    await expect(page.getByText("Scegli almeno una portata.")).toBeVisible();
    await expect(page.getByText("Controlla questi campi prima di salvare")).toBeVisible();
    await expectNoSeriousA11y(page, "S-07 con errori");
    await noOverflow(page);

    await page.getByLabel("Nome del piatto").fill("x".repeat(121));
    await page.getByRole("checkbox", { name: "Primo" }).check();
    await page.getByRole("button", { name: "Salva" }).click();
    await expect(page.getByText("Massimo 120 caratteri.")).toBeVisible();

    await page.getByLabel("Nome del piatto").fill("Frittata");
    await page.getByRole("button", { name: "Aggiungi una fonte" }).click();
    await page.getByLabel("Indirizzo (https://…)").fill("javascript:alert(1)");
    await page.getByRole("button", { name: "Salva" }).click();
    await expect(
      page.getByText("Inserisci un indirizzo che inizi con http:// o https://."),
    ).toBeVisible();
    await expect(page).toHaveURL(/\/piatti\/nuovo$/);
    await expect(page.getByLabel("Nome del piatto")).toHaveValue("Frittata");
    // nessun piatto è stato creato
    const list = await (await page.request.get("/api/v1/dishes")).json();
    expect(list.items).toEqual([]);
  });

  test("AC-004.5: la 11ª fonte non si può aggiungere", async ({ page, context, request }) => {
    await enter(page, context, request, { label: "dieci" });
    await page.goto("/piatti/nuovo");
    const add = page.getByRole("button", { name: "Aggiungi una fonte" });
    for (let i = 0; i < 10; i += 1) await add.click();
    await expect(page.getByRole("combobox", { name: "Tipo" })).toHaveCount(10);
    await expect(add).toBeDisabled();
    await expect(page.getByText("Hai raggiunto il massimo di 10 fonti.")).toBeVisible();
  });

  test("SR-032: nel modulo c'è l'avviso di non scrivere dati sulla salute", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "salute" });
    await page.goto("/piatti/nuovo");
    await expect(
      page.getByText("Non scrivere informazioni sulla salute di nessuno (per esempio allergie)."),
    ).toBeVisible();
  });

  test("modifica: il modulo è compilato, salva con If-Match e la scheda mostra i nuovi dati", async ({
    page,
    context,
    request,
  }) => {
    const id = randomUUID();
    await enter(page, context, request, { label: "modifica", dishes: [{ ...PASTA, id }] });
    await page.goto(`/piatti/${id}/modifica`);
    await expect(page.getByLabel("Nome del piatto")).toHaveValue("Pasta e ceci");
    await page.getByLabel("Nome del piatto").fill("Pasta e ceci alla romana");
    await page.getByRole("button", { name: "Salva" }).click();
    await page.waitForURL(new RegExp(`/piatti/${id}$`));
    await expect(
      page.getByRole("heading", { level: 1, name: "Pasta e ceci alla romana" }),
    ).toBeVisible();
    const detail = await (await page.request.get(`/api/v1/dishes/${id}`)).json();
    expect(detail.version).toBe(2);
  });
});

test.describe("THR-070 / AC-004.6: XSS memorizzato in nome e note", () => {
  const PAYLOADS = [
    '<img src=x onerror="window.__xss=1">',
    '"><script>window.__xss=1</script>',
    "<svg onload=window.__xss=1>",
    "<a href=javascript:window.__xss=1>clic</a>",
    "&lt;b&gt;grassetto&lt;/b&gt;",
  ];

  test("i payload si vedono come testo in elenco, scheda, modulo e ricerca, senza eseguire nulla", async ({
    page,
    context,
    request,
  }) => {
    const { seen, dialogs } = await enter(page, context, request, { label: "xss" });
    for (const payload of PAYLOADS) {
      await page.goto("/piatti/nuovo");
      await fillAndSave(page, { name: payload, courses: ["Primo"], notes: payload });
      await page.waitForURL(/\/piatti\/[0-9a-f-]{36}$/);
      // scheda
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(payload);
      await expect(page.getByRole("main")).toContainText(payload);
      expect(await xssFired(page)).toBeUndefined();
    }
    // elenco
    await page.goto("/piatti");
    for (const payload of PAYLOADS) {
      await expect(page.getByText(payload, { exact: true }).first()).toBeVisible();
    }
    // ricerca e messaggio «crea il piatto»
    await page.getByRole("textbox", { name: "Cerca per nome" }).fill(PAYLOADS[0] as string);
    await expect(page.getByText(PAYLOADS[0] as string, { exact: true }).first()).toBeVisible();
    await page.getByRole("textbox", { name: "Cerca per nome" }).fill("<b>nessuno</b>");
    await expect(page.getByText("Nessun piatto trovato")).toBeVisible();
    await expect(page.getByRole("link", { name: "Crea il piatto «<b>nessuno</b>»" })).toBeVisible();
    // modulo di modifica del primo
    await page.getByRole("textbox", { name: "Cerca per nome" }).fill("");
    await page
      .getByRole("link", { name: /onerror/ })
      .first()
      .click();
    await page.getByRole("link", { name: "Modifica" }).click();
    await expect(page.getByLabel("Nome del piatto")).toHaveValue(PAYLOADS[0] as string);

    expect(await xssFired(page)).toBeUndefined();
    expect(dialogs).toEqual([]);
    expect(
      await page
        .locator("script:not([src]), img[src='x'], svg[onload], a[href^='javascript']")
        .count(),
    ).toBe(0);
    expect(await page.locator("body").innerHTML()).not.toMatch(/\sonerror=|\sonload=/);
    expect(seen.pageErrors).toEqual([]);
    expect(await seen.cspViolations()).toEqual([]);
  });

  test("un nome con markup non produce violazioni di accessibilità", async ({
    page,
    context,
    request,
  }) => {
    const id = randomUUID();
    await enter(page, context, request, {
      label: "xssa11y",
      dishes: [{ name: PAYLOADS[0] as string, id, notes: PAYLOADS[1] as string }],
    });
    await page.goto("/piatti");
    await expectNoSeriousA11y(page, "S-05 payload");
    await page.goto(`/piatti/${id}`);
    await expectNoSeriousA11y(page, "S-06 payload");
  });
});

test.describe("US-006: cercare e filtrare", () => {
  const DISHES = [
    PASTA,
    PURE,
    { name: "Lasagne", courses: ["first"], archived: true },
    { name: "Insalata", courses: ["side"] },
    ...SPECIAL,
  ] satisfies SeedDish[];

  test("AC-006.1 + AC-006.2: parziale, senza maiuscole né accenti", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "cerca", dishes: DISHES });
    await page.goto("/piatti");
    const search = page.getByRole("textbox", { name: "Cerca per nome" });
    await expect(page.getByText("Pasta e ceci")).toBeVisible();
    for (const [query, found] of [
      ["ceci", "Pasta e ceci"],
      ["PASTA", "Pasta e ceci"],
      ["pure", "Purè di patate"],
      ["PURÈ", "Purè di patate"],
    ] as const) {
      await search.fill(query);
      await expect(page.getByText(found)).toBeVisible();
      await expect(page.getByText("Insalata", { exact: true })).toHaveCount(0);
    }
    await noOverflow(page);
    await expectNoSeriousA11y(page, "S-05 ricerca");
  });

  test("%, _ e ' si cercano alla lettera", async ({ page, context, request }) => {
    await enter(page, context, request, { label: "speciali", dishes: DISHES });
    await page.goto("/piatti");
    const search = page.getByRole("textbox", { name: "Cerca per nome" });
    await expect(page.getByText("Pasta e ceci")).toBeVisible();
    for (const [query, found] of [
      ["%", "50% sugo"],
      ["_", "a_b"],
      ["'", "L'insalata di Nonna"],
    ] as const) {
      await search.fill(query);
      await expect(page.getByText(found)).toBeVisible();
      await expect(page.getByText("Pasta e ceci")).toHaveCount(0);
    }
  });

  test("AC-006.3: filtri per portata e stato", async ({ page, context, request }) => {
    await enter(page, context, request, {
      label: "filtri",
      dishes: [
        { name: "Insalata", courses: ["side"] },
        { name: "Patate al forno", courses: ["side"], status: "tested" },
        { name: "Pasta al pomodoro", courses: ["first"] },
        { name: "Zucchine", courses: ["side"], archived: true },
      ],
    });
    await page.goto("/piatti");
    await page.getByRole("combobox", { name: /Portat/ }).selectOption({ label: "Contorno" });
    await page.getByRole("combobox", { name: "Stato" }).selectOption({ label: "Da provare" });
    await expect(page.getByText("Insalata")).toBeVisible();
    await expect(page.getByText("Patate al forno")).toHaveCount(0);
    await expect(page.getByText("Pasta al pomodoro")).toHaveCount(0);
    await expect(page.getByText("Zucchine")).toHaveCount(0);
  });

  test("AC-006.4: gli archiviati compaiono solo con l'interruttore e sono etichettati", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "archiviati", dishes: DISHES });
    await page.goto("/piatti");
    const search = page.getByRole("textbox", { name: "Cerca per nome" });
    await search.fill("lasagne");
    await expect(page.getByText("Nessun piatto trovato")).toBeVisible();
    await page.getByRole("checkbox", { name: "Mostra archiviati" }).check();
    const row = page.getByRole("link", { name: /Lasagne/ });
    await expect(row).toBeVisible();
    await expect(row).toContainText("Archiviato");
  });

  test("AC-006.5: nessun risultato → «Crea il piatto» apre il modulo con il nome", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "nessuno", dishes: [PASTA] });
    await page.goto("/piatti");
    await page.getByRole("textbox", { name: "Cerca per nome" }).fill("Shakshuka");
    await expect(page.getByText("Nessun piatto trovato")).toBeVisible();
    await page.getByRole("link", { name: "Crea il piatto «Shakshuka»" }).click();
    await page.waitForURL(/\/piatti\/nuovo/);
    await expect(page.getByLabel("Nome del piatto")).toHaveValue("Shakshuka");
  });

  test("SR-060: 60 piatti → pagina da 50 e «Mostra altri», nessun scorrimento automatico", async ({
    page,
    context,
    request,
  }) => {
    const many = Array.from({ length: 60 }, (_, i) => ({
      name: `Piatto ${String(i).padStart(3, "0")}`,
      courses: ["first"],
    }));
    await enter(page, context, request, { label: "paginazione", dishes: many });
    await page.goto("/piatti");
    await expect(page.getByRole("link", { name: /^Piatto 049/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Piatto 050/ })).toHaveCount(0);
    await page.getByRole("button", { name: "Mostra altri" }).click();
    await expect(page.getByRole("link", { name: /^Piatto 059/ })).toBeVisible();
    await expect(page.getByRole("button", { name: "Mostra altri" })).toHaveCount(0);
    await expectNoSeriousA11y(page, "S-05 paginata");
  });
});

test.describe("permessi e isolamento", () => {
  test("DD-04: un Membro consulta ma non vede «Nuovo piatto» né «Mostra archiviati»", async ({
    page,
    context,
    request,
  }) => {
    await enter(page, context, request, { label: "membro", role: "member", dishes: [PASTA] });
    await page.goto("/piatti");
    await expect(page.getByText("Pasta e ceci")).toBeVisible();
    await expect(page.getByRole("link", { name: /Nuovo piatto/ })).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: "Mostra archiviati" })).toHaveCount(0);
    await page.getByRole("link", { name: /Pasta e ceci/ }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Pasta e ceci" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Modifica" })).toHaveCount(0);
    // anche chiamando direttamente il server: 403, nessun piatto creato (SR-009)
    const me = await (await page.request.get("/api/v1/session")).json();
    const courses = (await (await page.request.get("/api/v1/courses")).json()).items;
    const refused = await page.request.post("/api/v1/dishes", {
      headers: { "X-CSRF-Token": me.csrfToken, Origin: new URL(page.url()).origin },
      data: { name: "Abusivo", courseIds: [courses[0].id], sources: [] },
    });
    expect(refused.status()).toBe(403);
  });

  test("THR-020: il piatto di un'altra famiglia è «non trovato», senza dettagli", async ({
    page,
    context,
    request,
  }) => {
    const foreign = randomUUID();
    const other = unique("altrafamiglia");
    await seedMember(request, {
      ...other,
      role: "planner",
      familyName: "Famiglia Beta",
      dishes: [{ name: "CANARY-BETA-DISH-1", id: foreign, notes: "CANARY-BETA-NOTE" }],
    });
    await enter(page, context, request, { label: "alfa", dishes: [PASTA] });
    await page.goto(`/piatti/${foreign}`);
    await expect(
      page.getByText("Non troviamo quello che cerchi. Potrebbe essere stato eliminato."),
    ).toBeVisible();
    await expect(page.getByRole("link", { name: "Torna ai piatti" })).toBeVisible();
    expect(await page.content()).not.toContain("CANARY-BETA");
    await page.goto(`/piatti/${foreign}/modifica`);
    await expect(page.getByLabel("Nome del piatto")).toHaveCount(0);
    expect(await page.content()).not.toContain("CANARY-BETA");
    await page.goto("/piatti");
    await expect(page.getByText("Pasta e ceci")).toBeVisible();
    expect(await page.content()).not.toContain("CANARY-BETA");
  });

  test("senza sessione le pagine dell'archivio portano all'accesso", async ({ page }) => {
    for (const path of ["/piatti", "/piatti/nuovo"]) {
      await page.goto(path);
      await expect(page).toHaveURL(/\/accedi$/);
    }
    const anonymous = await page.request.get("/api/v1/dishes");
    expect(anonymous.status()).toBe(401);
  });
});
