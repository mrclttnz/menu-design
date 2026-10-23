// @vitest-environment happy-dom
// CR-SL03b-003: S-08 «Altro» raggiungibile dalla navigazione (DD-06): «Piano» e «Altro»
// solo con una sessione, `aria-current` sulla voce attiva.
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import { anonymous, authenticated, installFakeApi, SESSION_ROUTE } from "../../support/fake-api";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function renderAt(path: string, session: () => Response): Promise<void> {
  installFakeApi({ [SESSION_ROUTE]: session });
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}

describe("navigazione principale", () => {
  it("con una sessione mostra Piano e Altro e porta a «Altro» con un clic", async () => {
    await renderAt("/piano", () => authenticated());
    const nav = await screen.findByRole("navigation", { name: "Navigazione principale" });
    const plan = screen.getByRole("link", { name: "Piano" });
    expect(nav.contains(plan)).toBe(true);
    expect(plan.getAttribute("aria-current")).toBe("page");
    const more = screen.getByRole("link", { name: "Altro" });
    expect(more.getAttribute("aria-current")).toBeNull();

    await userEvent.click(more);
    await screen.findByRole("heading", { level: 1, name: "Altro" });
    expect(screen.getByRole("link", { name: "Altro" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Piano" }).getAttribute("aria-current")).toBeNull();
  });

  it("senza sessione non c'è la navigazione", async () => {
    await renderAt("/accedi", () => anonymous());
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("navigation")).toBeNull();
  });
});
