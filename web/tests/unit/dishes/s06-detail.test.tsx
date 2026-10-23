// @vitest-environment happy-dom
// SL-04: S-06 «Scheda del piatto» (UX S-06). US-004 AC-004.2 (il link si apre in una nuova scheda),
// AC-004.6 (testo letterale), SR-024 (URL solo http/https, `rel="noopener noreferrer"`), DD-04.
//
// Contratto assunto (da confermare con il frontend-developer):
// - `/piatti/:id` mostra un `h1` con il nome, le portate (etichette `dish.course.*`), il badge di
//   stato, il tempo (`dish.time.*`), le note e «Dove trovi la ricetta» con le fonti;
// - il link di una fonte `link` è un `<a>` con `target="_blank"`, `rel` che contiene `noopener` e
//   `noreferrer`, nome accessibile che contiene «Apri la ricetta»; MAI un `href` che non sia
//   http/https (anche se il server, per un dato vecchio o manipolato, lo restituisse);
// - nessun `lastCookedOn` in M0 (arriva con SL-07): si mostra «Mai cucinato»;
// - «Modifica» (link a `/piatti/:id/modifica`) solo per Amministratore e Pianificatore;
// - un `404` mostra `error.notFound` con «Torna ai piatti»; piatto archiviato: banner
//   `dish.archivedBanner`.
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { authenticated, installFakeApi, SESSION_ROUTE } from "../../support/fake-api";
import {
  COURSES_ROUTE,
  coursesHandler,
  courseId,
  detail,
  dish,
  dishRoute,
  withEtag,
  type DishFixture,
} from "../../support/dishes";
import { problemResponse } from "../../support/problem";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function openDish(
  fixture: DishFixture,
  role = "planner",
  response: () => Response = () => withEtag(detail(fixture)),
): Promise<ReturnType<typeof createMemoryRouter>> {
  installFakeApi({
    [SESSION_ROUTE]: () =>
      authenticated({ person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role } }),
    [COURSES_ROUTE]: coursesHandler,
    [dishRoute(fixture.id)]: response,
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [`/piatti/${fixture.id}`] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return router;
}

const FULL = dish({
  name: "Pasta e ceci",
  status: "tested",
  courseIds: [courseId("first"), courseId("one_dish")],
  prepTime: "30_60",
  notes: "Con rosmarino. Meglio il giorno dopo.",
  sources: [
    { kind: "link", reference: "https://ricette.example.test/ceci", note: "la migliore" },
    { kind: "book", reference: "Il cucchiaio", page: "142" },
  ],
});

describe("S-06: contenuto", () => {
  it("mostra nome, portate, stato, tempo, note e fonti", async () => {
    await openDish(FULL);
    await screen.findByRole("heading", { level: 1, name: "Pasta e ceci" });
    const main = screen.getByRole("main");
    for (const text of [
      "Primo",
      "Piatto unico",
      "Collaudato",
      "30-60 minuti",
      "Con rosmarino. Meglio il giorno dopo.",
      "Dove trovi la ricetta",
      "Il cucchiaio",
      "142",
      "Mai cucinato",
    ]) {
      expect(main.textContent, text).toContain(text);
    }
  });

  it("AC-004.2: il link della fonte si apre in una nuova scheda, senza opener né referrer", async () => {
    await openDish(FULL);
    await screen.findByRole("heading", { level: 1, name: "Pasta e ceci" });
    const anchor = screen.getByRole("link", { name: /Apri la ricetta/ }) as HTMLAnchorElement;
    expect(anchor.getAttribute("href")).toBe("https://ricette.example.test/ceci");
    expect(anchor.getAttribute("target")).toBe("_blank");
    const rel = (anchor.getAttribute("rel") ?? "").split(/\s+/);
    expect(rel).toContain("noopener");
    expect(rel).toContain("noreferrer");
  });

  it("SR-024: una fonte con schema diverso da http/https non diventa mai un link", async () => {
    const hostile = dish({
      name: "Dato vecchio",
      sources: [
        { kind: "link", reference: "javascript:window.__xss=1" },
        { kind: "link", reference: "data:text/html,<script>window.__xss=1</script>" },
        { kind: "link", reference: "JaVaScRiPt:window.__xss=1" },
        { kind: "link", reference: "//evil.example/x" },
      ],
    });
    await openDish(hostile);
    await screen.findByRole("heading", { level: 1, name: "Dato vecchio" });
    const hrefs = Array.from(document.querySelectorAll("main a")).map((a) =>
      a.getAttribute("href"),
    );
    for (const href of hrefs) {
      expect(href ?? "", "href non http/https").toMatch(/^(https?:\/\/|\/)/);
      expect(href ?? "").not.toMatch(/^\/\//);
    }
    expect(document.querySelectorAll("a[href^='javascript' i], a[href^='data:' i]")).toHaveLength(
      0,
    );
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("AC-004.6: nome e note con markup si mostrano come testo", async () => {
    const hostile = dish({
      name: "<script>window.__xss=1</script>",
      notes: '"><img src=x onerror=window.__xss=1> <svg onload=window.__xss=1>',
    });
    await openDish(hostile);
    expect(
      await screen.findByRole("heading", { level: 1, name: "<script>window.__xss=1</script>" }),
    ).toBeTruthy();
    expect(screen.getByRole("main").textContent).toContain("<svg onload=window.__xss=1>");
    expect(document.querySelectorAll("script:not([src]), img[src='x'], svg[onload]")).toHaveLength(
      0,
    );
    expect((window as unknown as { __xss?: number }).__xss).toBeUndefined();
  });

  it("un piatto senza note, tempo e fonti non mostra sezioni vuote né «undefined»", async () => {
    await openDish(dish({ name: "Minestra" }));
    await screen.findByRole("heading", { level: 1, name: "Minestra" });
    const text = screen.getByRole("main").textContent ?? "";
    expect(text).not.toMatch(/undefined|null|NaN/);
    expect(screen.queryByText("Dove trovi la ricetta")).toBeNull();
  });
});

describe("S-06: permessi e stati", () => {
  it.each(["admin", "planner"])("%s vede «Modifica»", async (role) => {
    await openDish(FULL, role);
    await screen.findByRole("heading", { level: 1, name: "Pasta e ceci" });
    expect(screen.getByRole("link", { name: "Modifica" }).getAttribute("href")).toBe(
      `/piatti/${FULL.id}/modifica`,
    );
  });

  it("un Membro legge ma non vede «Modifica» (DD-04)", async () => {
    await openDish(FULL, "member");
    await screen.findByRole("heading", { level: 1, name: "Pasta e ceci" });
    expect(screen.queryByRole("link", { name: "Modifica" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Modifica" })).toBeNull();
  });

  it("un piatto archiviato mostra il banner", async () => {
    await openDish(dish({ name: "Lasagne", archived: true, everPlanned: true }));
    await screen.findByRole("heading", { level: 1, name: "Lasagne" });
    expect(
      screen.getByText("Questo piatto è archiviato e non compare più tra le scelte."),
    ).toBeTruthy();
  });

  it("404 (altra famiglia o inesistente): error.notFound con «Torna ai piatti», senza dettagli", async () => {
    const router = await openDish(FULL, "planner", () => problemResponse("not_found"));
    const main = await screen.findByRole("main");
    await screen.findByRole("link", { name: "Torna ai piatti" });
    expect(main.textContent).not.toContain("Pasta e ceci");
    await userEvent.click(screen.getByRole("link", { name: "Torna ai piatti" }));
    expect(router.state.location.pathname).toBe("/piatti");
  });

  it("errore del server: error.generic con «Riprova»", async () => {
    await openDish(FULL, "planner", () => problemResponse("internal"));
    const main = await screen.findByRole("main");
    await within(main).findByRole("button", { name: "Riprova" });
  });
});
