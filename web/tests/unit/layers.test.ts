// Livelli del frontend (piano §2.4): il test d'architettura del web, gemello di
// backend/tests/architecture/test_layers.py. Il controllo sa fallire (fixture sintetiche),
// poi si applica al codice reale. L'imposizione in `make lint-web` è provata in eslint-rules.test.ts.
import path from "node:path";
import { describe, expect, it } from "vitest";
import { SRC } from "../support/repo";
import {
  importsOf,
  placeOf,
  sourceFiles,
  violationsFor,
  violationsInTree,
} from "../support/layers";

describe("importsOf", () => {
  it("riconosce import, export from, side effect, dinamici e require; ignora commenti", () => {
    const refs = importsOf(`
      import a from './a';
      import { b } from "../b";
      import * as c from '@/c';
      import type { D } from '../api/d';
      import { type E, type F } from '../api/e';
      import { type G, h } from '../api/g';
      export { i } from './i';
      export type { J } from './j';
      import './side-effect.css';
      const k = await import('./k');
      const l = require('./l');
      // import fake from './commento';
      /* import fake2 from './blocco'; */
    `);
    expect(refs.map((r) => r.specifier)).toEqual([
      "./a",
      "../b",
      "@/c",
      "../api/d",
      "../api/e",
      "../api/g",
      "./i",
      "./j",
      "./side-effect.css",
      "./k",
      "./l",
    ]);
    const typeOnly = Object.fromEntries(refs.map((r) => [r.specifier, r.typeOnly]));
    expect(typeOnly["../api/d"]).toBe(true);
    expect(typeOnly["../api/e"]).toBe(true);
    expect(typeOnly["../api/g"]).toBe(false); // `h` è un valore
    expect(typeOnly["./a"]).toBe(false);
  });
});

describe("placeOf", () => {
  it.each([
    ["api/client.ts", 0, "api"],
    ["i18n/format.ts", 0, "i18n"],
    ["lib/pasto-id.ts", 0, "lib"],
    ["components/Toast.tsx", 1, "components"],
    ["session/csrf.ts", 1, "session"],
    ["features/plan/Week.tsx", 2, "features"],
    ["app/routes.tsx", 3, "app"],
    ["main.tsx", 3, "app"],
  ])("%s -> strato %i (%s)", (file, layer, area) => {
    expect(placeOf(file)).toMatchObject({ layer, area });
  });
});

describe("violationsFor: il controllo sa fallire", () => {
  const imp = (from: string, to: string, kind = "import { x } from"): string[] =>
    violationsFor(from, `${kind} '${to}';`);

  it.each([
    ["features/plan/a.ts", "../dishes/b", "una feature non importa un altro feature"],
    ["features/plan/a.ts", "@/features/dishes/b", "alias @/"],
    ["features/plan/a.ts", "../../app/routes", "una feature non importa app"],
    ["components/Toast.tsx", "../features/plan/a", "components non importa le feature"],
    ["components/Toast.tsx", "../session/csrf", "components e session sono dello stesso strato"],
    ["session/csrf.ts", "../components/Toast", "session non importa components"],
    ["lib/pasto-id.ts", "../api/client", "lib importa da api solo i tipi"],
    ["i18n/format.ts", "../lib/pasto-id", "i18n e lib non si importano a vicenda"],
    ["lib/x.ts", "../components/Toast", "lib non importa gli strati superiori"],
    ["api/errors.ts", "../i18n/index", "api non importa altre cartelle"],
    ["api/errors.ts", "../lib/x", "api non importa lib"],
    ["components/Toast.tsx", "../../tests/support/x", "src non importa fuori da src"],
  ])("%s -> %s è una violazione (%s)", (from, to) => {
    expect(imp(from, to)).not.toEqual([]);
  });

  it.each([
    ["features/plan/a.ts", "./b", "stessa feature"],
    ["features/plan/a.ts", "../../components/Toast", "feature -> components"],
    ["features/plan/a.ts", "../../api/client", "feature -> api"],
    ["features/plan/a.ts", "../../session/csrf", "feature -> session"],
    ["features/plan/a.ts", "react", "pacchetto esterno"],
    ["components/Toast.tsx", "../api/errors", "components -> api"],
    ["components/Toast.tsx", "../i18n/format", "components -> i18n"],
    ["app/routes.tsx", "../features/plan/a", "app compone le feature"],
    ["main.tsx", "./app/routes", "main -> app"],
    ["lib/pasto-id.ts", "../api/schema.gen", "lib -> api (tipi), vedi sotto"],
  ])("%s -> %s è ammesso (%s)", (from, to, label) => {
    const kind = label.includes("tipi") ? "import type { X } from" : "import { x } from";
    expect(imp(from, to, kind)).toEqual([]);
  });

  it("lo schema generato è fuori controllo (non è codice scritto a mano)", () => {
    expect(violationsFor("api/schema.gen.ts", "import { x } from '../lib/y';")).toEqual([]);
  });
});

describe("codice reale di web/src", () => {
  it("esiste ed è abbastanza grande da essere un controllo vero", () => {
    expect(sourceFiles(SRC).length).toBeGreaterThanOrEqual(15);
  });

  it("rispetta i livelli di piano §2.4", () => {
    expect(violationsInTree(SRC)).toEqual([]);
  });

  it("ogni cartella di src è prevista dal piano (nessuno strato inventato)", async () => {
    const fs = await import("node:fs");
    const allowed = new Set([
      "app",
      "api",
      "session",
      "i18n",
      "locales",
      "components",
      "lib",
      "features",
      "styles",
    ]);
    const dirs = fs
      .readdirSync(SRC, { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => e.name);
    expect(dirs.filter((d) => !allowed.has(d))).toEqual([]);
    expect(path.basename(SRC)).toBe("src");
  });
});
