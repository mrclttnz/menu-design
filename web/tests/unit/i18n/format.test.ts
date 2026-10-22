// NFR-011 / ADR-0010 / ADR-0009: date, ore e numeri solo con Intl, locale it-IT e fuso della
// famiglia (mai quello del dispositivo né quello del server). Esempi dalla UX §S-02 e §5.3.
// Contratto assunto per web/src/i18n/format.ts (ultimo parametro `locale`, predefinito 'it-IT'):
//   formatRange(startIso, endIso, locale?)       "19 - 25 ottobre 2026"
//   formatDayHeading(isoDate, locale?)           "Lunedì 19"
//   formatTime(instant, timeZone, locale?)       "02:30" (24 ore)
//   formatDateTime(instant, timeZone, locale?)   "25 ottobre 2026, 02:30"
//   formatNumber(value, locale?)                 "1.850"
// Le date di calendario sono stringhe `AAAA-MM-GG` senza fuso; gli istanti sono Date o ISO 8601.
import { afterEach, describe, expect, it } from "vitest";
import {
  formatDateTime,
  formatDayHeading,
  formatNumber,
  formatRange,
  formatTime,
} from "../../../src/i18n/format";

const ORIGINAL_TZ = process.env["TZ"];
afterEach(() => {
  if (ORIGINAL_TZ === undefined) delete process.env["TZ"];
  else process.env["TZ"] = ORIGINAL_TZ;
});

describe("formatRange (UX: «19 - 25 ottobre 2026»)", () => {
  it.each([
    ["2026-10-19", "2026-10-25", "19 - 25 ottobre 2026"],
    ["2026-10-28", "2026-11-03", "28 ottobre - 3 novembre 2026"],
    ["2026-12-30", "2027-01-05", "30 dicembre 2026 - 5 gennaio 2027"],
    ["2026-10-19", "2026-10-19", "19 ottobre 2026"],
    ["2028-02-27", "2028-03-01", "27 febbraio - 1 marzo 2028"],
  ])("%s .. %s -> %s", (start, end, expected) => {
    expect(formatRange(start, end)).toBe(expected);
  });

  it("non cambia con il fuso del dispositivo (la data di calendario non ha fuso)", () => {
    for (const tz of ["Pacific/Kiritimati", "America/Los_Angeles", "UTC"]) {
      process.env["TZ"] = tz;
      expect(formatRange("2026-10-19", "2026-10-25"), tz).toBe("19 - 25 ottobre 2026");
    }
  });

  it.each([
    ["2026-13-01", "2026-13-02"],
    ["2026-02-30", "2026-03-01"],
    ["2026-10-19", "domani"],
    ["", ""],
  ])("data non valida (%j, %j) -> RangeError", (a, b) => {
    expect(() => formatRange(a, b)).toThrow(RangeError);
  });
});

describe("formatDayHeading (UX: «Lunedì 19»)", () => {
  it("maiuscola iniziale e giorno senza zero", () => {
    expect(formatDayHeading("2026-10-19")).toBe("Lunedì 19");
    expect(formatDayHeading("2026-11-01")).toBe("Domenica 1");
    expect(formatDayHeading("2026-10-25")).toBe("Domenica 25");
  });

  it("il giorno della settimana non scivola con il fuso del dispositivo", () => {
    for (const tz of ["Pacific/Kiritimati", "America/Los_Angeles", "Pacific/Pago_Pago", "UTC"]) {
      process.env["TZ"] = tz;
      expect(formatDayHeading("2026-10-19"), tz).toBe("Lunedì 19");
    }
  });

  it("data inesistente -> RangeError", () => {
    expect(() => formatDayHeading("2026-02-29")).toThrow(RangeError);
    expect(() => formatDayHeading("19/10/2026")).toThrow(RangeError);
  });
});

describe("formatTime / formatDateTime: fuso della famiglia (ADR-0009)", () => {
  it("stesso istante, fusi diversi, ore diverse", () => {
    const instant = "2026-10-25T00:30:00Z";
    expect(formatTime(instant, "Europe/Rome")).toBe("02:30");
    expect(formatTime(instant, "America/New_York")).toBe("20:30");
    expect(formatTime(instant, "Asia/Tokyo")).toBe("09:30");
  });

  it("il fuso del dispositivo non conta", () => {
    for (const tz of ["Pacific/Kiritimati", "America/Los_Angeles", "UTC"]) {
      process.env["TZ"] = tz;
      expect(formatTime(new Date("2026-07-01T12:00:00Z"), "Europe/Rome"), tz).toBe("14:00");
    }
  });

  it("cambio d ora: 02:30 esiste due volte il 25 ottobre 2026 e gli istanti restano distinti", () => {
    const before = formatDateTime("2026-10-25T00:30:00Z", "Europe/Rome");
    const after = formatDateTime("2026-10-25T01:30:00Z", "Europe/Rome");
    expect(before).toContain("25 ottobre 2026");
    expect(before).toContain("02:30");
    expect(after).toContain("02:30");
    expect(formatTime("2026-10-25T00:59:00Z", "Europe/Rome")).toBe("02:59");
    expect(formatTime("2026-10-25T01:00:00Z", "Europe/Rome")).toBe("02:00");
  });

  it("mezzanotte è 00:00, non 24:00", () => {
    expect(formatTime("2026-10-18T22:00:00Z", "Europe/Rome")).toBe("00:00");
  });

  it("il giorno cambia con il fuso: 22:30 UTC è già il giorno dopo a Roma", () => {
    expect(formatDateTime("2026-10-18T22:30:00Z", "Europe/Rome")).toContain("19 ottobre 2026");
    expect(formatDateTime("2026-10-18T22:30:00Z", "America/New_York")).toContain("18 ottobre 2026");
  });

  it.each([
    ["2026-10-25T00:30:00Z", "Non/Esiste"],
    ["non una data", "Europe/Rome"],
    ["2026-10-25", "Europe/Rome"], // data senza ora né fuso: non è un istante
  ])("(%j, %j) -> RangeError", (instant, zone) => {
    expect(() => formatTime(instant, zone)).toThrow(RangeError);
  });
});

describe("formatNumber (UX §5.3: «1.850 / 2.000»)", () => {
  it("raggruppa sempre le migliaia, anche con quattro cifre", () => {
    // Intl 'it-IT' da solo scrive "1850": il contatore della UX vuole "1.850".
    expect(formatNumber(1850)).toBe("1.850");
    expect(formatNumber(2000)).toBe("2.000");
    expect(formatNumber(999)).toBe("999");
    expect(formatNumber(1_234_567)).toBe("1.234.567");
  });

  it("decimali con la virgola", () => {
    expect(formatNumber(12345.5)).toBe("12.345,5");
  });

  it("il locale è un parametro, non una costante nascosta (NFR-011)", () => {
    expect(formatNumber(1850.5, "en-GB")).toBe("1,850.5");
    expect(formatRange("2026-10-19", "2026-10-25", "en-GB")).not.toBe("19 - 25 ottobre 2026");
    expect(formatDayHeading("2026-10-19", "en-GB")).toMatch(/^Monday/);
  });
});
