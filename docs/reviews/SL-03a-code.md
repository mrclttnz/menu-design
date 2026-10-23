# Code review · SL-03a

- **Date:** 2026-10-23
- **Reviewer:** code-reviewer
- **Scope:** `git diff 685c3a9` (42 tracked files) plus the untracked files of SL-03a: `backend/migrations/versions/0005_identity.py`, `backend/src/menu/identity/*`, `backend/src/menu/family/{membership,onboarding}.py`, `backend/src/menu/views/{schemas,session}.py`, the new backend tests (architecture, concurrency, contract, db, integration, security, unit, support), `web/src/api/session.ts`, `web/src/app/RequireSession.tsx`, `web/src/session/*`, `web/src/features/plan/PlanPage.tsx`, and the new web tests. All changed files were read in full, together with their callers (`app/factory.py`, `tenancy/engine.py`, `platform/http/middleware.py`, `platform/routing.py`).
- **Verdict:** APPROVED (re-check, cycle 1: all FIX-IN-SLICE findings RESOLVED; see "Re-check (cycle 1)")
- **Cycle:** 1 (initial review: APPROVED WITH FIXES), re-check 1

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL03a-001 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/identity/oidc.py:167`, `web/src/features/auth/LoginPage.tsx:80` | "Usa un altro account Google" cannot switch accounts: the request sends no `prompt=select_account` | RESOLVED |
| CR-SL03a-002 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/identity/sessions.py:49`, `guards.py:59`, `views/session.py:54` | The sliding renewal moves `last_used_at` in every caller of `resolve_session`, but only `GET /session` refreshes the cookie's `Max-Age` | RESOLVED |
| CR-SL03a-003 | MEDIUM | FIX-IN-SLICE | `backend/tests/integration/test_auth_sessions.py:155` | No test covers the renewed `Set-Cookie` or its cap at the remaining absolute lifetime (AC-001.2) | RESOLVED |
| CR-SL03a-004 | LOW | FIX-IN-SLICE | `backend/src/menu/identity/tokens.py:40`, `sessions.py:77` | The session CSRF token is derived with HMAC from the session token. ADR-0004 specifies a random token, and the deviation is not recorded | RESOLVED |
| CR-SL03a-005 | LOW | FIX-IN-SLICE | `backend/tests/` (missing) | SR-004 is in the slice scope but no test cites it (known) | RESOLVED |
| CR-SL03a-006 | LOW | BACKLOG | `backend/src/menu/family/onboarding.py:57` | The loser of a same-`sub` first-login race gets `not_member` even though the account is now Admin | OPEN |
| CR-SL03a-007 | LOW | BACKLOG | `backend/src/menu/identity/oidc.py:226` | `iss` is checked only against `https://accounts.google.com`. Google also documents `accounts.google.com` (TO VERIFY with P-3) | OPEN |
| CR-SL03a-008 | LOW | BACKLOG | `backend/src/menu/identity/sessions.py:96`, `flows.py:105` | Dead `tx is None` branches | OPEN |
| CR-SL03a-009 | LOW | BACKLOG | `backend/tests/db/test_identity_schema.py:135` | The extra accepted exception applies to every parametrized case, which weakens the other cases | OPEN |
| CR-SL03a-010 | LOW | BACKLOG | `backend/pyproject.toml` (authlib 1.9.1) | Authlib emits `AuthlibDeprecationWarning` for its httpx integration ("use httpx2") | OPEN |
| CR-SL03a-011 | INFO | BACKLOG | `web/src/api/session.ts:65` | `safeRedirectUrl` allows `http:` on loopback hosts: acceptable, but no test covers that branch | RESOLVED |
| CR-SL03a-012 | INFO | BACKLOG | `backend/src/menu/views/schemas.py:25`, `identity/api.py:79` | Internal notes leak into OpenAPI descriptions. The "no `subject`" contract rule conflicts with the planned `Notice.subjectPersonId` | OPEN |

## Findings

