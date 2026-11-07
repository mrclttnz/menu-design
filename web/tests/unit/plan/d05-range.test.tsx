// @vitest-environment happy-dom
// SL-06a: D-05 «Scegli intervallo» e D-07 «Aggiungi un pasto a un giorno» da S-02
// (UX D-05, D-07; US-008 AC-008.3/.5; SR-060: al massimo 62 giorni).
// - menu «⋯» della settimana -> «Mostra un altro intervallo…» -> finestra «Scegli un intervallo»
//   con «Dal», «Al», «Mostra» e le scorciatoie «Questa settimana», «Prossime 2 settimane»;
// - validazione nel client: data finale non prima dell'iniziale, al massimo 62 giorni (nessuna
//   richiesta); se il server risponde `range_too_large {maxDays}` si mostra `error.range_too_large`;
// - «Aggiungi un pasto» (menu del giorno, solo A e P) elenca i tipi non presenti nel giorno e
//   invia `PUT .../presence {present: true}` con la versione letta (`GET` del pasto, `ETag`).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { authenticated, installFakeApi, SESSION_ROUTE, type FakeApi } from "../../support/fake-api";
import {
  meal,
  mealResponse,
  mealRoute,
  PLAN_ROUTE,
  planHandler,
  presenceRoute,
  type PlanOptions,
} from "../../support/plan";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function open(
  options: { role?: string; plan?: PlanOptions } = {},
): Promise<{ api: FakeApi; router: ReturnType<typeof createMemoryRouter> }> {
  const api = installFakeApi({
    [SESSION_ROUTE]: () =>
      authenticated({
        person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role: options.role ?? "planner" },
      }),
    [PLAN_ROUTE]: planHandler(options.plan ?? {}),
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: ["/piano"] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  await screen.findByRole("heading", { name: /Lunedì 19/ });
  return { api, router };
}

async function openRangeDialog(): Promise<HTMLElement> {
  const toolbar = screen.getByRole("button", { name: "Settimana successiva" })
    .parentElement as HTMLElement;
  const trigger = screen
    .getAllByRole("button")
    .find((b) => b.hasAttribute("aria-haspopup") && toolbar.contains(b));
  if (!trigger) throw new Error("manca il menu «⋯» della settimana");
  await userEvent.click(trigger);
  await userEvent.click(
    await screen.findByRole("menuitem", { name: "Mostra un altro intervallo…" }),
  );
  return screen.findByRole("dialog", { name: "Scegli un intervallo" });
}

function setDates(dialog: HTMLElement, from: string, to: string): void {
  fireEvent.change(within(dialog).getByLabelText("Dal"), { target: { value: from } });
  fireEvent.change(within(dialog).getByLabelText("Al"), { target: { value: to } });
}

describe("D-05: scegli intervallo", () => {
  it("la finestra ha Dal, Al, Mostra e le due scorciatoie", async () => {
    await open();
    const dialog = await openRangeDialog();
    expect(within(dialog).getByLabelText("Dal")).toBeTruthy();
    expect(within(dialog).getByLabelText("Al")).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Mostra" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Questa settimana" })).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: "Prossime 2 settimane" })).toBeTruthy();
  });

  it("dal 1° al 10° il piano mostra quei 10 giorni (AC-008.5)", async () => {
    const { api, router } = await open();
    const dialog = await openRangeDialog();
    api.set(PLAN_ROUTE, planHandler({ from: "2026-11-01", to: "2026-11-10" }));
    setDates(dialog, "2026-11-01", "2026-11-10");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostra" }));
    await screen.findByRole("heading", { name: /Domenica 1/ });
    const query = new URL(api.last(PLAN_ROUTE).path, "http://x").searchParams;
    expect([query.get("from"), query.get("to")]).toEqual(["2026-11-01", "2026-11-10"]);
    expect(router.state.location.search).toContain("da=2026-11-01");
    expect(router.state.location.search).toContain("a=2026-11-10");
  });

  it("62 giorni sono accettati", async () => {
    const { api } = await open();
    const dialog = await openRangeDialog();
    api.set(PLAN_ROUTE, planHandler({ from: "2026-10-01", to: "2026-12-01" }));
    setDates(dialog, "2026-10-01", "2026-12-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostra" }));
    await waitFor(() => {
      const query = new URL(api.last(PLAN_ROUTE).path, "http://x").searchParams;
      expect(query.get("to")).toBe("2026-12-01");
    });
  });

  it("63 giorni: errore nel client con il limite e nessuna richiesta", async () => {
    const { api } = await open();
    const before = api.count(PLAN_ROUTE);
    const dialog = await openRangeDialog();
    setDates(dialog, "2026-10-01", "2026-12-02");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostra" }));
    await within(dialog).findByText("Scegli al massimo 62 giorni.");
    expect(api.count(PLAN_ROUTE)).toBe(before);
  });

  it("la data finale prima dell'iniziale è un errore del client senza richiesta", async () => {
    const { api } = await open();
    const before = api.count(PLAN_ROUTE);
    const dialog = await openRangeDialog();
    setDates(dialog, "2026-10-10", "2026-10-09");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostra" }));
    await within(dialog).findByText("La data finale deve essere dopo quella iniziale.");
    expect(api.count(PLAN_ROUTE)).toBe(before);
  });

  it("una data mancante o non valida è «Inserisci una data valida.»", async () => {
    const { api } = await open();
    const before = api.count(PLAN_ROUTE);
    const dialog = await openRangeDialog();
    setDates(dialog, "", "2026-10-09");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostra" }));
    await within(dialog).findByText("Inserisci una data valida.");
    expect(api.count(PLAN_ROUTE)).toBe(before);
  });

  it("se il server risponde range_too_large mostra il limite del server", async () => {
    const { api } = await open();
    const dialog = await openRangeDialog();
    api.set(PLAN_ROUTE, () => problemResponse("range_too_large", { params: { maxDays: 62 } }));
    setDates(dialog, "2026-10-01", "2026-12-01");
    await userEvent.click(within(dialog).getByRole("button", { name: "Mostra" }));
    await screen.findByText("Scegli al massimo 62 giorni.");
  });

  it("«Prossime 2 settimane» riempie le date con 14 giorni dalla settimana corrente", async () => {
    await open();
    const dialog = await openRangeDialog();
    await userEvent.click(within(dialog).getByRole("button", { name: "Prossime 2 settimane" }));
    const from = (within(dialog).getByLabelText("Dal") as HTMLInputElement).value;
    const to = (within(dialog).getByLabelText("Al") as HTMLInputElement).value;
    const days = (Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000 + 1;
    expect(days).toBe(14);
    expect(from <= "2026-10-26" || from === "2026-10-19" || from === "2026-10-23").toBe(true);
  });

  it("un Membro può scegliere un intervallo (è lettura)", async () => {
    await open({ role: "member" });
    const dialog = await openRangeDialog();
    expect(within(dialog).getByRole("button", { name: "Mostra" })).toBeTruthy();
  });
});

