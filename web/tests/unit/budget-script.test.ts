// NFR-001: budget del bundle iniziale <= 150 KB gzip a ogni PR (piano §6.2 job `web`).
// Contratto assunto per web/scripts/check-budget.mjs:
//   node scripts/check-budget.mjs --dist <cartella> [--max-bytes <n>]    (predefinito 153600 = 150 KiB)
//   "iniziale" = ciò che index.html carica subito: <script src>, <link rel="modulepreload">,
//   <link rel="stylesheet">; si misura il gzip (livello 9) di ogni file e si sommano.
//   I chunk caricati dopo (import dinamici) NON contano.
//   Uscita: 0 entro il limite; 1 oltre il limite o contenuto vietato (script inline, risorsa
//   esterna: SR-031, CSP); 2 errore d uso (cartella o file mancante, nessuno script, percorso
//   che esce dalla cartella). Il messaggio riporta i byte misurati e il limite.
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { afterEach, describe, expect, it } from "vitest";
import { WEB_ROOT } from "../support/repo";

const SCRIPT = path.join(WEB_ROOT, "scripts", "check-budget.mjs");

// Senza lo script, `node` esce con codice 1: i test «deve fallire con 1» sarebbero verdi a vuoto.
function script(): string {
  if (!fs.existsSync(SCRIPT)) throw new Error("web/scripts/check-budget.mjs assente");
  return SCRIPT;
}
const made: string[] = [];

afterEach(() => {
  for (const dir of made.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

interface Fixture {
  dist: string;
  gz(file: string): number;
}

function makeDist(files: Record<string, Buffer | string>, indexBody: string): Fixture {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), "budget-"));
  made.push(dist);
  fs.mkdirSync(path.join(dist, "assets"));
  for (const [name, content] of Object.entries(files))
    fs.writeFileSync(path.join(dist, name), content);
  fs.writeFileSync(
    path.join(dist, "index.html"),
    `<!doctype html><html lang="it"><head><title>x</title>${indexBody}</head><body><div id="root"></div></body></html>`,
  );
  return {
    dist,
    gz: (file) => gzipSync(fs.readFileSync(path.join(dist, file)), { level: 9 }).length,
  };
}

function run(args: string[]): { status: number | null; output: string } {
  const result = spawnSync(process.execPath, [script(), ...args], {
    encoding: "utf8",
    timeout: 30_000,
  });
  return { status: result.status, output: `${result.stdout}${result.stderr}` };
}

const entry = '<script type="module" crossorigin src="/assets/index-AbCd1234.js"></script>';
const css = '<link rel="stylesheet" crossorigin href="/assets/index-EfGh5678.css">';
const preload = '<link rel="modulepreload" crossorigin href="/assets/vendor-IjKl9012.js">';

describe("check-budget.mjs", () => {
  it("esiste", () => {
    expect(fs.existsSync(SCRIPT), "web/scripts/check-budget.mjs assente").toBe(true);
  });

  it("un bundle piccolo passa e dichiara byte misurati e limite", () => {
    const f = makeDist({ "assets/index-AbCd1234.js": "console.log(1);\n".repeat(100) }, entry);
    const { status, output } = run(["--dist", f.dist]);
    expect(status, output).toBe(0);
    expect(output).toMatch(/153600/);
  });

  it("un bundle incomprimibile sopra 150 KiB fallisce con codice 1 e riporta la misura", () => {
    const f = makeDist({ "assets/index-AbCd1234.js": randomBytes(200 * 1024) }, entry);
    const { status, output } = run(["--dist", f.dist]);
    expect(status, output).toBe(1);
    expect(output).toContain(String(f.gz("assets/index-AbCd1234.js")).slice(0, 3));
  });

  it("il limite è sul gzip, non sui byte grezzi: 400 KB ripetitivi stanno nel budget", () => {
    const f = makeDist({ "assets/index-AbCd1234.js": "const a = 1;\n".repeat(40_000) }, entry);
    expect(fs.statSync(path.join(f.dist, "assets/index-AbCd1234.js")).size).toBeGreaterThan(
      400_000,
    );
    expect(run(["--dist", f.dist]).status).toBe(0);
  });

  it("--max-bytes: passa appena sotto il limite e fallisce appena sopra", () => {
    const f = makeDist({ "assets/index-AbCd1234.js": randomBytes(50 * 1024) }, entry);
    const measured = f.gz("assets/index-AbCd1234.js");
    expect(run(["--dist", f.dist, "--max-bytes", String(measured + 64)]).status).toBe(0);
    expect(run(["--dist", f.dist, "--max-bytes", String(measured - 64)]).status).toBe(1);
  });

  it("somma script, modulepreload e CSS: ciascuno sotto il limite, insieme sopra", () => {
    const f = makeDist(
      {
        "assets/index-AbCd1234.js": randomBytes(60 * 1024),
        "assets/vendor-IjKl9012.js": randomBytes(60 * 1024),
        "assets/index-EfGh5678.css": randomBytes(60 * 1024),
      },
      `${entry}${preload}${css}`,
    );
    const total = [
      "assets/index-AbCd1234.js",
      "assets/vendor-IjKl9012.js",
      "assets/index-EfGh5678.css",
    ]
      .map(f.gz)
      .reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThan(153_600);
    expect(run(["--dist", f.dist]).status).toBe(1);
  });

  it("i chunk non referenziati da index.html (caricati dopo) non contano", () => {
    const f = makeDist(
      {
        "assets/index-AbCd1234.js": "console.log(1);\n".repeat(100),
        "assets/lazy-MnOp3456.js": randomBytes(400 * 1024),
      },
      entry,
    );
    expect(run(["--dist", f.dist]).status).toBe(0);
  });

  it.each([
    ["script esterno", '<script type="module" src="https://cdn.example.test/x.js"></script>'],
    ["script con URL relativo al protocollo", '<script src="//cdn.example.test/x.js"></script>'],
    ["CSS esterno", '<link rel="stylesheet" href="https://fonts.example.test/x.css">'],
    ["script inline (vietato dalla CSP)", "<script>window.x = 1</script>"],
  ])("%s -> fallimento (SR-031, SR-023)", (_name, extra) => {
    const f = makeDist({ "assets/index-AbCd1234.js": "console.log(1);\n" }, `${entry}${extra}`);
    const { status, output } = run(["--dist", f.dist]);
    expect(status, output).toBe(1);
  });

  it.each([
    ["cartella inesistente", ["--dist", "/nonexistent/dist-xyz"]],
    ["argomenti assenti e nessuna build nella cwd", []],
  ])("%s -> codice 2", (_name, args) => {
    const result = spawnSync(process.execPath, [script(), ...args], {
      encoding: "utf8",
      cwd: os.tmpdir(),
      timeout: 30_000,
    });
    expect(result.status, `${result.stdout}${result.stderr}`).toBe(2);
  });

  it("file referenziato ma assente -> codice 2, mai un verde a vuoto", () => {
    const f = makeDist({}, entry);
    expect(run(["--dist", f.dist]).status).toBe(2);
  });

  it("index.html senza alcuno script -> codice 2 (una build vuota non è un bundle piccolo)", () => {
    const f = makeDist({}, "");
    expect(run(["--dist", f.dist]).status).toBe(2);
  });

  it("un percorso che esce dalla cartella è rifiutato senza leggerlo", () => {
    const f = makeDist({}, '<script type="module" src="/assets/../../etc/hostname"></script>');
    const { status, output } = run(["--dist", f.dist]);
    expect(status, output).toBe(2);
  });
});