### CR-SL03a-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/identity/oidc.py:167-173` (`authorization_url`), `web/src/features/auth/LoginPage.tsx:80`
- **Category:** correctness
- **Problem:** In the "Serve un invito" state (AC-001.5, UX S-01), the only command is "Usa un altro account Google". It calls the same `startLogin()`. The authorization URL carries only `state`, `nonce` and the PKCE challenge, with no `prompt=select_account`.
- **Scenario:** A user is signed in to a single Google account and has already granted consent on the first attempt. They get `not_member` and press "Usa un altro account Google". Google returns immediately with the same account, without showing the chooser. The callback produces `not_member` again, so the user is stuck in a loop and the button does not do what its label says.
- **Suggested fix:** The simplest option, with no contract change, is to always send `prompt=select_account` for `purpose=login` (pass it through `create_authorization_url(..., prompt="select_account")`). The cost is one extra click for returning users. Alternatively, add an optional `switchAccount: true` to `StartRequest`, but that changes the plan §4.3 contract, so it needs the tech-lead.
- **Verification:** Add an integration test asserting that the `redirectUrl` returned by `start` contains `prompt=select_account` (at least for the switch case), plus a manual check with real Google during the P-3 verification.
- **Status:** RESOLVED (re-check 1)

### CR-SL03a-002 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/identity/sessions.py:49-53`, `backend/src/menu/identity/guards.py:59`, `backend/src/menu/views/session.py:54-55`
- **Category:** correctness / design
- **Problem:** `resolve_session` renews `session.last_used_at` in the database whenever more than one hour has passed. The renewal returns `renewed_max_age` only to the caller that triggered it. Only `GET /session` turns that value into a `Set-Cookie`. `session_guard`, the dependency every future authenticated write (SL-04 onwards) will use, renews the database row and discards `renewed_max_age`. The cookie's 30-day window and the server's 30-day window can therefore drift apart.
- **Scenario:** An installed PWA stays open for weeks without a reload and the user works only through write endpoints guarded by `session_guard`. Each of those requests advances `last_used_at`. Any `GET /session` within the same hour then sees `renewed is None` and sends no cookie. Thirty days after the last `Set-Cookie`, the browser drops `__Host-session` while the server still considers the session valid, so the user is logged out despite daily use (AC-001.2). Today the only `session_guard` route is logout, so the defect is latent, but the guard is the contract this slice hands to SL-04.
- **Suggested fix:** Make the cookie refresh a property of session resolution rather than of one endpoint. For example, `session_guard` could also take the `Response` and call `set_session_cookie(response, token, session.renewed_max_age)` when the value is set, or a small dependency or middleware could do it for every resolved session. A simpler alternative is for `GET /session` to always re-issue the cookie with `max_age = min(IDLE, remaining absolute)`, computed from `created_at`, so its refresh no longer depends on whether it was the request that renewed the row.
- **Verification:** A test where the row is renewed by a `session_guard` request, followed by `GET /session`, asserts that the browser receives a fresh `__Host-session` with the expected `Max-Age` (see CR-SL03a-003).
- **Status:** RESOLVED (re-check 1)

### CR-SL03a-003 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/tests/integration/test_auth_sessions.py:155-186`. `backend/tests/support/browser_sim.py` does not model the passage of `Max-Age`.
- **Category:** tests
- **Problem:** The renewal tests assert only on `app.session.last_used_at`. No test asserts that `GET /session` re-sends `__Host-session` after a renewal, or that the new `Max-Age` is capped at the remaining absolute lifetime (`sessions.py:28` and `:53`). Deleting `views/session.py:54-55` breaks no test (`grep renewed_max_age backend/tests` → no hits), yet without those lines AC-001.2 fails in a real browser 30 days after login.
- **Scenario:** A regression in the cookie refresh, or in the `min(IDLE_SECONDS, remaining)` cap, passes the green suite. For the cap, a session created 89 days ago that receives a 30-day cookie is not a security issue, because the server rejects it at 90 days, but the contract is not proven either.
- **Suggested fix:** Add tests along these lines: (a) age `last_used_at` beyond one hour, call `GET /session`, and assert a `Set-Cookie: __Host-session` with the same value, `Max-Age=2592000` and the attributes of SR-005; (b) set `created_at` to 89 days ago, then assert `Max-Age ≈ 86400` (± tolerance); (c) within the hour, assert that no `Set-Cookie` for the session is sent.
- **Verification:** `make test-int` with the new tests, plus a quick mutation check (removing lines 54-55 must make the test fail).
- **Status:** RESOLVED (re-check 1)

