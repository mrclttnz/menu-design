// Server simulato per i test del frontend (08 §2: «fetch iniettato»). Le risposte rispettano il
// contratto di `docs/07-plan.md` §4 (SessionView, problem+json): un mock che mente nasconderebbe
// proprio il comportamento da provare (08 §16.2), per questo le forme sono quelle del piano.
import { vi } from "vitest";
import { problemResponse } from "./problem";

export interface FakeRequest {
  method: string;
  path: string;
  headers: Headers;
  body: unknown;
}

export type Handler = (request: FakeRequest) => Response | Promise<Response>;
/** Una richiesta che non risponde mai (stato di caricamento). */
export const PENDING: Handler = () => new Promise<Response>(() => undefined);

export interface FakeApi {
  calls: FakeRequest[];
  unexpected: FakeRequest[];
  /** Sostituisce un percorso (chiave `"GET /api/v1/session"`). */
  set(route: string, handler: Handler): void;
  count(route: string): number;
  last(route: string): FakeRequest;
}

export const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

export function installFakeApi(routes: Record<string, Handler>): FakeApi {
  const table = new Map<string, Handler>(Object.entries(routes));
  const calls: FakeRequest[] = [];
  const unexpected: FakeRequest[] = [];
  vi.stubGlobal("fetch", async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input.toString(), "http://localhost");
    const request: FakeRequest = {
      method: (init?.method ?? "GET").toUpperCase(),
      path: url.pathname + url.search,
      headers: new Headers(init?.headers),
      body: typeof init?.body === "string" && init.body !== "" ? JSON.parse(init.body) : undefined,
    };
    calls.push(request);
    const handler = table.get(`${request.method} ${url.pathname}`);
    if (!handler) {
      unexpected.push(request);
      return problemResponse("not_found");
    }
    return handler(request);
  });
  const matches = (route: string): FakeRequest[] =>
    calls.filter((c) => `${c.method} ${c.path.split("?")[0]}` === route);
  return {
    calls,
    unexpected,
    set: (route, handler) => table.set(route, handler),
    count: (route) => matches(route).length,
    last: (route) => {
      const found = matches(route).at(-1);
      if (!found) throw new Error(`nessuna chiamata a ${route}`);
      return found;
    },
  };
}

export const SESSION_ROUTE = "GET /api/v1/session";
export const START_ROUTE = "POST /api/v1/auth/google/start";
export const LOGOUT_ROUTE = "POST /api/v1/auth/logout";

export const CSRF_OF_SESSION = "csrf-della-sessione-0123456789abcdef";

export const anonymous = (authOutcome?: { code: string; params?: object }): Response =>
  json({ authenticated: false, notices: [], ...(authOutcome ? { authOutcome } : {}) });

export const authenticated = (overrides: Record<string, unknown> = {}): Response =>
  json({
    authenticated: true,
    csrfToken: CSRF_OF_SESSION,
    account: { id: "3f1c2b6e-8a47-4c55-9d0e-1a2b3c4d5e6f", displayName: "Alice Alfa" },
    family: {
      id: "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      name: "Famiglia Alfa",
      timezone: "Europe/Rome",
      today: "2026-10-23",
      status: "active",
    },
    person: { id: "0b3a1f0e-6f4e-4b57-8d2c-5a6b7c8d9e0f", role: "admin" },
    privacyReviewRequired: false,
    notices: [],
    ...overrides,
  });
