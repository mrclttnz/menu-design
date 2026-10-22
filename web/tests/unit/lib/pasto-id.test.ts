// ADR-0009: `pastoId` è un identificativo solo del client, biunivoco con (mealType, slot):
//   - tipo da solo per lo slot 0 (`cena`, `altro`), `<tipo>-<slot>` per gli slot 1-4 (`altro-2`);
//   - il server usa mealType in inglese; slot > 0 solo per "Altro pasto" (massimo 5 attivi);
//   - un pastoId non valido mostra error.notFound (quindi `fromPastoId` restituisce null).
// Contratto assunto per web/src/lib/pasto-id.ts:
//   toPastoId(mealType, slot): string            (RangeError se la coppia non esiste)
//   fromPastoId(input: unknown): { mealType, slot } | null
import { describe, expect, it } from "vitest";
import { fromPastoId, toPastoId } from "../../../src/lib/pasto-id";

const VALID: Array<[string, number, string]> = [
  ["breakfast", 0, "colazione"],
  ["lunch", 0, "pranzo"],
  ["snack", 0, "merenda"],
  ["dinner", 0, "cena"],
  ["other", 0, "altro"],
  ["other", 1, "altro-1"],
  ["other", 2, "altro-2"],
  ["other", 3, "altro-3"],
  ["other", 4, "altro-4"],
];

describe("pasto-id: conversione biunivoca (ADR-0009)", () => {
  it.each(VALID)("(%s, %i) <-> %s", (mealType, slot, id) => {
    expect(toPastoId(mealType as never, slot)).toBe(id);
    expect(fromPastoId(id)).toEqual({ mealType, slot });
  });

  it("il giro completo è l identità su tutte le 9 coppie valide", () => {
    const ids = new Set<string>();
    for (const [mealType, slot] of VALID) {
      const id = toPastoId(mealType as never, slot);
      expect(fromPastoId(id)).toEqual({ mealType, slot });
      ids.add(id);
    }
    expect(ids.size).toBe(VALID.length);
  });
});

describe("pasto-id: input non validi (error.notFound, mai un errore non gestito)", () => {
  it.each([
    "",
    " ",
    "Cena", // maiuscole: l identificativo è canonico
    "CENA",
    " cena",
    "cena ",
    "cena-0", // lo slot 0 si scrive senza suffisso: una sola forma per coppia
    "altro-0",
    "cena-1", // slot > 0 solo per "Altro pasto"
    "pranzo-2",
    "altro-5", // oltre i 5 attivi (slot 0-4)
    "altro-10",
    "altro-01",
    "altro--1",
    "altro-1-2",
    "altro-",
    "altro_1",
    "altro-1.0",
    "altro-1e0",
    "altro-+1",
    "altro-１", // cifra a larghezza piena
    "altro-١", // cifra arabo-indiana
    "-1",
    "dinner", // il nome del server non è un pastoId
    "other-1",
    "colazione/pranzo",
    "../cena",
    "cena\n",
    "cena\u0000",
    "__proto__",
    "constructor",
    "toString",
    "a".repeat(10_000),
  ])("fromPastoId(%j) -> null", (input) => {
    expect(fromPastoId(input)).toBeNull();
  });

  it.each([null, undefined, 0, 1, true, {}, [], ["cena"], { toString: () => "cena" }])(
    "fromPastoId(%j) -> null per input non stringa",
    (input) => {
      expect(fromPastoId(input)).toBeNull();
    },
  );

  it.each([
    ["dinner", 1],
    ["lunch", 4],
    ["other", 5],
    ["other", -1],
    ["other", 1.5],
    ["other", Number.NaN],
    ["other", Number.POSITIVE_INFINITY],
    ["brunch", 0],
    ["", 0],
  ])("toPastoId(%j, %j) lancia RangeError", (mealType, slot) => {
    expect(() => toPastoId(mealType as never, slot as number)).toThrow(RangeError);
  });
});
