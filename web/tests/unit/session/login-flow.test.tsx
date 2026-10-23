// @vitest-environment happy-dom
// SL-03a: provider di sessione e pagina S-01 con l'accesso Google (UX S-01; US-001 AC-001.1,
// AC-001.5, AC-001.6; SR-023, SR-037; ADR-0004 rev. 3). Si prova il comportamento visibile e le
// chiamate all'API con un server simulato (`tests/support/fake-api.ts`), usando solo l'interfaccia
// già pubblica della SPA: `routes`, `AppProviders` e il client `api`.
//
// Contratto assunto (da confermare con il frontend-developer):
// - all'avvio la SPA chiama una volta `GET /api/v1/session` (con la cartella `src/session`, piano §1);
//   finché non risponde mostra uno stato di caricamento (`aria-busy="true"`) e NON offre ancora
//   «Continua con Google» (il cookie `__Host-csrf` arriva proprio da quella risposta);
// - la rotta `/piano` esiste (S-02 arriva con SL-06a; qui basta che non sia «non trovato») e le
//   viste che richiedono una sessione portano a `/accedi` se la sessione è anonima;
// - «Continua con Google» invia `POST /api/v1/auth/google/start` con `{purpose: "login", returnTo?}`,
//   `Content-Type: application/json` e `X-CSRF-Token` = cookie `__Host-csrf`; poi, e solo se
//   `redirectUrl` è un URL `https:` assoluto, `window.location.assign(redirectUrl)`;
// - l'esito di `authOutcome` (una sola volta) si mostra in S-01 con i testi del catalogo `it`.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import {
  anonymous,
  authenticated,
  installFakeApi,
  json,
  PENDING,
  SESSION_ROUTE,
  START_ROUTE,
  type FakeApi,
} from "../../support/fake-api";

const CSRF_COOKIE = "cookie-csrf-anonimo-0123456789";
const GOOGLE = /Continua con Google/;
const GOOGLE_URL = "https://accounts.google.com/o/oauth2/v2/auth?state=s&nonce=n";

beforeEach(() => {
  document.cookie = `__Host-csrf=${CSRF_COOKIE}; Secure; Path=/`;
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.cookie = "__Host-csrf=; Max-Age=0; Path=/";
  localStorage.clear();
  sessionStorage.clear();
});

async function renderAt(path: string): Promise<ReturnType<typeof createMemoryRouter>> {
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return router;
}

const loginButton = (): HTMLElement =>
  screen.queryByRole("button", { name: GOOGLE }) ?? screen.getByRole("link", { name: GOOGLE });

function stubAssign(): ReturnType<typeof vi.fn> {
  const spy = vi.spyOn(window.location, "assign").mockImplementation(() => undefined);
  return spy as unknown as ReturnType<typeof vi.fn>;
}