describe("D-07: aggiungi un pasto a un giorno (AC-008.3)", () => {
  async function openAddMeal(day: string): Promise<void> {
    await userEvent.click(screen.getByRole("button", { name: `Azioni per ${day}` }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Aggiungi un pasto" }));
  }

  it("elenca i tipi non presenti nel giorno, compresi i pasti di default tolti", async () => {
    await open({
      plan: {
        meals: (date) =>
          date === "2026-10-21"
            ? [meal(date, "lunch")]
            : [meal(date, "lunch"), meal(date, "dinner")],
      },
    });
    await openAddMeal("Mercoledì 21");
    const dialog = await screen.findByRole("dialog", { name: "Aggiungi un pasto" });
    const names = within(dialog)
      .getAllByRole("button")
      .map((b) => b.textContent ?? "");
    expect(names.some((n) => n.includes("Cena"))).toBe(true); // di default, tolta da questo giorno
    expect(names.some((n) => n.includes("Merenda"))).toBe(true);
    expect(names.some((n) => n.includes("Colazione"))).toBe(true);
    expect(names.some((n) => n.includes("Altro pasto"))).toBe(true);
    expect(names.some((n) => n.includes("Pranzo"))).toBe(false);
  });

  it("«Altro pasto» non compare se il giorno ne ha già uno (M0/M1, nome fisso)", async () => {
    await open({
      plan: {
        meals: (date) =>
          date === "2026-10-21"
            ? [meal(date, "other", { contentVersion: 1 })]
            : [meal(date, "lunch"), meal(date, "dinner")],
      },
    });
    await openAddMeal("Mercoledì 21");
    const dialog = await screen.findByRole("dialog", { name: "Aggiungi un pasto" });
    expect(within(dialog).queryByRole("button", { name: /Altro pasto/ })).toBeNull();
  });

  it("scegliere «Merenda» legge la versione del pasto e invia present=true con quell'If-Match", async () => {
    const { api } = await open();
    const fixture = meal("2026-10-21", "snack", { present: false, contentVersion: 5 });
    api.set(mealRoute("2026-10-21", "snack"), () => mealResponse(fixture));
    api.set(presenceRoute("2026-10-21", "snack"), () =>
      mealResponse({ ...fixture, present: true, contentVersion: 6 }),
    );
    await openAddMeal("Mercoledì 21");
    const dialog = await screen.findByRole("dialog", { name: "Aggiungi un pasto" });
    await userEvent.click(within(dialog).getByRole("button", { name: /Merenda/ }));
    await waitFor(() => expect(api.count(presenceRoute("2026-10-21", "snack"))).toBe(1));
    const call = api.last(presenceRoute("2026-10-21", "snack"));
    expect(call.body).toEqual({ present: true });
    expect(call.headers.get("If-Match")).toBe('"5"');
  });

  it("dopo l'aggiunta il piano si rilegge e la Merenda compare in quel giorno", async () => {
    const { api } = await open();
    const fixture = meal("2026-10-21", "snack", { present: false });
    api.set(mealRoute("2026-10-21", "snack"), () => mealResponse(fixture));
    api.set(presenceRoute("2026-10-21", "snack"), () =>
      mealResponse({ ...fixture, present: true, contentVersion: 1 }),
    );
    await openAddMeal("Mercoledì 21");
    const dialog = await screen.findByRole("dialog", { name: "Aggiungi un pasto" });
    api.set(
      PLAN_ROUTE,
      planHandler({
        meals: (date) =>
          date === "2026-10-21"
            ? [
                meal(date, "lunch"),
                meal(date, "snack", { contentVersion: 1 }),
                meal(date, "dinner"),
              ]
            : [meal(date, "lunch"), meal(date, "dinner")],
      }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: /Merenda/ }));
    await waitFor(() => expect(screen.getAllByText("Merenda")).toHaveLength(1));
    const section = screen
      .getByRole("heading", { name: /Mercoledì 21/ })
      .closest("section") as HTMLElement;
    expect(within(section).getByText("Merenda")).toBeTruthy();
  });

  it("un Membro non ha né il menu del giorno né «Aggiungi un pasto»", async () => {
    await open({ role: "member" });
    expect(screen.queryByRole("button", { name: /Azioni per/ })).toBeNull();
    expect(screen.queryByText("Aggiungi un pasto")).toBeNull();
  });
});
