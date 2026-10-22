// Autotest del lettore di cataloghi usato dagli altri test: se sbaglia, i test dei cataloghi
// non provano nulla (08 §16.2: un controllo deve saper fallire).
import { describe, expect, it } from "vitest";
import { catalogMap, parsePo } from "../support/po";

const SAMPLE = `msgid ""
msgstr ""
"Language: it\\n"

#. js-lingui-explicit-id
#: src/app/x.tsx:3
msgid "common.save"
msgstr "Salva"

#. js-lingui-explicit-id
msgid "long.message"
msgstr ""
"Prima riga "
"seconda \\"citata\\"\\n"

msgid "icu.plural"
msgstr "{n, plural, one {1 pasto} other {# pasti}}"

#~ msgid "old.key"
#~ msgstr "Vecchio"
`;

describe("parsePo", () => {
  it("legge chiave e testo, ignora intestazione e commenti", () => {
    const map = catalogMap(SAMPLE);
    expect(map.get("common.save")).toBe("Salva");
    expect(map.has("")).toBe(false);
  });

  it("unisce le stringhe su più righe e risolve gli escape", () => {
    expect(catalogMap(SAMPLE).get("long.message")).toBe('Prima riga seconda "citata"\n');
  });

  it("conserva la sintassi ICU senza toccarla", () => {
    expect(catalogMap(SAMPLE).get("icu.plural")).toBe("{n, plural, one {1 pasto} other {# pasti}}");
  });

  it("esclude le voci obsolete dalla mappa ma le segnala nell elenco", () => {
    expect(catalogMap(SAMPLE).has("old.key")).toBe(false);
    expect(parsePo(SAMPLE).find((e) => e.id === "old.key")?.obsolete).toBe(true);
  });

  it("segnala le chiavi duplicate (la mappa ne perderebbe una)", () => {
    const dup = 'msgid "a.b"\nmsgstr "uno"\n\nmsgid "a.b"\nmsgstr "due"\n';
    expect(parsePo(dup).filter((e) => e.id === "a.b")).toHaveLength(2);
  });

  it("rifiuta righe che non appartengono al formato", () => {
    expect(() => parsePo("questo non è un catalogo")).toThrow(/non riconosciuta/);
  });
});
