// ESLint (piano §5.4): regole di prodotto su src/**; tests/** e scripts/** esenti dai divieti
// di prodotto (possono usare localStorage, innerHTML, fs con percorsi variabili, testo italiano).
// Nessun type-aware linting: la config deve funzionare anche su file virtuali (lintText).
import js from "@eslint/js";
import lingui from "eslint-plugin-lingui";
import reactHooks from "eslint-plugin-react-hooks";
import security from "eslint-plugin-security";
import globals from "globals";
import tseslint from "typescript-eslint";

// --- Strati (piano §2.4), imposti con no-restricted-imports sui percorsi relativi ----------
// Un import relativo con k livelli «../» da un file a profondità d (rispetto alla cartella
// dell'area) esce dall'area se k > d: si controlla dove arriva. Nessun alias: `@/` non esiste.
const UP = (n) => `(\\.\\./){${n}}`;
const FREE = "locales|styles"; // fuori dalle regole (cataloghi e fogli di stile)
const MAX_DEPTH = 4;

const msg = (text) => `Strati (piano §2.4): ${text}`;
const rule = (patterns) => ({
  "@typescript-eslint/no-restricted-imports": ["error", { patterns }],
});

function flatArea(area, allowedTargets, { apiTypesOnly = false } = {}) {
  // area di strato 0/1: `src/<area>/**`
  const blocks = [];
  for (let depth = 0; depth <= MAX_DEPTH; depth += 1) {
    const dirs = Array.from({ length: depth }, () => "*").join("/");
    const files = depth === 0 ? `src/${area}/*.{ts,tsx}` : `src/${area}/${dirs}/*.{ts,tsx}`;
    const up = depth + 1; // livelli per arrivare in src/
    const patterns = [
      {
        // fuori da src/
        regex: `^${UP(up + 1)}`,
        message: msg("un import non esce da src/"),
      },
      {
        // dentro src/ ma in un'area non ammessa
        regex: `^${UP(up)}(?!(${[...allowedTargets, area, FREE].join("|")})(/|$))`,
        message: msg(`${area} importa solo ${allowedTargets.join(", ") || "se stesso"}`),
      },
    ];
    if (apiTypesOnly) {
      patterns.push({
        regex: `^${UP(up)}api(/|$)`,
        allowTypeImports: true,
        message: msg("da src/api solo tipi (import type)"),
      });
    }
    blocks.push({ files: [files], rules: rule(patterns) });
  }
  return blocks;
}

function featureBlocks() {
  const blocks = [];
  for (let depth = 0; depth <= MAX_DEPTH; depth += 1) {
    const dirs = depth === 0 ? "" : `${Array.from({ length: depth }, () => "*").join("/")}/`;
    blocks.push({
      files: [`src/features/*/${dirs}*.{ts,tsx}`],
      rules: rule([
        {
          // in src/features/: un'altra feature
          regex: `^${UP(depth + 1)}[^.]`,
          message: msg("una feature non importa un'altra feature"),
        },
        {
          // in src/: app, features, main
          regex: `^${UP(depth + 2)}(app|features|main)(/|$|\\.)`,
          message: msg("una feature non importa lo strato app né altre feature"),
        },
        { regex: `^${UP(depth + 3)}`, message: msg("un import non esce da src/") },
      ]),
    });
  }
  return blocks;
}

function appBlocks() {
  const blocks = [];
  for (let depth = 0; depth <= MAX_DEPTH; depth += 1) {
    const dirs = depth === 0 ? "" : `${Array.from({ length: depth }, () => "*").join("/")}/`;
    blocks.push({
      files: [`src/app/${dirs}*.{ts,tsx}`],
      rules: rule([{ regex: `^${UP(depth + 2)}`, message: msg("un import non esce da src/") }]),
    });
  }
  return blocks;
}

const layerBlocks = [
  ...flatArea("api", []),
  ...flatArea("lib", ["api"], { apiTypesOnly: true }),
  ...flatArea("i18n", ["api"], { apiTypesOnly: true }),
  ...flatArea("components", ["api", "i18n", "lib"]),
  ...flatArea("session", ["api", "i18n", "lib"]),
  ...featureBlocks(),
  ...appBlocks(),
];

