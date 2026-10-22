// Mappa ErrorCode -> chiavi di catalogo (ADR-0010, piano §5.2, UX «Mappa dei codici d'errore»).
// Regola di copertura: ogni valore di ErrorCode e ValidationCode di openapi.json ha una chiave
// nel catalogo `it`; un codice sconosciuto produce `error.generic`; `title` e `detail` del
// server non arrivano mai all'utente (SR-021).
//
// Contratto assunto per web/src/api/errors.ts:
//   ERROR_KEYS:      Record<ErrorCode, string>        (una chiave per ogni codice del server)
//   VALIDATION_KEYS: Record<ValidationCode, string>   (`validation.<codice>`)
//   QUOTA_KEYS:      Record<string, string>           (per `quota_exceeded`, params.quota)
//   resolveProblem(input: unknown): { id: string; values: Record<string, string | number> }
//   resolveFieldErrors(input: unknown): Array<{ field: string; id: string; values: ... }>
import fs from "node:fs";
import { describe, expect, it } from "vitest";
import {
  ERROR_KEYS,
  QUOTA_KEYS,
  VALIDATION_KEYS,
  resolveFieldErrors,
  resolveProblem,
} from "../../../src/api/errors";
import { CATALOG_IT, OPENAPI } from "../../support/repo";
import { catalogMap } from "../../support/po";
import { uxMessages } from "../../support/ux-catalog";

const spec = JSON.parse(fs.readFileSync(OPENAPI, "utf8")) as {
  components: { schemas: { ErrorCode: { enum: string[] }; ValidationCode: { enum: string[] } } };
};
const ERROR_CODES = spec.components.schemas.ErrorCode.enum;
const VALIDATION_CODES = spec.components.schemas.ValidationCode.enum;
const catalog = (): Map<string, string> => catalogMap(fs.readFileSync(CATALOG_IT, "utf8"));

// Chiavi attese per codice (docs/03-ux.md, mappa dei codici). Più valori = alternative ammesse
// dove la UX ha due chiavi con lo stesso testo.
const EXPECTED: Record<string, string[]> = {
  not_found: ["error.notFound"],
  forbidden: ["error.forbidden"],
  unauthenticated: ["error.sessionExpired"],
  reauth_required: ["error.reauth"],
  reauth_wrong_account: ["error.reauth_wrong_account"],
  csrf_failed: ["error.generic"],
  precondition_required: ["error.generic"],
  payload_too_large: ["error.generic"],
  unsupported_media_type: ["error.generic"],
  internal: ["error.generic"],
  rate_limited: ["error.rateLimited"],
  family_pending_deletion: ["error.familyPendingDeletion"],
  invite_invalid: ["accept.invalid", "error.inviteInvalid"],
  code_invalid: ["code.invalid"],
  already_in_family: ["accept.alreadyInFamily"],
  last_admin: ["people.lastAdmin.blocked"],
  dish_already_planned: ["dish.deleteBlocked"],
  dish_not_planned: ["error.dish_not_planned"],
  course_in_use: ["error.course_in_use"],
  range_too_large: ["error.range_too_large"],
  course_not_allowed: ["picker.courseChoice"],
  person_before_join: ["presence.beforeJoin"],
  conflict: ["conflict.title.generic"],
  validation: ["validation.invalid_value"],
  quota_exceeded: ["validation.limit_reached"],
};
const PREFIXED: Record<string, string> = {
  age_declaration_blocked: "accept.under14.",
};

