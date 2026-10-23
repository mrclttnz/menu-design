// SL-03a: accesso con Google, sessione e logout nel browser vero, contro l'app collegata a un
// database di prova e al provider OIDC finto (08 §2, §4.2, §4.5). US-001 AC-001.1 (redirect e
// sessione; il piano della settimana arriva con SL-06a), AC-001.2, AC-001.4, AC-001.5, AC-001.6,
// AC-001.7; US-002 AC-002.1. SR-005, SR-031, SR-037, THR-005 (cookie, nessun token in storage o
// URL, nessuna richiesta verso terzi). Ogni test gira a 360 px e su desktop.
import { expect, test, type Page } from "@playwright/test";
import { expectNoSeriousA11y } from "./support/a11y";
import { observe } from "./support/browser";
import {
  actAs,
  denyConsent,
  seedBootstrap,
  seedMember,
  STUB_AVAILABLE,
  STUB_MISSING_REASON,
  STUB_URL,
  unique,
} from "./support/stub";

test.skip(!STUB_AVAILABLE, STUB_MISSING_REASON);

const LOGIN = /Continua con Google/;

async function startLogin(page: Page): Promise<void> {
  await page.goto("/accedi");
  const button = page
    .getByRole("button", { name: LOGIN })
    .or(page.getByRole("link", { name: LOGIN }));
  await expect(button).toBeVisible();
  await button.click();
}

test.describe("accesso di chi ha un bootstrap o è già in famiglia", () => {
  test("AC-002.1 + AC-001.1: il primo accesso con l'email del bootstrap porta al piano con una sessione", async ({
    page,
    context,
    request,
  }) => {
    const who = unique("gestore");
    await seedBootstrap(request, who.email, "Famiglia Gamma");
    await actAs(context, { ...who, name: "Gestore Gamma" });
    const seen = await observe(page);

    await startLogin(page);
    await page.waitForURL(/\/piano$/);

    // Nessun segreto o esito nell'URL (SR-037, ADR-0004 rev. 3).
    const url = new URL(page.url());
    expect(url.search).toBe("");
    expect(url.hash).toBe("");
    // Il piano non è la vista «non trovato» e non è tornato all'accesso.
    await expect(page.getByRole("heading", { name: "Pagina non trovata" })).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Accedi a Menu Design" })).toHaveCount(0);

    // Solo l'app e lo stub OIDC: nessuna richiesta verso terzi (SR-031, 08 §4.5).
    const allowed = new Set([new URL(page.url()).origin, new URL(STUB_URL).origin]);
    const foreign = seen.requests
      .map((r) => new URL(r.url()))
      .filter((u) => !allowed.has(u.origin));
    expect(foreign.map(String)).toEqual([]);
    expect(seen.pageErrors).toEqual([]);
    expect(await seen.cspViolations()).toEqual([]);
  });

  test("i cookie rispettano SR-005/SR-037 e il browser non conserva né legge il token di sessione", async ({
    page,
    context,
    request,
  }) => {
    const who = unique("cookie");
    await seedBootstrap(request, who.email);
    await actAs(context, who);
    await startLogin(page);
    await page.waitForURL(/\/piano$/);

    const cookies = await context.cookies(page.url());
    const session = cookies.find((c) => c.name === "__Host-session");
    expect(session, "cookie __Host-session impostato").toBeDefined();
    expect(session).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax", path: "/" });
    expect(session?.value.length ?? 0).toBeGreaterThanOrEqual(43);
    const csrf = cookies.find((c) => c.name === "__Host-csrf");
    expect(csrf, "cookie __Host-csrf impostato").toBeDefined();
    expect(csrf).toMatchObject({ httpOnly: false, secure: true, sameSite: "Strict", path: "/" });
    expect(cookies.find((c) => c.name === "__Host-auth_flow")).toBeUndefined();

    // JavaScript non vede il token di sessione; storage vuoti; il token non è nell'HTML.
    const visible = await page.evaluate(() => ({
      cookie: document.cookie,
      local: localStorage.length,
      session: sessionStorage.length,
      html: document.documentElement.outerHTML,
    }));
    expect(visible.cookie).not.toContain("__Host-session");
    expect(visible.cookie).not.toContain(session?.value ?? "x");
    expect(visible.local).toBe(0);
    expect(visible.session).toBe(0);
    expect(visible.html).not.toContain(session?.value ?? "x");
  });

  test("AC-001.2: ricaricando o riaprendo l'app si è ancora autenticati; S-01 porta al piano", async ({
    page,
    context,
    request,
  }) => {
    const who = unique("persiste");
    await seedBootstrap(request, who.email);
    await actAs(context, who);
    await startLogin(page);
    await page.waitForURL(/\/piano$/);

    await page.reload();
    await expect(page).toHaveURL(/\/piano$/);
    await page.goto("/accedi");
    await expect(page).toHaveURL(/\/piano$/);
    await page.goto("/");
    await expect(page).toHaveURL(/\/piano$/);

    const view = await (await page.request.get("/api/v1/session")).json();
    expect(view.authenticated).toBe(true);
    expect(view.person.role).toBe("admin");
    expect(view.family.name).toBe("Famiglia Alfa");
  });

  test("un membro già in famiglia entra con il proprio ruolo", async ({
    page,
    context,
    request,
  }) => {
    const who = unique("membro");
    await seedMember(request, { ...who, role: "member", displayName: "Mario Membro" });
    await actAs(context, who);
    await startLogin(page);
    await page.waitForURL(/\/piano$/);
    const view = await (await page.request.get("/api/v1/session")).json();
    expect(view.person.role).toBe("member");
    expect(view.account.displayName).toBe("Mario Membro");
    expect(JSON.stringify(view)).not.toContain(who.email);
  });

  test("AC-001.4: il logout invalida la sessione sul server e il vecchio cookie non vale più", async ({
    page,
    context,
    request,
    playwright,
  }) => {
    const who = unique("logout");
    await seedBootstrap(request, who.email);
    await actAs(context, who);
    await startLogin(page);
    await page.waitForURL(/\/piano$/);

    const stolen = (await context.cookies(page.url())).find((c) => c.name === "__Host-session");
    expect(stolen).toBeDefined();
    const view = await (await page.request.get("/api/v1/session")).json();
    const origin = new URL(page.url()).origin;
    const out = await page.request.post("/api/v1/auth/logout", {
      headers: { "X-CSRF-Token": view.csrfToken, Origin: origin },
      data: {},
    });
    expect(out.status()).toBe(204);

    await page.goto("/piano");
    await expect(page).toHaveURL(/\/accedi$/);

    // Chi aveva copiato il cookie non entra (THR-005).
    const thief = await playwright.request.newContext({
      baseURL: origin,
      extraHTTPHeaders: { Cookie: `__Host-session=${stolen?.value ?? ""}` },
    });
    const stolenView = await (await thief.get("/api/v1/session")).json();
    expect(stolenView.authenticated).toBe(false);
    await thief.dispose();
  });
});