describe("sessione all'avvio", () => {
  it("chiama GET /api/v1/session una volta e, finché non risponde, mostra il caricamento senza il comando di accesso", async () => {
    const api = installFakeApi({ [SESSION_ROUTE]: PENDING });
    await renderAt("/accedi");
    await waitFor(() => expect(api.count(SESSION_ROUTE)).toBe(1));
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull();
    expect(screen.queryByRole("button", { name: GOOGLE })).toBeNull();
    expect(screen.queryByRole("link", { name: GOOGLE })).toBeNull();
    expect(api.unexpected).toEqual([]);
  });

  it("con una sessione anonima mostra S-01 con il comando di accesso e nessun'altra chiamata", async () => {
    const api = installFakeApi({ [SESSION_ROUTE]: () => anonymous() });
    const router = await renderAt("/accedi");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).not.toBeNull();
    expect(loginButton().textContent).toContain("Continua con Google");
    expect(router.state.location.pathname).toBe("/accedi");
    expect(document.querySelector('[aria-busy="true"]')).toBeNull();
    expect(api.calls.map((c) => `${c.method} ${c.path}`)).toEqual(["GET /api/v1/session"]);
  });

  it("con una sessione valida S-01 porta al piano (UX S-01: «se esiste una sessione valida redirect a S-02»)", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => authenticated() });
    const router = await renderAt("/accedi");
    await waitFor(() => expect(router.state.location.pathname).toBe("/piano"));
    expect(screen.queryByRole("button", { name: GOOGLE })).toBeNull();
    expect(screen.queryByText("Pagina non trovata")).toBeNull();
  });

  it("la radice porta al piano con una sessione e a /accedi senza", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => authenticated() });
    const withSession = await renderAt("/");
    await waitFor(() => expect(withSession.state.location.pathname).toBe("/piano"));
    cleanup();
    installFakeApi({ [SESSION_ROUTE]: () => anonymous() });
    const without = await renderAt("/");
    await waitFor(() => expect(without.state.location.pathname).toBe("/accedi"));
  });

  it("senza sessione /piano porta a /accedi (nessun dato del piano senza accesso)", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => anonymous() });
    const router = await renderAt("/piano");
    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).not.toBeNull();
  });

  it("se GET /session fallisce mostra l'errore generico con «Riprova», e riprova davvero", async () => {
    let healthy = false;
    const api = installFakeApi({
      [SESSION_ROUTE]: () => (healthy ? anonymous() : json({ code: "internal" }, 500)),
    });
    await renderAt("/accedi");
    const alert = await screen.findByRole("alert", {}, { timeout: 5000 });
    expect(alert.textContent).toContain("Qualcosa non ha funzionato. Riprova tra poco.");
    expect(screen.queryByRole("button", { name: GOOGLE })).toBeNull();
    healthy = true;
    const before = api.count(SESSION_ROUTE);
    await userEvent.click(within(alert).getByRole("button", { name: "Riprova" }));
    await waitFor(() => expect(api.count(SESSION_ROUTE)).toBeGreaterThan(before));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).not.toBeNull();
    expect(loginButton()).not.toBeNull();
  });

  it("senza rete mostra il messaggio di rete, non quello generico", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    await renderAt("/accedi");
    const alert = await screen.findByRole("alert", {}, { timeout: 5000 });
    expect(alert.textContent).toContain("Non riesco a collegarmi");
  });
});

describe("avvio dell'accesso con Google", () => {
  async function ready(api: FakeApi, path = "/accedi"): Promise<void> {
    await renderAt(path);
    await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" });
    expect(api.count(START_ROUTE)).toBe(0);
  }

  it("invia la POST di avvio con JSON, token CSRF del cookie e scopo login, poi va a Google", async () => {
    const assign = stubAssign();
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: () => json({ redirectUrl: GOOGLE_URL }),
    });
    await ready(api);
    await userEvent.click(loginButton());
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(assign).toHaveBeenCalledWith(GOOGLE_URL);
    const sent = api.last(START_ROUTE);
    expect(sent.headers.get("X-CSRF-Token")).toBe(CSRF_COOKIE);
    expect(sent.headers.get("Content-Type")).toBe("application/json");
    expect(sent.body).toMatchObject({ purpose: "login" });
    expect(JSON.stringify(sent.body)).not.toContain(CSRF_COOKIE);
    expect(api.unexpected).toEqual([]);
  });

  it("mentre attende, il comando mostra «Accesso in corso…» ed è disattivato (UX S-01, stato di caricamento)", async () => {
    const assign = stubAssign();
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: PENDING,
    });
    await ready(api);
    await userEvent.click(loginButton());
    const busy = await screen.findByRole("button", { name: /Accesso in corso/ });
    expect(
      (busy as HTMLButtonElement).disabled || busy.getAttribute("aria-disabled") === "true",
    ).toBe(true);
    await userEvent.click(busy);
    expect(api.count(START_ROUTE)).toBe(1);
    expect(assign).not.toHaveBeenCalled();
  });

  it("partendo da /piano chiede di tornare a /piano dopo il login (UX 5.1: ritorno alla pagina di partenza)", async () => {
    stubAssign();
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: () => json({ redirectUrl: GOOGLE_URL }),
    });
    await ready(api, "/piano");
    await userEvent.click(loginButton());
    await waitFor(() => expect(api.count(START_ROUTE)).toBe(1));
    expect(api.last(START_ROUTE).body).toMatchObject({ purpose: "login", returnTo: "/piano" });
  });

  it.each([
    ["javascript:alert(1)"],
    ["data:text/html,<script>alert(1)</script>"],
    ["http://accounts.google.com/o/oauth2/v2/auth"],
    ["//evil.example/login"],
    ["/accedi"],
    [""],
  ])("non segue un redirectUrl che non è un URL https assoluto (%s)", async (redirectUrl) => {
    const assign = stubAssign();
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: () => json({ redirectUrl }),
    });
    await ready(api);
    await userEvent.click(loginButton());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Non siamo riusciti a completare l'accesso. Riprova.");
    expect(assign).not.toHaveBeenCalled();
    expect(loginButton()).not.toBeNull();
  });

  it("se l'avvio fallisce mostra auth.failed e permette di riprovare", async () => {
    const assign = stubAssign();
    let failing = true;
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: () =>
        failing ? json({ code: "internal", status: 500 }, 500) : json({ redirectUrl: GOOGLE_URL }),
    });
    await ready(api);
    await userEvent.click(loginButton());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Non siamo riusciti a completare l'accesso. Riprova.");
    expect(alert.textContent).not.toContain("internal");
    failing = false;
    await userEvent.click(loginButton());
    await waitFor(() => expect(assign).toHaveBeenCalledWith(GOOGLE_URL));
  });

  it("un 403 csrf_failed ricarica la sessione (nuovo cookie) invece di mostrare il codice", async () => {
    stubAssign();
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: () =>
        json({ type: "about:blank", title: "x", status: 403, code: "csrf_failed" }, 403),
    });
    await ready(api);
    await userEvent.click(loginButton());
    await screen.findByRole("alert");
    expect(screen.queryByText(/csrf/i)).toBeNull();
    await waitFor(() => expect(api.count(SESSION_ROUTE)).toBeGreaterThan(1));
  });
});

