// NFR-011 / ADR-0010: il catalogo `it` contiene i testi di «Piano e pasto (S-02, S-03)» di
// docs/03-ux.md §7.3 (milestone M0), con il testo esatto della UX. Le chiavi M1/M2 della stessa
// sezione non sono richieste.
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
  uxMessages().filter((m) => m.section === "Piano e pasto (S-02, S-03)" && m.milestone === null);

describe("catalogo it: sezione Piano e pasto (SL-06a)", () => {
  it("la sezione della UX ha almeno 50 voci M0", () => {
    expect(required().length).toBeGreaterThanOrEqual(50);
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

  it("ha il messaggio del limite dell'intervallo (D-05)", () => {
    const messages = catalog();
    for (const key of [
      "error.range_too_large",
      "validation.date_invalid",
      "validation.range_order",
    ]) {
      expect(messages.has(key), key).toBe(true);
    }
  });
});
