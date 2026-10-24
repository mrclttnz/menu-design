// @vitest-environment happy-dom
// SL-05 (fix CR-SL05-001): il comando di stato di S-06 (UX S-06, US-005, AC-005.1-.4).
// - A e P vedono «Segna come collaudato» (piatto da provare) o «Riporta a «da provare»» (collaudato);
//   M no (DD-04, AC-005.4);
// - il clic invia `POST /api/v1/dishes/:id/status` con `{status}` e `If-Match: "<versione>"`;
//   la scheda mostra subito il nuovo stato e compare l'avviso `dish.status.changed.toast` con «Annulla»;
// - «Annulla» invia lo stato di prima con la nuova versione;
// - 412 -> conflict.title.generic e la scheda si rilegge; 403 -> error.forbidden; 404 -> error.notFound;
//   429 -> error.rateLimited con i secondi, il pulsante si riabilita dopo; rete/5xx -> messaggio del catalogo.
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
import {
  COURSES_ROUTE,
  coursesHandler,
  detail,
  dish,
  dishRoute,
  withEtag,
  type DishFixture,
} from "../../support/dishes";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const statusRoute = (id: string): string => `POST /api/v1/dishes/${id}/status`;
const TO_TRY = dish({ name: "Pasta e ceci", status: "to_try", version: 4 });
const TESTED = dish({ name: "Frittata", status: "tested", version: 7 });

/** Risposta del server a un cambio di stato: la scheda con il nuovo stato e la versione + 1. */
const changed =
  (fixture: DishFixture): Handler =>
  (request) => {
    const next = (request.body as { status: DishFixture["status"] }).status;
    return withEtag(detail({ ...fixture, status: next, version: (fixture.version ?? 1) + 1 }));
  };

