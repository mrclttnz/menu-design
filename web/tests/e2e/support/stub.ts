// Il provider OIDC finto degli e2e (SL-03a, 08 §4.2): lo avvia `backend/tests/support/e2e_stack.py`
// accanto all'app. Ogni test sceglie l'identità con un cookie sul proprio contesto di browser
// (così i test in parallelo non si pestano i piedi) e prepara i dati con `POST /__seed`.
// Mai su staging: lì lo stub non esiste (08 §4.1b).
import { randomInt, randomUUID } from "node:crypto";
import { expect, type APIRequestContext, type BrowserContext } from "@playwright/test";

const port = process.env["E2E_PORT"] ?? "8000";
export const STUB_URL = process.env["E2E_STUB_URL"] ?? `http://127.0.0.1:${Number(port) + 1}`;
export const STUB_AVAILABLE = !process.env["E2E_BASE_URL"] || Boolean(process.env["E2E_STUB_URL"]);
export const STUB_MISSING_REASON =
  "contro un server esterno servono E2E_STUB_URL e lo stack di backend/tests/support/e2e_stack.py";

export interface StubIdentity {
  sub: string;
  email: string;
  name?: string;
  email_verified?: boolean;
}

/** Identificatori unici per test e per progetto (mobile e desktop girano insieme). */
export function unique(label: string): { sub: string; email: string } {
  const tag = `${label}-${randomUUID().slice(0, 8)}`;
  return { sub: `sub-${tag}`, email: `${tag}@example.test` };
}

const b64url = (value: unknown): string => Buffer.from(JSON.stringify(value)).toString("base64url");

/**
 * SL-03b: gli avvii di accesso sono limitati a 30 per IP in 15 minuti e in questo stack tutti i
 * test arrivano dallo stesso indirizzo. Ogni contesto si presenta quindi con un IP proprio: l'app
 * dello stack di prova si fida di UN proxy (`TRUSTED_PROXY_HOPS=1`) e legge l'ultima voce di
 * `X-Forwarded-For`. Indirizzi del blocco 198.18.0.0/15 (RFC 2544, solo prove), mai reali.
 */
export async function isolateIp(context: BrowserContext): Promise<string> {
  const ip = `198.${18 + randomInt(2)}.${randomInt(256)}.${1 + randomInt(254)}`;
  await context.setExtraHTTPHeaders({ "x-forwarded-for": ip });
  return ip;
}

/** Da ora, nella pagina di consenso dello stub, questo contesto è l'utente indicato. */
export async function actAs(context: BrowserContext, identity: StubIdentity): Promise<void> {
  await isolateIp(context);
  await context.addCookies([
    { name: "stub_identity", value: b64url(identity), url: STUB_URL, httpOnly: false },
  ]);
}

/** Da ora lo stub nega il consenso (l'utente annulla sulla pagina di Google). */
export async function denyConsent(context: BrowserContext): Promise<void> {
  await isolateIp(context);
  await context.addCookies([
    { name: "stub_identity", value: b64url({ deny: true }), url: STUB_URL, httpOnly: false },
  ]);
}

export async function seedBootstrap(
  request: APIRequestContext,
  email: string,
  familyName = "Famiglia Alfa",
): Promise<void> {
  const response = await request.post(`${STUB_URL}/__seed`, {
    data: { kind: "bootstrap", email, familyName },
  });
  expect(response.status(), await response.text()).toBe(204);
}

/** Un piatto da preparare con `seedMember` (SL-04): portate per codice base, id facoltativo. */
export interface SeedDish {
  name: string;
  id?: string;
  status?: "to_try" | "tested";
  courses?: string[];
  notes?: string;
  prepTime?: "under_30" | "30_60" | "over_60";
  archived?: boolean;
  sources?: Array<{ kind: string; reference: string; page?: string }>;
}

export async function seedMember(
  request: APIRequestContext,
  member: {
    sub: string;
    email: string;
    role?: string;
    displayName?: string;
    familyName?: string;
    dishes?: SeedDish[];
  },
): Promise<void> {
  const response = await request.post(`${STUB_URL}/__seed`, {
    data: { kind: "member", ...member },
  });
  expect(response.status(), await response.text()).toBe(204);
}
