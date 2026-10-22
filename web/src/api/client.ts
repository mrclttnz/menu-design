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

export function createApiClient(options: { fetch?: typeof globalThis.fetch } = {}): ApiClient {
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
    if (response.ok) {
      if (!body.ok) {
        return { ok: false, status: response.status, problem: { code: "invalid_response" } };
      }
      return { ok: true, status: response.status, data: body.value as T };
    }
    return {
      ok: false,
      status: response.status,
      problem: body.ok ? problemFrom(body.value) : { code: "unknown" },
    };
  }

  return {
    get: (path, o) => request("GET", path, o),
    post: (path, o) => request("POST", path, o),
    put: (path, o) => request("PUT", path, o),
    patch: (path, o) => request("PATCH", path, o),
    delete: (path, o) => request("DELETE", path, o),
  };
}

export const api: ApiClient = createApiClient();
