// Raccolta di ciò che il browser vede: richieste, risposte, errori di console, violazioni CSP.
import type { Page, Request, Response } from "@playwright/test";

export interface Observed {
  requests: Request[];
  failedResponses: Response[];
  consoleErrors: string[];
  pageErrors: string[];
  cspViolations(): Promise<Array<{ directive: string; blocked: string }>>;
}

export async function observe(page: Page): Promise<Observed> {
  const observed: Observed = {
    requests: [],
    failedResponses: [],
    consoleErrors: [],
    pageErrors: [],
    cspViolations: async () =>
      page.evaluate(
        () =>
          (window as unknown as { __csp?: Array<{ directive: string; blocked: string }> }).__csp ??
          [],
      ),
  };
  await page.addInitScript(() => {
    const store: Array<{ directive: string; blocked: string }> = [];
    (window as unknown as { __csp: typeof store }).__csp = store;
    document.addEventListener("securitypolicyviolation", (event) => {
      store.push({ directive: event.violatedDirective, blocked: event.blockedURI });
    });
  });
  page.on("request", (request) => observed.requests.push(request));
  page.on("response", (response) => {
    // /favicon.ico lo chiede il browser da solo: il documento deve dichiarare un\'icona propria.
    if (response.status() >= 400 && !response.url().endsWith("/favicon.ico"))
      observed.failedResponses.push(response);
  });
  page.on("console", (message) => {
    if (message.type() === "error") observed.consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => observed.pageErrors.push(error.message));
  return observed;
}

/** Tutte le viste raggiungibili in SL-01 (la rotta inesistente è la vista «non trovato»). */
export const VIEWS = [
  { name: "S-01 Accesso", path: "/accedi" },
  { name: "Non trovato", path: "/questa-rotta-non-esiste" },
  { name: "Radice", path: "/" },
] as const;
