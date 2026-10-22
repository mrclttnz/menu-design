// Playwright (08 §2, §15; piano §6.2 job `e2e`): Chromium a 360 px e desktop, axe incluso.
// L'app sotto test è quella servita da FastAPI (CSP, cache e fallback SPA sono dell'app, non
// di Vite). Variabili: E2E_BASE_URL (usa un server già avviato, per esempio un container),
// E2E_PORT (porta del server avviato da qui, predefinita 8000).
// Il server avviato da qui usa un database fittizio: S-01 e la shell non toccano il database.
import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const external = process.env["E2E_BASE_URL"];
const port = process.env["E2E_PORT"] ?? "8000";
const baseURL = external ?? `http://127.0.0.1:${port}`;
const dist = path.resolve(import.meta.dirname, "dist");
const dummyDatabase =
  "postgresql+psycopg://menu_app:" +
  "dummy-e2e-never-connected" +
  "@localhost:1/menu?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt";

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
        command: `uv run --frozen python -m menu serve --host 127.0.0.1 --port ${port}`,
        cwd: "../backend",
        env: {
          APP_ENV: "test",
          TRUSTED_PROXY_HOPS: "0",
          DATABASE_URL_APP: dummyDatabase,
          WEB_DIST_DIR: dist,
        },
        url: `${baseURL}/`,
        timeout: 60_000,
        reuseExistingServer: false,
      },
});
