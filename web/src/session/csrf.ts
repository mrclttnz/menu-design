// Token CSRF della sessione autenticata (ADR-0004): solo in memoria, mai in storage né in cookie
// scritti dalla SPA (SR-037). Senza sessione il client usa il cookie anonimo `__Host-csrf`.
import type { SessionView } from "../api/session";

let current: string | undefined;

export function rememberSession(view: SessionView | undefined): void {
  current = view?.authenticated ? view.csrfToken : undefined;
}

export const sessionCsrfToken = (): string | undefined => current;
