// SR-031: nessuno strumento di terzi. NFR-001: build leggera. THR-090: niente codice di
// analitica nel pacchetto che gira nel browser delle famiglie.
import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { VIEWS } from "./support/browser";

const DIST = path.resolve(import.meta.dirname, "../../dist");
const ANALYTICS =
  /(googletagmanager\.com|google-analytics\.com|googleapis\.com|gstatic\.com|doubleclick\.net|facebook\.(net|com)|hotjar\.com|segment\.(io|com)|mixpanel\.com|amplitude\.com|posthog\.com|sentry\.io|clarity\.ms|plausible\.io|matomo\.|fullstory\.com|logrocket\.(com|io)|cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com)/i;

function walk(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

for (const view of VIEWS) {
  test(`ogni richiesta resta sulla stessa origine: ${view.name}`, async ({ page, baseURL }) => {
    const origin = new URL(baseURL as string).origin;
    const foreign: string[] = [];
    await page.route("**/*", async (route) => {
      const url = route.request().url();
      if (url.startsWith("data:") || new URL(url).origin === origin) await route.continue();
      else {
        foreign.push(url);
        await route.abort();
      }
    });
    await page.goto(view.path);
    await page.getByRole("heading", { level: 1 }).waitFor();
    await page.waitForLoadState("networkidle");
    expect(foreign, "richieste verso terzi").toEqual([]);
  });
}

test.describe("la build in web/dist", () => {
  test("esiste (make e2e la costruisce prima dei test)", () => {
    expect(fs.existsSync(path.join(DIST, "index.html")), "web/dist/index.html assente").toBe(true);
  });

  test("nessun riferimento ad analitica, font o CDN di terzi in nessun file", () => {
    const offenders: string[] = [];
    for (const file of walk(DIST)) {
      if (!/\.(js|css|html|json|webmanifest|svg|txt)$/.test(file)) continue;
      const hit = ANALYTICS.exec(fs.readFileSync(file, "utf8"));
      if (hit) offenders.push(`${path.relative(DIST, file)}: ${hit[0]}`);
    }
    expect(offenders).toEqual([]);
  });

  test("nessuna source map e nessun commento sourceMappingURL (si pubblica solo ciò che serve)", () => {
    const files = walk(DIST);
    expect(files.filter((f) => f.endsWith(".map"))).toEqual([]);
    const withComment = files.filter(
      (f) => /\.(js|css)$/.test(f) && /sourceMappingURL=/.test(fs.readFileSync(f, "utf8")),
    );
    expect(withComment.map((f) => path.relative(DIST, f))).toEqual([]);
  });

  test("index.html: nessuno script o stile inline, nessuna risorsa esterna, lingua it", () => {
    const html = fs.readFileSync(path.join(DIST, "index.html"), "utf8");
    expect(html).toMatch(/<html[^>]*lang="it"/);
    expect(html).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>\s*\S/);
    expect(html).not.toMatch(/<style[\s>]|\sstyle\s*=|\son[a-z]+\s*=/i);
    expect(html).not.toMatch(/(?:src|href)\s*=\s*["']?(?:https?:)?\/\//i);
  });

  test("nomi dei file con hash: ogni file in assets/ ha l hash nel nome (cache immutable sicura)", () => {
    const assets = walk(path.join(DIST, "assets"));
    expect(assets.length).toBeGreaterThan(0);
    const unhashed = assets
      .map((f) => path.basename(f))
      .filter((name) => !/-[A-Za-z0-9_-]{8,}\.[a-z0-9]+$/.test(name));
    expect(unhashed).toEqual([]);
  });
});
