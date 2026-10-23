// @vitest-environment happy-dom
// SL-04: S-05 «Piatti: archivio» (UX S-05). US-004 AC-004.6 (testo letterale), AC-004.7 (archivio
// vuoto), US-006 AC-006.1-.5 (cerca, filtra, archiviati, nessun risultato). SR-024, SR-060, DD-04.
// Server simulato con le forme del piano (`tests/support/dishes.ts`), catalogo `it` vero.
//
// Contratto assunto (da confermare con il frontend-developer):
// - `/piatti` esiste in `routes` dietro `RequireSession`; un solo `h1` «Piatti»; la barra in basso
//   ha la voce «Piatti» (DD-06) accanto a «Piano» e «Altro»;
// - carica `GET /api/v1/courses` e `GET /api/v1/dishes` (senza `archived` finché l'interruttore è
//   spento); le portate si mostrano con le etichette del catalogo (`dish.course.*`), lo stato con
//   `dish.status.toTry|tested`, «Archiviato» con `dish.status.archived`;
// - ricerca: `textbox` «Cerca per nome» (si invia `q`, dopo un breve ritardo); filtri: `combobox`
//   «Portata» e «Stato» (si inviano `courseId` e `status`); `checkbox` «Mostra archiviati»
//   (si invia `archived=true`), solo per Amministratore e Pianificatore (DD-04);
// - «Nuovo piatto» (link a `/piatti/nuovo`) solo per Amministratore e Pianificatore;
// - archivio vuoto: `dishes.empty.title` + `dishes.empty.cta` («Aggiungi il primo piatto»);
// - nessun risultato con una ricerca: `dishes.noResults` + «Crea il piatto «testo»» che porta al
//   modulo con il nome già compilato;
// - «Mostra altri» carica la pagina successiva con `cursor` e accoda; mai scorrimento automatico;
// - ogni nome si mostra come testo: nessun markup creato dal contenuto.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { authenticated, installFakeApi, SESSION_ROUTE, type FakeApi } from "../../support/fake-api";
import {
  COURSE_LABEL,
  COURSES_ROUTE,
  coursesHandler,
  courseId,
  dish,
  DISHES_ROUTE,
  page,
} from "../../support/dishes";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ROLE = (role: string) => (): Response =>
  authenticated({ person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role } });

