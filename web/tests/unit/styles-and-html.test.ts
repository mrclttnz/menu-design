// UX §8-§9 e SR-031/NFR-001 sui file statici del frontend: token di colore con i contrasti
// WCAG, focus visibile, movimento ridotto, testo >= 14 px, nessun font o CSS remoto,
// index.html senza script o stili inline (CSP `script-src 'self'`, `style-src 'self'`).
// Contratto: web/src/styles/tokens.css definisce le variabili `--color-*` della UX §9.2.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { SRC, WEB_ROOT } from "../support/repo";

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}
function luminance(hex: string): number {
  const n = Number.parseInt(hex.replace("#", ""), 16);
  return (
    0.2126 * channel((n >> 16) & 255) + 0.7152 * channel((n >> 8) & 255) + 0.0722 * channel(n & 255)
  );
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

function tokens(): Record<string, string> {
  const css = fs.readFileSync(path.join(SRC, "styles", "tokens.css"), "utf8");
  return Object.fromEntries(
    [...css.matchAll(/(--color-[a-z-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)].map((m) => [
      m[1],
      (m[2] as string).toUpperCase(),
    ]),
  );
}

describe("calcolo del contrasto (il controllo sa fallire)", () => {
  it("bianco su nero è 21:1 e grigio su grigio è sotto 4,5", () => {
    expect(contrast("#FFFFFF", "#000000")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#888888")).toBeLessThan(1.5);
  });
});

describe("token di colore (UX 9.2)", () => {
  const expected: Record<string, string> = {
    "--color-bg": "#FFFFFF",
    "--color-surface": "#F9FAFB",
    "--color-text": "#1F2937",
    "--color-text-muted": "#4B5563",
    "--color-border": "#6B7280",
    "--color-divider": "#D1D5DB",
    "--color-primary": "#15803D",
    "--color-primary-hover": "#166534",
    "--color-primary-subtle": "#F0FDF4",
    "--color-danger": "#B91C1C",
    "--color-danger-subtle": "#FEF2F2",
    "--color-warning-subtle": "#FFFBEB",
    "--color-info": "#1D4ED8",
    "--color-info-subtle": "#EFF6FF",
    "--color-focus": "#1D4ED8",
  };

  it("definisce tutti i token con i valori della UX", () => {
    expect(tokens()).toMatchObject(expected);
  });

  it.each([
    ["--color-text", "--color-bg", 4.5],
    ["--color-text-muted", "--color-bg", 4.5],
    ["--color-text-muted", "--color-surface", 4.5],
    ["--color-bg", "--color-primary", 4.5], // testo bianco sul pulsante primario
    ["--color-bg", "--color-primary-hover", 4.5],
    ["--color-danger", "--color-bg", 4.5], // testo e icone di errore su bianco
    ["--color-bg", "--color-danger", 4.5],
    ["--color-info", "--color-bg", 4.5], // link
    ["--color-border", "--color-bg", 3], // bordi dei campi (1.4.11)
    ["--color-focus", "--color-bg", 3], // anello di focus (2.4.7)
  ])("%s su %s >= %s:1 (WCAG 1.4.3 / 1.4.11)", (fg, bg, minimum) => {
    const t = tokens();
    expect(contrast(t[fg] as string, t[bg] as string)).toBeGreaterThanOrEqual(minimum);
  });
});

function cssFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const full = path.join(dir, e.name);
    return e.isDirectory() ? cssFiles(full) : e.name.endsWith(".css") ? [full] : [];
  });
}

describe("CSS (UX 8.1, 8.2, 9.3; SR-031, NFR-001)", () => {
  const files = cssFiles(SRC);
  const css = (): string => files.map((f) => fs.readFileSync(f, "utf8")).join("\n");

  it("ci sono fogli di stile", () => {
    expect(files.length).toBeGreaterThanOrEqual(1);
  });

  it("nessun font, @import o url() remoto: carattere di sistema (SR-031)", () => {
    const text = css();
    expect(text).not.toMatch(/@import\s+(url\()?["']?(https?:)?\/\//i);
    expect(text).not.toMatch(/url\(\s*["']?(https?:)?\/\//i);
    expect(text).not.toMatch(/@font-face/);
    expect(text).toMatch(/font-family:[^;]*system-ui/);
  });

  it("non toglie mai l anello di focus senza sostituto (WCAG 2.4.7)", () => {
    const text = css();
    if (/outline\s*:\s*(none|0)\b/.test(text)) {
      expect(text).toMatch(/:focus-visible[^{]*\{[^}]*(outline|box-shadow)\s*:/);
    }
    expect(text).toMatch(/:focus-visible/);
  });

  it("rispetta prefers-reduced-motion se usa transizioni o animazioni (UX 8.2)", () => {
    const text = css();
    if (/\b(transition|animation)\s*:/.test(text)) {
      expect(text).toMatch(/@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)/);
    }
  });

  it("nessun testo sotto 14 px (0,875 rem)", () => {
    const small: string[] = [];
    for (const m of css().matchAll(/font-size\s*:\s*([\d.]+)(px|rem|em)/g)) {
      const px = Number(m[1]) * (m[2] === "px" ? 1 : 16);
      if (px < 14) small.push(m[0]);
    }
    expect(small).toEqual([]);
  });
});

describe("index.html (SR-031, CSP, WCAG 3.1.1, 1.4.4)", () => {
  const html = (): string => fs.readFileSync(path.join(WEB_ROOT, "index.html"), "utf8");

  it("lingua italiana, viewport che non blocca lo zoom, titolo e radice", () => {
    const text = html();
    expect(text).toMatch(/<html[^>]*\blang="it"/);
    expect(text).toMatch(/<meta[^>]*name="viewport"[^>]*width=device-width/);
    expect(text).not.toMatch(/user-scalable\s*=\s*(no|0)/i);
    expect(text).not.toMatch(/maximum-scale\s*=\s*1(\.0)?\b/);
    expect(text).toMatch(/<title>\s*Menu Design/);
    expect(text).toMatch(/<div id="root"><\/div>/);
  });

  it("nessuno script o stile inline, nessuna risorsa esterna", () => {
    const text = html();
    expect(text).not.toMatch(/<script(?![^>]*\bsrc=)[^>]*>\s*\S/);
    expect(text).not.toMatch(/<style[\s>]/i);
    expect(text).not.toMatch(/\sstyle\s*=/i);
    expect(text).not.toMatch(/\son[a-z]+\s*=/i);
    expect(text).not.toMatch(/(?:src|href)\s*=\s*["']?(?:https?:)?\/\//i);
  });
});