### CR-SL03a-004 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/identity/tokens.py:40-42`, `backend/src/menu/identity/sessions.py:77`, `backend/src/menu/identity/guards.py:62-68`
- **Category:** design
- **Problem:** ADR-0004 (Decision → CSRF) says "token casuale per sessione, salvato come hash nella riga della sessione". The implementation instead derives `csrf = HMAC-SHA256(key=session_token, msg="menu-design/csrf/v1")` and stores its hash. I see no weakness in this: the key is the 256-bit secret session token, HMAC is not invertible, so a leaked CSRF token reveals nothing about the session token, and the comparison is constant-time. However, it is an undocumented deviation from an ACCEPTED ADR. The CSRF token can no longer be rotated independently of the session, and `session.csrf_token_hash` becomes redundant: the server can recompute the expected value from the cookie it already receives.
- **Scenario:** A future reader, or SL-25 (session revocation and listing), assumes per ADR-0004 that the CSRF token is independent and random, and builds on that assumption (for example "rotate CSRF without logging out").
- **Suggested fix:** This is documentation only. The architect records the choice and its rationale (a stable token across `GET /session` calls without storing it in plaintext) as an amendment to ADR-0004, and the data-architect notes the derivation in `05-data.md` §4.1 `session.csrf_token_hash`. Optionally, keep the column as defence in depth: it does no harm.
- **Verification:** ADR-0004 and 05-data mention the HMAC derivation.
- **Status:** RESOLVED (re-check 1)

### CR-SL03a-005 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/` (no test cites SR-004)
- **Category:** tests
- **Problem:** SR-004 (errors do not reveal whether an account or email exists) is in the slice scope (plan, SL-03a, SR list), but no test cites it. The orchestrator already knows about this gap.
- **Scenario:** The traceability chain SR → test is broken for SR-004, so the DoD item "every requirement of the slice verified" cannot be checked.
- **Suggested fix:** A test asserting that an unknown `sub` without a bootstrap, an expired bootstrap, an alias email and a bootstrap redeemed by someone else all produce the same 302, the same `authOutcome` (`not_member`) and the same response shape, with no account, bootstrap or family information in the body or headers. Cite SR-004 in the test.
- **Verification:** `grep -rn "SR-004" backend/tests` finds the test, and `make test-int` is green.
- **Status:** RESOLVED (re-check 1)

### CR-SL03a-006 · LOW · BACKLOG
- **Location:** `backend/src/menu/family/onboarding.py:57-62` (and `backend/tests/concurrency/test_bootstrap_redemption_race.py:73-93`, which accepts the behaviour)
- **Category:** correctness
- **Problem:** Two callbacks for the same new `sub` (two tabs or a double click) race. The winner creates the account and redeems the bootstrap. The loser's `find_account` ran before the winner committed, and its `_LOCK` then returns no row. `resolve` falls through to `NotMember`, and the loser records `not_member`.
- **Scenario:** In the losing tab, the bootstrap owner (now Admin) sees "Serve un invito". Data stays correct (one account, one person) and a reload fixes it, but the message is wrong.
- **Suggested fix:** When `_redeem` finds the bootstrap already taken, re-run the membership lookup by `sub` (READ COMMITTED: the new statement sees the committed winner), and return `Member` if the account now exists. Tighten the test so that both tabs are authenticated, or so that neither shows `not_member`.
- **Verification:** The concurrency test asserts that no contender reads `authOutcome.code == "not_member"`.
- **Status:** OPEN

### CR-SL03a-007 · LOW · BACKLOG
- **Location:** `backend/src/menu/identity/oidc.py:226`
- **Category:** correctness
- **Problem:** `claims["iss"] == self._issuer` accepts only `https://accounts.google.com`. Google's OIDC documentation states that the ID token `iss` is `https://accounts.google.com` **or** `accounts.google.com`. The authorization-code flow normally returns the https form, so this is TO VERIFY rather than a confirmed bug.
- **Scenario:** If Google issues the schemeless form for some accounts or clients, every login in production ends in `auth_failed` with reason `token`.
- **Suggested fix:** When the configured issuer is `GOOGLE_ISSUER`, also accept the literal `accounts.google.com`. Keep strict equality for the fake issuer in dev and test.
- **Verification:** A unit test where a token with `iss="accounts.google.com"` is accepted only under the Google issuer, plus the manual P-3 check with real Google (log the `iss` value seen, without other claims).
- **Status:** OPEN

### CR-SL03a-008 · LOW · BACKLOG
- **Location:** `backend/src/menu/identity/sessions.py:96-102` (`delete_session`, `tx is None` branch), `backend/src/menu/identity/flows.py:105-109` (`record_failure`, `tx is None` branch)
- **Category:** maintainability
- **Problem:** Every caller passes `tx` (`logout.py:13`, `login.py:98`, `login.py:192`), so the branches that open their own transaction are never executed. They add a second, untested way to write these rows.
- **Scenario:** A future caller uses the implicit-transaction form and splits the outcome or session write from its security event, which breaks the "same transaction" rule the module docstrings promise.
- **Suggested fix:** Make `tx` mandatory and remove the branches.
- **Verification:** `mypy` and the suite stay green.
- **Status:** OPEN