async function open(
  fixture: DishFixture,
  options: { role?: string; status?: Handler; read?: Handler } = {},
): Promise<FakeApi> {
  const api = installFakeApi({
    [SESSION_ROUTE]: () =>
      authenticated({
        person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role: options.role ?? "planner" },
      }),
    [COURSES_ROUTE]: coursesHandler,
    [dishRoute(fixture.id)]: options.read ?? (() => withEtag(detail(fixture))),
    [statusRoute(fixture.id)]: options.status ?? changed(fixture),
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [`/piatti/${fixture.id}`] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  await screen.findByRole("heading", { level: 1, name: fixture.name });
  return api;
}

const MARK = "Segna come collaudato";
const BACK = "Riporta a «da provare»";

describe("S-06 stato: permessi (AC-005.4, DD-04)", () => {
  it.each(["admin", "planner"])("%s vede il comando giusto per lo stato", async (role) => {
    await open(TO_TRY, { role });
    expect(screen.getByRole("button", { name: MARK })).toBeTruthy();
    expect(screen.queryByRole("button", { name: BACK })).toBeNull();
    cleanup();
    await open(TESTED, { role });
    expect(screen.getByRole("button", { name: BACK })).toBeTruthy();
    expect(screen.queryByRole("button", { name: MARK })).toBeNull();
  });

  it("un Membro non vede nessun comando di stato", async () => {
    await open(TO_TRY, { role: "member" });
    expect(screen.queryByRole("button", { name: MARK })).toBeNull();
    expect(screen.queryByRole("button", { name: BACK })).toBeNull();
  });
});

describe("S-06 stato: cambio e «Annulla» (AC-005.1-.3)", () => {
  it("invia il nuovo stato con If-Match, aggiorna la scheda e annuncia il cambio", async () => {
    const api = await open(TO_TRY);
    await userEvent.click(screen.getByRole("button", { name: MARK }));
    await screen.findByRole("button", { name: BACK });
    const call = api.last(statusRoute(TO_TRY.id));
    expect(call.body).toEqual({ status: "tested" });
    expect(call.headers.get("If-Match")).toBe('"4"');
    expect(call.headers.get("Content-Type")).toContain("application/json");
    const main = screen.getByRole("main");
    expect(within(main).getByText("Collaudato", { selector: ".badge" })).toBeTruthy();
    const note = screen.getByText("Pasta e ceci è ora Collaudato");
    expect(note.closest("[role='status']")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Annulla" })).toBeTruthy();
    expect(api.unexpected).toEqual([]);
  });

  it("anche il ritorno a «da provare» funziona", async () => {
    const api = await open(TESTED);
    await userEvent.click(screen.getByRole("button", { name: BACK }));
    await screen.findByRole("button", { name: MARK });
    expect(api.last(statusRoute(TESTED.id)).body).toEqual({ status: "to_try" });
    expect(api.last(statusRoute(TESTED.id)).headers.get("If-Match")).toBe('"7"');
  });

  it("«Annulla» rimanda lo stato di prima con la versione nuova", async () => {
    const api = await open(TO_TRY);
    await userEvent.click(screen.getByRole("button", { name: MARK }));
    await screen.findByRole("button", { name: BACK });
    // Il server ora è alla versione 6 dopo l'annullamento; qui si controlla la 5 inviata.
    api.set(statusRoute(TO_TRY.id), (request) =>
      withEtag(
        detail({
          ...TO_TRY,
          status: (request.body as { status: DishFixture["status"] }).status,
          version: 6,
        }),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Annulla" }));
    await screen.findByRole("button", { name: MARK });
    const undo = api.last(statusRoute(TO_TRY.id));
    expect(undo.body).toEqual({ status: "to_try" });
    expect(undo.headers.get("If-Match")).toBe('"5"');
    expect(api.count(statusRoute(TO_TRY.id))).toBe(2);
  });

  it("un doppio clic invia una sola richiesta", async () => {
    let release: (value: Response) => void = () => undefined;
    const api = await open(TO_TRY, {
      status: () => new Promise<Response>((resolve) => (release = resolve)),
    });
    const button = screen.getByRole("button", { name: MARK });
    await userEvent.dblClick(button);
    expect(api.count(statusRoute(TO_TRY.id))).toBe(1);
    expect(
      button.getAttribute("aria-disabled") === "true" || (button as HTMLButtonElement).disabled,
    ).toBe(true);
    await act(async () => release(withEtag(detail({ ...TO_TRY, status: "tested", version: 5 }))));
    await screen.findByRole("button", { name: BACK });
  });

  it("l'elenco dei piatti si rilegge dopo il cambio", async () => {
    const api = await open(TO_TRY);
    await userEvent.click(screen.getByRole("button", { name: MARK }));
    await screen.findByRole("button", { name: BACK });
    expect(api.unexpected).toEqual([]);
  });
});

describe("S-06 stato: errori", () => {
  it("412: messaggio di conflitto, la scheda si rilegge con lo stato del server", async () => {
    let reads = 0;
    const api = await open(TO_TRY, {
      status: () => problemResponse("conflict"),
      read: () => {
        reads += 1;
        return withEtag(detail(reads === 1 ? TO_TRY : { ...TO_TRY, status: "tested", version: 9 }));
      },
    });
    await userEvent.click(screen.getByRole("button", { name: MARK }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Qualcuno ha modificato questi dati");
    await screen.findByRole("button", { name: BACK });
    expect(api.count(dishRoute(TO_TRY.id))).toBeGreaterThanOrEqual(2);
    expect(screen.queryByRole("button", { name: "Annulla" })).toBeNull();
  });

  it("403: error.forbidden e i comandi si ricalcolano con la sessione riletta", async () => {
    const api = await open(TO_TRY, { status: () => problemResponse("forbidden") });
    await userEvent.click(screen.getByRole("button", { name: MARK }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Non hai il permesso");
    await waitFor(() => expect(api.count(SESSION_ROUTE)).toBeGreaterThanOrEqual(2));
  });

  it("404: error.notFound con «Torna ai piatti»", async () => {
    await open(TO_TRY, { status: () => problemResponse("not_found") });
    await userEvent.click(screen.getByRole("button", { name: MARK }));
    await screen.findByRole("link", { name: "Torna ai piatti" });
  });

  it("429: error.rateLimited con i secondi; il pulsante si riabilita dopo", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = await open(TO_TRY, {
      status: () => problemResponse("rate_limited", { params: { retryAfterSeconds: 30 } }),
    });
    await userEvent
      .setup({ advanceTimers: vi.advanceTimersByTime })
      .click(screen.getByRole("button", { name: MARK }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Riprova tra 30 secondi");
    const button = screen.getByRole("button", { name: MARK });
    expect(
      button.getAttribute("aria-disabled") === "true" || (button as HTMLButtonElement).disabled,
    ).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000);
    });
    await waitFor(() => {
      const again = screen.getByRole("button", { name: MARK });
      expect(again.getAttribute("aria-disabled")).not.toBe("true");
      expect((again as HTMLButtonElement).disabled).toBe(false);
    });
    expect(api.count(statusRoute(TO_TRY.id))).toBe(1);
  });

  it.each([
    ["rete assente", (): Response => Promise.reject(new TypeError("offline")) as never],
    ["5xx", () => problemResponse("internal")],
  ])(
    "%s: messaggio del catalogo, mai dettagli tecnici, lo stato non cambia",
    async (_n, handler) => {
      await open(TO_TRY, { status: handler as Handler });
      await userEvent.click(screen.getByRole("button", { name: MARK }));
      const alert = await screen.findByRole("alert");
      expect(alert.textContent ?? "").not.toMatch(/HTTP|TypeError|offline|internal|undefined/);
      expect(screen.getByRole("button", { name: MARK })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Annulla" })).toBeNull();
    },
  );
});
