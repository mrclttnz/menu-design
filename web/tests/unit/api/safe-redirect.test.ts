// Hardening SEC-SL03a-002 / CR-SL03a-011: il redirect di login accetta solo Google (https) o,
// per lo stack di prova, http su loopback esatto.
import { describe, expect, it } from "vitest";
import { safeRedirectUrl } from "../../../src/api/session";

describe("safeRedirectUrl", () => {
  it.each([
    "https://accounts.google.com/o/oauth2/v2/auth?client_id=x&state=y",
    "https://accounts.google.com",
  ])("accetta Google https: %s", (u) => expect(safeRedirectUrl(u)).toBe(u));

  it.each([
    "http://127.0.0.1:9999/authorize?x=1",
    "http://localhost:8080/authorize",
    "http://[::1]:8080/authorize",
  ])("accetta http su loopback: %s", (u) => expect(safeRedirectUrl(u)).toBe(u));

  it.each([
    "https://accounts.google.com.evil.test/auth",
    "https://evil.test/accounts.google.com",
    "https://notaccounts.google.com/",
    "https://evil.test/",
    "https://accounts.google.com@evil.test/",
    "https://user:pw@accounts.google.com/",
    "https://accounts.google.com:pw@evil.test/",
    "http://accounts.google.com/",
    "http://localhost.evil.test/",
    "http://127.0.0.1.evil.test/",
    "http://evil.test@127.0.0.1/",
    "http://user@localhost/",
    "https://127.0.0.1/",
    "https://localhost/",
    "javascript:alert(1)",
    "//accounts.google.com/",
    "/piano",
    "",
  ])("rifiuta %s", (u) => expect(safeRedirectUrl(u)).toBeUndefined());

  it("rifiuta i valori non stringa", () => {
    for (const v of [undefined, null, 1, {}, []]) expect(safeRedirectUrl(v)).toBeUndefined();
  });
});
