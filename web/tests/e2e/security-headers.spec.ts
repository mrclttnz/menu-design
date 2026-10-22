// SR-023, SR-031, SR-046; THR-074, THR-075, THR-070 (header): ciò che il browser riceve davvero
// dall'app servita da FastAPI (stessi controlli di backend/tests/unit/test_static_files.py,
// ma sulla build reale e, con E2E_BASE_URL, anche su un container o sullo staging).
import { expect, test, type APIRequestContext } from "@playwright/test";

function csp(value: string | undefined): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const part of (value ?? "").split(";")) {
    const words = part.trim().split(/\s+/).filter(Boolean);
    if (words[0]) out[words[0]] = words.slice(1);
  }
  return out;
}

const tokens = (value: string | undefined): string[] =>
  (value ?? "").split(",").map((t) => t.trim().toLowerCase());

async function entryAssets(
  request: APIRequestContext,
): Promise<{ scripts: string[]; styles: string[] }> {
  const response = await request.get("/");
  expect(response.status(), "GET / deve servire index.html").toBe(200);
  const html = await response.text();
  const scripts = [...html.matchAll(/<script[^>]*\bsrc="(\/assets\/[^"]+)"/g)].map(
    (m) => m[1] as string,
  );
  const styles = [...html.matchAll(/<link[^>]*rel="stylesheet"[^>]*href="(\/assets\/[^"]+)"/g)].map(
    (m) => m[1] as string,
  );
  // Senza questo controllo i test sugli asset sarebbero verdi a vuoto (nessun file da provare).
  expect(scripts.length, "index.html non referenzia script in /assets/").toBeGreaterThan(0);
  return { scripts, styles };
}

test.describe("header di sicurezza su ogni risposta", () => {
  for (const path of [
    "/",
    "/accedi",
    "/questa-rotta-non-esiste",
    "/api/v1/inesistente",
    "/healthz",
  ]) {
    test(`${path}`, async ({ request }) => {
      const response = await request.get(path);
      const expectedStatus = path.startsWith("/api/")
        ? [404]
        : path === "/healthz"
          ? [200, 503]
          : [200];
      expect(expectedStatus, `${path} -> ${response.status()}`).toContain(response.status());
      const h = response.headers();
      expect(h["x-content-type-options"]).toBe("nosniff");
      expect(h["strict-transport-security"]).toMatch(/max-age=\d{7,}/);
      expect(h["referrer-policy"]).toBeTruthy();
      const policy = csp(h["content-security-policy"]);
      expect(policy["default-src"]).toEqual(["'self'"]);
      expect(policy["script-src"]).toEqual(["'self'"]);
      expect(policy["connect-src"]).toEqual(["'self'"]);
      expect(policy["object-src"]).toEqual(["'none'"]);
      expect(policy["base-uri"]).toEqual(["'none'"]);
      expect(policy["frame-ancestors"]).toEqual(["'none'"]);
      expect(policy["form-action"]).toEqual(["'self'"]);
      expect(policy["require-trusted-types-for"]).toEqual(["'script'"]);
      expect(policy["style-src"]).toEqual(["'self'"]);
      expect(policy["img-src"]).toEqual(["'self'"]);
      expect(policy["trusted-types"]).toEqual(["'none'"]);
      const allowed = new Set(["'self'", "'none'", "'script'"]);
      for (const [directive, values] of Object.entries(policy)) {
        expect(
          values.filter((v) => !allowed.has(v)),
          `${directive} ammette origini esterne`,
        ).toEqual([]);
      }
    });
  }
});

test.describe("cache (SR-046)", () => {
  test("index.html e il fallback SPA: no-cache con validatore, mai immutable né no-store+max-age", async ({
    request,
  }) => {
    for (const path of ["/", "/index.html", "/accedi"]) {
      const response = await request.get(path);
      expect(response.status(), path).toBe(200);
      const cache = tokens(response.headers()["cache-control"]);
      expect(cache, path).toContain("no-cache");
      expect(cache, path).not.toContain("immutable");
      expect(response.headers()["etag"] ?? response.headers()["last-modified"], path).toBeTruthy();
    }
  });

  test("gli asset con hash nel nome sono immutable per un anno", async ({ request }) => {
    const { scripts, styles } = await entryAssets(request);
    expect(scripts.length).toBeGreaterThan(0);
    for (const url of [...scripts, ...styles]) {
      const response = await request.get(url);
      expect(response.status(), url).toBe(200);
      const cache = tokens(response.headers()["cache-control"]);
      expect(cache, url).toEqual(
        expect.arrayContaining(["public", "immutable", "max-age=31536000"]),
      );
      expect(response.headers()["x-content-type-options"], url).toBe("nosniff");
    }
  });

  test("sw.js, se esiste, è JavaScript con no-cache; se non esiste è 404, mai l HTML della SPA", async ({
    request,
  }) => {
    const response = await request.get("/sw.js");
    if (response.status() === 200) {
      expect(response.headers()["content-type"]).toMatch(/javascript/);
      expect(tokens(response.headers()["cache-control"])).toContain("no-cache");
    } else {
      expect(response.status()).toBe(404);
      expect(await response.text()).not.toContain('id="root"');
    }
  });

  test("le risposte dell API restano no-store (SR-046, THR-075)", async ({ request }) => {
    for (const path of ["/healthz", "/api/v1/inesistente"]) {
      expect(tokens((await request.get(path)).headers()["cache-control"]), path).toContain(
        "no-store",
      );
    }
  });
});

test.describe("consegna e allow-list", () => {
  test("NFR-001: i file JS e CSS arrivano compressi (il budget è sul gzip)", async ({
    request,
  }) => {
    const { scripts, styles } = await entryAssets(request);
    for (const url of [...scripts, ...styles]) {
      const response = await request.get(url, { headers: { "Accept-Encoding": "gzip" } });
      expect(response.headers()["content-encoding"], url).toBe("gzip");
      expect(response.headers()["vary"]?.toLowerCase(), url).toContain("accept-encoding");
    }
  });

  test("nessuna source map e nessun file fuori allow-list è servito (THR-074)", async ({
    request,
  }) => {
    const { scripts, styles } = await entryAssets(request);
    for (const url of [...scripts, ...styles]) {
      const response = await request.get(`${url}.map`);
      expect(response.status(), `${url}.map`).toBe(404);
    }
    for (const path of [
      "/.env",
      "/.git/config",
      "/package.json",
      "/assets/",
      "/..%2f..%2fetc/passwd",
      "/assets/..%5cindex.html",
    ]) {
      const response = await request.get(path);
      const body = await response.text();
      expect(body, path).not.toMatch(/root:x:|DATABASE_URL|"dependencies"/);
      expect([400, 404], path).toContain(response.status());
    }
  });

  test("un percorso API sconosciuto è un errore problem+json, non la pagina HTML", async ({
    request,
  }) => {
    const response = await request.get("/api/v1/inesistente");
    expect(response.status()).toBe(404);
    expect(response.headers()["content-type"]).toContain("application/problem+json");
    expect((await response.json()).code).toBe("not_found");
  });

  test("i metodi di scrittura sui file statici sono rifiutati", async ({ request }) => {
    for (const method of ["post", "put", "patch", "delete"] as const) {
      const response = await request[method]("/", { data: { a: 1 } });
      expect([404, 405], method).toContain(response.status());
    }
  });
});
