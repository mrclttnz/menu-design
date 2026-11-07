// @vitest-environment happy-dom
// SL-06a: S-03 «Pasto» in sola lettura con «Togli questo pasto da questo giorno» (UX S-03,
// US-008 AC-008.4/.7, AC-011.4: M legge anche i pasti passati; DD-04, DD-05).
// - rotta `/piano/:data/:pastoId` (`:pastoId` = nome italiano del tipo, ADR-0009);
// - `GET /api/v1/meals/{data}/{tipo}/{slot}` con `ETag` = versione del contenuto;
// - A e P: dal menu «⋯» del pasto, «Togli questo pasto da questo giorno» invia `PUT .../presence`
//   con `{present: false}` e `If-Match: "<versione>"`; M non ha né menu né comando;
// - `412` -> `conflict.title.generic`; `403` -> `error.forbidden`; `404` -> `error.notFound`.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import {
  authenticated,
  installFakeApi,
  SESSION_ROUTE,
  type FakeApi,
  type Handler,
} from "../../support/fake-api";
import { detail, dish, dishRoute, withEtag } from "../../support/dishes";
import {
  dishItem,
  meal,
  mealResponse,
  mealRoute,
  PLAN_ROUTE,
  planHandler,
  presenceRoute,
  textItem,
  type MealFixture,
} from "../../support/plan";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const CECI = dish({ name: "Pasta e ceci", status: "tested" });

async function open(
  fixture: MealFixture,
  options: { role?: string; presence?: Handler; read?: Handler } = {},
): Promise<{ api: FakeApi; router: ReturnType<typeof createMemoryRouter> }> {
  const type = fixture.mealType;
  const api = installFakeApi({
    [SESSION_ROUTE]: () =>
      authenticated({
        person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role: options.role ?? "planner" },
      }),
    [mealRoute(fixture.date, type, fixture.slot)]: options.read ?? (() => mealResponse(fixture)),
    [presenceRoute(fixture.date, type, fixture.slot)]:
      options.presence ??
      ((request) =>
        mealResponse({
          ...fixture,
          present: (request.body as { present: boolean }).present,
          contentVersion: fixture.contentVersion + 1,
        })),
    [dishRoute(CECI.id)]: () => withEtag(detail(CECI)),
    [PLAN_ROUTE]: planHandler(),
  });
  await activateLocale("it");
  const names: Record<string, string> = {
    breakfast: "colazione",
    lunch: "pranzo",
    snack: "merenda",
    dinner: "cena",
    other: "altro",
  };
  const router = createMemoryRouter(routes, {
    initialEntries: [`/piano/${fixture.date}/${names[type] as string}`],
  });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { api, router };
}

const REMOVE = "Togli questo pasto da questo giorno";

async function openMenu(): Promise<void> {
  const trigger = (await screen.findAllByRole("button")).find((b) =>
    b.hasAttribute("aria-haspopup"),
  );
  if (!trigger) throw new Error("manca il menu «⋯» del pasto");
  await userEvent.click(trigger);
}

describe("S-03 in lettura", () => {
  it("chiede il pasto con data, tipo e slot e mostra tipo e data nell'intestazione", async () => {
    const { api } = await open(meal("2026-10-23", "dinner", { contentVersion: 3 }));
    expect(
      await screen.findByRole("heading", { level: 1, name: /Cena.*venerdì 23 ottobre/ }),
    ).toBeTruthy();
    expect(api.count(mealRoute("2026-10-23", "dinner"))).toBe(1);
    expect(api.unexpected).toEqual([]);
  });

  it("un pasto vuoto mostra «Ancora niente in questo pasto»", async () => {
    await open(meal("2026-10-23", "dinner"));
    await screen.findByText("Ancora niente in questo pasto");
  });

  it("elenca le voci nell'ordine, piatti e voci libere", async () => {
    await open(
      meal("2026-10-23", "dinner", {
        contentVersion: 2,
        items: [textItem("Pane e olio", 1), dishItem(CECI.id, 0)],
      }),
    );
    await screen.findByText("Pasta e ceci");
    const items = screen.getAllByRole("listitem").map((li) => li.textContent ?? "");
    const ceci = items.findIndex((t) => t.includes("Pasta e ceci"));
    const pane = items.findIndex((t) => t.includes("Pane e olio"));
    expect(ceci).toBeGreaterThanOrEqual(0);
    expect(pane).toBeGreaterThan(ceci);
    expect(screen.getByText("Voce libera")).toBeTruthy();
  });

  it("un pasto passato mostra l'avviso informativo (AC-011.4)", async () => {
    await open(meal("2026-10-21", "lunch", { contentVersion: 1 }));
    await screen.findByText(/Stai correggendo un pasto passato/);
  });

  it("un pasto di oggi o futuro non mostra l'avviso del passato", async () => {
    await open(meal("2026-10-24", "lunch"));
    await screen.findByText("Ancora niente in questo pasto");
    expect(screen.queryByText(/Stai correggendo un pasto passato/)).toBeNull();
  });

  it("un «Altro pasto» con nome mostra il nome", async () => {
    await open(meal("2026-10-24", "other", { name: "Aperitivo", contentVersion: 1 }));
    expect(await screen.findByRole("heading", { level: 1, name: /Aperitivo/ })).toBeTruthy();
  });

  it("un pasto che non esiste (404) mostra «Pagina non trovata»-tipo errore, non un guasto", async () => {
    await open(meal("2026-10-23", "dinner"), { read: () => problemResponse("not_found") });
    await screen.findByText(/non trovat/i);
  });

  it("un errore di caricamento offre «Riprova»", async () => {
    const fixture = meal("2026-10-23", "dinner");
    const { api } = await open(fixture, { read: () => problemResponse("internal") });
    await screen.findByRole("button", { name: "Riprova" });
    api.set(mealRoute(fixture.date, "dinner"), () => mealResponse(fixture));
    await userEvent.click(screen.getByRole("button", { name: "Riprova" }));
    await screen.findByText("Ancora niente in questo pasto");
  });
});

