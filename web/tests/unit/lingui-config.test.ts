// ADR-0010: lingue ricavate dalle cartelle dei cataloghi; formato .po con ID espliciti;
// aggiungere una lingua richiede solo nuovi file (NFR-011).
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import config from "../../lingui.config";
import { SRC } from "../support/repo";

describe("lingui.config.ts", () => {
  it("lingua sorgente e unica lingua dell MVP: it", () => {
    expect(config.sourceLocale).toBe("it");
    expect(config.locales).toEqual(["it"]);
  });

  it("le lingue configurate coincidono con le cartelle di src/locales (nessuna lingua nel codice)", () => {
    const dirs = fs
      .readdirSync(path.join(SRC, "locales"), { withFileTypes: true })
      .filter((e) => e.isDirectory())
      .map((e) => e.name)
      .sort();
    expect([...config.locales].sort()).toEqual(dirs);
  });

  it("catalogo .po in src/locales/{locale}/messages, formato po", () => {
    const catalog = config.catalogs?.[0];
    expect(catalog?.path).toMatch(/src\/locales\/\{locale\}\/messages$/);
    // Lingui 6: il formato è un oggetto (`formatter()` di @lingui/format-po), non la stringa 'po'.
    expect((config.format as { catalogExtension?: string } | undefined)?.catalogExtension).toBe(
      ".po",
    );
  });

  it("il locale di formattazione dell MVP è it-IT, il fuso è della famiglia (non del dispositivo)", () => {
    const source = fs.readFileSync(path.join(SRC, "i18n", "format.ts"), "utf8");
    expect(source).toMatch(/it-IT/);
    expect(source).not.toMatch(/toLocale(Date|Time)?String\(\s*\)/);
    expect(source).not.toMatch(/getTimezoneOffset|new Date\(\)\.getHours/);
  });
});
