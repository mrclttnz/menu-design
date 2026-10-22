// Client API (piano §1 `src/api`, ADR-0004/0008/0010): sottile, tipizzato dallo schema generato,
// sulla stessa origine. Contratto assunto per web/src/api/client.ts:
//   createApiClient({ fetch? }) -> { get, post, put, patch, delete }
//   metodo(path, { body?, ifMatch?, signal?, headers? }) -> Promise<ApiResult<T>>
//   ApiResult = { ok: true, status, data } | { ok: false, status, problem: { code, params?, errors? } }
// Regole verificate: solo percorsi relativi (SR-031, connect-src 'self'); `Content-Type:
// application/json` su ogni metodo non sicuro, anche senza corpo (il server risponde 415
// altrimenti, nota di SL-00a); `If-Match` solo nella forma di ADR-0008 (mai un 500);
// errori problem+json -> `problem.code`; rete assente -> `network_error`.
import { describe, expect, it, vi } from "vitest";
import { createApiClient } from "../../../src/api/client";
import { resolveProblem } from "../../../src/api/errors";
import {
  problemBody,
  problemResponse,
  STATUS_BY_CODE,
  validateProblem,
} from "../../support/problem";

type FetchMock = ReturnType<typeof vi.fn<(input: string, init?: RequestInit) => Promise<Response>>>;

function clientWith(response: Response | (() => Response | Promise<Response>)): {
  api: ReturnType<typeof createApiClient>;
  fetch: FetchMock;
} {
  const fetch: FetchMock = vi.fn(async () =>
    typeof response === "function" ? response() : response.clone(),
  );
  return { api: createApiClient({ fetch: fetch as unknown as typeof globalThis.fetch }), fetch };
}

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function sent(fetch: FetchMock): { url: string; init: RequestInit; headers: Headers } {
  const [url, init] = fetch.mock.calls[0] as [string, RequestInit];
  return { url, init, headers: new Headers(init.headers) };
}

