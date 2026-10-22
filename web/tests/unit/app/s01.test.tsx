// @vitest-environment happy-dom
// SL-01: guscio della SPA e pagina S-01 statica (UX S-01, 8.1; NFR-008, NFR-011, SR-031).
// Contratto assunto:
//   web/src/app/routes.tsx     export const routes: RouteObject[]   (/ -> /accedi, /accedi, * = non trovato)
//   web/src/app/providers.tsx  export function AppProviders({ children })  (I18nProvider + QueryClientProvider)
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routes } from "../../../src/app/routes";
import { AppProviders } from "../../../src/app/providers";
import { activateLocale } from "../../../src/i18n";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
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

describe("S-01 Accesso (statica)", () => {
  it("mostra il titolo, la frase di presentazione e il pulsante Google, dal catalogo it", async () => {
    await renderAt("/accedi");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: "Accedi a Menu Design" })).not.toBeNull();
    expect(
      screen.getByText("Il piano dei pasti della tua famiglia, sempre in tasca."),
    ).not.toBeNull();
    // Pulsante o collegamento (redirect lato server): conta il nome accessibile, non l elemento.
    const google =
      screen.queryByRole("button", { name: /Continua con Google/ }) ??
      screen.getByRole("link", { name: /Continua con Google/ });
    expect(google.textContent).toContain("Continua con Google");
  });

  it("la radice / porta a /accedi (nessuna sessione in questa slice)", async () => {
    const router = await renderAt("/");
    expect(router.state.location.pathname).toBe("/accedi");
    expect(screen.getByRole("heading", { level: 1, name: "Accedi a Menu Design" })).not.toBeNull();
  });

  it("ha un solo punto di riferimento main e il collegamento «Vai al contenuto» come primo elemento (WCAG 2.4.1)", async () => {
    await renderAt("/accedi");
    expect(screen.getAllByRole("main")).toHaveLength(1);
    const focusable = [
      ...document.querySelectorAll<HTMLElement>(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ];
    const first = focusable[0] as HTMLAnchorElement;
    expect(first.textContent).toBe("Vai al contenuto");
    const target = document.querySelector(first.getAttribute("href") as string);
    expect(target, "il collegamento deve puntare a un elemento esistente").not.toBeNull();
    expect(screen.getByRole("main").contains(target)).toBe(true);
  });

  it("nessuna risorsa esterna: ogni src e href è sulla stessa origine (SR-031)", async () => {
    await renderAt("/accedi");
    const urls = [...document.querySelectorAll("[src],[href]")].map(
      (el) => el.getAttribute("src") ?? el.getAttribute("href") ?? "",
    );
    for (const url of urls) {
      expect(url, url).not.toMatch(/^(https?:)?\/\//i);
      expect(url, url).not.toMatch(/^(javascript|data|blob):/i);
    }
  });

  it("non scrive in localStorage, sessionStorage né nei cookie (SR-037, THR-005)", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    await renderAt("/accedi");
    expect(setItem).not.toHaveBeenCalled();
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
    expect(document.cookie).toBe("");
  });

  it("non fa richieste di rete fuori dalla stessa origine", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchSpy);
    await renderAt("/accedi");
    for (const [url] of fetchSpy.mock.calls as unknown as Array<[string]>) {
      expect(String(url).startsWith("/"), String(url)).toBe(true);
    }
    vi.unstubAllGlobals();
  });
});

describe("rotta non trovata (UX 5.1: error.notFound con ritorno alla schermata madre)", () => {
  it("mostra il messaggio del catalogo e un collegamento a /accedi", async () => {
    await renderAt("/questa-rotta-non-esiste");
    expect(
      screen.getAllByText(/Non troviamo quello che cerchi\. Potrebbe essere stato eliminato\./)
        .length,
    ).toBeGreaterThan(0);
    const back = screen.getAllByRole("link").find((a) => a.getAttribute("href") === "/accedi");
    expect(back, "collegamento di ritorno a /accedi").toBeDefined();
  });

  it("il percorso richiesto non è riflesso come HTML né come testo (THR-070)", async () => {
    await renderAt("/%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E");
    expect(document.querySelector("img")).toBeNull();
    expect(document.body.textContent).not.toContain("onerror");
  });

  it("dopo il cambio di rotta il focus va sul titolo h1 (UX 2.4.3)", async () => {
    await renderAt("/questa-rotta-non-esiste");
    const back = screen
      .getAllByRole("link")
      .find((a) => a.getAttribute("href") === "/accedi") as HTMLElement;
    await userEvent.setup().click(back);
    const h1 = await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" });
    expect(document.activeElement).toBe(h1);
  });
});
