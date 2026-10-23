# SL-03a: security review

| Field | Value |
|---|---|
| Slice | SL-03a: Google login, sessions, CSRF, logout (mandatory review, R-09: own session and CSRF code) |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-23 |
| Diff base | `685c3a9` (nothing committed: `git diff 685c3a9` plus the untracked files from `git status`) |
| SRs in scope | SR-001, SR-004, SR-005, SR-014, SR-023, SR-033, SR-037, SR-049 |
| THRs in scope | THR-001, THR-002, THR-003, THR-005, THR-006, THR-007, THR-010, THR-015, THR-028 |
| ADRs checked | ADR-0003, ADR-0004 (rev. 2 and 3), 05-data v7 (§4.1, §6.1, §6.2) |
| Verdict | First pass: **APPROVED WITH ONE FIX-IN-SLICE** (1 MEDIUM FIX-IN-SLICE, 2 LOW BACKLOG, 6 INFO). **Re-check (fix cycle 1): APPROVED**, see §5. |

The OIDC, session and CSRF code is good. It is small, fails closed, and is backed by negative tests for every claim, flow and CSRF variant the threat model lists. I found nothing exploitable from outside. The one fix asked for in this slice is cheap only now: migration 0005 is not committed yet, so it can be edited in place without adding a new migration.

## 1. What was checked and how

**Files read in full:**
- `menu/identity/` (all 18 modules: `oidc`, `login`, `flows`, `sessions`, `tokens`, `cookies`, `guards`, `api`, `accounts`, `logout`, `services`, `models`, `schemas`, `labels`, `clientinfo`, `export`, `__init__`);
- `menu/family/{onboarding,membership}.py`, `menu/views/{session,schemas}.py`;
- the diffs of `tenancy/engine.py`, `platform/config.py`, `app/factory.py`, `audit/catalog.py`;
- `migrations/versions/0005_identity.py`;
- web: `api/client.ts` (diff), `api/session.ts`, `session/*`, `app/RequireSession.tsx`, `features/auth/LoginPage.tsx`, `routes.tsx`, `RootLayout.tsx`, `providers.tsx`;
- `.gitleaks.toml`, `ci.yml` (e2e job), `Makefile`, `.env.example`, `pyproject.toml` (diffs), `playwright.config.ts`;
- `platform/http/middleware.py` (body guard, headers, request log) and `platform/logging.py` (redaction);
- the test lists of `security/test_auth_{tokens,csrf,canaries}.py`, `integration/test_auth_{flow,sessions,accounts}.py`, `db/test_session_rls.py`, `concurrency/test_bootstrap_redemption_race.py`, `contract/test_identity_contract.py`.

**Tools run (fresh output, 2026-10-23):**

| Command | Result |
|---|---|
| `make scan-secrets` (gitleaks 8.30.1 `git` + `dir`, `--redact`) | **no leaks found** (7 commits ~2.56 MB, working tree ~6.5 MB) |
| gitleaks with no config on copies of the 2 allow-listed test files | 2 hits, both the allow-listed synthetic strings (an unsigned `alg=none` JWT `{"sub":"x"}` and a dummy token). Not secrets |
| `make scan-sast` (semgrep `--test` on custom rules, then `p/python p/owasp-top-ten p/typescript p/react .semgrep` on `backend web`) | rules tests all passed; scan **rc=0, 0 findings** |
| `bandit -r src -c pyproject.toml` | 0 issues |
| `make scan-deps` (pip-audit on the exported lock, osv-scanner on `uv.lock` + `pnpm-lock.yaml`) | **No known vulnerabilities**; only the already-accepted GHSA-vfj7-8cjw-p6xm filtered (ADR-0017) |
| `make scan-web` (pnpm audit, high) | passes (same dated exception) |
| `make scan-workflows` (zizmor 1.30.1, offline) | No findings |
| OSV API and GitHub Advisory DB for `authlib` 1.9.1, `joserfc` 1.7.5, `httpx` 0.28.1 | OSV `{}` for all three; every published GHSA for authlib (latest affects `<=1.6.11`/`=1.7.0`) and joserfc (latest affects `<=1.6.7`) is below the locked versions |
| `make test-sec` / `make test-int` / `make test-db` | **131 / 140 / 482 passed** |
| Probe on a throwaway DB (`sec_probe_sl03a` from the head template, then dropped) | see SEC-SL03a-001 |