// --- Sicurezza del client (THR-070, THR-005, SR-037, Trusted Types) ------------------------
const DOM_SINKS = "innerHTML|outerHTML|insertAdjacentHTML";
const restrictedSyntax = [
  {
    selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
    message: "dangerouslySetInnerHTML è vietato (THR-070).",
  },
  {
    selector: "Property[key.name='dangerouslySetInnerHTML']",
    message: "dangerouslySetInnerHTML è vietato (THR-070).",
  },
  {
    selector: `MemberExpression[property.name=/^(${DOM_SINKS})$/]`,
    message: "innerHTML, outerHTML e insertAdjacentHTML sono vietati (Trusted Types).",
  },
  {
    selector: "MemberExpression[property.name=/^(localStorage|sessionStorage)$/]",
    message: "localStorage e sessionStorage sono vietati (SR-037).",
  },
  {
    selector: "CallExpression[callee.object.name='document'][callee.property.name=/^write(ln)?$/]",
    message: "document.write è vietato.",
  },
];

const productRules = {
  "no-restricted-syntax": ["error", ...restrictedSyntax],
  "no-restricted-globals": [
    "error",
    { name: "localStorage", message: "localStorage è vietato (SR-037)." },
    { name: "sessionStorage", message: "sessionStorage è vietato (SR-037)." },
  ],
  // Rumorosa e senza falsi negativi utili qui: le ricerche per chiave usano Object.hasOwn.
  "security/detect-object-injection": "off",
  "no-eval": "error",
  "no-implied-eval": "off",
  "no-new-func": "error",
  "no-script-url": "error",
};

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "test-results/**",
      "playwright-report/**",
      "src/api/schema.gen.ts",
      "src/locales/*/messages.{js,ts}",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    linterOptions: { reportUnusedDisableDirectives: "error" },
  },
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks, security, lingui },
    languageOptions: { globals: globals.browser },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...security.configs.recommended.rules,
      ...productRules,
    },
  },
  {
    // Il testo dell'interfaccia sta nel catalogo (NFR-011): solo UI, non api/lib/i18n.
    files: [
      "src/components/**/*.{ts,tsx}",
      "src/features/**/*.{ts,tsx}",
      "src/app/**/*.{ts,tsx}",
      "src/session/**/*.{ts,tsx}",
      "src/main.tsx",
    ],
    plugins: { lingui },
    rules: {
      "lingui/no-unlocalized-strings": [
        "error",
        {
          // ID di catalogo, nomi di classe, percorsi e altri valori tecnici non sono testo utente.
          ignore: [
            "^[a-z][A-Za-z0-9_]*(\\.[A-Za-z0-9_]+)+$",
            "^(/|\\.{1,2}/|#)[\\w./#*$-]*$",
            "^[^A-Za-zÀ-ÿ]*$",
          ],
          ignoreFunctions: [
            "querySelector",
            "getElementById",
            "createElement",
            "Error",
            "*.querySelector",
            "*.getElementById",
          ],
          ignoreNames: [
            "className",
            "id",
            "key",
            "type",
            "role",
            "href",
            "to",
            "src",
            "slot",
            "code",
            "MAIN_ID",
            "path",
            "kind",
            "tabIndex",
            { regex: { pattern: "^(aria-(?!label|description|placeholder)|data-)", flags: "i" } },
          ],
        },
      ],
      "lingui/t-call-in-function": "error",
      "lingui/no-single-variables-to-translate": "error",
      "lingui/no-expression-in-message": "error",
      "lingui/no-trans-inside-trans": "error",
    },
  },
  ...layerBlocks.map((block) => ({
    ...block,
    files: block.files,
  })),
  {
    files: ["src/**/*.{ts,tsx}"],
    // Il registro dei messaggi contiene per definizione il testo italiano.
    ignores: [],
  },
  {
    files: ["tests/**/*.{ts,tsx}", "scripts/**/*.{js,mjs,ts}", "*.config.{js,ts}", "*.config.mjs"],
    rules: {
      "@typescript-eslint/no-non-null-assertion": "off",
    },
  },
);
