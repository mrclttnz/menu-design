// Client API sottile (ADR-0004, ADR-0008, ADR-0010): solo la stessa origine (SR-031,
// `connect-src 'self'`), cookie di sessione gestiti dal server, nessun dato nella console.
export interface ProblemInfo {
  code: string;
  params?: Record<string, unknown>;
  errors?: Array<{ field: string; code: string; params?: Record<string, unknown> }>;
}

export type ApiResult<T> =
  { ok: true; status: number; data: T } | { ok: false; status: number; problem: ProblemInfo };

export interface RequestOptions {
  body?: unknown;
  /** Versione per `If-Match` (ADR-0008): intero >= 0, al massimo 18 cifre. */
  ifMatch?: number | string;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export interface ApiClient {
  get<T = unknown>(path: string, options?: RequestOptions): Promise<ApiResult<T>>;
  post<T = unknown>(path: string, options?: RequestOptions): Promise<ApiResult<T>>;
  put<T = unknown>(path: string, options?: RequestOptions): Promise<ApiResult<T>>;
  patch<T = unknown>(path: string, options?: RequestOptions): Promise<ApiResult<T>>;
  delete<T = unknown>(path: string, options?: RequestOptions): Promise<ApiResult<T>>;
}

/** Esito di una chiamata, per chi deve reagire (sessione scaduta, uscita): mai il corpo. */
export interface ResponseInfo {
  method: string;
  path: string;
  status: number;
  code?: string;
}

/** Aggancio della sessione al client condiviso: token CSRF della sessione e reazioni agli esiti. */
export interface ApiHooks {
  csrfToken?: () => string | undefined;
  onResponse?: (info: ResponseInfo) => void;
}

const CSRF_COOKIE = "__Host-csrf";
const CSRF_HEADER = "X-CSRF-Token";

function readCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  for (const part of document.cookie.split("; ")) {
    const eq = part.indexOf("=");
    if (eq > 0 && part.slice(0, eq) === name) return part.slice(eq + 1) || undefined;
  }
  return undefined;
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

// Percorso assoluto sulla stessa origine: né `//host`, né `\`, né frammento, né controlli.
// eslint-disable-next-line no-control-regex
const SAME_ORIGIN_PATH = /^\/(?![/\\])[^\\#\u0000- \u007f]*$/;
const VERSION = /^(0|[1-9][0-9]{0,17})$/;

function ifMatchHeader(version: unknown): string {
  if (typeof version === "number" && Number.isSafeInteger(version) && version >= 0) {
    return `"${version}"`;
  }
  if (typeof version === "string" && VERSION.test(version)) return `"${version}"`;
  throw new RangeError("versione If-Match non valida");
}

function problemFrom(parsed: unknown): ProblemInfo {
  if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
    const record = parsed as Record<string, unknown>;
    if (typeof record["code"] === "string") {
      const problem: ProblemInfo = { code: record["code"] };
      if (typeof record["params"] === "object" && record["params"] !== null) {
        problem.params = record["params"] as Record<string, unknown>;
      }
      if (Array.isArray(record["errors"])) {
        problem.errors = record["errors"] as NonNullable<ProblemInfo["errors"]>;
      }
      return problem;
    }
  }
  return { code: "unknown" };
}

async function readJson(response: Response): Promise<{ ok: true; value: unknown } | { ok: false }> {
  try {
    const text = await response.text();
    return { ok: true, value: text === "" ? undefined : (JSON.parse(text) as unknown) };
  } catch {
    return { ok: false };
  }
}

export function createApiClient(
  options: { fetch?: typeof globalThis.fetch; hooks?: () => ApiHooks } = {},
): ApiClient {
  const hooks = options.hooks ?? ((): ApiHooks => ({}));
  const doFetch: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init));

  async function request<T>(
    method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
    path: string,
    opts: RequestOptions = {},
  ): Promise<ApiResult<T>> {
    if (!SAME_ORIGIN_PATH.test(path)) throw new TypeError("percorso non ammesso");
    const headers = new Headers(opts.headers);
    headers.set("Accept", "application/json");
    if (method !== "GET") headers.set("Content-Type", "application/json");
    if (method !== "GET" && !headers.has(CSRF_HEADER)) {
      // Doppio invio (SR-023): token della sessione se c'è, altrimenti il cookie anonimo.
      const token = hooks().csrfToken?.() ?? readCookie(CSRF_COOKIE);
      if (token) headers.set(CSRF_HEADER, token);
    }
    if (opts.ifMatch !== undefined) headers.set("If-Match", ifMatchHeader(opts.ifMatch));
    const init: RequestInit = { method, headers, credentials: "same-origin" };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    if (opts.signal) init.signal = opts.signal;

    let response: Response;
    try {
      response = await doFetch(path, init);
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") throw error;
      if (error instanceof Error && error.name === "AbortError") throw error;
      return { ok: false, status: 0, problem: { code: "network_error" } };
    }

    const body = await readJson(response);
    const notify = (code?: string): void => {
      const info: ResponseInfo = {
        method,
        path: path.split("?")[0] ?? path,
        status: response.status,
      };
      if (code !== undefined) info.code = code;
      hooks().onResponse?.(info);
    };
    if (response.ok) {
      notify();
      if (!body.ok) {
        return { ok: false, status: response.status, problem: { code: "invalid_response" } };
      }
      return { ok: true, status: response.status, data: body.value as T };
    }
    const problem: ProblemInfo = body.ok ? problemFrom(body.value) : { code: "unknown" };
    notify(problem.code);
    return { ok: false, status: response.status, problem };
  }

  return {
    get: (path, o) => request("GET", path, o),
    post: (path, o) => request("POST", path, o),
    put: (path, o) => request("PUT", path, o),
    patch: (path, o) => request("PATCH", path, o),
    delete: (path, o) => request("DELETE", path, o),
  };
}

let sharedHooks: ApiHooks = {};

/** Imposta gli agganci del client condiviso; restituisce la funzione che li toglie. */
export function configureApi(hooks: ApiHooks): () => void {
  sharedHooks = hooks;
  return () => {
    if (sharedHooks === hooks) sharedHooks = {};
  };
}

export const api: ApiClient = createApiClient({ hooks: () => sharedHooks });