### CR-SL03a-009 · LOW · BACKLOG
- **Location:** `backend/tests/db/test_identity_schema.py:120-147`
- **Category:** tests
- **Problem:** To accommodate `varchar(254)` (the email-length case raises 22001 before the CHECK), `StringDataRightTruncation` was added to the exception tuple shared by **all** eleven parametrized cases. Each case should fail only for its own reason.
- **Scenario:** If, for example, `display_name` were later turned into `varchar(60)` and its CHECK dropped, the "nome oltre 60 caratteri" case would still pass via truncation. That is harmless here, but the test no longer pins which constraint rejects which row.
- **Suggested fix:** Parametrize the expected exception per case (or move the email-length case into its own test expecting `StringDataRightTruncation`), and keep `CheckViolation` or `NotNullViolation` for the others.
- **Verification:** `make test-db`.
- **Status:** OPEN

### CR-SL03a-010 · LOW · BACKLOG
- **Location:** `backend/pyproject.toml` (`authlib>=1.9.1`). The warning is visible in every pytest run: `authlib/integrations/httpx_client/assertion_client.py:5: AuthlibDeprecationWarning: The httpx module is deprecated; please use httpx2 instead.`
- **Category:** maintainability (dependency)
- **Problem:** The integration chosen in ADR-0004 (`authlib.integrations.httpx_client.OAuth2Client`) is deprecated by its maintainer in the pinned version.
- **Scenario:** A future Authlib release removes the httpx integration, and an upgrade (for example for a CVE) breaks login.
- **Suggested fix:** Record this as technical debt. Before the next Authlib upgrade, evaluate the httpx2 path and verify on the registry that `httpx2` exists, is maintained and is the maintainer-endorsed package, following the protocol's verified-dependencies rule. Consider promoting the deprecation warning to an error in pytest for `authlib.*` so the change is not missed.
- **Verification:** The STATUS backlog has an entry; a later upgrade runs the SR-033 token tests.
- **Status:** OPEN

### CR-SL03a-011 · INFO · BACKLOG
- **Location:** `web/src/api/session.ts:65-77`
- **Category:** security (judgement requested by the orchestrator) / tests
- **Problem:** `safeRedirectUrl` also allows `http:` when `hostname` is `127.0.0.1`, `localhost` or `[::1]`, in every build including production. My judgement is that this is **acceptable**. The value comes from our own server (same-origin `POST /auth/google/start`). In staging and production, the configuration forces the Google issuer, so the server can only return `https://accounts.google.com/...`. The WHATWG `hostname` comparison is exact, so `http://localhost.evil.example` is refused. A server able to return a malicious URL already controls the SPA. Gating the branch on `import.meta.env.DEV` would break the e2e suite, which runs the production build against the loopback fake provider. The only gap is that no unit test exercises the loopback branch, either accepted or refused.
- **Scenario:** A future edit widens the branch (for example to `.endsWith("localhost")`) and no test notices.
- **Suggested fix:** Add cases to `login-flow.test.tsx`: `http://127.0.0.1:9999/auth` is followed, while `http://localhost.evil.example/`, `http://127.0.0.2/` and `http://[::2]/` are refused.
- **Verification:** `pnpm test`.
- **Status:** RESOLVED (re-check 1, fixed early although BACKLOG)

### CR-SL03a-012 · INFO · BACKLOG
- **Location:** `backend/src/menu/views/schemas.py:25-30`, `backend/src/menu/identity/api.py:79` (both copied into `openapi.json` and `web/src/api/schema.gen.ts`)
- **Category:** maintainability / design
- **Problem:** Docstrings meant for developers become public API descriptions. One is "Il valore dichiarato serve solo al contratto: i parametri si leggono con `_single`", and the other is NoticeView's "... da precisare". The NoticeView note also flags a real conflict: the SL-03a contract test forbids any property name containing "subject", while plan §4.2 defines `Notice.subjectPersonId` for SL-24.
- **Scenario:** SL-24 either weakens the contract test ad hoc or renames a field the plan fixes.
- **Suggested fix:** Move the developer notes into `#` comments, or use `description=` explicitly on the route. Ask the tech-lead now to narrow the contract test to `sub` and `authSubject`, or to rename the planned field.
- **Verification:** `make openapi` and `pnpm run api:check` show the cleaned descriptions.
- **Status:** OPEN