describe("esiti dell'accesso (authOutcome, letto una volta dal server)", () => {
  it("AC-001.6: consenso annullato → messaggio generico e il comando per riprovare", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => anonymous({ code: "auth_cancelled" }) });
    await renderAt("/accedi");
    const message = await screen.findByText("Accesso annullato. Puoi riprovare quando vuoi.");
    expect(message.closest('[role="alert"], [role="status"]')).not.toBeNull();
    expect(loginButton()).not.toBeNull();
  });

  it("accesso non riuscito (token rifiutato) → auth.failed, senza dettagli", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => anonymous({ code: "auth_failed" }) });
    await renderAt("/accedi");
    const message = await screen.findByText("Non siamo riusciti a completare l'accesso. Riprova.");
    expect(message.closest('[role="alert"], [role="status"]')).not.toBeNull();
    expect(loginButton()).not.toBeNull();
  });

  it("AC-001.5: account senza famiglia → «Serve un invito», senza dati e con «Usa un altro account Google»", async () => {
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous({ code: "not_member" }),
      [START_ROUTE]: () => json({ redirectUrl: GOOGLE_URL }),
    });
    const assign = stubAssign();
    await renderAt("/accedi");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Serve un invito" }),
    ).not.toBeNull();
    expect(
      screen.getByText(/Questo account Google non fa ancora parte di una famiglia/),
    ).not.toBeNull();
    const other = screen.getByRole("button", { name: "Usa un altro account Google" });
    await userEvent.click(other);
    await waitFor(() => expect(assign).toHaveBeenCalledWith(GOOGLE_URL));
    expect(api.last(START_ROUTE).body).toMatchObject({ purpose: "login" });
  });

  it("un esito che arriva dopo il ritorno su /piano si vede in S-01 (la SPA non lo perde nel redirect)", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => anonymous({ code: "not_member" }) });
    const router = await renderAt("/piano");
    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Serve un invito" }),
    ).not.toBeNull();
  });

  it("un codice d'esito sconosciuto non si mostra mai: testo generico", async () => {
    installFakeApi({ [SESSION_ROUTE]: () => anonymous({ code: "qualcosa_di_nuovo" }) });
    await renderAt("/accedi");
    expect(
      await screen.findByText("Non siamo riusciti a completare l'accesso. Riprova."),
    ).not.toBeNull();
    expect(screen.queryByText(/qualcosa_di_nuovo/)).toBeNull();
  });

  it("senza esito S-01 non mostra alcun avviso", async () => {
    const api = installFakeApi({ [SESSION_ROUTE]: () => anonymous() });
    await renderAt("/accedi");
    await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" });
    expect(api.count(SESSION_ROUTE)).toBe(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
