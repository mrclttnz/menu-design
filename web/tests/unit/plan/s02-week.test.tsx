// @vitest-environment happy-dom
// SL-06a: S-02 «Piano: settimana» (UX S-02, US-008 AC-008.1/.3/.4/.5, AC-003.3, AC-024.1/.4).
// - `GET /api/v1/plan` (senza parametri: settimana corrente, da lunedì, nel fuso della famiglia);
// - un blocco per giorno («Lunedì 19»), badge «Oggi» sul giorno corrente e «Passato» prima;
// - per ogni pasto una riga che apre S-03 (`/piano/:data/:pastoId`); riga vuota con «Aggiungi
//   piatto» per A e P, «Ancora niente» per M (DD-04: i comandi non ci sono);
// - navigazione ‹ ›, «Oggi», intervallo nell'indirizzo (`?da=&a=`); stati vuoto/caricamento/errore.
// I testi sono quelli di docs/03-ux.md §7.3 (catalogo `it` reale, nessun mock dell'i18n).
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import {
  authenticated,
  installFakeApi,
  PENDING,
  SESSION_ROUTE,
  type FakeApi,
  type Handler,
} from "../../support/fake-api";
import {
  dishItem,
  meal,
  PLAN_ROUTE,
  planHandler,
  textItem,
  type PlanOptions,
} from "../../support/plan";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const PASTA = "d0000000-0000-4000-8000-000000000001";
const DAYS = [
  "Lunedì 19",
  "Martedì 20",
  "Mercoledì 21",
  "Giovedì 22",
  "Venerdì 23",
  "Sabato 24",
  "Domenica 25",
];