## Tools run
| Tool | Command | Result |
|---|---|---|
| ruff | `backend/.venv/bin/ruff check . && ruff format --check .` | All checks passed; 170 files already formatted |
| mypy | `backend/.venv/bin/mypy` | Success: no issues found in 164 source files |
| bandit | `backend/.venv/bin/bandit -q -c pyproject.toml -r src` | no findings |
| pytest unit, architecture, contract | `pytest tests/unit tests/architecture tests/contract -m "not container"` | 734 passed |
| pytest db, integration, security, property | `pytest tests/db tests/integration tests/security tests/property -n 4` (MENU_TEST_PG_* as in `make`) | 759 passed |
| pytest concurrency | `pytest tests/concurrency -n 2` | 4 passed (one run, not repeated 3×) |
| tsc | `pnpm run typecheck` | clean |
| eslint | `pnpm run lint` | clean (max-warnings 0) |
| vitest | `pnpm exec vitest run` | 18 files, 447 tests passed |
| api:check | `pnpm run api:check` | `schema.gen.ts` matches `openapi.json` |
| e2e | not run by the reviewer | tester reports 136 green |

## What was done well
The callback transaction is well designed. The flow is claimed once with an atomic `UPDATE … WHERE consumed_at IS NULL` before the code exchange. `state` is checked before the provider `error`, so a forged cancel cannot plant an outcome. The bootstrap is locked `FOR UPDATE` before `ensure_account`, so the loser of a race leaves no account behind (SR-049). Account, person, redemption, session, `auth.login` event and flow deletion are committed in one transaction. Expiry boundaries are identical in `session_resolve`, the cleanup policies and 05-data (inclusive, in hours), and they are proven to the second in `test_session_rls.py`. The CSRF and fixation negative tests are thorough.

## Re-check (cycle 1)
- **Date:** 2026-10-23
- **Scope:** only the FIX-IN-SLICE findings CR-SL03a-001 to -005, the diff of their fixes, and the regressions those fixes could introduce: the logout cookie ordering, the new `Response` parameter of `session_guard`, the `fake_oidc_server.py` key pre-generation, and the `safeRedirectUrl` change for CR-SL03a-011. BACKLOG findings -006 to -010 and -012 stay OPEN as backlog and were not re-reviewed.
- **Verdict:** **APPROVED**. No BLOCKER or FIX-IN-SLICE finding is open, and the fixes introduce no new BLOCKER (anti-loop rule).

| ID | Result | Evidence |
|---|---|---|
| CR-SL03a-001 | RESOLVED | `identity/oidc.py:175` passes `prompt="select_account"` to `create_authorization_url` on every authorization request, with no contract change. `tests/integration/test_auth_flow.py:60` asserts `params["prompt"] == "select_account"` on the URL that the fake provider receives (it cites AC-001.5). Real Google behaviour is still part of the manual P-3 check. |
| CR-SL03a-002 | RESOLVED | `identity/guards.py:56-67`: `session_guard(request, response)` re-issues `__Host-session` with `renewed_max_age` whenever the resolution renewed the row. The cookie refresh is now a property of every guarded route, not only of `GET /session` (`views/session.py:54-55` unchanged). Mutation check: with the guard's `set_session_cookie` neutralised (a pytest plugin in the scratchpad, with no project file touched), `test_ac_001_2_session_guard_renews_the_cookie_for_every_guarded_route` and `..._keeps_the_get_session_cookie_in_step` fail. |
| CR-SL03a-003 | RESOLVED | New tests in `tests/integration/test_auth_sessions.py:200-282` cover all three requested cases: the re-issued cookie with the same value, `Max-Age=2592000` and the SR-005 attributes; the cap at the remaining absolute lifetime (`80000 < Max-Age <= 86400` at 89 days); and no `Set-Cookie` within the hour, for both `GET /session` and a guarded route. Mutation checks: removing the refresh in `GET /session` fails 2 tests, and forcing `renewed_max_age = IDLE_SECONDS` (no cap) fails 2 tests. |
| CR-SL03a-004 | RESOLVED | ADR-0004 now has "Revisione 5" (header line 4, Decisione → CSRF line 102, the dedicated section at line 174). It records the derivation, the rationale, the security argument and the explicit consequence that the CSRF token cannot be rotated without rotating the session, which addresses the SL-25 scenario. `04-architecture.md` (v6.1, line 29, and the `identity` row at line 227) and `05-data.md:400` (`session.csrf_token_hash`) describe the HMAC derivation. The code matches the text (`tokens.py:40-42`, `sessions.py`). |
| CR-SL03a-005 | RESOLVED | `tests/security/test_auth_enumeration.py` cites SR-004 and checks 8 cases: unknown `sub`, an expired bootstrap, a bootstrap redeemed by someone else, an alias email, an existing account without a family, and three forged `email_verified` cases. All produce the same 302, `Location`, body and headers (cookie values excluded), with no session. The non-forged cases share the same `authOutcome` (`not_member`), and the forged outcome does not depend on whether the invite exists. Names, emails, `sub`s and IDs never appear. `grep -rln SR-004 backend/tests` finds it, and it passes. |
| CR-SL03a-011 (BACKLOG, fixed early) | RESOLVED | `web/src/api/session.ts:68-79` now also rejects URLs with userinfo, and accepts `http:` only on the exact loopback `hostname`. `web/tests/unit/api/safe-redirect.test.ts` covers the accepted loopback forms (`127.0.0.1`, `localhost`, `[::1]`) and the refusals I proposed (`localhost.evil.test`, `127.0.0.1.evil.test`, `evil.test@127.0.0.1`, `https://127.0.0.1/`, and others), plus userinfo tricks on Google. The tightening does not affect the fake provider URL used by e2e (`http://127.0.0.1:<port>/...`, no userinfo). |

