// Date di calendario del piano (SL-06a): lunedì-domenica, intervalli (SR-060: al massimo 62 giorni).
import { describe, expect, it } from "vitest";
import {
  addDays,
  checkRange,
  dayCount,
  isIsoDate,
  rangeFromSearch,
  shifted,
  toUtc,
  weekOf,
} from "../../../src/lib/dates";

describe("date di calendario", () => {
  it("riconosce solo date esistenti", () => {
    expect(isIsoDate("2026-10-23")).toBe(true);
    expect(isIsoDate("2024-02-29")).toBe(true);
    for (const bad of ["2026-02-29", "2026-13-01", "2026-10-32", "boh", "", "2026-1-1", 5, null]) {
      expect(isIsoDate(bad), String(bad)).toBe(false);
    }
    expect(toUtc("0000-01-01")).toBeNull();
  });

  it("addDays attraversa mesi e anni", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-01-01", -1)).toBe("2025-12-31");
    expect(() => addDays("boh", 1)).toThrow(RangeError);
    expect(() => dayCount({ from: "boh", to: "2026-10-01" })).toThrow(RangeError);
    expect(() => weekOf("boh")).toThrow(RangeError);
  });

  it("weekOf dà lunedì-domenica", () => {
    expect(weekOf("2026-10-23")).toEqual({ from: "2026-10-19", to: "2026-10-25" });
    expect(weekOf("2026-10-19")).toEqual({ from: "2026-10-19", to: "2026-10-25" });
    expect(weekOf("2026-10-25")).toEqual({ from: "2026-10-19", to: "2026-10-25" });
  });
});

describe("intervalli", () => {
  it("conta i giorni con gli estremi", () => {
    expect(dayCount({ from: "2026-10-19", to: "2026-10-25" })).toBe(7);
    expect(dayCount({ from: "2026-10-19", to: "2026-10-19" })).toBe(1);
  });

  it("checkRange: date, ordine e 62 giorni", () => {
    expect(checkRange("2026-10-01", "2026-12-01")).toBeNull(); // 62 giorni
    expect(checkRange("2026-10-01", "2026-12-02")).toBe("size"); // 63
    expect(checkRange("2026-10-10", "2026-10-09")).toBe("order");
    expect(checkRange("", "2026-10-09")).toBe("date");
    expect(checkRange("2026-10-01", "2026-02-30")).toBe("date");
  });

  it("rangeFromSearch accetta solo un intervallo completo e valido", () => {
    const q = (s: string): URLSearchParams => new URLSearchParams(s);
    expect(rangeFromSearch(q("da=2026-11-01&a=2026-11-10"))).toEqual({
      from: "2026-11-01",
      to: "2026-11-10",
    });
    expect(rangeFromSearch(q("da=2026-11-01"))).toBeNull();
    expect(rangeFromSearch(q("a=2026-11-01"))).toBeNull();
    expect(rangeFromSearch(q("da=boh&a=2026-13-45"))).toBeNull();
    expect(rangeFromSearch(q("da=2026-11-10&a=2026-11-01"))).toBeNull();
    expect(rangeFromSearch(q("da=2026-01-01&a=2026-12-31"))).toBeNull();
  });

  it("shifted sposta della lunghezza dell'intervallo", () => {
    const week = { from: "2026-10-19", to: "2026-10-25" };
    expect(shifted(week, 1)).toEqual({ from: "2026-10-26", to: "2026-11-01" });
    expect(shifted(week, -1)).toEqual({ from: "2026-10-12", to: "2026-10-18" });
    expect(shifted({ from: "2026-11-01", to: "2026-11-10" }, 1)).toEqual({
      from: "2026-11-11",
      to: "2026-11-20",
    });
  });
});
