// Mappa unica ErrorCode -> chiave di catalogo (ADR-0010, docs/03-ux.md «Mappa dei codici
// d'errore»). Del server si usano solo `code` e i `params` previsti: `title` e `detail` non
// arrivano mai all'utente (SR-021).
import type { components } from "./schema.gen";

export type ErrorCode = components["schemas"]["ErrorCode"];
export type ValidationCode = components["schemas"]["ValidationCode"];
export type MessageValues = Record<string, string | number>;
export interface ResolvedMessage {
  id: string;
  values: MessageValues;
}

export const ERROR_KEYS: Record<ErrorCode, string> = {
  validation: "validation.invalid_value",
  not_found: "error.notFound",
  forbidden: "error.forbidden",
  unauthenticated: "error.sessionExpired",
  reauth_required: "error.reauth",
  reauth_wrong_account: "error.reauth_wrong_account",
  csrf_failed: "error.generic",
  conflict: "conflict.title.generic",
  precondition_required: "error.generic",
  rate_limited: "error.rateLimited",
  payload_too_large: "error.generic",
  family_pending_deletion: "error.familyPendingDeletion",
  invite_invalid: "accept.invalid",
  code_invalid: "code.invalid",
  age_declaration_blocked: "accept.under14.body",
  already_in_family: "accept.alreadyInFamily",
  last_admin: "people.lastAdmin.blocked",
  dish_already_planned: "dish.deleteBlocked",
  dish_not_planned: "error.dish_not_planned",
  course_in_use: "error.course_in_use",
  quota_exceeded: "validation.limit_reached",
  range_too_large: "error.range_too_large",
  course_not_allowed: "picker.courseChoice",
  person_before_join: "presence.beforeJoin",
  unsupported_media_type: "error.generic",
  internal: "error.generic",
};

export const VALIDATION_KEYS: Record<ValidationCode, string> = {
  required: "validation.required",
  string_too_long: "validation.string_too_long",
  limit_reached: "validation.limit_reached",
  url_invalid: "validation.url_invalid",
  course_required: "validation.course_required",
  guests_range: "validation.guests_range",
  priority_range: "validation.priority_range",
  date_invalid: "validation.date_invalid",
  range_order: "validation.range_order",
  duplicate_course: "validation.duplicate_course",
  invalid_value: "validation.invalid_value",
  unknown_field: "validation.unknown_field",
  dish_archived: "validation.dish_archived",
};

/** Chiave per `quota_exceeded`, scelta da `params.quota`. */
export const QUOTA_KEYS: Record<string, string> = {
  other_meals_per_day: "error.quota_exceeded.other_meals_per_day",
  pending_invites: "invite.limit",
  daily_invites: "invite.limit",
  dishes: "validation.limit_reached",
  people: "validation.limit_reached",
  courses: "validation.limit_reached",
  tags: "validation.limit_reached",
};

/** Codici generati dal client, non dal server. */
const CLIENT_KEYS: Record<string, string> = { network_error: "error.network" };

const GENERIC: ResolvedMessage = { id: "error.generic", values: {} };
const generic = (): ResolvedMessage => ({ id: GENERIC.id, values: {} });

const has = (table: object, key: string): boolean => Object.hasOwn(table, key);
const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isCount = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v >= 0;
const isText = (v: unknown): v is string => typeof v === "string" && v !== "";

/** Parametri obbligatori per codice: (nome nel server -> nome nel messaggio, controllo). */
const PARAMS: Record<string, Array<[string, string, (v: unknown) => boolean]>> = {
  rate_limited: [["retryAfterSeconds", "seconds", isCount]],
  family_pending_deletion: [["deletionDate", "date", isText]],
  reauth_wrong_account: [["expectedEmailMasked", "expectedEmailMasked", isText]],
  course_in_use: [["usageCount", "usageCount", isCount]],
  range_too_large: [["maxDays", "maxDays", isCount]],
  person_before_join: [["joinedOn", "joinedOn", isText]],
};

export function resolveProblem(input: unknown): ResolvedMessage {
  if (!isRecord(input) || typeof input["code"] !== "string") return generic();
  const code = input["code"];
  if (has(CLIENT_KEYS, code)) return { id: CLIENT_KEYS[code] as string, values: {} };
  if (!has(ERROR_KEYS, code)) return generic();
  const params = isRecord(input["params"]) ? input["params"] : {};
  if (code === "quota_exceeded") {
    const quota = params["quota"];
    const limit = params["limit"];
    if (typeof quota !== "string" || !has(QUOTA_KEYS, quota) || !isCount(limit)) return generic();
    const name = quota === "other_meals_per_day" ? "limit" : "max";
    return { id: QUOTA_KEYS[quota] as string, values: { [name]: limit } };
  }
  const values: MessageValues = {};
  for (const [from, to, valid] of PARAMS[code] ?? []) {
    const value = params[from];
    if (!valid(value)) return generic();
    values[to] = value as string | number;
  }
  return { id: ERROR_KEYS[code as ErrorCode], values };
}

export interface FieldMessage extends ResolvedMessage {
  field: string;
}

export function resolveFieldErrors(input: unknown): FieldMessage[] {
  if (!isRecord(input) || input["code"] !== "validation" || !Array.isArray(input["errors"])) {
    return [];
  }
  const out: FieldMessage[] = [];
  for (const item of input["errors"] as unknown[]) {
    if (!isRecord(item)) continue;
    const code = item["code"];
    const known = typeof code === "string" && has(VALIDATION_KEYS, code);
    const values: MessageValues = {};
    if (isRecord(item["params"])) {
      for (const [name, value] of Object.entries(item["params"])) {
        if (typeof value === "string" || typeof value === "number") values[name] = value;
      }
    }
    out.push({
      field: typeof item["field"] === "string" ? item["field"] : "",
      id: known ? VALIDATION_KEYS[code as ValidationCode] : "validation.invalid_value",
      values,
    });
  }
  return out;
}