**Dependency verification (standard §11):**
- `authlib` 1.9.1 and `joserfc` 1.7.5 are on PyPI under these exact names, BSD-3-Clause, from the same maintainer, actively released (joserfc 1.7.6/1.7.7 came out 2026-10-18/19 and are still inside the 7-day cooldown).
- Those two joserfc releases contain hardening ("validate compact size before split", "reject asymmetric public keys in oct imports"), but no advisory. Neither applies here: tokens come only from Google's token endpoint over TLS, and keys are imported as `RSAKey` with `algorithms=["RS256"]`.
- `httpx` moved from dev to runtime with the version unchanged.
- Everything is pinned in `uv.lock` with hashes.

## 2. Checks against THRs, SRs and the standard

| Item | Result |
|---|---|
| **THR-001, SR-001, SR-033: ID token validation** (`oidc.py:196-241`) | The `alg` in the header must be RS256 before key lookup, and joserfc `decode(..., algorithms=["RS256"])` checks it again. `kid` is looked up in Google's JWKS (RSA keys only). An unknown `kid` forces at most one refresh per 60 s, globally. `exp` is essential (60 s leeway) and `nbf` is checked. Exact `iss`. `aud` must contain our client ID. Multiple audiences require `azp == client_id`, and an `azp` that is present must equal it. The `nonce` is hashed and compared in constant time against the flow. `sub` is a non-empty string ≤255. `email` passes the table CHECK, and `email_verified is True` (strictly boolean). The token comes only from `fetch_token` (TLS, `follow_redirects=False`, default certificate verification), never from browser parameters (test `test_an_id_token_in_the_browser_request_is_never_trusted`). Discovery `issuer` must equal the configured issuer, and endpoint schemes must match it. Tests cover 22 manipulated-claim cases and 8 signature/alg/kid cases (`alg=none`, HS256 with the public key, RS384, wrong key with the same `kid`, payload edited after signing). **Met.** |
| **PKCE and state** (`login.py:57-71`, `flows.py`) | `code_verifier` comes from `secrets.token_urlsafe(48)` (64 chars, RFC 7636 alphabet, also a DB CHECK). The challenge is S256 via Authlib. `state`, `nonce` and the flow handle are 256-bit `secrets` values, and only their SHA-256 is stored. The verifier is the only plaintext (needed for Google), lives ≤15 min, and its classification in 05-data §9 is correct. **Met.** |
| **THR-002: single use under concurrency** | The callback claims the row with `UPDATE … WHERE handle_hash=:h AND consumed_at IS NULL AND expires_at > now RETURNING`. That is atomic in PostgreSQL: under READ COMMITTED a second updater re-evaluates the predicate after the first commits and gets 0 rows. Order: claim, then `state` compared in constant time, then provider error, then code exchange. An attacker's `code`+`state` in the victim's browser fails the state hash. Even if it did not, the attacker's code is bound to the attacker's PKCE challenge, so Google would refuse it. Tests: attacker code/state, a state from another flow with the victim's own cookie, a missing or altered state (refused before the exchange), a forged flow cookie, replay after success, expired flow. **Met.** (No test races two callbacks on the *same* handle; see INFO-5.) |
| **auth_flow outcome** | Read once with `DELETE … RETURNING`, and only by the browser that holds `__Host-auth_flow`. No outcome parameter ever appears in a URL. The callback always answers `302` to the allow-listed `return_to` or `/piano`. **Met.** |
| **THR-003: bootstrap** (`onboarding.py`) | Membership of an existing account wins, so a member never redeems another family's bootstrap. Bootstrap lookup is by `email_sha256` of the verified email (single normalization `strip().lower()`, no dot or `+` folding). The row is locked with `FOR UPDATE` and the same expiry predicate *before* the account is created, so the losing racer leaves nothing behind (SR-049). Redemption clears the hash. Tests: expired, inside 7 days, aliases and look-alikes, case, unverified email, single use across two `sub`s, race of N first logins, console-to-login end-to-end. **Met.** |
| **THR-005, SR-037: session token** | 256-bit `secrets.token_urlsafe(32)`. Only the SHA-256 is stored (`uq_session_token_hash`, CHECK 32 bytes). The token never appears in a response body, URL or log (canary test). Idle 720 h and absolute 2160 h, both checked in `session_resolve` (bounds included). Renewal at most hourly, with the cookie `Max-Age` capped by the remaining absolute lifetime. SPA: no storage use (grep of `web/src`: no `localStorage`, `sessionStorage`, `indexedDB` or `innerHTML`; the e2e asserts that the only JS-visible cookie is `__Host-csrf`). **Met.** |
| **Cookies, SR-005** (`cookies.py`) | `__Host-session` (HttpOnly, Secure, Lax, Path=/, no Domain), `__Host-auth_flow` (HttpOnly, Secure, Lax, 600 s; Lax is needed for Google's top-level redirect back), `__Host-csrf` (Secure, Strict, not HttpOnly by design, ADR-0004 r.3). Deletions repeat the same attributes. **Met.** |
| **THR-006: fixation** | Every successful callback creates a new session and deletes the session named by the browser's existing cookie in the same transaction (`drop_session_of_cookie`). An attacker cannot plant a `__Host-` cookie cross-origin. Tests: a pre-existing cookie is replaced, a relogin gets a fresh token, an attacker-chosen value is never adopted. **Met.** |
| **THR-007, SR-023: CSRF** (`guards.py`) | Every unsafe method needs `Content-Type: application/json`, globally (`BodyGuardMiddleware`, else 415), so no cross-site form posts. `Sec-Fetch-Site` other than `same-origin` → 403. `Origin` must equal `APP_BASE_URL`'s origin exactly, and a missing `Origin` is accepted only with `Sec-Fetch-Site: same-origin`, so `Origin: null` and old browsers fail closed. Anonymous `POST`: double submit of `__Host-csrf` (well-formed, `compare_digest`). Session `POST`: `sha256(header)` compared in constant time with `session.csrf_token_hash`. The CSRF token is `HMAC-SHA256(key=session token, "menu-design/csrf/v1")`: per session, unforgeable without the HttpOnly session token, and it does not reveal the session token (INFO-3 on the ADR wording). No CORS. Logout is `POST` only. Tests: missing or foreign token, another session's token (same and other account), the anonymous value on logout, foreign `Origin`, `same-site`/`cross-site` fetch metadata, non-JSON types, GET/HEAD on logout. **Met** for the two routes of the slice (structural guarantee for future routes: SEC-SL03a-003). |
| **THR-010: return path** | Server-side allow-list `/(piano\|piatti\|altro)(/[A-Za-z0-9_.-]+)*/?(\?[A-Za-z0-9_.=&-]*)?` with `fullmatch`, ≤200 chars, no `..`. It is applied at start and again at the callback, and the DB CHECK refuses `//`. So no absolute URL, `//host`, `\`, scheme or newline can reach `Location`. The client sends a path only from in-memory router state. **Met.** |
| **THR-015: client secret** | `SecretStr`, sent only with `client_secret_post` to the token endpoint, never to the browser (test). Mandatory in staging/production. Production storage in Secret Manager is SL-10b. **Met for this slice.** |
| **THR-028, SR-014: account data** | `account` has no RLS (accepted). It is touched only in `identity` via `system_tx` (architecture test). `SessionView` carries only account ID and display name, never email or `sub` (contract test plus a cross-family test). Stored: `sub`, email, its hash, verification time, display name (proposed by Google once and never overwritten). **Met.** |
| **SR-049** | `not_member` creates no account, person or session (the `ensure_account` callback is called only after admission). It leaves only an anonymous `auth.login denied` event and the flow row (≤15 min). **Met.** |
| **SR-004: enumeration and timing** | Google-only: the callback is a uniform `302`, and the outcome can be read only by the browser that holds the flow cookie. The only party who learns "no family" is the owner of that verified Google account. Nothing to enumerate for a third party. No citing test yet (known), see INFO-2. **Not violated.** |
| **RLS on `session`, SECURITY DEFINER** | ENABLE + FORCE. `p_session_self` (ALL, USING = WITH CHECK). `session_resolve` / `bootstrap_resolve`: plpgsql, `search_path = app, pg_temp`, EXECUTE only to `menu_app`, return only IDs, instants and the CSRF hash, only for valid secrets. **Met**, except the expired-row policies: SEC-SL03a-001. |
| **Logs and events, standard §9** | The structured logger keeps only allow-listed keys. Errors are logged by exception type name only. The request log has the path without the query string, and uvicorn's access log is off, so `code` and `state` never reach app logs. `auth.login`/`auth.logout` events carry only `reason`, actor IDs and the IP (as SL-02's security log). No email, `sub` or token in any event (canary test). **Met.** |
| **Config guards** | Staging/production: issuer forced to `https://accounts.google.com`, client ID and secret mandatory, `APP_BASE_URL` https and a pure origin. Only `dev`/`test` accept another issuer (the fake provider). No network call at startup. **Met.** |
| **`.gitleaks.toml`** | The new `[[allowlists]]` uses `condition = "AND"`: only those two exact strings, only in those two files. The old global path allow-list is unchanged. CI pins gitleaks 8.30.1 (supports the new syntax). **Fine.** |
| **`ci.yml` e2e job** | Postgres service pinned by digest, bound to `127.0.0.1`, a throwaway password identical to the existing `backend` job. Workflow permissions `contents: read`, checkout `persist-credentials: false`, actions pinned to SHAs, no secrets. zizmor clean. **Fine.** |

**Done well:** the flow is claimed *before* the code exchange, so a double click cannot exchange the same code twice. `_identity_from_claims` evaluates every check as a tuple and refuses if any one fails, with no early-return paths that could be skipped. The forced JWKS refresh is rate-limited, so random `kid`s cannot turn the app into a request generator against Google. The callback catches every exception and still answers a clean `302`, recording the failure server-side.

## 3. Findings

### SEC-SL03a-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/migrations/versions/0005_identity.py:171-174` (`p_session_expired_select`, `p_session_expired_delete`). The claim in `docs/05-data.md:985` that expired rows "contengono solo hash e istanti" is inaccurate.
- **Category:** security (CWE-863 incorrect authorization; CWE-359 exposure of personal information)
- **Problem:** the two cleanup policies are permissive and have no context condition. PostgreSQL ORs them with `p_session_self`, so **any** `menu_app` transaction, including one bound to account A, sees and can delete the expired sessions of every other account in every family. Those rows hold `account_id`, `device_label`, the truncated `ip_prefix`, `created_at` and `last_used_at`: personal data of other families.
- **Scenario (verified on a throwaway DB):** account B has a session idle for 31 days with `device_label = 'Chrome · Android'` and `ip_prefix = 203.0.113.0/24`. In a transaction with `app.account_id = A`, `SELECT … FROM app.session WHERE account_id = B` returns 1 row with that device and prefix, and `DELETE` for B succeeds. No route exposes it today: every current query filters by `account_id` or by ID. But SL-25 "My sessions" will list sessions under account RLS, and one missing `WHERE account_id = …` would show other families' devices and network prefixes. RLS exists in this design precisely so that such a slip cannot leak (ADR-0003, SR-042).
- **Suggested fix:** the worker purges with no context, so restrict both policies to that case. Edit 0005 in place (it is not committed yet):
  ```sql
  create policy p_session_expired_select on app.session for select to menu_app
    using ((last_used_at < app.now_utc() - interval '720 hours'
            or created_at < app.now_utc() - interval '2160 hours')
           and app.current_account_id() is null);
  -- same predicate for p_session_expired_delete
  ```
  Verified on the probe DB: with this predicate, A's context sees 0 rows, and a no-context `DELETE … WHERE last_used_at < now - 720 h` still purges. Fix the sentence in 05-data §6.1 (data-architect).
- **Verification:** add to `tests/db/test_session_rls.py` "with account A's context, B's expired sessions are invisible and not deletable". Keep `test_expired_sessions_are_visible_and_deletable_for_cleanup_without_context` green. Re-run the ladder and base↔head tests.
- **Status:** RESOLVED (fix cycle 1, §5)

### SEC-SL03a-002 · LOW · BACKLOG
- **Location:** `web/src/api/session.ts:65-77` (`safeRedirectUrl`)
- **Category:** security (CWE-601, defense in depth)
- **Problem:** the production bundle accepts **any** `https:` URL, plus `http:` on loopback hosts, as the target of `window.location.assign`. The only source is the same-origin JSON of `POST /auth/google/start`, so exploiting it requires control of that response (server compromise, or injection into a same-origin response). That makes it not exploitable today. The loopback `http:` branch alone is harmless: it can only send the user to their own machine.
- **Scenario:** a future bug that reflects user input into `redirectUrl` would turn the login button into an open redirect to any https site. The client check would not stop it.
- **Suggested fix (simple):** for `https:` accept only `url.hostname === "accounts.google.com"`, and keep the loopback `http:` branch so the e2e stack still works with the production bundle. No build-time flag needed.
- **Verification:** unit test: `https://evil.example/...` → `undefined`; `https://accounts.google.com/o/oauth2/v2/auth?...` → accepted; `http://127.0.0.1:8001/...` → accepted.
- **Status:** RESOLVED (fixed in fix cycle 1 although BACKLOG, §5)

### SEC-SL03a-003 · LOW · BACKLOG (before SL-04, the first family-scoped write)
- **Location:** `backend/src/menu/platform/routing.py` (`validate_authz`), `backend/src/menu/identity/guards.py`
- **Category:** security (CWE-352 prevention; standard §5 "deny by default", §10 CSRF [MUST])
- **Problem:** `x-authz.scope` is declarative only. CSRF and session checks run only because each route remembers to add `Depends(anonymous_guard)` or `Depends(session_guard)`. Both current routes do. Nothing fails if a future `POST` with `scope: family` forgets it.
- **Scenario:** in SL-04 a developer adds `POST /dishes` with `scope: family` and its own session lookup, but without `session_guard`. The route is then open to cross-site requests from same-site subdomains, or wherever `Content-Type` gets relaxed. That would be a [MUST] violation discovered only in review.
- **Suggested fix:** either `AuthzRoute` injects the guard from the scope for unsafe methods (`anonymous` → `anonymous_guard`, `account`/`family` → `session_guard`, `signup` → its guard), or an architecture test walks `app.routes` and asserts the guard is in each unsafe route's dependant tree for its scope. The test is the simpler option.
- **Verification:** the architecture test fails on a deliberately unguarded test route.
- **Status:** OPEN

### INFO notes (no action required unless stated)
- **INFO-1 (SL-03b, SL-10a):** no rate limit on `POST /auth/google/start` yet, and the hourly `auth_flow` purge does not exist yet. A script, which can forge `Origin` and fetch `__Host-csrf` via `GET /session`, can insert flow rows without bound. That is planned: AC-001.9 and the 30/IP/15 min limit in SL-03b, and the purge in SL-10a (05-data §3.4). Both must exist before the M0 release (SL-10b). SL-03b should cover the callback too, and close SEC-SL00a-005 (`TRUSTED_PROXY_HOPS`) as scheduled.
- **INFO-2 (SR-004):** for the backlog test, assert that member, `not_member` and invalid-token callbacks produce the same status, the same `Location` and the same set of `Set-Cookie` names.
- **INFO-3 (ADR-0004 wording):** ADR-0004 says "token casuale per sessione, salvato come hash". The code derives it as `HMAC-SHA256(session token, label)` so that `GET /session` can return it again without storing it. It is security-equivalent: per session, unforgeable, and the session token cannot be recovered from it. The architect should record the variant in ADR-0004.
- **INFO-4 (callback nuisance):** because the flow is claimed before `state` is compared, a cross-site top-level navigation to the callback (the Lax flow cookie is sent) with a bogus `state` consumes a victim's in-progress login. The victim sees "accesso non riuscito" and retries. There is no account impact; accepted as is. Similarly, a cross-site navigation to `GET /session` can consume a pending outcome message.
- **INFO-5 (test gap):** there is no test that races two callbacks on the *same* flow handle. Correctness rests on PostgreSQL row-locking semantics, and Google's single-use codes protect independently. Optional `tests/concurrency` case.
- **INFO-6 (maintenance):** Authlib 1.9.1 emits `AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2` (seen in the test runs). The integration ADR-0004 names will go away in a future Authlib major. Plan a check at the next Authlib upgrade (ADR-0004 "Quando rivedere"). Google also documents `iss = "accounts.google.com"` (without scheme) as valid. The strict https-only match is the safer choice, and a mismatch would show up as a visible login failure, not a bypass.

## 4. Threat model status (06-threat-model)
- THR-001, 002, 003, 005, 006, 007, 010 are verified by the tests listed in §2.
- THR-015 is met for code; the OAuth client checklist and Secret Manager come in SL-10b.
- THR-028 is met (residual accepted).
- No new THR and no new SR proposed.

## 5. Re-check, fix cycle 1 (2026-10-23)

Scope: only my findings (SEC-SL03a-001, SEC-SL03a-002), plus a regression check of the fix-cycle changes that touch security. Same diff base `685c3a9` (working tree plus untracked files). No application code changed by the reviewer.

**Tools run again (fresh output):**

| Command | Result |
|---|---|
| `make test-db` / `make test-sec` / `make test-int` | **484 / 133 / 145 passed** (were 482 / 131 / 140) |
| `pnpm exec vitest run tests/unit/api/safe-redirect.test.ts` | 24 passed |
| `make scan-secrets` (gitleaks `git` + `dir`, `--redact`) | no leaks found |
| `make scan-sast` (custom rules plus semgrep packs) | rc=0, 0 findings |
| `make scan-deps` / `make scan-web` | rc=0. Only the already-accepted GHSA-vfj7-8cjw-p6xm is filtered (ADR-0017, expires 2026-11-21). No new dependencies in this cycle |
| Probe on a throwaway DB `sec_probe_sl03a_r1` (cloned from the head template, then dropped) | see below |

### SEC-SL03a-001: RESOLVED
- **Change:** `0005_identity.py:174-177`. Both `p_session_expired_select` and `p_session_expired_delete` are now `USING ((<expired>) AND app.current_account_id() IS NULL)`. Migration 0005 was edited in place (still uncommitted). There is still no expired-row policy for `UPDATE`.
- **Probe (independent of the test suite):** `pg_policies` on the head template shows exactly the new predicate. Setup: account B has a session idle for 31 days, with `device_label = 'Chrome · Android'` and `ip_prefix = 203.0.113.0/24`. As `menu_app` with `app.account_id = A`:
  - `SELECT … WHERE account_id = B` returns **0** rows, and an unfiltered `SELECT` returns 0 rows;
  - `DELETE … WHERE account_id = B` affects **0** rows, and `UPDATE` affects 0 rows.

  As `menu_app` with no context, the row is visible and the worker's purge predicate deletes it (rowcount 1, 0 rows left).

  An empty `app.account_id` (`''`) counts as no context, because `current_account_id()` uses `nullif(..., '')`. That is consistent with how `system_tx` runs and is not a bypass: an empty value is not an account identity.
- **Tests:** the new `tests/db/test_session_rls.py::test_with_account_context_other_accounts_expired_sessions_are_invisible_and_undeletable` is parametrized for idle 31 days and absolute 91 days. It also checks that A still sees its own expired session (via `p_session_self`), and that the no-context purge then removes both. `test_expired_sessions_are_visible_and_deletable_for_cleanup_without_context` and `test_expired_sessions_cannot_be_updated_without_context` stay green. The ladder and base↔head tests are green within `make test-db`.
- **Docs:** 05-data §6.1 (line 985) now states the full predicate. It explains why `IS NULL` is needed (permissive policies are ORed) and lists the personal data those rows hold. The sentence "contengono solo hash e istanti" has been removed. The changelog line at the top of 05-data and the RLS test list (line 1036) are aligned.

### SEC-SL03a-002: RESOLVED
- **Change:** `web/src/api/session.ts` `safeRedirectUrl` now behaves as follows:
  - it rejects any URL that has a username or password;
  - it accepts `https:` only when `hostname === "accounts.google.com"`;
  - it accepts `http:` only on the exact loopback hosts `127.0.0.1`, `localhost`, `[::1]`;
  - everything else returns `undefined`, and a URL that cannot be parsed falls into the `catch`.

  The only call site is `LoginPage.tsx:36-38`, which assigns the location only if the result is defined.
- **Check:** the comparison uses the WHATWG `URL` parser, the same one `location.assign` uses, so the host that is checked is the host the browser navigates to. Backslashes, tabs, newlines and percent-encoding are normalized the same way. An exact hostname match also rejects a trailing dot. The new `web/tests/unit/api/safe-redirect.test.ts` covers:
  - look-alike and suffix hosts;
  - `@` userinfo tricks in both directions;
  - `http://accounts.google.com`, and `https` on loopback;
  - `javascript:`, protocol-relative and relative URLs, and non-strings.

  It has 24 cases, all passing.

### Regression check of the fix-cycle changes
- **`session_guard` sets the session cookie (CR-SL03a-002):**
  - **Attributes:** `set_session_cookie` is the single helper, with `HttpOnly; Secure; SameSite=Lax; Path=/`, no `Domain`, and the value is the existing token. This is renewal, not rotation: no new token, so no fixation surface.
  - **Max-Age:** `min(IDLE_SECONDS = 30 days, remaining absolute lifetime)`, with a floor of 1 second. The remaining lifetime comes from SQL `RETURNING (created_at + 2160 h) - now()`, so the cookie can never outlive the server's 90-day absolute limit. The effective cap is 30 days, which is stricter than 90. The tests assert both the 30-day value and the "≤ 1 day left" cap at day 89, on `GET /session` and on a guarded `POST`.
  - **Ordering:** renewal happens after `require_same_origin`, so a cross-site request cannot extend a session. A same-origin request with a bad CSRF token can bump `last_used_at` (at most hourly) and then gets a 403. The renewed `Set-Cookie` is then lost, because the error response is a new object. That is harmless: the cookie can only lag the server window, never exceed it.
  - **Logout:** `logout` returns the same `Response` object that `session_guard` wrote to. If the session was renewed in that request, the response carries `Set-Cookie: __Host-session=<token>; Max-Age=…` followed by the deletion with the same attributes. Browsers apply `Set-Cookie` headers in order, so the deletion wins. `test_logout_ends_up_with_the_session_cookie_deleted_even_if_it_was_renewed` covers this. Even if a client kept the cookie, the server row is already deleted (`end_session`), so the token no longer resolves. No issue.
- **`prompt=select_account`** (`oidc.py:175`): a static parameter added through Authlib's `create_authorization_url`, so it is URL-encoded. No user input reaches it, and it does not affect `state`, `nonce` or PKCE. The integration test asserts it. No issue.
- **`tests/security/test_auth_enumeration.py` (SR-004, closes INFO-2 and INFO-5):**
  - It compares status, `Location`, body, headers apart from `Set-Cookie` values, the session cookie, and the outcome read back across eight refusal cases: unknown `sub`, expired or redeemed bootstrap, alias email, an account with no family, and three forged or unverified-email variants.
  - It also checks that no email, `sub`, family name or bootstrap ID leaks.
  - Forged tokens get one outcome that does not depend on whether an invitation exists. That outcome is readable only by the browser that holds the flow cookie, so SR-004 still holds.
  - The second test races two callbacks on the same flow handle and asserts one session and a single `/token` exchange. This closes INFO-5.
  - The file is test-only, with no production surface.
- **`tests/support/fake_oidc_server.py`:**
  - test-only, never imported by `src` (grep);
  - binds to `127.0.0.1` only;
  - the `stub_identity` cookie and `POST /__seed` exist only in the e2e stack (`APP_ENV=test`, app on `127.0.0.1`);
  - a seed error is reported by exception type name only.

  Production stays protected by the configuration guard, which forces the Google issuer in staging and production. No issue.
- **ADR-0004 rev. 5 (CSRF as HMAC of the session token, closes INFO-3):** the text matches `tokens.csrf_token_for`. It uses HMAC-SHA256 with the 256-bit session token as the key and a fixed context label, and stores only `SHA-256(csrf)`. Verification is constant-time against the stored hash. The ADR states the correct security argument and the real constraint: the CSRF token cannot rotate without rotating the session, and SL-25 must not assume otherwise. Not reversible, per session, unforgeable without the HttpOnly cookie. No issue.

### Final verdict of the re-check
**APPROVED.** SEC-SL03a-001 and SEC-SL03a-002 are RESOLVED. No regressions and no new findings. SEC-SL03a-003 (structural guard check before SL-04) stays **OPEN · BACKLOG**. INFO-1 (rate limit and `auth_flow` purge in SL-03b/SL-10a) and INFO-6 (Authlib httpx deprecation) stay as they were. INFO-2, INFO-3 and INFO-5 are closed by this cycle.
