// @vitest-environment happy-dom
// SL-03b: S-01 davanti a un 429 dell'avvio (AC-001.9; UX «Troppe richieste (429)»: `error.rateLimited`
// con i secondi di `Retry-After`, il pulsante si riabilita dopo). Server simulato come in SL-03a.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "../../../src/app/providers";
import { routes } from "../../../src/app/routes";
import { activateLocale } from "../../../src/i18n";
import {
  anonymous,
  installFakeApi,
  json,
  SESSION_ROUTE,
  START_ROUTE,
} from "../../support/fake-api";
import { problemResponse } from "../../support/problem";

const GOOGLE = /Continua con Google/;

beforeEach(() => {
  document.cookie = "__Host-csrf=cookie-csrf-anonimo-0123456789; Secure; Path=/";
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  document.cookie = "__Host-csrf=; Max-Age=0; Path=/";
});

async function renderLogin(): Promise<void> {
  await activateLocale("it");
  const router = createMemoryRouter(routes, { initialEntries: ["/accedi"] });
  render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}

describe("AC-001.9: S-01 con troppi avvii", () => {
  it("mostra «Troppi tentativi. Riprova tra N secondi.» dal Retry-After, non parte per Google e permette di riprovare", async () => {
    const assign = vi.spyOn(window.location, "assign").mockImplementation(() => undefined);
    let calls = 0;
    const api = installFakeApi({
      [SESSION_ROUTE]: () => anonymous(),
      [START_ROUTE]: () => {
        calls += 1;
        return calls === 1
          ? problemResponse("rate_limited", { params: { retryAfterSeconds: 42 } })
          : json({ redirectUrl: "https://accounts.google.com/o/oauth2/v2/auth?state=s" });
      },
    });
    await renderLogin();
    const button = await screen.findByRole("button", { name: GOOGLE });
    const user = userEvent.setup();
    await user.click(button);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Troppi tentativi. Riprova tra 42 secondi.");
    expect(alert.textContent).not.toMatch(/429|rate_limited|IP/);
    expect(assign).not.toHaveBeenCalled();
    const again = screen.getByRole("button", { name: GOOGLE });
    expect(again.getAttribute("aria-disabled")).not.toBe("true");

    await user.click(again);
    await waitFor(() => expect(assign).toHaveBeenCalledTimes(1));
    expect(api.count(START_ROUTE)).toBe(2);
  });
});
