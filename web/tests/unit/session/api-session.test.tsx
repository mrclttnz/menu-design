// @vitest-environment happy-dom
// SL-03a: il client `api` condiviso e la sessione (SR-023, SR-037, THR-005, THR-007; UX 5.1
// «Sessione scaduta (401)»; ADR-0004: token CSRF restituito da GET /session, nessun token in
// storage). Si prova il comportamento osservabile del client già pubblico (`api`) dopo che la
// SPA ha caricato la sessione, con un server simulato.
//
// Contratto assunto:
// - ogni richiesta non sicura dell'`api` condiviso porta `X-CSRF-Token`: con una sessione
//   autenticata il `csrfToken` di GET /session, senza sessione il cookie `__Host-csrf`
//   (doppio invio); le `GET` non portano il header;
// - un `401` con `code: unauthenticated` su una qualunque chiamata autenticata azzera la sessione,
//   porta a `/accedi` e mostra `auth.sessionExpired`; la SPA ricarica la sessione (ora anonima);
// - il token CSRF e ogni dato di sessione restano in memoria: né `localStorage`, né
//   `sessionStorage`, né scritture di cookie dalla SPA, né log in console.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../../../src/api/client";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { problemResponse } from "../../support/problem";
import {
  anonymous,
  authenticated,
  CSRF_OF_SESSION,
  installFakeApi,
  LOGOUT_ROUTE,
  SESSION_ROUTE,
  type FakeApi,
} from "../../support/fake-api";

const CSRF_COOKIE = "cookie-csrf-anonimo-0123456789";

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

async function signedIn(extra: Record<string, () => Response | Promise<Response>> = {}): Promise<{
  api: FakeApi;
  router: ReturnType<typeof createMemoryRouter>;
}> {
  const fake = installFakeApi({ [SESSION_ROUTE]: () => authenticated(), ...extra });
  const router = await renderAt("/piano");
  await waitFor(() => expect(fake.count(SESSION_ROUTE)).toBe(1));
  await waitFor(() => expect(router.state.location.pathname).toBe("/piano"));
  // lascia il tempo alla SPA di aver ricevuto la sessione prima di usare il client
  await screen.findByRole("main");
  await waitFor(() => expect(document.querySelector('[aria-busy="true"]')).toBeNull());
  return { api: fake, router };
}

describe("token CSRF del client condiviso", () => {
  it("con una sessione autenticata le scritture portano il csrfToken di GET /session, non il cookie anonimo", async () => {
    const { api: fake } = await signedIn({
      [LOGOUT_ROUTE]: () => new Response(null, { status: 204 }),
    });
    const result = await api.post("/api/v1/auth/logout", { body: {} });
    expect(result.ok).toBe(true);
    const sent = fake.last(LOGOUT_ROUTE);
    expect(sent.headers.get("X-CSRF-Token")).toBe(CSRF_OF_SESSION);
    expect(sent.headers.get("Content-Type")).toBe("application/json");
  });

  it("le richieste di sola lettura non portano il header CSRF", async () => {
    const { api: fake } = await signedIn({
      "GET /api/v1/me": () => new Response("{}", { status: 200 }),
    });
    await api.get("/api/v1/me");
    expect(fake.last("GET /api/v1/me").headers.has("X-CSRF-Token")).toBe(false);
  });

  it("senza sessione le scritture portano il cookie anonimo __Host-csrf (doppio invio)", async () => {
    const fake = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      "POST /api/v1/auth/google/start": () => new Response("{}", { status: 200 }),
    });
    await renderAt("/accedi");
    await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" });
    await api.post("/api/v1/auth/google/start", { body: { purpose: "login" } });
    expect(fake.last("POST /api/v1/auth/google/start").headers.get("X-CSRF-Token")).toBe(
      CSRF_COOKIE,
    );
  });

  it("dopo il logout (sessione anonima) il token della sessione non viene più inviato", async () => {
    const { api: fake } = await signedIn({
      [LOGOUT_ROUTE]: () => {
        fake.set(SESSION_ROUTE, () => anonymous());
        return new Response(null, { status: 204 });
      },
      "POST /api/v1/other": () => new Response("{}", { status: 200 }),
    });
    await api.post("/api/v1/auth/logout", { body: {} });
    await waitFor(() => expect(fake.count(SESSION_ROUTE)).toBeGreaterThan(1));
    await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" });
    await api.post("/api/v1/other", { body: {} });
    expect(fake.last("POST /api/v1/other").headers.get("X-CSRF-Token")).not.toBe(CSRF_OF_SESSION);
  });
});

