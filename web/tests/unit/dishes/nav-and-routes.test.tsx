// @vitest-environment happy-dom
// SL-04: navigazione e rotte dell'archivio (UX §3, DD-06). La voce «Piatti» entra nella barra in
// basso accanto a «Piano» e «Altro»; la barra si nasconde nel modulo (S-07); le quattro rotte
// esistono dietro la sessione (un anonimo va all'accesso) e non sono la pagina «non trovato».
import { cleanup, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { anonymous, authenticated, installFakeApi, SESSION_ROUTE } from "../../support/fake-api";
import {
  COURSES_ROUTE,
  coursesHandler,
  detail,
  dish,
  dishRoute,
  DISHES_ROUTE,
  page,
  withEtag,
} from "../../support/dishes";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ID = "d3333333-3333-4333-8333-333333333333";

async function renderAt(path: string, session: () => Response = () => authenticated()) {
  installFakeApi({
    [SESSION_ROUTE]: session,
    [COURSES_ROUTE]: coursesHandler,
    [DISHES_ROUTE]: () => page([dish({ name: "Pasta e ceci" })]),
    [dishRoute(ID)]: () => withEtag(detail(dish({ id: ID, name: "Pasta e ceci" }))),
  });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return router;
}

describe("rotte dell'archivio piatti", () => {
  it.each(["/piatti", "/piatti/nuovo", `/piatti/${ID}`, `/piatti/${ID}/modifica`])(
    "%s esiste dietro la sessione e non è «Pagina non trovata»",
    async (path) => {
      await renderAt(path);
      await screen.findByRole("main");
      await screen.findAllByRole("heading", { level: 1 });
      expect(screen.queryByRole("heading", { name: "Pagina non trovata" })).toBeNull();
    },
  );

  it.each(["/piatti", "/piatti/nuovo", `/piatti/${ID}`, `/piatti/${ID}/modifica`])(
    "%s porta all'accesso senza sessione",
    async (path) => {
      const router = await renderAt(path, () => anonymous());
      await screen.findByRole("heading", { level: 1, name: "Accedi a Menu Design" });
      expect(router.state.location.pathname).toBe("/accedi");
    },
  );

  it("un identificativo che non è un UUID non rompe l'app", async () => {
    await renderAt("/piatti/non-un-uuid");
    await screen.findByRole("main");
    expect(await screen.findByRole("link", { name: "Torna ai piatti" })).toBeTruthy();
    expect(screen.queryByText(/undefined|TypeError/)).toBeNull();
  });
});

describe("barra in basso", () => {
  it("con una sessione ha Piano, Piatti e Altro, con aria-current sulla voce attiva", async () => {
    await renderAt("/altro");
    const nav = await screen.findByRole("navigation", { name: "Navigazione principale" });
    const labels = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent);
    expect(labels).toEqual(["Piano", "Piatti", "Altro"]);
    expect(screen.getByRole("link", { name: "Altro" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Piatti" }).getAttribute("aria-current")).toBeNull();
  });

  it("«Piatti» resta attiva sulla scheda del piatto", async () => {
    await renderAt(`/piatti/${ID}`);
    await screen.findByRole("heading", { level: 1, name: "Pasta e ceci" });
    expect(screen.getByRole("link", { name: "Piatti" }).getAttribute("aria-current")).toBe("page");
  });

  it("nel modulo (nuovo e modifica) la barra non compare", async () => {
    await renderAt("/piatti/nuovo");
    await screen.findByLabelText("Nome del piatto");
    expect(screen.queryByRole("navigation", { name: "Navigazione principale" })).toBeNull();
  });
});