describe("S-03: togliere il pasto dal giorno (AC-008.4)", () => {
  it.each(["admin", "planner"])(
    "%s toglie il pasto con If-Match della versione letta",
    async (role) => {
      const fixture = meal("2026-10-24", "dinner", { contentVersion: 3 });
      const { api } = await open(fixture, { role });
      await screen.findByText("Ancora niente in questo pasto");
      await openMenu();
      await userEvent.click(await screen.findByRole("menuitem", { name: REMOVE }));
      await waitFor(() => expect(api.count(presenceRoute("2026-10-24", "dinner"))).toBe(1));
      const call = api.last(presenceRoute("2026-10-24", "dinner"));
      expect(call.body).toEqual({ present: false });
      expect(call.headers.get("If-Match")).toBe('"3"');
      expect(call.headers.get("Content-Type")).toContain("application/json");
      expect(call.headers.get("X-CSRF-Token")).toBeTruthy();
    },
  );

  it('un pasto mai scritto parte da If-Match "0"', async () => {
    const { api } = await open(meal("2026-10-24", "dinner"));
    await screen.findByText("Ancora niente in questo pasto");
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: REMOVE }));
    await waitFor(() => expect(api.count(presenceRoute("2026-10-24", "dinner"))).toBe(1));
    expect(api.last(presenceRoute("2026-10-24", "dinner")).headers.get("If-Match")).toBe('"0"');
  });

  it("un Membro non ha il menu né il comando (DD-04, AC-008.8)", async () => {
    await open(meal("2026-10-24", "dinner", { contentVersion: 1 }), { role: "member" });
    await screen.findByText("Ancora niente in questo pasto");
    expect(screen.queryByRole("menuitem", { name: REMOVE })).toBeNull();
    expect(screen.queryByText(REMOVE)).toBeNull();
    expect(screen.queryByRole("button", { name: /Aggiungi piatto o voce/ })).toBeNull();
    const trigger = screen.queryAllByRole("button").find((b) => b.hasAttribute("aria-haspopup"));
    expect(trigger).toBeUndefined();
  });

  it("412: titolo di conflitto generico e il pasto si rilegge", async () => {
    const fixture = meal("2026-10-24", "dinner", { contentVersion: 3 });
    const { api } = await open(fixture, {
      presence: () => problemResponse("conflict", { params: { current: { contentVersion: 4 } } }),
    });
    await screen.findByText("Ancora niente in questo pasto");
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: REMOVE }));
    await screen.findByText("Qualcuno ha modificato questi dati");
    await waitFor(() => expect(api.count(mealRoute("2026-10-24", "dinner"))).toBeGreaterThan(1));
  });

  it("403: error.forbidden, mai una schermata che finge che l'azione sia riuscita", async () => {
    await open(meal("2026-10-24", "dinner"), { presence: () => problemResponse("forbidden") });
    await screen.findByText("Ancora niente in questo pasto");
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: REMOVE }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Non hai il permesso");
  });

  it("429: error.rateLimited con i secondi di Retry-After", async () => {
    await open(meal("2026-10-24", "dinner"), {
      presence: () =>
        new Response(
          JSON.stringify({
            type: "about:blank",
            title: "HTTP 429",
            status: 429,
            code: "rate_limited",
          }),
          {
            status: 429,
            headers: { "Content-Type": "application/problem+json", "Retry-After": "42" },
          },
        ),
    });
    await screen.findByText("Ancora niente in questo pasto");
    await openMenu();
    await userEvent.click(await screen.findByRole("menuitem", { name: REMOVE }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("42");
  });

  it("il comando è dentro la pagina del pasto, non fuori: nessuna chiamata di scrittura alla sola apertura", async () => {
    const { api } = await open(meal("2026-10-24", "dinner"));
    await screen.findByText("Ancora niente in questo pasto");
    expect(api.count(presenceRoute("2026-10-24", "dinner"))).toBe(0);
    expect(within(document.body).queryByRole("alert")).toBeNull();
  });
});
