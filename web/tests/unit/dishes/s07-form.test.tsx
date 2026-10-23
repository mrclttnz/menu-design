// @vitest-environment happy-dom
// SL-04: S-07 «Modulo del piatto» (UX S-07, §5.4). US-004 AC-004.1 (salva con tutti i dati),
// AC-004.2 (fonti), AC-004.3 (nome e portate obbligatori), AC-004.4 (URL solo http/https),
// AC-004.5 (limiti), AC-004.6 (testo letterale). SR-024, SR-032, ADR-0008 (`If-Match`), DD-04.
//
// Contratto assunto (da confermare con il frontend-developer):
// - `/piatti/nuovo` (nuovo, stato «Da provare» predefinito) e `/piatti/:id/modifica` (compilato
//   dalla `GET`, con `If-Match: "<version>"` nel `PUT`, senza campo `status`);
// - campi: `textbox` «Nome del piatto», gruppo «Portate» di `checkbox` con le etichette
//   `dish.course.*`, `radio` «Da provare» / «Collaudato», `combobox` «Tempo di preparazione»,
//   `textbox` «Note» con l'avviso sulla salute (SR-032), fonti con `combobox` «Tipo», «Indirizzo
//   (https://…)» / «Titolo» + «Pagina» / «Descrizione», «Nota», «Togli questa fonte»,
//   «Aggiungi una fonte» (disabilitato a 10 con `dish.source.limit`); «Salva» e «Annulla»;
// - la richiesta ha `X-CSRF-Token` della sessione; il corpo è un `DishWrite` (nessun campo extra);
// - dopo il salvataggio si va alla scheda `/piatti/:id` con il toast `dish.saved.toast`;
// - errori del server (`errors[].field` -> campo, `code` -> `validation.*`) restano accanto al
//   campo, con `form.errorSummary`; il testo digitato non si perde mai;
// - la validazione locale (nome vuoto, nessuna portata, URL non http/https) impedisce l'invio;
// - «Annulla» con modifiche chiede conferma (`form.discard.*`); un Membro non può aprire il modulo
//   in M0 (`error.forbidden`), e la barra in basso non compare nel modulo.
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import {
  authenticated,
  CSRF_OF_SESSION,
  installFakeApi,
  json,
  SESSION_ROUTE,
  type FakeApi,
  type FakeRequest,
} from "../../support/fake-api";
import {
  COURSES_ROUTE,
  coursesHandler,
  courseId,
  CREATE_ROUTE,
  detail,
  dish,
  dishRoute,
  updateRoute,
  validation,
  withEtag,
} from "../../support/dishes";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const NEW_ID = "d1111111-1111-4111-8111-111111111111";

interface Opened {
  api: FakeApi;
  router: ReturnType<typeof createMemoryRouter>;
}