async function open(
  options: { role?: string; plan?: PlanOptions | Handler; url?: string } = {},
): Promise<{ api: FakeApi; router: ReturnType<typeof createMemoryRouter> }> {
  const plan = typeof options.plan === "function" ? options.plan : planHandler(options.plan ?? {});
  const api = installFakeApi({
    [SESSION_ROUTE]: () =>
      authenticated({
        person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role: options.role ?? "planner" },
      }),
    [PLAN_ROUTE]: plan,
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [options.url ?? "/piano"] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { api, router };
}

const dayHeading = (name: string): HTMLElement =>
  screen.getByRole("heading", { name: new RegExp(name) });

describe("S-02: la settimana corrente (AC-008.1)", () => {
  it("chiede il piano e mostra sette giorni da lunedì a domenica", async () => {
    const { api } = await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    for (const day of DAYS) expect(dayHeading(day)).toBeTruthy();
    const call = api.last(PLAN_ROUTE);
    const query = new URL(call.path, "http://x").searchParams;
    // Senza parametri la settimana corrente la sceglie il server; se il client li manda, sono questi.
    if (query.has("from")) {
      expect([query.get("from"), query.get("to")]).toEqual(["2026-10-19", "2026-10-25"]);
    }
    expect(api.unexpected).toEqual([]);
  });

  it("mostra l'intervallo della settimana e i comandi di navigazione", async () => {
    await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.getByText(/19\s*-\s*25 ottobre 2026/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Settimana precedente" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Settimana successiva" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Oggi" })).toBeTruthy();
  });

  it("mostra i pasti di default di ogni giorno: Pranzo e Cena", async () => {
    await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.getAllByText("Pranzo")).toHaveLength(7);
    expect(screen.getAllByText("Cena")).toHaveLength(7);
    expect(screen.queryByText("Merenda")).toBeNull();
  });

  it("il giorno di oggi ha il badge «Oggi» e solo i giorni prima hanno «Passato»", async () => {
    await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    const badgeOf = (day: string, label: string): HTMLElement | null =>
      within(dayHeading(day).closest("section") ?? document.body).queryByText(label, {
        selector: ".badge",
      });
    expect(badgeOf("Venerdì 23", "Oggi")).not.toBeNull();
    for (const day of DAYS.filter((d) => d !== "Venerdì 23")) {
      expect(badgeOf(day, "Oggi"), day).toBeNull();
    }
    for (const day of DAYS.slice(0, 4)) expect(badgeOf(day, "Passato"), day).not.toBeNull();
    for (const day of DAYS.slice(4)) expect(badgeOf(day, "Passato"), day).toBeNull();
  });

  it("una riga di pasto porta a S-03 con la data e il pastoId del tipo", async () => {
    await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    const section = dayHeading("Lunedì 19").closest("section") as HTMLElement;
    const link = within(section).getByRole("link", { name: /Pranzo/ });
    expect(link.getAttribute("href")).toBe("/piano/2026-10-19/pranzo");
    const dinner = within(section).getByRole("link", { name: /Cena/ });
    expect(dinner.getAttribute("href")).toBe("/piano/2026-10-19/cena");
  });
});

describe("S-02: contenuto dei pasti", () => {
  it("riassume piatti (dai riferimenti), voci libere e stato speciale", async () => {
    await open({
      plan: {
        dishes: { [PASTA]: { name: "Pasta e ceci", status: "tested", archived: false } },
        meals: (date) =>
          date === "2026-10-20"
            ? [
                meal(date, "lunch", {
                  contentVersion: 2,
                  items: [dishItem(PASTA, 0), textItem("Insalata mista", 1)],
                }),
                meal(date, "dinner", { contentVersion: 1, special: "restaurant" }),
              ]
            : [meal(date, "lunch"), meal(date, "dinner")],
      },
    });
    const section = (await screen.findByRole("heading", { name: /Martedì 20/ })).closest(
      "section",
    ) as HTMLElement;
    expect(within(section).getByText(/Pasta e ceci/)).toBeTruthy();
    expect(within(section).getByText(/Insalata mista/)).toBeTruthy();
    expect(within(section).getByText("Ristorante")).toBeTruthy();
  });

  it("un pasto aggiunto a un solo giorno compare solo lì (AC-008.3)", async () => {
    await open({
      plan: {
        meals: (date) =>
          date === "2026-10-21"
            ? [
                meal(date, "lunch"),
                meal(date, "snack", { contentVersion: 1 }),
                meal(date, "dinner"),
              ]
            : [meal(date, "lunch"), meal(date, "dinner")],
      },
    });
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.getAllByText("Merenda")).toHaveLength(1);
    const section = dayHeading("Mercoledì 21").closest("section") as HTMLElement;
    expect(within(section).getByText("Merenda")).toBeTruthy();
  });

  it("un pasto di default tolto da un giorno non compare in quel giorno (AC-008.4)", async () => {
    await open({
      plan: {
        meals: (date) =>
          date === "2026-10-24"
            ? [meal(date, "lunch")]
            : [meal(date, "lunch"), meal(date, "dinner")],
      },
    });
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.getAllByText("Cena")).toHaveLength(6);
    const section = dayHeading("Sabato 24").closest("section") as HTMLElement;
    expect(within(section).queryByText("Cena")).toBeNull();
  });

  it("un «Altro pasto» con nome mostra il nome scelto (non la parola generica)", async () => {
    await open({
      plan: {
        meals: (date) =>
          date === "2026-10-24"
            ? [meal(date, "other", { name: "Aperitivo", contentVersion: 1 })]
            : [meal(date, "lunch")],
      },
    });
    const section = (await screen.findByRole("heading", { name: /Sabato 24/ })).closest(
      "section",
    ) as HTMLElement;
    expect(within(section).getByText("Aperitivo")).toBeTruthy();
  });
});

describe("S-02: permessi (DD-04, AC-024.1)", () => {
  it.each(["admin", "planner"])("%s vede «Aggiungi piatto» e il menu del giorno", async (role) => {
    await open({ role });
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.getAllByRole("button", { name: /Aggiungi piatto/ }).length).toBe(14);
    expect(screen.getByRole("button", { name: "Azioni per Lunedì 19" })).toBeTruthy();
    expect(screen.queryByText("Ancora niente")).toBeNull();
  });

  it("un Membro vede solo la lettura: «Ancora niente», nessun comando di modifica", async () => {
    await open({ role: "member" });
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.getAllByText("Ancora niente")).toHaveLength(14);
    expect(screen.queryByRole("button", { name: /Aggiungi piatto/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Azioni per/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Aggiungi un pasto/ })).toBeNull();
  });
});

