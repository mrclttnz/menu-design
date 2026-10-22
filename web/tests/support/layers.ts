// Regole dei livelli del frontend (piano §2.4), applicate con un'analisi statica degli import:
//   0  api            nessun'altra cartella dell'app
//   0  i18n, lib      src/api, solo come tipi (`import type`)
//   1  components, session   strato 0 (non tra loro)
//   2  features/<x>   strati 0-1, mai un'altra feature, mai app
//   3  app (e main.tsx)      tutto
// Nessuna dipendenza esterna: il test non deve fidarsi dello strumento che controlla.
import fs from "node:fs";
import path from "node:path";

export interface ImportRef {
  specifier: string;
  typeOnly: boolean;
}

const COMMENTS = /\/\*[\s\S]*?\*\/|(^|[^:\\])\/\/[^\n]*/g;
const STATEMENT =
  /\b(import|export)\s+(type\s+)?([\w*${}\s,]*?)\s*from\s*(['"])([^'"\n]+)\4|\bimport\s*(['"])([^'"\n]+)\6|\bimport\s*\(\s*(['"])([^'"\n]+)\8\s*\)|\brequire\s*\(\s*(['"])([^'"\n]+)\10\s*\)/g;

export function importsOf(source: string): ImportRef[] {
  const code = source.replace(COMMENTS, "$1");
  const refs: ImportRef[] = [];
  for (const m of code.matchAll(STATEMENT)) {
    if (m[5]) {
      const clause = m[3] ?? "";
      const named = /^\s*\{([\s\S]*)\}\s*$/.exec(clause);
      const allInlineTypes =
        named !== null &&
        (named[1] as string)
          .split(",")
          .map((part) => part.trim())
          .filter(Boolean)
          .every((part) => part.startsWith("type "));
      refs.push({ specifier: m[5], typeOnly: Boolean(m[2]) || allInlineTypes });
    } else {
      const specifier = m[7] ?? m[9] ?? m[11];
      if (specifier) refs.push({ specifier, typeOnly: false });
    }
  }
  return refs;
}

export interface Place {
  layer: 0 | 1 | 2 | 3;
  area: string;
  feature?: string;
}

/** `relativeToSrc` con barre normali, per esempio `features/plan/x.ts`. */
export function placeOf(relativeToSrc: string): Place | null {
  const [first, second] = relativeToSrc.split("/");
  if (!first) return null;
  if (first === "api") return { layer: 0, area: "api" };
  if (first === "i18n" || first === "lib") return { layer: 0, area: first };
  if (first === "components" || first === "session") return { layer: 1, area: first };
  if (first === "features" && second) return { layer: 2, area: "features", feature: second };
  if (first === "app" || /^main\.tsx?$/.test(first)) return { layer: 3, area: "app" };
  return null; // locales, styles, vite-env.d.ts: fuori dalle regole
}

/** Percorso di un import relativo a `src/`, oppure `null` se è un pacchetto esterno. */
export function resolveInSrc(fromRelative: string, specifier: string): string | null {
  if (specifier.startsWith("@/")) return path.posix.normalize(specifier.slice(2));
  if (!specifier.startsWith(".")) return null;
  return path.posix.normalize(path.posix.join(path.posix.dirname(fromRelative), specifier));
}

export function violationsFor(fromRelative: string, source: string): string[] {
  const from = placeOf(fromRelative);
  if (!from || /\bschema\.gen\.ts$/.test(fromRelative)) return [];
  const problems: string[] = [];
  for (const ref of importsOf(source)) {
    const target = resolveInSrc(fromRelative, ref.specifier);
    if (target === null) continue;
    if (target.startsWith("..")) {
      problems.push(`${fromRelative}: importa fuori da src/ (${ref.specifier})`);
      continue;
    }
    const to = placeOf(target);
    if (!to) continue;
    const sameArea = to.area === from.area && to.feature === from.feature;
    if (sameArea) continue;
    const label = `${fromRelative} -> ${target}`;
    if (from.layer === 3) continue;
    if (from.area === "api") {
      problems.push(`${label}: src/api non importa altre cartelle dell'app`);
    } else if (from.layer === 0) {
      if (to.area !== "api") problems.push(`${label}: ${from.area} può importare solo src/api`);
      else if (!ref.typeOnly) problems.push(`${label}: da src/api solo tipi (import type)`);
    } else if (from.layer === 1) {
      if (to.layer !== 0) problems.push(`${label}: ${from.area} importa solo lo strato 0`);
    } else if (to.area === "features") {
      problems.push(`${label}: una feature non importa un'altra feature`);
    } else if (to.layer >= 2) {
      problems.push(`${label}: una feature non importa lo strato app`);
    }
  }
  return problems;
}

export function sourceFiles(root: string): string[] {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(root, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) ? [full] : [];
  });
}

export function violationsInTree(srcRoot: string): string[] {
  return sourceFiles(srcRoot).flatMap((file) =>
    violationsFor(
      path.relative(srcRoot, file).split(path.sep).join("/"),
      fs.readFileSync(file, "utf8"),
    ),
  );
}
