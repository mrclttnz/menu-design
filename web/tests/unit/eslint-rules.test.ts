// `make lint-web` deve far rispettare davvero le regole di piano §2.4, §5.4 e di THR-070/THR-005:
// qui si danno all'ESLint reale (web/eslint.config.js) frammenti che DEVONO essere respinti e
// frammenti puliti che DEVONO passare. Se questa suite è verde, le regole non sono decorative.
// Assunzione sul contratto: la config lavora anche su file virtuali (lintText) sotto src/ e
// tests/ senza richiedere che esistano su disco (niente errori «file non trovato dal project
// service» per questi percorsi).
import path from "node:path";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";
import { WEB_ROOT } from "../support/repo";

async function lint(relativePath: string, code: string): Promise<string[]> {
  const eslint = new ESLint({ cwd: WEB_ROOT });
  const [result] = await eslint.lintText(code, { filePath: path.join(WEB_ROOT, relativePath) });
  return (result?.messages ?? []).map((m) => `${m.ruleId ?? "FATAL"}: ${m.message}`);
}

const hasRule = (messages: string[], rule: RegExp): boolean => messages.some((m) => rule.test(m));
// Il piano dice `no-restricted-imports` (anche la variante di typescript-eslint con
// allowTypeImports, che serve per «src/api solo come tipi»). Se la regola di base non vede i
// percorsi relativi, sono ammessi `import/no-restricted-paths` o `boundaries/*`: conta che
// il lint fallisca per un import fuori livello, non il nome del plugin.
const LAYER_RULE = /(no-restricted-imports|no-restricted-paths|boundaries\/)/;

describe("livelli (piano §2.4): imposti dal lint", () => {
  it.each([
    [
      "src/features/plan/Week.tsx",
      "import { x } from '../dishes/List';\nexport const a = x;\n",
      "altra feature",
    ],
    [
      "src/features/plan/Week.tsx",
      "import { r } from '../../app/routes';\nexport const a = r;\n",
      "app",
    ],
    [
      "src/components/Toast.tsx",
      "import { x } from '../features/plan/Week';\nexport const a = x;\n",
      "feature",
    ],
    [
      "src/lib/pasto-id.ts",
      "import { client } from '../api/client';\nexport const a = client;\n",
      "valore da api",
    ],
    [
      "src/api/errors.ts",
      "import { lib } from '../lib/pasto-id';\nexport const a = lib;\n",
      "api verso lib",
    ],
  ])("%s respinto (%s)", async (file, code) => {
    expect(hasRule(await lint(file, code), LAYER_RULE)).toBe(true);
  });

  it.each([
    [
      "src/features/plan/Week.ts",
      "import { x } from '../../components/Toast';\nexport const a = x;\n",
    ],
    [
      "src/features/plan/Week.ts",
      "import type { P } from '../../api/errors';\nexport type A = P;\n",
    ],
    ["src/lib/pasto-id.ts", "import type { P } from '../api/errors';\nexport type A = P;\n"],
    ["src/app/routes.ts", "import { x } from '../features/plan/Week';\nexport const a = x;\n"],
  ])("%s ammesso", async (file, code) => {
    expect(hasRule(await lint(file, code), LAYER_RULE)).toBe(false);
  });
});

describe("sicurezza del client (THR-070, THR-005, SR-037, Trusted Types)", () => {
  it.each([
    [
      "dangerouslySetInnerHTML",
      "src/features/plan/A.tsx",
      "export const A = (p: { h: string }) => <div dangerouslySetInnerHTML={{ __html: p.h }} />;\n",
    ],
    [
      "localStorage",
      "src/features/plan/a.ts",
      "export const save = (v: string) => localStorage.setItem('k', v);\n",
    ],
    [
      "sessionStorage",
      "src/session/a.ts",
      "export const save = (v: string) => sessionStorage.setItem('k', v);\n",
    ],
    [
      "window.localStorage",
      "src/lib/a.ts",
      "export const read = () => window.localStorage.getItem('k');\n",
    ],
    [
      "innerHTML",
      "src/components/a.ts",
      "export const put = (e: HTMLElement, h: string) => { e.innerHTML = h; };\n",
    ],
    [
      "outerHTML",
      "src/components/a.ts",
      "export const put = (e: HTMLElement, h: string) => { e.outerHTML = h; };\n",
    ],
    [
      "insertAdjacentHTML",
      "src/components/a.ts",
      "export const put = (e: HTMLElement, h: string) => { e.insertAdjacentHTML('beforeend', h); };\n",
    ],
    ["document.write", "src/lib/a.ts", "export const w = (h: string) => { document.write(h); };\n"],
    ["eval", "src/lib/a.ts", "export const run = (s: string) => eval(s);\n"],
    ["new Function", "src/lib/a.ts", "export const run = (s: string) => new Function(s);\n"],
  ])("%s è un errore bloccante", async (_name, file, code) => {
    const messages = await lint(file, code);
    expect(messages, "nessun errore per codice vietato").not.toEqual([]);
    expect(messages.some((m) => !m.startsWith("FATAL"))).toBe(true);
  });
});

describe("il codice di test non è bloccato dalle regole del codice di prodotto", () => {
  it("i test possono usare localStorage, innerHTML ed fs con percorsi variabili", async () => {
    const code = [
      "import fs from 'node:fs';",
      "export const a = (p: string) => fs.readFileSync(p);",
      "export const b = () => localStorage.clear();",
      'export const c = (e: HTMLElement) => { e.innerHTML = ""; };',
      "",
    ].join("\n");
    for (const file of ["tests/unit/x.test.ts", "tests/e2e/x.spec.ts"]) {
      expect(await lint(file, code), file).toEqual([]);
    }
  });
});

describe("i18n (NFR-011): lingui/no-unlocalized-strings", () => {
  it("testo italiano scritto nel JSX di una feature è un errore", async () => {
    const messages = await lint(
      "src/features/plan/A.tsx",
      "export const A = () => <p>Ciao famiglia</p>;\n",
    );
    expect(hasRule(messages, /lingui\/no-unlocalized-strings/)).toBe(true);
  });

  it("testo in un attributo accessibile (aria-label, title, alt, placeholder) è un errore", async () => {
    const code =
      'export const A = () => <input aria-label="Cerca un piatto" placeholder="Cerca" />;\n';
    expect(
      hasRule(await lint("src/features/plan/A.tsx", code), /lingui\/no-unlocalized-strings/),
    ).toBe(true);
  });

  it("un componente senza testo scritto nel codice è pulito", async () => {
    expect(
      await lint("src/features/plan/A.tsx", 'export const A = () => <div className="card" />;\n'),
    ).toEqual([]);
  });

  it("i test possono contenere testo italiano (altrimenti non si potrebbero scrivere)", async () => {
    const messages = await lint(
      "tests/unit/x.test.tsx",
      "export const A = () => <p>Ciao famiglia</p>;\n",
    );
    expect(hasRule(messages, /lingui\/no-unlocalized-strings/)).toBe(false);
  });
});
