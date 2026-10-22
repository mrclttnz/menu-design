// NFR-001: bundle iniziale <= 150 KB gzip, misurato due volte: con lo script del CI sulla
// build e con ciò che il browser scarica davvero caricando S-01 (script + CSS, lazy chunk
// inclusi se la rotta li richiede).
import { spawnSync } from "node:child_process";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { expect, test } from "@playwright/test";

const LIMIT = 150 * 1024;
const WEB = path.resolve(import.meta.dirname, "../..");

test("lo script di budget del CI passa sulla build corrente", () => {
  const result = spawnSync(process.execPath, ["scripts/check-budget.mjs", "--dist", "dist"], {
    cwd: WEB,
    encoding: "utf8",
  });
  expect(result.status, `${result.stdout}${result.stderr}`).toBe(0);
});

test("S-01 scarica meno di 150 KiB di JS e CSS (gzip)", async ({ page }) => {
  const sizes: Array<{ url: string; gzip: number }> = [];
  const pending: Array<Promise<void>> = [];
  page.on("response", (response) => {
    const type = response.request().resourceType();
    if (type !== "script" && type !== "stylesheet") return;
    pending.push(
      response.body().then((body) => {
        sizes.push({ url: response.url(), gzip: gzipSync(body, { level: 9 }).length });
      }),
    );
  });
  await page.goto("/accedi");
  await page.getByRole("heading", { level: 1 }).waitFor();
  await page.waitForLoadState("networkidle");
  await Promise.all(pending);
  expect(sizes.length, "nessuno script o CSS caricato").toBeGreaterThan(0);
  const total = sizes.reduce((sum, item) => sum + item.gzip, 0);
  expect(total, JSON.stringify(sizes)).toBeLessThanOrEqual(LIMIT);
});
