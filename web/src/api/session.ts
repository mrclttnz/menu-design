// Contratto di sessione e accesso lato client (piano §4.2, ADR-0004), tipizzato dallo schema
// generato. Qui stanno i percorsi, i codici e i controlli sui valori che arrivano dal server:
// la UI (session, features) usa solo queste funzioni.
import { api, type ApiResult, type ProblemInfo, type ResponseInfo } from "./client";
import { resolveProblem } from "./errors";
import type { components, paths } from "./schema.gen";

export type SessionView =
  paths["/api/v1/session"]["get"]["responses"]["200"]["content"]["application/json"];
export type AuthOutcome = components["schemas"]["AuthOutcomeView"];
type StartBody =
  paths["/api/v1/auth/google/start"]["post"]["requestBody"]["content"]["application/json"];
type StartView =
  paths["/api/v1/auth/google/start"]["post"]["responses"]["200"]["content"]["application/json"];

export const SESSION_QUERY_KEY = ["session"] as const;
export const ANONYMOUS: SessionView = { authenticated: false, notices: [] };

/** Perché la sessione è finita (si mostra in S-01, una volta). */
export type SessionEnd = "expired" | "loggedOut";

/** Una risposta che chiude la sessione: `401 unauthenticated`, oppure l'uscita riuscita. */
export function sessionEndOf(info: ResponseInfo): SessionEnd | null {
  if (info.status === 401 && info.code === "unauthenticated") return "expired";
  if (info.method === "POST" && info.path === "/api/v1/auth/logout" && info.status < 300) {
    return "loggedOut";
  }
  return null;
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

/** La forma si ricontrolla: una risposta storta è un errore, mai una sessione «a metà». */
export function isSessionView(value: unknown): value is SessionView {
  if (!isRecord(value) || !Array.isArray(value["notices"])) return false;
  if (value["authenticated"] === false) return true;
  return (
    value["authenticated"] === true &&
    typeof value["csrfToken"] === "string" &&
    value["csrfToken"] !== "" &&
    isRecord(value["account"])
  );
}

export const fetchSession = (): Promise<ApiResult<unknown>> => api.get("/api/v1/session");

export const requestLogout = (): Promise<ApiResult<unknown>> =>
  api.post("/api/v1/auth/logout", { body: {} });

export const startLogin = (returnTo?: string): Promise<ApiResult<StartView>> => {
  const body: StartBody = returnTo ? { purpose: "login", returnTo } : { purpose: "login" };
  return api.post<StartView>("/api/v1/auth/google/start", { body });
};

// Percorsi della SPA a cui tornare dopo il login. Il server applica la sua allow-list (`/piano`
// negli altri casi): questo controllo evita di mandargli ciò che non è un percorso interno.
const RETURN_TO = /^\/(?:piano|piatti|altro)[A-Za-z0-9_./?=&-]*$/;

export function safeReturnTo(value: unknown): string | undefined {
  if (typeof value !== "string" || value.length > 200 || value.includes("..")) return undefined;
  return RETURN_TO.test(value) ? value : undefined;
}

const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

const GOOGLE_HOST = "accounts.google.com";

/** Solo `https://accounts.google.com`; in locale (stack di prova) `http:` ma solo su loopback esatto. */
export function safeRedirectUrl(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  try {
    const url = new URL(value);
    if (url.username !== "" || url.password !== "") return undefined;
    const google = url.protocol === "https:" && url.hostname === GOOGLE_HOST;
    const local = url.protocol === "http:" && LOOPBACK.has(url.hostname);
    return google || local ? value : undefined;
  } catch {
    return undefined;
  }
}

export interface Message {
  id: string;
  values: Record<string, string | number>;
}

/** Messaggio di S-01 per un `authOutcome`; i codici sconosciuti danno il testo generico. */
export function outcomeMessage(outcome: AuthOutcome): Message {
  if (outcome.code === "auth_cancelled") return { id: "auth.cancelled", values: {} };
  if (outcome.code === "reauth_wrong_account") {
    const resolved = resolveProblem({ code: outcome.code, params: outcome.params ?? {} });
    if (resolved.id !== "error.generic") return resolved;
  }
  return { id: "auth.failed", values: {} };
}

/** Messaggio per un avvio non riuscito: rete e limite di frequenza sì, il resto è generico. */
export function startFailureMessage(problem: ProblemInfo): Message {
  const resolved = resolveProblem(problem);
  const specific = resolved.id === "error.network" || resolved.id === "error.rateLimited";
  return specific ? resolved : { id: "auth.failed", values: {} };
}

export const isCsrfFailure = (problem: ProblemInfo): boolean => problem.code === "csrf_failed";