### Regression check
- **Logout cookie ordering:** on logout, `session_guard` can append a renewing `Set-Cookie: __Host-session=<token>; Max-Age=...` before the endpoint appends the deletion. FastAPI injects the same `Response` object into the dependency and the endpoint, and `logout` returns that object, so both headers are sent in order: set, then delete. Browsers apply `Set-Cookie` headers in order, so the deletion wins. `test_logout_ends_up_with_the_session_cookie_deleted_even_if_it_was_renewed` ages the session so that the renewal does happen, and asserts that the cookie is gone. That test would fail if the order were reversed. No regression.
- **New `Response` parameter of the guard:** it is a FastAPI-injected parameter, so the signature seen by callers (`Depends(session_guard)`) is unchanged. `mypy`, the architecture and contract tests, and `api:check` are green, and `openapi.json` is unaffected. Residual note (INFO, not a new finding): `resolve_session` renews the row *before* the CSRF check. On a guarded request rejected with `403 csrf_failed`, the row is renewed but the error response, built by the exception handler, does not carry the refreshed cookie. The drift is bounded: it closes at the next renewal, one hour later, and needs a failed CSRF request close to the 30-day edge. Acceptable. If desired, a later slice can move the renewal after the CSRF check.
- **`tests/support/fake_oidc_server.py` pre-generating keys:** `start()` warms `get_key("primary"|"other"|"rotated")` before serving. `get_key` is now guarded by `_KEYS_LOCK` (`fake_oidc.py:162-177`), so concurrent first use can no longer produce two different `primary` keys. Any other label is still generated lazily under the lock. This is test-support code only, with no production hook. The full suite is green, including concurrency.
- **`safeRedirectUrl`:** see CR-SL03a-011 above. The change only makes the check stricter.

### Tools run (re-check)
| Tool | Command | Result |
|---|---|---|
| ruff | `backend/.venv/bin/ruff check . && ruff format --check .` | All checks passed; 171 files already formatted |
| mypy | `backend/.venv/bin/mypy` | Success: no issues found in 165 source files |
| pytest | `pytest tests/integration/test_auth_sessions.py tests/integration/test_auth_flow.py tests/security tests/unit -n 4` | 866 passed |
| pytest | `pytest tests/db tests/integration tests/property tests/architecture tests/contract -n 4` | 729 passed |
| pytest concurrency | `pytest tests/concurrency -n 2` | 4 passed |
| mutation (scratchpad plugins) | renewal refresh removed in the view or in the guard; cap removed | each mutation fails 2 tests in `test_auth_sessions.py` |
| vitest | `pnpm exec vitest run` | 19 files, 471 tests passed |
| tsc / eslint / api:check | `pnpm run typecheck`, `pnpm run lint`, `pnpm run api:check` | clean; `schema.gen.ts` matches `openapi.json` |
| e2e | not run by the reviewer | — |