describe("copertura: ogni codice del server ha una chiave nel catalogo it", () => {
  it("ERROR_KEYS ha esattamente i codici di ErrorCode (né più né meno)", () => {
    expect(Object.keys(ERROR_KEYS).sort()).toEqual([...ERROR_CODES].sort());
  });

  it.each(ERROR_CODES)("%s -> una chiave esistente nel catalogo", (code) => {
    const key = (ERROR_KEYS as Record<string, string>)[code];
    expect(key, `nessuna chiave per ${code}`).toBeTypeOf("string");
    expect(catalog().has(key as string), `${code} -> ${key} manca nel catalogo it`).toBe(true);
    if (code in EXPECTED) expect(EXPECTED[code]).toContain(key);
    else expect(key).toMatch(new RegExp(`^${(PREFIXED[code] ?? "").replace(".", "\\.")}`));
  });

  it("VALIDATION_KEYS ha esattamente i codici di ValidationCode, come validation.<codice>", () => {
    expect(Object.keys(VALIDATION_KEYS).sort()).toEqual([...VALIDATION_CODES].sort());
    for (const code of VALIDATION_CODES) {
      const key = (VALIDATION_KEYS as Record<string, string>)[code];
      expect(key).toBe(`validation.${code}`);
      expect(catalog().has(key as string), key).toBe(true);
    }
  });

  it("QUOTA_KEYS copre le sette quote di ADR-0010 con le chiavi della UX", () => {
    expect(QUOTA_KEYS).toEqual({
      other_meals_per_day: "error.quota_exceeded.other_meals_per_day",
      pending_invites: "invite.limit",
      daily_invites: "invite.limit",
      dishes: "validation.limit_reached",
      people: "validation.limit_reached",
      courses: "validation.limit_reached",
      tags: "validation.limit_reached",
    });
    for (const key of Object.values(QUOTA_KEYS)) expect(catalog().has(key), key).toBe(true);
  });

  it("ogni chiave del catalogo raggiungibile dalla mappa ha il testo della UX", () => {
    const messages = catalog();
    const reachable = new Set([
      ...Object.values(ERROR_KEYS),
      ...Object.values(VALIDATION_KEYS),
      ...Object.values(QUOTA_KEYS),
    ]);
    const ux = uxMessages();
    for (const key of reachable) {
      const texts = ux.filter((m) => m.key === key).map((m) => m.text);
      expect(texts.length, `${key} non è nella UX §7.3`).toBeGreaterThan(0);
      expect(texts, key).toContain(messages.get(key));
    }
  });
});