describe("S-02: navigazione e intervallo nell'indirizzo", () => {
  it("«Settimana successiva» chiede la settimana dopo e la scrive nell'indirizzo", async () => {
    const { api, router } = await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    api.set(PLAN_ROUTE, planHandler({ from: "2026-10-26", to: "2026-11-01" }));
    await userEvent.click(screen.getByRole("button", { name: "Settimana successiva" }));
    await screen.findByRole("heading", { name: /Lunedì 26/ });
    const query = new URL(api.last(PLAN_ROUTE).path, "http://x").searchParams;
    expect([query.get("from"), query.get("to")]).toEqual(["2026-10-26", "2026-11-01"]);
    expect(router.state.location.search).toContain("da=2026-10-26");
    expect(router.state.location.search).toContain("a=2026-11-01");
  });

  it("«Settimana precedente» e poi «Oggi» riportano alla settimana del `today` del server", async () => {
    const { api } = await open();
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    api.set(PLAN_ROUTE, planHandler({ from: "2026-10-12", to: "2026-10-18" }));
    await userEvent.click(screen.getByRole("button", { name: "Settimana precedente" }));
    await screen.findByRole("heading", { name: /Lunedì 12/ });
    api.set(PLAN_ROUTE, planHandler());
    await userEvent.click(screen.getByRole("button", { name: "Oggi" }));
    await screen.findByRole("heading", { name: /Lunedì 19/ });
  });

  it("un intervallo nell'indirizzo (AC-008.5) si chiede così com'è e mostra quei giorni", async () => {
    const { api } = await open({
      url: "/piano?da=2026-11-01&a=2026-11-10",
      plan: planHandler({ from: "2026-11-01", to: "2026-11-10" }),
    });
    await screen.findByRole("heading", { name: /Domenica 1/ });
    const query = new URL(api.last(PLAN_ROUTE).path, "http://x").searchParams;
    expect([query.get("from"), query.get("to")]).toEqual(["2026-11-01", "2026-11-10"]);
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThanOrEqual(10);
  });

  it("parametri non validi nell'indirizzo non rompono la pagina: torna la settimana corrente", async () => {
    const { api } = await open({ url: "/piano?da=boh&a=2026-13-45" });
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    for (const call of api.calls.filter((c) => c.path.startsWith("/api/v1/plan"))) {
      expect(call.path).not.toContain("boh");
    }
  });
});

describe("S-02: stati", () => {
  it("nessun pasto di default (AC-003.3): A e P vedono lo stato vuoto con i due pulsanti", async () => {
    await open({ plan: { meals: () => [] } });
    await screen.findByText("Nessun pasto da pianificare");
    expect(screen.getByText(/Scegli quali pasti compaiono ogni giorno/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Scegli i pasti di ogni giorno" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Aggiungi un pasto a un giorno" })).toBeTruthy();
  });

  it("un Membro con la settimana vuota vede «Il piano non è ancora pronto» (AC-024.4)", async () => {
    await open({ role: "member", plan: { meals: () => [] } });
    await screen.findByText("Il piano non è ancora pronto");
    expect(screen.queryByText("Nessun pasto da pianificare")).toBeNull();
    expect(screen.queryByRole("button", { name: /Aggiungi/ })).toBeNull();
  });

  it("durante il caricamento si vedono intestazione e scheletro con aria-busy", async () => {
    await open({ plan: PENDING });
    expect(await screen.findByRole("heading", { level: 1, name: "Piano" })).toBeTruthy();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
  });

  it("un errore di caricamento mostra il messaggio e «Riprova» che richiede il piano", async () => {
    const { api } = await open({ plan: () => problemResponse("internal") });
    await screen.findByText(/Non riusciamo a caricare il piano/);
    api.set(PLAN_ROUTE, planHandler());
    await userEvent.click(screen.getByRole("button", { name: "Riprova" }));
    await screen.findByRole("heading", { name: /Lunedì 19/ });
    expect(screen.queryByText(/Non riusciamo a caricare il piano/)).toBeNull();
  });
});