async function openArchive(
  dishes: (url: URL) => Response | Promise<Response>,
  role = "planner",
): Promise<{ api: FakeApi; router: ReturnType<typeof createMemoryRouter> }> {
  const api = installFakeApi({
    [SESSION_ROUTE]: ROLE(role),
    [COURSES_ROUTE]: coursesHandler,
    [DISHES_ROUTE]: (request) => dishes(new URL(request.path, "http://localhost")),
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: ["/piatti"] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { api, router };
}

const dishCalls = (api: FakeApi): URL[] =>
  api.calls
    .filter((c) => c.method === "GET" && c.path.startsWith("/api/v1/dishes"))
    .map((c) => new URL(c.path, "http://localhost"));

describe("S-05: struttura e permessi", () => {
  it("ha un solo titolo «Piatti» e la voce «Piatti» nella barra in basso", async () => {
    await openArchive(() => page([dish({ name: "Pasta e ceci" })]));
    await screen.findByRole("heading", { level: 1, name: "Piatti" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    const nav = screen.getByRole("navigation", { name: "Navigazione principale" });
    const link = within(nav).getByRole("link", { name: "Piatti" });
    expect(link.getAttribute("aria-current")).toBe("page");
    expect(
      within(nav)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Piano", "Piatti", "Altro"]);
  });

  it.each(["admin", "planner"])("%s vede «Nuovo piatto» e «Mostra archiviati»", async (role) => {
    await openArchive(() => page([dish({ name: "Pasta e ceci" })]), role);
    await screen.findByText("Pasta e ceci");
    expect(screen.getByRole("link", { name: /Nuovo piatto/ }).getAttribute("href")).toBe(
      "/piatti/nuovo",
    );
    expect(screen.getByRole("checkbox", { name: "Mostra archiviati" })).toBeTruthy();
  });

  it("un Membro consulta ma non vede i comandi che non può usare (DD-04)", async () => {
    await openArchive(() => page([dish({ name: "Pasta e ceci" })]), "member");
    await screen.findByText("Pasta e ceci");
    expect(screen.queryByRole("link", { name: /Nuovo piatto/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Nuovo piatto/ })).toBeNull();
    expect(screen.queryByRole("checkbox", { name: "Mostra archiviati" })).toBeNull();
  });
});

describe("S-05: elenco", () => {
  it("mostra nome, portate e stato di ogni piatto, con il nome che apre la scheda", async () => {
    const lasagne = dish({
      name: "Lasagne",
      status: "tested",
      courseIds: [courseId("first"), courseId("one_dish")],
    });
    await openArchive(() =>
      page([lasagne, dish({ name: "Shakshuka", courseIds: [courseId("second")] })]),
    );
    const row = (await screen.findByText("Lasagne")).closest("li, tr, article, a") as HTMLElement;
    expect(row.textContent).toContain(COURSE_LABEL["first"]);
    expect(row.textContent).toContain(COURSE_LABEL["one_dish"]);
    expect(row.textContent).toContain("Collaudato");
    const other = (await screen.findByText("Shakshuka")).closest(
      "li, tr, article, a",
    ) as HTMLElement;
    expect(other.textContent).toContain("Secondo");
    expect(other.textContent).toContain("Da provare");
    const link = screen.getByRole("link", { name: /Lasagne/ });
    expect(link.getAttribute("href")).toBe(`/piatti/${lasagne.id}`);
  });

  it("AC-004.6: nome con markup si mostra come testo e non crea elementi", async () => {
    const hostile = [
      "<script>window.__xss=1</script>",
      '"><img src=x onerror=window.__xss=1>',
      "<svg onload=window.__xss=1>",
    ];
    await openArchive(() => page(hostile.map((name) => dish({ name }))));
    for (const name of hostile) expect(await screen.findByText(name)).toBeTruthy();
    expect(document.querySelectorAll("script:not([src]), img[src='x'], svg[onload]")).toHaveLength(
      0,
    );
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("mostra la fase di caricamento e poi l'elenco", async () => {
    let release: (r: Response) => void = () => undefined;
    await openArchive(() => new Promise<Response>((resolve) => (release = resolve)));
    await screen.findByRole("heading", { level: 1, name: "Piatti" });
    expect(screen.queryByText("Il tuo archivio è vuoto")).toBeNull();
    release(page([dish({ name: "Pasta e ceci" })]));
    expect(await screen.findByText("Pasta e ceci")).toBeTruthy();
  });

  it("un errore di caricamento mostra dishes.error.load con «Riprova» che ricarica", async () => {
    let fail = true;
    const { api } = await openArchive(() =>
      fail ? problemResponse("internal") : page([dish({ name: "Pasta e ceci" })]),
    );
    await screen.findByText("Non riusciamo a caricare i piatti. Riprova.");
    fail = false;
    await userEvent.click(screen.getByRole("button", { name: "Riprova" }));
    expect(await screen.findByText("Pasta e ceci")).toBeTruthy();
    expect(dishCalls(api).length).toBeGreaterThanOrEqual(2);
  });
});

describe("AC-004.7: archivio vuoto", () => {
  it("mostra lo stato vuoto con il pulsante per aggiungere il primo piatto", async () => {
    await openArchive(() => page([]));
    expect(await screen.findByText("Il tuo archivio è vuoto")).toBeTruthy();
    expect(
      screen.getByText("Aggiungi i piatti che cucinate e quelli che vorreste provare."),
    ).toBeTruthy();
    const cta = screen.getByRole("link", { name: "Aggiungi il primo piatto" });
    expect(cta.getAttribute("href")).toBe("/piatti/nuovo");
    expect(screen.queryByText("Nessun piatto trovato")).toBeNull();
  });

  it("per un Membro lo stato vuoto non offre il pulsante", async () => {
    await openArchive(() => page([]), "member");
    expect(await screen.findByText("Il tuo archivio è vuoto")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Aggiungi il primo piatto" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Aggiungi il primo piatto" })).toBeNull();
  });
});

describe("US-006: cerca e filtra", () => {
  it("AC-006.1: la ricerca invia q al server e mostra i risultati", async () => {
    const { api } = await openArchive((url) =>
      url.searchParams.get("q") === "ceci"
        ? page([dish({ name: "Pasta e ceci" })])
        : page([dish({ name: "Pasta e ceci" }), dish({ name: "Risotto" })]),
    );
    await screen.findByText("Risotto");
    await userEvent.type(screen.getByRole("textbox", { name: "Cerca per nome" }), "ceci");
    await waitFor(() => expect(screen.queryByText("Risotto")).toBeNull());
    expect(screen.getByText("Pasta e ceci")).toBeTruthy();
    expect(dishCalls(api).some((u) => u.searchParams.get("q") === "ceci")).toBe(true);
  });

  it("la ricerca non invia una richiesta per ogni lettera (ritardo)", async () => {
    const { api } = await openArchive(() => page([dish({ name: "Pasta e ceci" })]));
    await screen.findByText("Pasta e ceci");
    const before = dishCalls(api).length;
    await userEvent.type(screen.getByRole("textbox", { name: "Cerca per nome" }), "pastaececi");
    await waitFor(() =>
      expect(dishCalls(api).some((u) => u.searchParams.get("q") === "pastaececi")).toBe(true),
    );
    expect(dishCalls(api).length - before).toBeLessThanOrEqual(3);
  });

  it("AC-006.3: i filtri portata e stato inviano courseId e status", async () => {
    const { api } = await openArchive((url) => {
      const side = url.searchParams.get("courseId") === courseId("side");
      const toTry = url.searchParams.get("status") === "to_try";
      return side && toTry
        ? page([dish({ name: "Insalata", courseIds: [courseId("side")] })])
        : page([dish({ name: "Insalata" }), dish({ name: "Lasagne", status: "tested" })]);
    });
    await screen.findByText("Lasagne");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Portat/ }), "Contorno");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Stato" }), "Da provare");
    await waitFor(() => expect(screen.queryByText("Lasagne")).toBeNull());
    const last = dishCalls(api).at(-1) as URL;
    expect(last.searchParams.get("courseId")).toBe(courseId("side"));
    expect(last.searchParams.get("status")).toBe("to_try");
  });

  it("AC-006.4: gli archiviati compaiono solo con l'interruttore, con l'etichetta «Archiviato»", async () => {
    const lasagne = dish({ name: "Lasagne", archived: true, everPlanned: true });
    const { api } = await openArchive((url) =>
      url.searchParams.get("archived") === "true"
        ? page([lasagne, dish({ name: "Pasta e ceci" })])
        : page([dish({ name: "Pasta e ceci" })]),
    );
    await screen.findByText("Pasta e ceci");
    expect(screen.queryByText("Lasagne")).toBeNull();
    expect(dishCalls(api).every((u) => u.searchParams.get("archived") !== "true")).toBe(true);

    await userEvent.click(screen.getByRole("checkbox", { name: "Mostra archiviati" }));
    const row = (await screen.findByText("Lasagne")).closest("li, tr, article, a") as HTMLElement;
    expect(row.textContent).toContain("Archiviato");
    const active = screen.getByText("Pasta e ceci").closest("li, tr, article, a") as HTMLElement;
    expect(active.textContent).not.toContain("Archiviato");
  });

  it("AC-006.5: senza risultati compare «Nessun piatto trovato» e «Crea il piatto con questo nome»", async () => {
    await openArchive((url) =>
      url.searchParams.get("q") ? page([]) : page([dish({ name: "Pasta e ceci" })]),
    );
    await screen.findByText("Pasta e ceci");
    await userEvent.type(screen.getByRole("textbox", { name: "Cerca per nome" }), "Shakshuka");
    expect(await screen.findByText("Nessun piatto trovato")).toBeTruthy();
    expect(screen.queryByText("Il tuo archivio è vuoto")).toBeNull();
    const create = screen.getByRole("link", { name: "Crea il piatto «Shakshuka»" });
    await userEvent.click(create);
    // il modulo si apre con il nome già inserito (UX S-05, AC-006.5)
    const field = await screen.findByLabelText("Nome del piatto");
    expect((field as HTMLInputElement).value).toBe("Shakshuka");
  });

  it("il testo cercato con markup non diventa markup nel messaggio «crea»", async () => {
    await openArchive((url) =>
      url.searchParams.get("q") ? page([]) : page([dish({ name: "X" })]),
    );
    await screen.findByText("X");
    await userEvent.type(
      screen.getByRole("textbox", { name: "Cerca per nome" }),
      "<img src=x onerror=window.__xss=1>",
    );
    await screen.findByText("Nessun piatto trovato");
    expect(document.querySelectorAll("img[src='x']")).toHaveLength(0);
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });
});

describe("S-05: paginazione (SR-060)", () => {
  const first = Array.from({ length: 50 }, (_, i) =>
    dish({ name: `Piatto ${String(i).padStart(3, "0")}` }),
  );
  const second = Array.from({ length: 10 }, (_, i) => dish({ name: `Torta ${i}` }));

  it("«Mostra altri» carica la pagina con il cursore e accoda; nessun caricamento automatico", async () => {
    const { api } = await openArchive((url) =>
      url.searchParams.get("cursor") === "pagina-2" ? page(second) : page(first, "pagina-2"),
    );
    await screen.findByText("Piatto 000");
    expect(screen.queryByText("Torta 0")).toBeNull();
    expect(dishCalls(api).filter((u) => u.searchParams.get("cursor")).length).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: "Mostra altri" }));
    expect(await screen.findByText("Torta 9")).toBeTruthy();
    expect(screen.getByText("Piatto 000")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mostra altri" })).toBeNull();
    const withCursor = dishCalls(api).filter((u) => u.searchParams.get("cursor"));
    expect(withCursor).toHaveLength(1);
  });

  it("non chiede mai più di 100 elementi per pagina", async () => {
    const { api } = await openArchive(() => page(first, "pagina-2"));
    await screen.findByText("Piatto 000");
    for (const url of dishCalls(api)) {
      expect(Number(url.searchParams.get("limit") ?? 50)).toBeLessThanOrEqual(100);
    }
  });

  it("senza pagina successiva non c'è «Mostra altri»", async () => {
    await openArchive(() => page(second));
    await screen.findByText("Torta 0");
    expect(screen.queryByRole("button", { name: "Mostra altri" })).toBeNull();
  });
});