describe("resolveProblem: parametri e comportamento", () => {
  it("rate_limited: retryAfterSeconds diventa il parametro seconds", () => {
    expect(resolveProblem({ code: "rate_limited", params: { retryAfterSeconds: 7 } })).toEqual({
      id: "error.rateLimited",
      values: { seconds: 7 },
    });
  });

  it.each([
    [
      "family_pending_deletion",
      { deletionDate: "2026-11-02" },
      "error.familyPendingDeletion",
      { date: "2026-11-02" },
    ],
    [
      "reauth_wrong_account",
      { expectedEmailMasked: "m***@gmail.com" },
      "error.reauth_wrong_account",
      { expectedEmailMasked: "m***@gmail.com" },
    ],
    ["course_in_use", { usageCount: 3 }, "error.course_in_use", { usageCount: 3 }],
    ["range_too_large", { maxDays: 62 }, "error.range_too_large", { maxDays: 62 }],
    [
      "person_before_join",
      { joinedOn: "2026-10-01" },
      "presence.beforeJoin",
      { joinedOn: "2026-10-01" },
    ],
  ])("%s passa i parametri del server al messaggio", (code, params, id, values) => {
    expect(resolveProblem({ code, params })).toEqual({ id, values });
  });

  it("quota_exceeded sceglie la chiave dalla quota e rinomina limit", () => {
    expect(
      resolveProblem({
        code: "quota_exceeded",
        params: { quota: "other_meals_per_day", limit: 5 },
      }),
    ).toEqual({
      id: "error.quota_exceeded.other_meals_per_day",
      values: { limit: 5 },
    });
    expect(
      resolveProblem({ code: "quota_exceeded", params: { quota: "pending_invites", limit: 20 } }),
    ).toEqual({
      id: "invite.limit",
      values: { max: 20 },
    });
    expect(
      resolveProblem({ code: "quota_exceeded", params: { quota: "dishes", limit: 500 } }),
    ).toEqual({
      id: "validation.limit_reached",
      values: { max: 500 },
    });
  });

  it("un codice sconosciuto o una quota sconosciuta danno error.generic", () => {
    expect(resolveProblem({ code: "qualcosa_di_nuovo" }).id).toBe("error.generic");
    expect(
      resolveProblem({ code: "quota_exceeded", params: { quota: "nuova", limit: 1 } }).id,
    ).toBe("error.generic");
  });

  it("401 -> error.sessionExpired, errore di rete del client -> error.network", () => {
    expect(resolveProblem({ code: "unauthenticated" }).id).toBe("error.sessionExpired");
    expect(resolveProblem({ code: "network_error" }).id).toBe("error.network");
  });

  it('parametro obbligatorio mancante o non numerico: error.generic, mai "NaN" o "undefined"', () => {
    for (const params of [
      undefined,
      {},
      { retryAfterSeconds: "abc" },
      { retryAfterSeconds: -3 },
      { retryAfterSeconds: Number.NaN },
      { retryAfterSeconds: null },
    ]) {
      expect(resolveProblem({ code: "rate_limited", params }).id, JSON.stringify(params)).toBe(
        "error.generic",
      );
    }
  });

  it("title e detail del server non compaiono mai nel risultato (SR-021)", () => {
    const result = resolveProblem({
      code: "internal",
      title: "Internal Server Error SECRET-TITLE",
      detail: "psycopg.errors: SECRET-DETAIL",
      params: { leak: "SECRET-PARAM" },
    });
    expect(JSON.stringify(result)).not.toMatch(/SECRET/);
  });

  it.each([
    null,
    undefined,
    "not_found",
    404,
    [],
    {},
    { code: 404 },
    { code: null },
    { code: "__proto__" },
    { code: "constructor" },
    { code: "toString" },
    { code: "hasOwnProperty" },
    { code: "valueOf" },
  ])("input non valido %j -> error.generic (nessuna ricerca nel prototipo)", (input) => {
    expect(resolveProblem(input)).toEqual({ id: "error.generic", values: {} });
  });
});

describe("resolveFieldErrors: errori per campo di un 422", () => {
  it("traduce errors[] in chiavi validation.* con i parametri", () => {
    const out = resolveFieldErrors({
      code: "validation",
      errors: [
        { field: "name", code: "string_too_long", params: { max: 120 } },
        { field: "sources[2].url", code: "url_invalid" },
        { field: "If-Match", code: "invalid_value" },
      ],
    });
    expect(out).toEqual([
      { field: "name", id: "validation.string_too_long", values: { max: 120 } },
      { field: "sources[2].url", id: "validation.url_invalid", values: {} },
      { field: "If-Match", id: "validation.invalid_value", values: {} },
    ]);
  });

  it("un codice di validazione sconosciuto diventa validation.invalid_value", () => {
    expect(
      resolveFieldErrors({ code: "validation", errors: [{ field: "x", code: "nuovo" }] }),
    ).toEqual([{ field: "x", id: "validation.invalid_value", values: {} }]);
  });

  it("campo non stringa o mancante: campo vuoto (avviso in cima al modulo)", () => {
    const out = resolveFieldErrors({
      code: "validation",
      errors: [{ code: "required" }, { field: 7, code: "required" }],
    });
    expect(out.map((e) => e.field)).toEqual(["", ""]);
  });

  it.each([
    null,
    undefined,
    "x",
    {},
    { code: "not_found" },
    { code: "validation" },
    { code: "validation", errors: "no" },
  ])("input %j senza errors[] validi -> elenco vuoto", (input) => {
    expect(resolveFieldErrors(input)).toEqual([]);
  });
});