describe("richieste", () => {
  it("GET: URL relativo, nessun Content-Type, stessa origine", async () => {
    const { api, fetch } = clientWith(json({ status: "ok" }));
    await api.get("/healthz");
    const { url, init, headers } = sent(fetch);
    expect(url).toBe("/healthz");
    expect(init.method).toBe("GET");
    expect(headers.has("content-type")).toBe(false);
    expect(headers.get("accept")).toContain("application/json");
    expect(init.credentials).toBe("same-origin");
    expect(headers.has("authorization")).toBe(false);
  });

  it.each(["post", "put", "patch", "delete"] as const)(
    "%s senza corpo: Content-Type application/json comunque (altrimenti 415)",
    async (method) => {
      const { api, fetch } = clientWith(json({ ok: true }));
      await api[method]("/api/v1/x");
      const { init, headers } = sent(fetch);
      expect(init.method).toBe(method.toUpperCase());
      expect(headers.get("content-type")).toMatch(/^application\/json\b/);
      expect(init.body ?? null).toBeNull();
    },
  );

  it("POST con corpo: JSON serializzato", async () => {
    const { api, fetch } = clientWith(json({ ok: true }));
    await api.post("/api/v1/x", { body: { name: "Risotto", n: 2 } });
    expect(sent(fetch).init.body).toBe('{"name":"Risotto","n":2}');
  });

  it("inoltra il segnale di annullamento", async () => {
    const { api, fetch } = clientWith(json({}));
    const controller = new AbortController();
    await api.get("/healthz", { signal: controller.signal });
    expect(sent(fetch).init.signal).toBe(controller.signal);
  });

  it.each([
    "https://evil.example/x",
    "http://localhost/x",
    "//evil.example/x",
    "/\\evil.example",
    "\\\\evil.example",
    "evil.example",
    "api/v1/x",
    "",
    "/x\r\nHost: evil",
    "/x#frammento",
    "javascript:alert(1)",
    "data:text/plain,x",
  ])("percorso %j rifiutato prima di inviare (SR-031: solo la stessa origine)", async (path) => {
    const { api, fetch } = clientWith(json({}));
    await expect(api.get(path)).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("If-Match (ADR-0008, THR-107)", () => {
  it.each([
    [0, '"0"'],
    [3, '"3"'],
    [9_007_199_254_740_991, '"9007199254740991"'],
    ["999999999999999999", '"999999999999999999"'], // 18 cifre: il massimo accettato dal server
  ])("versione %j -> intestazione %s", async (version, header) => {
    const { api, fetch } = clientWith(json({}));
    await api.put("/api/v1/x", { body: {}, ifMatch: version });
    expect(sent(fetch).headers.get("if-match")).toBe(header);
  });

  it.each([
    -1,
    1.5,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    2 ** 53,
    "",
    "01",
    "1e3",
    " 1",
    "-1",
    "1234567890123456789",
    "abc",
    null,
  ])("versione %j rifiutata prima dell invio (il server risponderebbe 422)", async (version) => {
    const { api, fetch } = clientWith(json({}));
    await expect(api.put("/api/v1/x", { body: {}, ifMatch: version as never })).rejects.toThrow(
      RangeError,
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("senza ifMatch non inventa l intestazione", async () => {
    const { api, fetch } = clientWith(json({}));
    await api.put("/api/v1/x", { body: {} });
    expect(sent(fetch).headers.has("if-match")).toBe(false);
  });
});

describe("risposte", () => {
  it("2xx con JSON -> ok con i dati e lo stato", async () => {
    const { api } = clientWith(json({ status: "ok" }, 200));
    expect(await api.get("/healthz")).toEqual({ ok: true, status: 200, data: { status: "ok" } });
  });

  it("204 senza corpo -> ok senza dati", async () => {
    const { api } = clientWith(new Response(null, { status: 204 }));
    expect(await api.delete("/api/v1/x")).toEqual({ ok: true, status: 204, data: undefined });
  });

  it.each(Object.keys(STATUS_BY_CODE))(
    "problem+json %s -> problem.code conservato",
    async (code) => {
      const { api } = clientWith(
        problemResponse(code, code === "rate_limited" ? { params: { retryAfterSeconds: 3 } } : {}),
      );
      const result = await api.get("/api/v1/x");
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.status).toBe(STATUS_BY_CODE[code]);
        expect(result.problem.code).toBe(code);
      }
    },
  );

  it("422: errors[] arriva intatto", async () => {
    const body = problemBody("validation", {
      errors: [{ field: "name", code: "string_too_long", params: { max: 120 } }],
    });
    const { api } = clientWith(problemResponse("validation", { errors: body.errors ?? [] }));
    const result = await api.post("/api/v1/x", { body: {} });
    expect(!result.ok && result.problem.errors).toEqual(body.errors);
  });

  it.each([
    [
      "502 HTML del proxy",
      () =>
        new Response("<html>Bad gateway</html>", {
          status: 502,
          headers: { "Content-Type": "text/html" },
        }),
    ],
    ["500 senza corpo", () => new Response(null, { status: 500 })],
    ["500 con JSON senza code", () => json({ message: "boom" }, 500)],
    [
      "400 con corpo illeggibile",
      () =>
        new Response("{", { status: 400, headers: { "Content-Type": "application/problem+json" } }),
    ],
    [
      "200 con JSON rotto",
      () => new Response('{"a":', { status: 200, headers: { "Content-Type": "application/json" } }),
    ],
    ["404 con code non stringa", () => json({ code: { x: 1 } }, 404)],
  ])("%s -> errore, e il messaggio mostrato è error.generic", async (_name, make) => {
    const { api } = clientWith(make);
    const result = await api.get("/api/v1/x");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(resolveProblem(result.problem).id).toBe("error.generic");
  });

  it("rete assente (fetch rifiuta con TypeError) -> network_error, stato 0", async () => {
    const { api } = clientWith(() => Promise.reject(new TypeError("Failed to fetch")));
    const result = await api.get("/api/v1/x");
    expect(result).toMatchObject({ ok: false, status: 0, problem: { code: "network_error" } });
    if (!result.ok) expect(resolveProblem(result.problem).id).toBe("error.network");
  });

  it("annullamento: la promessa rifiuta con AbortError, non diventa un errore di rete", async () => {
    const abort = new DOMException("annullato", "AbortError");
    const { api } = clientWith(() => Promise.reject(abort));
    await expect(api.get("/api/v1/x")).rejects.toMatchObject({ name: "AbortError" });
  });

  it("non registra nulla nella console (nessun dato in chiaro, SR-021)", async () => {
    const spies = (["log", "info", "warn", "error", "debug"] as const).map((m) =>
      vi.spyOn(console, m).mockImplementation(() => undefined),
    );
    const { api } = clientWith(problemResponse("internal"));
    await api.post("/api/v1/x", { body: { note: "DATO-SENSIBILE" } });
    for (const spy of spies) expect(spy).not.toHaveBeenCalled();
    vi.restoreAllMocks();
  });
});

describe("le risposte simulate rispettano lo schema OpenAPI (08 §16.2)", () => {
  it.each(Object.keys(STATUS_BY_CODE))("problemBody(%s) è valido", (code) => {
    expect(validateProblem(problemBody(code))).toEqual([]);
  });

  it("il validatore sa fallire", () => {
    expect(validateProblem(problemBody("codice_inventato"))).toContain("code non in ErrorCode");
    expect(validateProblem({ type: "x" })).toEqual(
      expect.arrayContaining(["manca title", "manca code"]),
    );
    expect(validateProblem({ ...problemBody("internal"), detail: "x" })).toContain(
      "campo non previsto: detail",
    );
  });
});
