// @vitest-environment happy-dom
// La CSP vieta i <style> inseriti a runtime: l'id che React Aria cerca è occupato da un <meta>.
import { describe, expect, it } from "vitest";
import { reserveAriaStyleId } from "../../../src/lib/aria-style";

describe("reserveAriaStyleId", () => {
  it("mette un <meta> con l'id e non un <style>, una volta sola", () => {
    reserveAriaStyleId(document);
    reserveAriaStyleId(document);
    const found = document.querySelectorAll("#react-aria-pressable-style");
    expect(found).toHaveLength(1);
    expect(found[0]?.tagName).toBe("META");
    expect(document.querySelectorAll("style")).toHaveLength(0);
  });
});
