import { lingui } from "@lingui/vite-plugin";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react(), lingui({ macroTransform: true })],
  build: {
    target: "es2023",
    sourcemap: false, // il server non serve mai i .map
    assetsInlineLimit: 0, // niente data: URI (CSP)
    modulePreload: { polyfill: false },
  },
  test: {
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    globals: false,
    environment: "node",
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/api/schema.gen.ts", "src/main.tsx", "src/vite-env.d.ts"],
      reporter: ["text-summary", "lcov"],
      thresholds: {
        lines: 80,
        branches: 70,
        "src/lib/**": { lines: 95, branches: 95, functions: 95, statements: 95 },
        "src/api/errors.ts": { lines: 95, branches: 95, functions: 95, statements: 95 },
      },
    },
  },
});