test.describe("esiti senza sessione", () => {
  test("AC-001.5: un account Google senza famiglia vede «Serve un invito» e non entra", async ({
    page,
    context,
  }) => {
    const who = unique("orfano");
    await actAs(context, who);
    await startLogin(page);
    await expect(page).toHaveURL(/\/accedi$/);
    await expect(page.getByRole("heading", { level: 1, name: "Serve un invito" })).toBeVisible();
    await expect(page.getByText(/non fa ancora parte di una famiglia/)).toBeVisible();
    await expect(page.getByRole("button", { name: "Usa un altro account Google" })).toBeVisible();
    expect(new URL(page.url()).search).toBe("");
    expect(await page.content()).not.toContain(who.email);

    const cookies = await context.cookies(page.url());
    expect(cookies.find((c) => c.name === "__Host-session")).toBeUndefined();
    const view = await (await page.request.get("/api/v1/session")).json();
    expect(view.authenticated).toBe(false);

    // L'esito si legge una volta: ricaricando si torna a S-01 normale.
    await page.reload();
    await expect(
      page.getByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).toBeVisible();
    await expect(page.getByText(/non fa ancora parte di una famiglia/)).toHaveCount(0);
  });

  test("AC-001.5: lo stato «Serve un invito» non ha violazioni di accessibilità", async ({
    page,
    context,
  }) => {
    await actAs(context, unique("a11y"));
    await startLogin(page);
    await expect(page.getByRole("heading", { level: 1, name: "Serve un invito" })).toBeVisible();
    await expectNoSeriousA11y(page, "S-01 Serve un invito");
  });

  test("AC-001.6: il consenso annullato su Google dà un messaggio generico e resta anonimo", async ({
    page,
    context,
  }) => {
    await denyConsent(context);
    await startLogin(page);
    await expect(page).toHaveURL(/\/accedi$/);
    await expect(page.getByText("Accesso annullato. Puoi riprovare quando vuoi.")).toBeVisible();
    await expect(
      page.getByRole("button", { name: LOGIN }).or(page.getByRole("link", { name: LOGIN })),
    ).toBeVisible();
    const view = await (await page.request.get("/api/v1/session")).json();
    expect(view.authenticated).toBe(false);
  });

  test("AC-001.7: un'email non verificata è rifiutata con un messaggio generico", async ({
    page,
    context,
    request,
  }) => {
    const who = unique("nonverificata");
    await seedBootstrap(request, who.email);
    await actAs(context, { ...who, email_verified: false });
    await startLogin(page);
    await expect(page).toHaveURL(/\/accedi$/);
    await expect(
      page.getByText("Non siamo riusciti a completare l'accesso. Riprova."),
    ).toBeVisible();
    const view = await (await page.request.get("/api/v1/session")).json();
    expect(view.authenticated).toBe(false);
  });

  test("«Usa un altro account Google» riavvia l'accesso", async ({ page, context }) => {
    await actAs(context, unique("primo"));
    await startLogin(page);
    await expect(page.getByRole("heading", { level: 1, name: "Serve un invito" })).toBeVisible();
    const second = unique("secondo");
    await actAs(context, second);
    await page.getByRole("button", { name: "Usa un altro account Google" }).click();
    await expect(page).toHaveURL(/\/accedi$/);
    await expect(page.getByRole("heading", { level: 1, name: "Serve un invito" })).toBeVisible();
  });
});