describe("sessione scaduta (401)", () => {
  it("un 401 su una chiamata autenticata porta a /accedi con «La sessione è scaduta»", async () => {
    const { api: fake, router } = await signedIn({
      "GET /api/v1/me": () => problemResponse("unauthenticated"),
    });
    fake.set(SESSION_ROUTE, () => anonymous());
    const result = await api.get("/api/v1/me");
    expect(result.ok).toBe(false);
    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    const message = await screen.findByText(
      "La sessione è scaduta. Accedi di nuovo per continuare.",
    );
    expect(message.closest('[role="alert"], [role="status"]')).not.toBeNull();
    expect(
      screen.queryByRole("button", { name: /Continua con Google/ }) ??
        screen.queryByRole("link", { name: /Continua con Google/ }),
    ).not.toBeNull();
  });

  it("dopo il 401 la SPA ricarica la sessione invece di fidarsi di quella vecchia", async () => {
    const { api: fake } = await signedIn({
      "GET /api/v1/me": () => problemResponse("unauthenticated"),
    });
    fake.set(SESSION_ROUTE, () => anonymous());
    const before = fake.count(SESSION_ROUTE);
    await api.get("/api/v1/me");
    await waitFor(() => expect(fake.count(SESSION_ROUTE)).toBeGreaterThan(before));
  });

  it("un 401 non fa partire un secondo avviso se più chiamate falliscono insieme", async () => {
    const { api: fake, router } = await signedIn({
      "GET /api/v1/me": () => problemResponse("unauthenticated"),
    });
    fake.set(SESSION_ROUTE, () => anonymous());
    await Promise.all([api.get("/api/v1/me"), api.get("/api/v1/me"), api.get("/api/v1/me")]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    expect(await screen.findAllByText(/La sessione è scaduta/)).toHaveLength(1);
  });

  it("un 403 csrf_failed non è una sessione scaduta: nessun redirect a /accedi", async () => {
    const { router } = await signedIn({
      "POST /api/v1/x": () => problemResponse("csrf_failed"),
    });
    await api.post("/api/v1/x", { body: {} });
    expect(router.state.location.pathname).toBe("/piano");
    expect(screen.queryByText(/La sessione è scaduta/)).toBeNull();
  });
});

describe("segreti nel browser (SR-037, THR-005)", () => {
  it("il token CSRF e i dati di sessione non vanno in storage, cookie né console", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const debug = vi.spyOn(console, "debug").mockImplementation(() => undefined);
    const { api: fake } = await signedIn({
      [LOGOUT_ROUTE]: () => new Response(null, { status: 204 }),
    });
    await api.post("/api/v1/auth/logout", { body: {} });
    expect(fake.last(LOGOUT_ROUTE).headers.get("X-CSRF-Token")).toBe(CSRF_OF_SESSION);

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
    expect(document.cookie).not.toContain(CSRF_OF_SESSION);
    const everything = [log, warn, error, info, debug]
      .flatMap((spy) => spy.mock.calls.flat())
      .map(String)
      .join("\n");
    expect(everything).not.toContain(CSRF_OF_SESSION);
    expect(everything).not.toContain("Alice Alfa");
  });

  it("la SPA non ha mai bisogno di leggere o scrivere il cookie di sessione", async () => {
    await signedIn();
    expect(document.cookie).not.toMatch(/__Host-session/);
    const writes = vi.spyOn(document, "cookie", "set");
    await api.get("/api/v1/session");
    expect(writes).not.toHaveBeenCalled();
  });
});