async function openForm(
  path: string,
  extra: Record<string, (request: FakeRequest) => Response | Promise<Response>> = {},
  role = "planner",
): Promise<Opened> {
  const api = installFakeApi({
    [SESSION_ROUTE]: () =>
      authenticated({ person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role } }),
    [COURSES_ROUTE]: coursesHandler,
    ...extra,
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { api, router };
}

const created = (body: Record<string, unknown>): Response =>
  withEtag({ ...detail(dish({ id: NEW_ID, name: String(body["name"]) })), version: 1 }, 201);

const nameField = (): HTMLInputElement => screen.getByLabelText("Nome del piatto");
const save = (): Promise<void> => userEvent.click(screen.getByRole("button", { name: "Salva" }));
const sent = (api: FakeApi, route: string): Record<string, unknown> =>
  api.last(route).body as Record<string, unknown>;

describe("S-07: nuovo piatto", () => {
  it("parte vuoto, con «Da provare» scelto e l'avviso sulla salute (SR-032)", async () => {
    await openForm("/piatti/nuovo");
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    expect(nameField().value).toBe("");
    expect((screen.getByRole("radio", { name: "Da provare" }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((screen.getByRole("radio", { name: "Collaudato" }) as HTMLInputElement).checked).toBe(
      false,
    );
    expect(screen.getAllByRole("checkbox").filter((c) => (c as HTMLInputElement).checked)).toEqual(
      [],
    );
    expect(
      screen.getByText("Non scrivere informazioni sulla salute di nessuno (per esempio allergie)."),
    ).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Navigazione principale" })).toBeNull();
  });

  it("offre le otto portate base con le etichette italiane", async () => {
    await openForm("/piatti/nuovo");
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    for (const label of [
      "Antipasto",
      "Primo",
      "Secondo",
      "Contorno",
      "Piatto unico",
      "Dolce",
      "Bevanda",
      "Altro",
    ]) {
      expect(screen.getByRole("checkbox", { name: label }), label).toBeTruthy();
    }
  });

  it("AC-004.1: salva nome, portate, stato e fascia; la richiesta è un DishWrite con il CSRF", async () => {
    const { api, router } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: (r) => created(r.body as Record<string, unknown>),
      [dishRoute(NEW_ID)]: () =>
        withEtag(detail(dish({ id: NEW_ID, name: "Frittata di zucchine" }))),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata di zucchine");
    await userEvent.click(screen.getByRole("checkbox", { name: "Secondo" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Piatto unico" }));
    await userEvent.click(screen.getByRole("radio", { name: "Collaudato" }));
    await userEvent.selectOptions(
      screen.getByRole("combobox", { name: "Tempo di preparazione" }),
      "Meno di 30 minuti",
    );
    await save();

    await waitFor(() => expect(api.count(CREATE_ROUTE)).toBe(1));
    const request = api.last(CREATE_ROUTE);
    expect(request.headers.get("X-CSRF-Token")).toBe(CSRF_OF_SESSION);
    expect(request.headers.get("Content-Type")).toBe("application/json");
    const body = request.body as Record<string, unknown>;
    expect(body["name"]).toBe("Frittata di zucchine");
    expect([...(body["courseIds"] as string[])].sort()).toEqual(
      [courseId("second"), courseId("one_dish")].sort(),
    );
    expect(body["status"]).toBe("tested");
    expect(body["prepTime"]).toBe("under_30");
    expect(body["sources"]).toEqual([]);
    const allowed = new Set(["name", "courseIds", "status", "prepTime", "notes", "sources"]);
    expect(
      Object.keys(body).filter((k) => !allowed.has(k)),
      "campi non scrivibili",
    ).toEqual([]);
    expect(body["notes"] ?? null).toBeNull();

    await waitFor(() => expect(router.state.location.pathname).toBe(`/piatti/${NEW_ID}`));
    expect(await screen.findByText("Piatto salvato")).toBeTruthy();
  });

  it("AC-004.2: aggiunge una fonte link e una fonte libro con titolo e pagina", async () => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: (r) => created(r.body as Record<string, unknown>),
      [dishRoute(NEW_ID)]: () => withEtag(detail(dish({ id: NEW_ID, name: "Frittata" }))),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata");
    await userEvent.click(screen.getByRole("checkbox", { name: "Secondo" }));

    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    await userEvent.type(
      screen.getByLabelText("Indirizzo (https://…)"),
      "https://ricette.example.test/frittata",
    );
    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    const kinds = screen.getAllByRole("combobox", { name: "Tipo" });
    await userEvent.selectOptions(kinds[1] as HTMLElement, "Libro");
    await userEvent.type(screen.getByLabelText("Titolo"), "Il cucchiaio");
    await userEvent.type(screen.getByLabelText("Pagina"), "142");
    await save();

    await waitFor(() => expect(api.count(CREATE_ROUTE)).toBe(1));
    expect(sent(api, CREATE_ROUTE)["sources"]).toEqual([
      { kind: "link", reference: "https://ricette.example.test/frittata" },
      { kind: "book", reference: "Il cucchiaio", page: "142" },
    ]);
  });

  it("«Togli questa fonte» rimuove la fonte scelta", async () => {
    await openForm("/piatti/nuovo");
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    expect(screen.getAllByRole("combobox", { name: "Tipo" })).toHaveLength(2);
    await userEvent.click(
      screen.getAllByRole("button", { name: "Togli questa fonte" })[0] as HTMLElement,
    );
    expect(screen.getAllByRole("combobox", { name: "Tipo" })).toHaveLength(1);
  });

  it("AC-004.5: «Aggiungi una fonte» si ferma a 10 e lo spiega", async () => {
    await openForm("/piatti/nuovo");
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    for (let i = 0; i < 10; i += 1) {
      await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    }
    expect(screen.getAllByRole("combobox", { name: "Tipo" })).toHaveLength(10);
    const add = screen.getByRole("button", { name: "Aggiungi una fonte" });
    expect(add.hasAttribute("disabled") || add.getAttribute("aria-disabled") === "true").toBe(true);
    expect(screen.getByText("Hai raggiunto il massimo di 10 fonti.")).toBeTruthy();
  });
});

describe("S-07: validazione locale (nessuna richiesta se il modulo non è valido)", () => {
  it("AC-004.3: senza nome si indica il campo e non si invia", async () => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => created({ name: "x" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.click(screen.getByRole("checkbox", { name: "Primo" }));
    await save();
    expect(await screen.findByText("Compila questo campo.")).toBeTruthy();
    expect(nameField().getAttribute("aria-invalid")).toBe("true");
    expect(api.count(CREATE_ROUTE)).toBe(0);
    expect(screen.getByText("Controlla questi campi prima di salvare")).toBeTruthy();
  });

  it("AC-004.3: senza portate si indica il gruppo e non si invia", async () => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => created({ name: "x" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata");
    await save();
    expect(await screen.findByText("Scegli almeno una portata.")).toBeTruthy();
    expect(api.count(CREATE_ROUTE)).toBe(0);
  });

  it("AC-004.3: un nome di soli spazi vale come vuoto", async () => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => created({ name: "x" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "    ");
    await userEvent.click(screen.getByRole("checkbox", { name: "Primo" }));
    await save();
    expect(await screen.findByText("Compila questo campo.")).toBeTruthy();
    expect(api.count(CREATE_ROUTE)).toBe(0);
  });

  it.each([
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "data:text/html,x",
    "ftp://ricette.example.test/a",
    "ricette.example.test",
  ])("AC-004.4: la fonte %s è rifiutata con validation.url_invalid", async (url) => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => created({ name: "x" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata");
    await userEvent.click(screen.getByRole("checkbox", { name: "Secondo" }));
    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    await userEvent.type(screen.getByLabelText("Indirizzo (https://…)"), url);
    await save();
    expect(
      await screen.findByText("Inserisci un indirizzo che inizi con http:// o https://."),
    ).toBeTruthy();
    expect(api.count(CREATE_ROUTE)).toBe(0);
  });

  it("AC-004.5: un nome di 121 caratteri mostra il limite (massimo 120) e non si invia", async () => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => created({ name: "x" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.click(screen.getByRole("checkbox", { name: "Primo" }));
    await userEvent.click(nameField());
    await userEvent.paste("a".repeat(121));
    await save();
    expect(await screen.findByText("Massimo 120 caratteri.")).toBeTruthy();
    expect(api.count(CREATE_ROUTE)).toBe(0);
  });

  it("AC-004.5: le note oltre 2.000 caratteri mostrano il limite e non si inviano", async () => {
    const { api } = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => created({ name: "x" }),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata");
    await userEvent.click(screen.getByRole("checkbox", { name: "Primo" }));
    await userEvent.click(screen.getByRole("textbox", { name: /^Note/ }));
    await userEvent.paste("n".repeat(2001));
    await save();
    expect(await screen.findByText("Massimo 2000 caratteri.")).toBeTruthy();
    expect(api.count(CREATE_ROUTE)).toBe(0);
  });
});

describe("S-07: errori del server", () => {
  async function submitValid(api: Opened): Promise<void> {
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata <b>di</b> zucchine");
    await userEvent.click(screen.getByRole("checkbox", { name: "Secondo" }));
    await userEvent.type(screen.getByRole("textbox", { name: /^Note/ }), "Con basilico");
    await save();
    await waitFor(() => expect(api.api.count(CREATE_ROUTE)).toBe(1));
  }

  it("un 422 per campo si mostra accanto al campo e il testo digitato resta", async () => {
    const opened = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () =>
        validation([
          { field: "name", code: "string_too_long", params: { max: 120 } },
          { field: "notes", code: "string_too_long", params: { max: 2000 } },
        ]),
    });
    await submitValid(opened);
    expect(await screen.findByText("Massimo 120 caratteri.")).toBeTruthy();
    expect(screen.getByText("Massimo 2000 caratteri.")).toBeTruthy();
    expect(nameField().value).toBe("Frittata <b>di</b> zucchine");
    expect((screen.getByRole("textbox", { name: /^Note/ }) as HTMLTextAreaElement).value).toBe(
      "Con basilico",
    );
    expect(opened.router.state.location.pathname).toBe("/piatti/nuovo");
  });

  it("un errore sulla fonte si lega alla fonte giusta (sources[1].reference)", async () => {
    const opened = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => validation([{ field: "sources[1].reference", code: "url_invalid" }]),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata");
    await userEvent.click(screen.getByRole("checkbox", { name: "Secondo" }));
    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    await userEvent.type(
      screen.getByLabelText("Indirizzo (https://…)"),
      "https://a.example.test/1",
    );
    await userEvent.click(screen.getByRole("button", { name: "Aggiungi una fonte" }));
    const addresses = screen.getAllByLabelText("Indirizzo (https://…)");
    await userEvent.type(addresses[1] as HTMLElement, "https://a.example.test/2");
    await save();
    await waitFor(() => expect(opened.api.count(CREATE_ROUTE)).toBe(1));
    const message = await screen.findByText(
      "Inserisci un indirizzo che inizi con http:// o https://.",
    );
    const second = addresses[1] as HTMLElement;
    expect(second.getAttribute("aria-invalid")).toBe("true");
    expect(addresses[0]?.getAttribute("aria-invalid")).not.toBe("true");
    expect(message.closest("fieldset, li, div")?.contains(second)).toBe(true);
  });

  it("quota raggiunta (409 quota_exceeded): messaggio chiaro, nessuna perdita dei dati", async () => {
    const opened = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: () => problemResponse("quota_exceeded", { params: { quota: "dishes" } }),
    });
    await submitValid(opened);
    await screen.findByRole("alert");
    expect(nameField().value).toBe("Frittata <b>di</b> zucchine");
    expect(opened.router.state.location.pathname).toBe("/piatti/nuovo");
  });

  it.each([["forbidden"], ["internal"], ["rate_limited"]])(
    "un errore %s non fa perdere il testo e lascia riprovare",
    async (code) => {
      const opened = await openForm("/piatti/nuovo", {
        [CREATE_ROUTE]: () => problemResponse(code),
      });
      await submitValid(opened);
      await screen.findByRole("alert");
      expect(nameField().value).toBe("Frittata <b>di</b> zucchine");
      expect(screen.getByRole("button", { name: "Salva" }).hasAttribute("disabled")).toBe(false);
    },
  );

  it("un doppio clic su «Salva» invia una sola richiesta", async () => {
    const opened = await openForm("/piatti/nuovo", {
      [CREATE_ROUTE]: async (r) => {
        await new Promise((resolve) => setTimeout(resolve, 20));
        return created(r.body as Record<string, unknown>);
      },
      [dishRoute(NEW_ID)]: () => withEtag(detail(dish({ id: NEW_ID, name: "Frittata" }))),
    });
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Frittata");
    await userEvent.click(screen.getByRole("checkbox", { name: "Secondo" }));
    const button = screen.getByRole("button", { name: "Salva" });
    await userEvent.dblClick(button);
    await waitFor(() => expect(opened.router.state.location.pathname).toBe(`/piatti/${NEW_ID}`));
    expect(opened.api.count(CREATE_ROUTE)).toBe(1);
  });
});

describe("S-07: uscire senza salvare", () => {
  it("senza modifiche «Annulla» torna all'archivio subito, senza conferma", async () => {
    const { router } = await openForm("/piatti/nuovo");
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.click(screen.getByRole("button", { name: "Annulla" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/piatti"));
    expect(screen.queryByText("Uscire senza salvare?")).toBeNull();
  });

  it("con modifiche chiede conferma e «Esci senza salvare» abbandona", async () => {
    const { router } = await openForm("/piatti/nuovo");
    await screen.findByRole("heading", { level: 1, name: "Nuovo piatto" });
    await userEvent.type(nameField(), "Bozza");
    await userEvent.click(screen.getByRole("button", { name: "Annulla" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Uscire senza salvare?")).toBeTruthy();
    expect(within(dialog).getByText("Le modifiche che hai fatto andranno perse.")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/piatti/nuovo");
    await userEvent.click(within(dialog).getByRole("button", { name: "Esci senza salvare" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/piatti"));
  });
});

describe("S-07: permessi", () => {
  it("un Membro non può usare il modulo in M0: error.forbidden e nessun campo", async () => {
    await openForm("/piatti/nuovo", {}, "member");
    expect(await screen.findByText("Non hai il permesso di fare questa operazione.")).toBeTruthy();
    expect(screen.queryByLabelText("Nome del piatto")).toBeNull();
  });
});

describe("S-07: modifica", () => {
  const existing = dish({
    id: "d2222222-2222-4222-8222-222222222222",
    name: "Pasta e ceci",
    status: "tested",
    courseIds: [courseId("first")],
    prepTime: "30_60",
    notes: "Con rosmarino.",
    sources: [{ kind: "link", reference: "https://ricette.example.test/ceci" }],
    version: 3,
  });
  const path = `/piatti/${existing.id}/modifica`;

  it("carica i dati nel modulo e non propone di cambiare lo stato", async () => {
    await openForm(path, { [dishRoute(existing.id)]: () => withEtag(detail(existing)) });
    await screen.findByLabelText("Nome del piatto");
    expect(nameField().value).toBe("Pasta e ceci");
    expect((screen.getByRole("checkbox", { name: "Primo" }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect((screen.getByRole("checkbox", { name: "Secondo" }) as HTMLInputElement).checked).toBe(
      false,
    );
    expect((screen.getByRole("textbox", { name: /^Note/ }) as HTMLTextAreaElement).value).toBe(
      "Con rosmarino.",
    );
    expect((screen.getByLabelText("Indirizzo (https://…)") as HTMLInputElement).value).toBe(
      "https://ricette.example.test/ceci",
    );
  });

  it("il PUT porta If-Match con la versione letta e nessun campo status", async () => {
    const { api, router } = await openForm(path, {
      [dishRoute(existing.id)]: () => withEtag(detail(existing)),
      [updateRoute(existing.id)]: (r) =>
        withEtag({
          ...detail(existing),
          name: String((r.body as { name: string }).name),
          version: 4,
        }),
    });
    await screen.findByLabelText("Nome del piatto");
    await userEvent.clear(nameField());
    await userEvent.type(nameField(), "Pasta e ceci alla romana");
    await save();
    await waitFor(() => expect(api.count(updateRoute(existing.id))).toBe(1));
    const request = api.last(updateRoute(existing.id));
    expect(request.headers.get("If-Match")).toBe('"3"');
    expect(request.headers.get("X-CSRF-Token")).toBe(CSRF_OF_SESSION);
    const body = request.body as Record<string, unknown>;
    expect(body["name"]).toBe("Pasta e ceci alla romana");
    expect(Object.keys(body)).not.toContain("status");
    expect(Object.keys(body)).not.toContain("version");
    await waitFor(() => expect(router.state.location.pathname).toBe(`/piatti/${existing.id}`));
  });

  it("dopo un salvataggio un secondo PUT usa la versione nuova (ETag)", async () => {
    const { api } = await openForm(path, {
      [dishRoute(existing.id)]: () => withEtag(detail(existing)),
      [updateRoute(existing.id)]: (r) =>
        r.headers.get("If-Match") === '"3"'
          ? withEtag({ ...detail(existing), version: 4 })
          : withEtag({ ...detail(existing), version: 5 }),
    });
    await screen.findByLabelText("Nome del piatto");
    await save();
    await waitFor(() => expect(api.count(updateRoute(existing.id))).toBe(1));
    expect(api.last(updateRoute(existing.id)).headers.get("If-Match")).toBe('"3"');
  });

  it("428 e 412 non si fingono salvataggi: restano sul modulo con un errore", async () => {
    for (const code of ["precondition_required", "conflict"]) {
      cleanup();
      const { router } = await openForm(path, {
        [dishRoute(existing.id)]: () => withEtag(detail(existing)),
        [updateRoute(existing.id)]: () =>
          problemResponse(code, code === "conflict" ? { params: { current: { version: 4 } } } : {}),
      });
      await screen.findByLabelText("Nome del piatto");
      await save();
      await screen.findByRole("alert");
      expect(router.state.location.pathname).toBe(path);
      expect(nameField().value).toBe("Pasta e ceci");
    }
  });

  it("404 sul piatto: error.notFound, nessun modulo", async () => {
    await openForm(path, { [dishRoute(existing.id)]: () => problemResponse("not_found") });
    expect(
      await screen.findByText("Non troviamo quello che cerchi. Potrebbe essere stato eliminato."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Nome del piatto")).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "Pagina non trovata" }),
      "è la rotta, non il 404 globale",
    ).toBeNull();
  });

  it("senza dati dal server non mostra un modulo vuoto da salvare", async () => {
    await openForm(path, { [dishRoute(existing.id)]: () => json({}, 500) });
    await screen.findByRole("alert");
    expect(screen.queryByRole("heading", { name: "Pagina non trovata" })).toBeNull();
    expect(await screen.findByRole("button", { name: "Riprova" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Salva" })).toBeNull();
  });
});
