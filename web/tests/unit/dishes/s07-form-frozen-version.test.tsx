// @vitest-environment happy-dom
// CR-SL04-001: la versione per If-Match si fissa all'apertura del modulo. Un refetch (ritorno della
// rete) che porta una versione più nuova non deve spostarla: il server deve rispondere 412.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { onlineManager } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { authenticated, installFakeApi, SESSION_ROUTE } from "../../support/fake-api";
import {
  COURSES_ROUTE,
  coursesHandler,
  detail,
  dish,
  dishRoute,
  updateRoute,
  withEtag,
} from "../../support/dishes";

afterEach(() => {
  onlineManager.setOnline(true);
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("S-07: versione fissata all'apertura", () => {
  it("un refetch con versione più nuova non cambia l'If-Match del PUT", async () => {
    const existing = dish({ name: "Pasta e ceci", version: 3 });
    let gets = 0;
    const api = installFakeApi({
      [SESSION_ROUTE]: () =>
        authenticated({
          person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role: "planner" },
        }),
      [COURSES_ROUTE]: coursesHandler,
      [dishRoute(existing.id)]: () => {
        gets += 1;
        return withEtag({ ...detail(existing), version: gets === 1 ? 3 : 4 });
      },
      [updateRoute(existing.id)]: () => withEtag({ ...detail(existing), version: 5 }),
    });
    await activateLocale("it");
    const router = createMemoryRouter(routes, {
      initialEntries: [`/piatti/${existing.id}/modifica`],
    });
    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    );
    await screen.findByLabelText("Nome del piatto");

    act(() => onlineManager.setOnline(false));
    act(() => onlineManager.setOnline(true));
    await waitFor(() => expect(gets).toBeGreaterThan(1));

    await userEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(api.count(updateRoute(existing.id))).toBe(1));
    expect(api.last(updateRoute(existing.id)).headers.get("If-Match")).toBe('"3"');
  });
});
