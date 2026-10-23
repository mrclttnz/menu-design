// Playwright (08 §2, §15; piano §6.2 job `e2e`): Chromium a 360 px e desktop, axe incluso.
// L'app sotto test è quella servita da FastAPI (CSP, cache e fallback SPA sono dell'app, non
// di Vite). Variabili: E2E_BASE_URL (usa un server già avviato, per esempio un container),
// E2E_PORT (porta del server avviato da qui, predefinita 8000).
// SL-03a: il server avviato da qui è lo stack di `backend/tests/support/e2e_stack.py`: database di
// prova sul cluster di test (`make dev`, variabili MENU_TEST_PG_*), provider OIDC finto su
// E2E_STUB_PORT (predefinita: E2E_PORT + 1) e l'app collegata a entrambi. Contro un server esterno
// (E2E_BASE_URL) servono anche E2E_STUB_URL e lo stesso stack: senza, gli e2e di accesso saltano.
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const external = process.env["E2E_BASE_URL"];
const port = process.env["E2E_PORT"] ?? "8000";
const baseURL = external ?? `http://127.0.0.1:${port}`;
const stubPort = process.env["E2E_STUB_PORT"] ?? String(Number(port) + 1);
const dist = path.resolve(import.meta.dirname, "dist");

export default defineConfig({
  testDir: "./tests/e2e",
  outputDir: "./test-results/artifacts",
  fullyParallel: true,
  forbidOnly: Boolean(process.env["CI"]),
  retries: 0, // zero test instabili sulla linea principale (08 §16.1)
  workers: process.env["CI"] ? 2 : undefined,
  reporter: [["list"], ["junit", { outputFile: "test-results/e2e-junit.xml" }]],
  use: {
    baseURL,
    locale: "it-IT",
    timezoneId: "Europe/Rome",
    colorScheme: "light",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "mobile-360", use: { ...devices["Pixel 5"], viewport: { width: 360, height: 740 } } },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } },
    },
  ],
  webServer: external
    ? undefined
    : {
        command:
          `uv run --frozen python tests/support/e2e_stack.py --port ${port} ` +
          `--stub-port ${stubPort} --dist ${dist}`,
        cwd: "../backend",
        url: `${baseURL}/`,
        timeout: 120_000,
        reuseExistingServer: false,
      },
});
