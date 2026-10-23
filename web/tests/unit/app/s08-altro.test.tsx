// @vitest-environment happy-dom
// SL-03b: S-08 «Altro» minima (UX S-08): chi sono (nome, ruolo, famiglia) e «Esci».
// US-001 AC-001.4 (il logout parte da qui), FR-004. Il resto delle voci (S-09 …) arriva con le
// loro slice: qui non si prova. Stessi aiuti di SL-03a: server simulato con le forme del piano
// (`tests/support/fake-api.ts`), catalogo `it` vero, nessun mock dell'i18n.
//
// Contratto assunto (da confermare con il frontend-developer):
// - la rotta `/altro` esiste in `routes` ed è dietro `RequireSession` (anonimi → `/accedi`);
// - mostra un solo `h1` «Altro», il testo `account.signedInAs` («Hai effettuato l'accesso come
//   {name}»), il ruolo del catalogo (`role.admin|planner|member`) e il nome della famiglia, tutti
//   presi da `GET /api/v1/session` (account.displayName, person.role, family.name);
// - «Esci» è un `button` che invia `POST /api/v1/auth/logout` con `{}` e `X-CSRF-Token` della
//   sessione; a uscita avvenuta si torna a `/accedi` con `auth.loggedOut`;
// - se il server risponde con un errore (per esempio `429`) si resta su `/altro`, compare un
//   `role="alert"` col testo del catalogo e «Esci» resta disponibile per riprovare;
// - non si mostra mai l'email, né l'ID della persona o dell'account.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import {
  anonymous,
  authenticated,
  CSRF_OF_SESSION,
  installFakeApi,
  LOGOUT_ROUTE,
  SESSION_ROUTE,
  type FakeApi,
} from "../../support/fake-api";
import { problemResponse } from "../../support/problem";

const ACCOUNT_ID = "3f1c2b6e-8a47-4c55-9d0e-1a2b3c4d5e6f";
const PERSON_ID = "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f";

