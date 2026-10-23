// Il provider OIDC finto degli e2e (SL-03a, 08 §4.2): lo avvia `backend/tests/support/e2e_stack.py`
// accanto all'app. Ogni test sceglie l'identità con un cookie sul proprio contesto di browser
// (così i test in parallelo non si pestano i piedi) e prepara i dati con `POST /__seed`.
// Mai su staging: lì lo stub non esiste (08 §4.1b).
import { randomUUID } from "node:crypto";
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

/** Da ora, nella pagina di consenso dello stub, questo contesto è l'utente indicato. */
export async function actAs(context: BrowserContext, identity: StubIdentity): Promise<void> {
  await context.addCookies([
    { name: "stub_identity", value: b64url(identity), url: STUB_URL, httpOnly: false },
  ]);
}

/** Da ora lo stub nega il consenso (l'utente annulla sulla pagina di Google). */
export async function denyConsent(context: BrowserContext): Promise<void> {
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

export async function seedMember(
  request: APIRequestContext,
  member: { sub: string; email: string; role?: string; displayName?: string; familyName?: string },
): Promise<void> {
  const response = await request.post(`${STUB_URL}/__seed`, {
    data: { kind: "member", ...member },
  });
  expect(response.status(), await response.text()).toBe(204);
}
