// Risposte simulate del server per i test del frontend: RFC 9457 come da openapi.json.
// 08 §16.2: i mock non devono nascondere il comportamento; un test controlla che le risposte
// simulate rispettino lo schema OpenAPI (`validateProblem`, usato da api/client.test.ts).
import fs from "node:fs";
import { OPENAPI } from "./repo";

interface Contract {
  components: {
    schemas: {
      ErrorCode: { enum: string[] };
      ValidationCode: { enum: string[] };
      ProblemDetails: { required: string[]; properties: Record<string, unknown> };
      FieldError: { required: string[] };
    };
  };
}

const contract = (): Contract => JSON.parse(fs.readFileSync(OPENAPI, "utf8")) as Contract;

export const STATUS_BY_CODE: Record<string, number> = {
  validation: 422,
  not_found: 404,
  forbidden: 403,
  unauthenticated: 401,
  reauth_required: 403,
  reauth_wrong_account: 403,
  csrf_failed: 403,
  conflict: 412,
  precondition_required: 428,
  rate_limited: 429,
  payload_too_large: 413,
  family_pending_deletion: 409,
  invite_invalid: 404,
  code_invalid: 404,
  age_declaration_blocked: 422,
  already_in_family: 409,
  last_admin: 409,
  dish_already_planned: 409,
  dish_not_planned: 409,
  course_in_use: 409,
  quota_exceeded: 409,
  range_too_large: 422,
  course_not_allowed: 422,
  person_before_join: 422,
  unsupported_media_type: 415,
  internal: 500,
};

export interface ProblemBody {
  type: string;
  title: string;
  status: number;
  code: string;
  params?: Record<string, unknown>;
  errors?: Array<{ field: string; code: string; params?: Record<string, unknown> }>;
}

export function problemBody(code: string, extra: Partial<ProblemBody> = {}): ProblemBody {
  const status = STATUS_BY_CODE[code] ?? 500;
  return { type: "about:blank", title: `HTTP ${status}`, status, code, ...extra };
}

export function problemResponse(code: string, extra: Partial<ProblemBody> = {}): Response {
  const body = problemBody(code, extra);
  return new Response(JSON.stringify(body), {
    status: body.status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

/** Elenco degli scostamenti dallo schema `ProblemDetails` (vuoto = valido). */
export function validateProblem(body: unknown): string[] {
  const { schemas } = contract().components;
  const problems: string[] = [];
  if (typeof body !== "object" || body === null) return ["non è un oggetto"];
  const record = body as Record<string, unknown>;
  for (const key of schemas.ProblemDetails.required) {
    if (!(key in record)) problems.push(`manca ${key}`);
  }
  for (const key of Object.keys(record)) {
    if (!(key in schemas.ProblemDetails.properties)) problems.push(`campo non previsto: ${key}`);
  }
  if (typeof record["status"] !== "number") problems.push("status non numerico");
  if (!schemas.ErrorCode.enum.includes(record["code"] as string))
    problems.push("code non in ErrorCode");
  const errors = record["errors"];
  if (errors !== undefined) {
    for (const [i, item] of (errors as Array<Record<string, unknown>>).entries()) {
      for (const key of schemas.FieldError.required) {
        if (!(key in item)) problems.push(`errors[${i}]: manca ${key}`);
      }
      if (!schemas.ValidationCode.enum.includes(item["code"] as string)) {
        problems.push(`errors[${i}].code non in ValidationCode`);
      }
    }
  }
  return problems;
}