beforeEach(() => {
  document.cookie = "__Host-csrf=cookie-csrf-anonimo-0123456789; Secure; Path=/";
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

async function openAltro(
  session: () => Response = () => authenticated(),
  extra: Record<string, () => Response | Promise<Response>> = {},
): Promise<{ api: FakeApi; router: ReturnType<typeof createMemoryRouter> }> {
  const api = installFakeApi({ [SESSION_ROUTE]: session, ...extra });
  const router = await renderAt("/altro");
  return { api, router };
}

describe("S-08 Altro: chi sono", () => {
  it("mostra il titolo, il nome, il ruolo e la famiglia dalla sessione", async () => {
    await openAltro();
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const main = screen.getByRole("main");
    expect(main.textContent).toContain("Hai effettuato l'accesso come Alice Alfa");
    expect(main.textContent).toContain("Amministratore");
    expect(main.textContent).toContain("Famiglia Alfa");
  });

  it.each([
    ["admin", "Amministratore"],
    ["planner", "Pianificatore"],
    ["member", "Membro"],
  ])("il ruolo %s si legge come «%s»", async (role, label) => {
    await openAltro(() => authenticated({ person: { id: PERSON_ID, role } }));
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    expect(screen.getByRole("main").textContent).toContain(label);
    for (const other of ["Amministratore", "Pianificatore", "Membro"]) {
      if (other !== label) expect(screen.getByRole("main").textContent).not.toContain(other);
    }
  });

  it("usa il nome della sessione, non uno fisso: un altro account mostra il suo nome", async () => {
    await openAltro(() =>
      authenticated({
        account: { id: ACCOUNT_ID, displayName: "Mario Membro" },
        family: {
          id: "7c9e6679-7425-40de-944b-e07fc1f90ae7",
          name: "Famiglia Beta",
          timezone: "Europe/Rome",
          today: "2026-10-23",
          status: "active",
        },
      }),
    );
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    const text = screen.getByRole("main").textContent ?? "";
    expect(text).toContain("Mario Membro");
    expect(text).toContain("Famiglia Beta");
    expect(text).not.toContain("Alice Alfa");
    expect(text).not.toContain("Famiglia Alfa");
  });

  it("un nome con markup viene mostrato come testo, mai interpretato (XSS)", async () => {
    const hostile = '<img src=x onerror="window.__pwned=1"><b>Eve</b>';
    await openAltro(() => authenticated({ account: { id: ACCOUNT_ID, displayName: hostile } }));
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    expect(screen.getByRole("main").textContent).toContain(hostile);
    expect(document.querySelector("main img")).toBeNull();
    expect(document.querySelector("main b")).toBeNull();
  });

  it("non mostra l'email né gli ID interni", async () => {
    await openAltro(() =>
      authenticated({
        account: { id: ACCOUNT_ID, displayName: "Alice Alfa", email: "a@example.test" },
      }),
    );
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    const html = document.body.innerHTML;
    expect(html).not.toContain("a@example.test");
    expect(html).not.toContain(ACCOUNT_ID);
    expect(html).not.toContain(PERSON_ID);
    expect(html).not.toContain(CSRF_OF_SESSION);
  });

  it("senza sessione porta a /accedi e non mostra nessun dato", async () => {
    const { router } = await openAltro(() => anonymous());
    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" }),
    ).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Esci" })).toBeNull();
  });

  it("ha un solo main, il collegamento «Vai al contenuto» e «Esci» è un vero pulsante (WCAG 2.4.1, 4.1.2)", async () => {
    await openAltro();
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    expect(screen.getAllByRole("main")).toHaveLength(1);
    const exit = screen.getByRole("button", { name: "Esci" });
    expect(exit.tagName).toBe("BUTTON");
    expect(exit.hasAttribute("disabled")).toBe(false);
  });
});

describe("S-08 Altro: Esci", () => {
  it("invia il logout con il token CSRF della sessione e torna a S-01 con «Hai effettuato l'uscita.»", async () => {
    const { api, router } = await openAltro(() => authenticated(), {
      [LOGOUT_ROUTE]: () => {
        api.set(SESSION_ROUTE, () => anonymous());
        return new Response(null, { status: 204 });
      },
    });
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Esci" }));

    await waitFor(() => expect(api.count(LOGOUT_ROUTE)).toBe(1));
    const sent = api.last(LOGOUT_ROUTE);
    expect(sent.headers.get("X-CSRF-Token")).toBe(CSRF_OF_SESSION);
    expect(sent.headers.get("Content-Type")).toBe("application/json");
    expect(sent.body).toEqual({});

    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    expect(await screen.findByText("Hai effettuato l'uscita.")).not.toBeNull();
    expect(screen.queryByText("Alice Alfa")).toBeNull();
    expect(api.unexpected).toEqual([]);
  });

  it("un secondo clic mentre l'uscita è in corso non invia un secondo logout", async () => {
    let release: (r: Response) => void = () => undefined;
    const { api } = await openAltro(() => authenticated(), {
      [LOGOUT_ROUTE]: () =>
        new Promise<Response>((resolve) => {
          release = resolve;
        }),
    });
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    const user = userEvent.setup();
    const button = screen.getByRole("button", { name: "Esci" });
    await user.click(button);
    await user.click(button);
    expect(api.count(LOGOUT_ROUTE)).toBe(1);
    release(new Response(null, { status: 204 }));
  });

  it("con 429 resta su /altro, mostra «Troppi tentativi…» col numero di secondi e permette di riprovare", async () => {
    let calls = 0;
    const { api, router } = await openAltro(() => authenticated(), {
      [LOGOUT_ROUTE]: () => {
        calls += 1;
        if (calls === 1)
          return problemResponse("rate_limited", { params: { retryAfterSeconds: 7 } });
        api.set(SESSION_ROUTE, () => anonymous());
        return new Response(null, { status: 204 });
      },
    });
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Esci" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Troppi tentativi. Riprova tra 7 secondi.");
    expect(router.state.location.pathname).toBe("/altro");
    expect(screen.getByText(/Alice Alfa/)).not.toBeNull();
    const retry = screen.getByRole("button", { name: "Esci" });
    expect(retry.hasAttribute("disabled")).toBe(false);

    await user.click(retry);
    await waitFor(() => expect(router.state.location.pathname).toBe("/accedi"));
    expect(api.count(LOGOUT_ROUTE)).toBe(2);
  });

  it("con un errore del server (500) resta su /altro con il messaggio generico e senza dettagli", async () => {
    const { router } = await openAltro(() => authenticated(), {
      [LOGOUT_ROUTE]: () => problemResponse("internal"),
    });
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    await userEvent.setup().click(screen.getByRole("button", { name: "Esci" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent ?? "").not.toMatch(/internal|500|HTTP/);
    expect(router.state.location.pathname).toBe("/altro");
  });
});
