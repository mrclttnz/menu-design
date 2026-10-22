// NFR-001: bundle iniziale <= 150 KiB gzip (153600 byte). «Iniziale» = ciò che index.html carica
// subito (<script src>, <link rel="modulepreload">, <link rel="stylesheet">); i chunk caricati
// dopo con import dinamico non contano.
//   node scripts/check-budget.mjs [--dist <cartella>] [--max-bytes <n>]
// Uscita: 0 entro il limite; 1 oltre il limite o contenuto vietato (script/stile inline,
// risorsa esterna: SR-031, CSP); 2 errore d'uso (cartella o file mancante, nessuno script,
// percorso fuori dalla cartella).
import fs from "node:fs";
import path from "node:path";
import { gzipSync } from "node:zlib";

const DEFAULT_MAX = 150 * 1024;

function usage(message) {
  console.error(`check-budget: ${message}`);
  process.exit(2);
}

const args = process.argv.slice(2);
let distArg = "dist";
let max = DEFAULT_MAX;
for (let i = 0; i < args.length; i += 1) {
  if (args[i] === "--dist") distArg = args[(i += 1)] ?? usage("manca il valore di --dist");
  else if (args[i] === "--max-bytes") {
    const value = args[(i += 1)];
    if (!/^[0-9]+$/.test(value ?? "")) usage("--max-bytes vuole un intero");
    max = Number(value);
  } else usage(`argomento sconosciuto: ${args[i]}`);
}

const dist = path.resolve(distArg);
const indexPath = path.join(dist, "index.html");
if (!fs.existsSync(indexPath)) usage(`${indexPath} non esiste: eseguire prima la build`);
const html = fs.readFileSync(indexPath, "utf8");

const attr = (tag, name) =>
  new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, "i")
    .exec(tag)
    ?.slice(1)
    .find((v) => v !== undefined);

const references = [];
const forbidden = [];
const isExternal = (url) => /^([a-z][a-z0-9+.-]*:|\/\/)/i.test(url);

for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
  const src = attr(m[1], "src");
  if (src === undefined) {
    if (m[2].trim() !== "") forbidden.push("script inline");
  } else references.push(src);
}
for (const m of html.matchAll(/<link\b[^>]*>/gi)) {
  const rel = (attr(m[0], "rel") ?? "").toLowerCase().split(/\s+/);
  const href = attr(m[0], "href");
  if (href !== undefined && (rel.includes("stylesheet") || rel.includes("modulepreload"))) {
    references.push(href);
  }
}
if (/<style[\s>]/i.test(html)) forbidden.push("stile inline");

const files = [];
for (const url of references) {
  if (isExternal(url)) {
    forbidden.push(`risorsa esterna: ${url}`);
    continue;
  }
  const clean = url.split(/[?#]/)[0];
  const full = path.resolve(dist, clean.replace(/^\/+/, ""));
  if (full !== dist && !full.startsWith(dist + path.sep))
    usage(`percorso fuori dalla cartella: ${url}`);
  files.push({ url, full });
}

if (references.length === 0 && forbidden.length === 0) usage("index.html non carica alcuno script");
if (forbidden.length > 0) {
  console.error(`check-budget: contenuto vietato in index.html (${forbidden.join("; ")})`);
  process.exit(1);
}

let total = 0;
for (const { url, full } of files) {
  if (!fs.existsSync(full) || !fs.statSync(full).isFile())
    usage(`file referenziato ma assente: ${url}`);
  const gz = gzipSync(fs.readFileSync(full), { level: 9 }).length;
  total += gz;
  console.log(`  ${String(gz).padStart(8)} B gzip  ${url}`);
}
const verdict = total <= max ? "entro" : "OLTRE";
console.log(`bundle iniziale: ${total} byte gzip, limite ${max} (${verdict} il budget)`);
process.exit(total <= max ? 0 : 1);
