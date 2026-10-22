// NFR-011 / ADR-0010: il catalogo `it` contiene tutti i testi della UX (nessuna chiave mancante),
// ogni chiave usata dal codice esiste, ogni codice del server ha il suo messaggio.
// Fonte dei testi: docs/03-ux.md §7.3. Fonte dei codici: openapi.json e ADR-0010.
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CATALOG_IT, DOCS, OPENAPI, SRC } from "../support/repo";
import { catalogMap, parsePo } from "../support/po";
import { requiredForSl01, uxMessages } from "../support/ux-catalog";

function catalog(): Map<string, string> {
  expect(fs.existsSync(CATALOG_IT), "web/src/locales/it/messages.po assente").toBe(true);
  return catalogMap(fs.readFileSync(CATALOG_IT, "utf8"));
}

function sourceFiles(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(ts|tsx)$/.test(entry.name) && !/schema\.gen\.ts$/.test(entry.name) ? [full] : [];
  });
}

describe("catalogo it: completezza (NFR-011)", () => {
  it("contiene tutte le chiavi della UX per le sezioni di SL-01, con il testo esatto", () => {
    const messages = catalog();
    const required = requiredForSl01();
    expect(required.length).toBeGreaterThanOrEqual(60);
    const missing = required.filter((m) => !messages.has(m.key)).map((m) => m.key);
    expect(missing, "chiavi mancanti").toEqual([]);
    const different = required
      .filter((m) => messages.get(m.key) !== m.text)
      .map((m) => `${m.key}: «${messages.get(m.key)}» invece di «${m.text}»`);
    expect(different, "testi diversi dalla UX").toEqual([]);
  });

  it("contiene le varianti e le chiavi nuove di plan §11.3", () => {
    const messages = catalog();
    for (const key of [
      "validation.invalid_value",
      "validation.unknown_field",
      "validation.dish_archived",
      "validation.dish_archived.noRestore",
      "error.dish_not_planned",
      "error.course_in_use",
      "error.reauth_wrong_account",
      "app.name",
      "app.documentTitle",
      "error.notFound.title",
      "error.notFound.back",
      "conflict.title.generic",
    ]) {
      expect(messages.has(key), key).toBe(true);
    }
    expect(messages.get("validation.dish_archived.noRestore")).toBe(
      "Questo piatto è archiviato e non si può aggiungere. Scegline un altro.",
    );
  });

  it("non ha messaggi vuoti, chiavi duplicate o voci obsolete", () => {
    const entries = parsePo(fs.readFileSync(CATALOG_IT, "utf8"));
    expect(entries.length).toBeGreaterThan(60);
    expect(
      entries.filter((e) => e.obsolete).map((e) => e.id),
      "voci obsolete",
    ).toEqual([]);
    expect(
      entries.filter((e) => e.message.trim() === "").map((e) => e.id),
      "vuoti",
    ).toEqual([]);
    const ids = entries.map((e) => e.id);
    expect(
      ids.filter((id, i) => ids.indexOf(id) !== i),
      "duplicate",
    ).toEqual([]);
  });

  it("usa chiavi semantiche (area.nome), mai il testo come identificatore", () => {
    for (const id of catalog().keys()) {
      expect(id, id).toMatch(/^[a-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+$/);
    }
  });

  it("ogni testo ICU ha le graffe bilanciate e le variabili della UX", () => {
    for (const [id, text] of catalog()) {
      let depth = 0;
      for (const ch of text) {
        if (ch === "{") depth += 1;
        if (ch === "}") depth -= 1;
        expect(depth, `${id}: graffa chiusa senza apertura`).toBeGreaterThanOrEqual(0);
      }
      expect(depth, `${id}: graffa non chiusa`).toBe(0);
    }
  });

  it("ogni chiave usata dal codice con id esplicito esiste nel catalogo", () => {
    const messages = catalog();
    const files = sourceFiles(SRC);
    expect(files.length, "nessun sorgente in web/src").toBeGreaterThan(5);
    const used = new Set<string>();
    for (const file of files) {
      const code = fs.readFileSync(file, "utf8");
      // id="x.y", id: 'x.y', i18n._('x.y') / t._('x.y'): i modi in cui il codice cita un id.
      const patterns = [
        /\bid\s*[=:]\s*\{?\s*["'`]([a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)["'`]/g,
        /\b_\(\s*["'`]([a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)["'`]/g,
      ];
      for (const pattern of patterns) {
        for (const m of code.matchAll(pattern)) used.add(m[1] as string);
      }
    }
    expect(used.size, "il codice non usa alcun id del catalogo").toBeGreaterThan(5);
    expect([...used].filter((id) => !messages.has(id)).sort()).toEqual([]);
  });
});

describe("catalogo it: codici del server (ADR-0010)", () => {
  const spec = JSON.parse(fs.readFileSync(OPENAPI, "utf8")) as {
    components: { schemas: { ErrorCode: { enum: string[] }; ValidationCode: { enum: string[] } } };
  };

  it("la tabella di ADR-0010 e l enumerazione di openapi.json coincidono (base dei test)", () => {
    const adr = fs.readFileSync(
      path.join(DOCS, "adr", "ADR-0010-internazionalizzazione.md"),
      "utf8",
    );
    const rows = [...adr.matchAll(/^\s*\|\s*(?:\*\*)?`([a-z_]+)`(?:\*\*)?\s*\|\s*\d{3}\s*\|/gm)];
    const codes = rows.map((m) => m[1] as string);
    expect(codes.length).toBeGreaterThanOrEqual(26);
    expect([...codes].sort()).toEqual([...spec.components.schemas.ErrorCode.enum].sort());
  });

  it("ogni testo della UX per un codice del server è nel catalogo (error.*, validation.*)", () => {
    const messages = catalog();
    const keys = uxMessages()
      .map((m) => m.key)
      .filter((k) => /^(error|validation)\./.test(k));
    expect(keys.length).toBeGreaterThanOrEqual(24);
    expect(keys.filter((k) => !messages.has(k))).toEqual([]);
  });
});
