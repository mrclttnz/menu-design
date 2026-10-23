// NFR-011 / ADR-0010: il catalogo `it` contiene i testi di «Piatti (S-05, S-06, S-07)» di
// docs/03-ux.md §7.3 (milestone M0), con il testo esatto della UX, più le voci nuove di questa
// slice. Le chiavi M1/M2 della stessa sezione non sono richieste.
import fs from "node:fs";
import { describe, expect, it } from "vitest";
import { catalogMap } from "../../support/po";
import { CATALOG_IT } from "../../support/repo";
import { uxMessages } from "../../support/ux-catalog";

function catalog(): Map<string, string> {
  expect(fs.existsSync(CATALOG_IT)).toBe(true);
  return catalogMap(fs.readFileSync(CATALOG_IT, "utf8"));
}

const required = (): ReturnType<typeof uxMessages> =>
  uxMessages().filter((m) => m.section === "Piatti (S-05, S-06, S-07)" && m.milestone === null);

describe("catalogo it: sezione Piatti (SL-04)", () => {
  it("la sezione della UX ha almeno 40 voci M0", () => {
    expect(required().length).toBeGreaterThanOrEqual(40);
  });

  it("contiene tutte le chiavi M0 con il testo esatto", () => {
    const messages = catalog();
    const missing = required()
      .filter((m) => !messages.has(m.key))
      .map((m) => m.key);
    expect(missing, "chiavi mancanti").toEqual([]);
    const different = required()
      .filter((m) => messages.get(m.key) !== m.text)
      .map((m) => `${m.key}: «${messages.get(m.key)}» invece di «${m.text}»`);
    expect(different, "testi diversi dalla UX").toEqual([]);
  });

  it("ha un messaggio per ogni codice di validazione dell'archivio", () => {
    const messages = catalog();
    for (const key of [
      "validation.required",
      "validation.string_too_long",
      "validation.course_required",
      "validation.url_invalid",
      "validation.limit_reached",
      "error.notFound",
      "error.forbidden",
    ]) {
      expect(messages.has(key), key).toBe(true);
    }
  });
});
