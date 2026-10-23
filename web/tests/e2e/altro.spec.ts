// SL-03b: S-08 «Altro» minima e limite sugli avvii di accesso, nel browser vero contro l'app
// collegata a un database di prova e al provider OIDC finto (08 §2, §4.2, §4.5).
// US-001 AC-001.4 (uscita da «Altro»), AC-001.9 (31° avvio → messaggio con i secondi), FR-004.
// SR-059, SR-031. Ogni test gira a 360 px e su desktop; ogni contesto ha un IP proprio
// (`isolateIp`, dentro `actAs`), così i 30 avvii per IP non si consumano tra test diversi.
import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11y } from "./support/a11y";
import { observe } from "./support/browser";
import {
  actAs,
  isolateIp,
  seedMember,
  STUB_AVAILABLE,
  STUB_MISSING_REASON,
  unique,
} from "./support/stub";

test.skip(!STUB_AVAILABLE, STUB_MISSING_REASON);

const LOGIN = /Continua con Google/;

async function openAltro(page: Page): Promise<void> {
  await page.getByRole("navigation").getByRole("link", { name: "Altro" }).click();
  await page.waitForURL(/\/altro$/);
}

async function signIn(page: Page): Promise<void> {
  await page.goto("/accedi");
  const button = page
    .getByRole("button", { name: LOGIN })
    .or(page.getByRole("link", { name: LOGIN }));
  await expect(button).toBeVisible();
  await button.click();
  await page.waitForURL(/\/piano$/);
}

test.describe("S-08 Altro", () => {
  test("FR-004: mostra nome, ruolo e famiglia di chi è collegato, e «Esci»", async ({
    page,
    context,
    request,
  }) => {
    const who = unique("altro");
    await seedMember(request, {
      ...who,
      role: "planner",
      displayName: "Paola Pianificatrice",
      familyName: "Famiglia Delta",
    });
    await actAs(context, { ...who, name: "Paola Pianificatrice" });
    const seen = await observe(page);
    await signIn(page);

    await openAltro(page);
    await expect(page.getByRole("heading", { level: 1, name: "Altro" })).toBeVisible();
    const main = page.getByRole("main");
    await expect(main).toContainText("Hai effettuato l'accesso come Paola Pianificatrice");
    await expect(main).toContainText("Pianificatore");
    await expect(main).toContainText("Famiglia Delta");
    await expect(page.getByRole("button", { name: "Esci" })).toBeVisible();
    // Nessuna email né ID in pagina; nessun errore, nessuna richiesta verso terzi.
    expect(await page.content()).not.toContain(who.email);
    expect(seen.pageErrors).toEqual([]);
    expect(await seen.cspViolations()).toEqual([]);
  });

  test("S-08 non ha violazioni di accessibilità gravi", async ({ page, context, request }) => {
    const who = unique("altro-a11y");
    await seedMember(request, { ...who, role: "member", displayName: "Mario Membro" });
    await actAs(context, who);
    await signIn(page);
    await openAltro(page);
    await expect(page.getByRole("heading", { level: 1, name: "Altro" })).toBeVisible();
    await expectNoSeriousA11y(page, "S-08 Altro");
  });

  test("AC-001.4: «Esci» invalida la sessione sul server e porta a S-01 con «Hai effettuato l'uscita.»", async ({
    page,
    context,
    request,
    playwright,
  }) => {
    const who = unique("esci");
    await seedMember(request, { ...who, role: "admin", displayName: "Alice Alfa" });
    await actAs(context, who);
    await signIn(page);
    await openAltro(page);
    const stolen = (await context.cookies(page.url())).find((c) => c.name === "__Host-session");
    expect(stolen).toBeDefined();

    await page.getByRole("button", { name: "Esci" }).click();
    await page.waitForURL(/\/accedi$/);
    await expect(page.getByText("Hai effettuato l'uscita.")).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).toBeVisible();

    // Nel browser non resta la sessione e «Altro» non è più raggiungibile.
    const cookies = await context.cookies(page.url());
    expect(cookies.find((c) => c.name === "__Host-session")).toBeUndefined();
    await page.goto("/altro");
    await expect(page).toHaveURL(/\/accedi$/);

    // Sul server il vecchio cookie non vale più (THR-005).
    const origin = new URL(page.url()).origin;
    const thief = await playwright.request.newContext({
      baseURL: origin,
      extraHTTPHeaders: { Cookie: `__Host-session=${stolen?.value ?? ""}` },
    });
    expect((await (await thief.get("/api/v1/session")).json()).authenticated).toBe(false);
    await thief.dispose();
  });

  test("senza sessione «Altro» porta a S-01 e non mostra nulla", async ({ page, context }) => {
    await isolateIp(context);
    await page.goto("/altro");
    await expect(page).toHaveURL(/\/accedi$/);
    await expect(page.getByRole("button", { name: "Esci" })).toHaveCount(0);
  });
});

test.describe("AC-001.9: troppi avvii di accesso dallo stesso IP", () => {
  test("il 31° avvio mostra «Troppi tentativi. Riprova tra N secondi.» e resta su S-01", async ({
    page,
    context,
  }) => {
    await isolateIp(context);
    await page.goto("/accedi");
    await expect(
      page.getByRole("button", { name: LOGIN }).or(page.getByRole("link", { name: LOGIN })),
    ).toBeVisible();
    const origin = new URL(page.url()).origin;
    const csrf = (await context.cookies(page.url())).find((c) => c.name === "__Host-csrf");
    expect(csrf, "cookie __Host-csrf impostato da GET /session").toBeDefined();

    // 30 avvii dallo stesso IP passano (la 30ª è l'ultima consentita)...
    for (let n = 1; n <= 30; n += 1) {
      const response = await page.request.post("/api/v1/auth/google/start", {
        headers: { "X-CSRF-Token": csrf?.value ?? "", Origin: origin },
        data: { purpose: "login" },
      });
      expect(response.status(), `avvio ${n}`).toBe(200);
    }
    // ... il 31°, dal pulsante, mostra il messaggio con i secondi e non parte per Google.
    await page
      .getByRole("button", { name: LOGIN })
      .or(page.getByRole("link", { name: LOGIN }))
      .click();
    const alert = page.getByRole("alert");
    await expect(alert).toContainText(/Troppi tentativi\. Riprova tra \d+ second[oi]\./);
    await expect(page).toHaveURL(/\/accedi$/);
    expect(await page.content()).not.toMatch(/rate_limited|429/);
    await expectNoSeriousA11y(page, "S-01 troppi tentativi");

    // Un altro IP (un altro contesto) non è toccato.
    const other = await context.browser()?.newContext({ baseURL: origin });
    if (other) {
      await isolateIp(other);
      const page2 = await other.newPage();
      await page2.goto("/accedi");
      await expect(
        page2.getByRole("button", { name: LOGIN }).or(page2.getByRole("link", { name: LOGIN })),
      ).toBeVisible();
      await other.close();
    }
  });
});
