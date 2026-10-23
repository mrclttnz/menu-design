# Code review · SL-03b

- **Date:** 2026-10-23
- **Reviewer:** code-reviewer
- **Scope:** `git diff c026d42` (19 tracked files) plus the untracked SL-03b files: `backend/migrations/versions/0006_rate_counter.py`, `backend/src/menu/ratelimit/{middleware,rules,store}.py`, `backend/tests/{concurrency/test_ratelimit_race,db/test_rate_counter_schema,integration/test_ratelimit,integration/test_session_cap,security/test_ratelimit_security,support/ratelimit,unit/test_ratelimit_config,unit/test_ratelimit_store}.py`, `web/src/features/altro/AltroPage.tsx`, `web/tests/e2e/altro.spec.ts`, `web/tests/unit/app/s08-altro.test.tsx`, `web/tests/unit/session/login-rate-limit.test.tsx`. I read every changed file in full, together with these callers and collaborators: `app/factory.py`, `tenancy/engine.py`, `platform/http/{client_ip,middleware,problem}.py`, `identity/{login,api}.py`, `web/src/app/RootLayout.tsx`, `web/src/api/errors.ts`. I also read the references: plan SL-03b and §2, SR-059, SR-070, AC-001.9, AC-047.4, UX S-08, ADR-0006, and `docs/05-data.md` v8.
- **Verdict:** APPROVED (re-check, cycle 2, 2026-10-23). Cycle 1: APPROVED WITH FIXES
- **Cycle:** 2

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL03b-001 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/ratelimit/store.py:20-28`, `rules.py:1-6`, ADR-0006 | The code uses a pure fixed window and a path-keyed middleware table. ADR-0006 specifies a sliding-window estimate and per-route FastAPI dependencies. The deviation is not recorded anywhere (D1) | RESOLVED (ADR-0006 rev. 6, CHG-021) |
| CR-SL03b-002 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/ratelimit/rules.py:30-32`, plan SL-03b, SR-059 | Two SR-059 rows that are in force for the MVP Google login are neither implemented nor recorded as deferred: "Callback OIDC" 30/IP/15 min and "Login fallito" 20/IP/15 min (D2) | RESOLVED (deferred: CHG-021, ADR-0006 rev. 6) |
| CR-SL03b-003 | MEDIUM | FIX-IN-SLICE | `web/src/app/RootLayout.tsx:23-37`, `web/src/app/routes.tsx:20` | S-08 "Altro" (and so "Esci") cannot be reached from the UI. It opens only by typing `/altro` | RESOLVED |
| CR-SL03b-004 | LOW | FIX-IN-SLICE | `backend/tests/integration/test_ratelimit.py:47-58` | No test pins the value of `Retry-After`: any value in 1..900 passes | RESOLVED |
| CR-SL03b-005 | LOW | BACKLOG | `backend/src/menu/ratelimit/middleware.py:102-114` | Only the first crossing rule is logged, and `details_json` is built by string concatenation | OPEN |
| CR-SL03b-006 | LOW | BACKLOG | `backend/src/menu/ratelimit/middleware.py:75`, `identity/sessions.py:86-94` | Each authenticated API request resolves the session twice (middleware, then guard) and pays three DB round trips | OPEN |
| CR-SL03b-007 | LOW | BACKLOG | `backend/src/menu/platform/config.py:72`, `.env.example:24` | `SESSION_PEPPER` is a misleading name: it is the pepper for the rate-limit keys, not for sessions | OPEN |
| CR-SL03b-008 | LOW | BACKLOG | `backend/src/menu/ratelimit/middleware.py:78-80` | The fail-closed `503` under `/api/v1/` is `application/json` `{"status":"unavailable"}`, not problem+json (plan §4 "Errori") | OPEN |
| CR-SL03b-009 | INFO | BACKLOG | `docs/07-plan.md` §2.2, SR-070 traceability | `SessionIdentifier` is a new upward protocol (identity → ratelimit) that §2.2 does not list. `WRITE_ACCOUNT` (SR-070) ships here, earlier than planned (SL-05) | RESOLVED (plan §2.2 and traceability updated) |
| CR-SL03b-010 | INFO | BACKLOG | `backend/src/menu/ratelimit/store.py:20-28` | The store only supports fixed-second UTC bins. The SR-070 family window is a local day in the family's time zone (05-data §13), which SL-05 will need | OPEN |

## Findings

### CR-SL03b-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/ratelimit/store.py:20-28` (`_UPSERT` with `date_bin`), `backend/src/menu/ratelimit/rules.py:1-6`, `backend/src/menu/ratelimit/middleware.py:93-99` (`ROUTE_RULES` lookup by path); `docs/adr/ADR-0006-store-limiti-di-frequenza.md` "Algoritmo" and "Applicazione"
- **Category:** design
- **Problem:** ADR-0006 specifies two things the code does not do:
  - a "fixed window with a sliding-window estimate" (the previous window's count is weighted in);
  - per-rule FastAPI dependencies on the routes. The middleware is reserved for the general authenticated limit.

  The code instead uses a pure fixed window, aligned with `date_bin` on 2000-01-01 UTC, and a `(method, path)` table inside the middleware. Both choices are reasonable, and the module docstring even states the first one, but they contradict an ACCEPTED ADR without an amendment (protocol §3 rule 5). The security-engineer reviewed the ADR's algorithm, not this one.
- **Scenario:** On each side of a window boundary, a client can use the whole limit. An IP can make 30 starts at 12:14:59 and 30 more at 12:15:00, so 60 starts within one second. Likewise a session can make 120 writes in about two seconds across a minute boundary. SR-059 says "30 per IP in 15 minuti": the effective bound is 2× in the worst case.
- **Suggested fix (D1, my recommendation: amend the ADR, keep the code):**
  - **Amend ADR-0006** (owner: architect; security-engineer to confirm). State the following:
    - the fixed, aligned window;
    - the accepted worst-case burst of 2× the limit across a boundary;
    - why it is accepted: proportionate controls, and Google handles the credentials, so this is abuse and DoS damping, not brute-force protection;
    - that `Retry-After` is exact (seconds to the end of the window), whereas the sliding estimate could only give an approximate value;
    - the `ROUTE_RULES` table in the middleware instead of per-route dependencies (one upsert per request is easier to keep in a single place).
  - **Changing the code instead** is feasible in one statement: `RETURNING` can carry a scalar subquery for the previous window's `count`, and the code compares `count + prev × (1 − elapsed/window)`. The cost is that `Retry-After` becomes approximate, the window logic is no longer obvious, and the frozen-clock tests must be rewritten. For this app's risk level I do not think that is worth it.
- **Verification:** ADR-0006 gets a new revision line that matches `store.py` and `middleware.py`, and the security-engineer's SL-03b review cites it. If the code changes instead, add a test for 30 requests just before and just after the boundary: the 31st must get `429`.
- **Status:** RESOLVED (re-check 2026-10-23). ADR-0006 revision 6 records the fixed window with `date_bin` on `app.now_utc()`, the accepted 2× burst, the exact `Retry-After`, the review trigger (low-entropy secrets) and the ASGI middleware with declarative rules instead of per-route dependencies. CHG-021 records the user's decision D1. Plan §1 and SL-03b and test strategy §7.4 match the code (`store.py`, `rules.py`, `middleware.py`).

### CR-SL03b-002 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/ratelimit/rules.py:30-32` (`ROUTE_RULES` has only `POST /api/v1/auth/google/start`); `docs/02-requirements.md` SR-059 (CHG-020 note); `docs/07-plan.md` SL-03b and traceability row SR-059
- **Category:** correctness (requirements)
- **Problem:** The CHG-020 note on SR-059 says that, for Google login in the MVP, two rows apply: "Callback OIDC e avvio del login" (30/IP/15 min) and the per-IP limit of "Login fallito" (20/IP/15 min). The plan's SL-03b names only the start. The traceability table maps SR-059 to SL-03b, and no other slice picks these rows up. So two MVP requirements quietly fall through the gap.
- **Scenario:** Reading `identity/login.py:140-200`, the real impact is small:
  - **Callback.** Unlimited `GET /api/v1/auth/google/callback` calls with no flow or a bogus one cost one `claim_flow` query each and write nothing. A callback with a real flow needs a start, which is already capped at 30/IP.
  - **Failed logins.** Failures recorded per IP are therefore bounded by the starts: at most 30 per 15 minutes. SR-059 asks for 20.

  So the gap is in compliance, not an open door. But the "un test per ogni riga" verification of SR-059 cannot pass for these rows.
- **Suggested fix (D2, my recommendation: defer with a recorded note, do not implement now):**
  - **Callback.** The plan §4.3 contract says the callback "risponde sempre `302`". A middleware `429` problem+json on a top-level navigation would break that contract and show raw JSON to the user. Adding the rule properly therefore needs a contract decision first: for example, a `302` to `/accedi` with outcome `rate_limited`. That is more than this S slice should absorb.
  - **Failed logins.** These need a counter that is incremented on a failure outcome and checked at the start (a "peek" the store does not offer).
  - **Record the deferral.** The tech-lead adds a line to SL-03b "Rischi" or §11.3 with the bound argument above (failures ≤ starts ≤ 30/IP/15 min), points the SR-059 traceability to the slice that will close the rows (SL-12, which already touches the callback with invites, is a natural home), and records the decision in `docs/STATUS.md`. Because SR-059 is a security requirement, the security-engineer should confirm the deferral. If they judge it a MEDIUM security gap, the review contract requires the user's explicit acceptance.
  - **Alternative.** If the orchestrator prefers to close it now, add `oidc_callback_ip` (30, 900, a separate counter so that a normal login doesn't cost 2 of the 30) and agree on the `302` behaviour with the UX designer.
- **Verification:** A plan, traceability and STATUS entry exists naming the target slice, or a test shows the 31st callback from one IP within 15 minutes is limited without breaking the `302` contract.
- **Status:** RESOLVED (re-check 2026-10-23), as a recorded deferral. CHG-021 (user decision D2), SR-059 summary row, ADR-0006 rev. 6 "Righe di SR-059 rinviate" (rationale: work on the callback requires a start-created flow; callback contract is always `302`; review with SL-12 or SL-33/SL-34), plan SL-03b SR line and traceability row, test strategy §7.4 ("un test per ogni riga attiva"). The `docs/STATUS.md` log entry is the orchestrator's (see re-check notes).

### CR-SL03b-003 · MEDIUM · FIX-IN-SLICE
- **Location:** `web/src/app/RootLayout.tsx:23-37` (no navigation), `web/src/app/routes.tsx:20`, `web/src/features/plan/PlanPage.tsx` (empty placeholder)
- **Category:** correctness (UX)
- **Problem:** The slice goal is that "la persona collegata vede chi è ed esce da 'Altro'". `/altro` exists, but no link, tab or account button anywhere in the shell points to it. UX DD-06 places "Altro" in the bottom bar (Piano, Piatti, Altro), and S-02 also has an account button. Neither exists yet, and no slice in the plan explicitly owns the bottom bar. The e2e test reaches the page with `page.goto("/altro")`, which hides the gap.
- **Scenario:** A family member signs in and lands on `/piano`, which is an empty placeholder until SL-06a. They have no way to see who is signed in or to sign out without typing a URL. On a shared device, this defeats the purpose of "Esci" (FR-004).
- **Suggested fix:** Add a minimal bottom navigation to the authenticated layout (or to `RequireSession`'s outlet) with "Piano" and "Altro" (`nav.plan` and `nav.more` already exist). "Piatti" can follow with SL-04. Alternatively, the tech-lead assigns the bar to a named slice and adds an interim link from `PlanPage` to S-08. Either way, record who owns DD-06.
- **Verification:** In `altro.spec.ts`, replace `page.goto("/altro")` with a click on the "Altro" entry, starting from `/piano`. Add a vitest check that the link is present only with a session.
- **Status:** RESOLVED (re-check 2026-10-23). `RootLayout.tsx` renders `<nav aria-label="Navigazione principale">` with `NavLink`s to `/piano` and `/altro` only when `session?.authenticated`; `nav.label` added to the catalog and the `.po`. `nav.test.tsx` checks the click from `/piano` to S-08, `aria-current`, and no nav without a session. `altro.spec.ts` now reaches S-08 via `openAltro()` (click in the navigation) in all three signed-in tests; `page.goto("/altro")` remains only for the anonymous and post-logout redirects, which is correct.

### CR-SL03b-004 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/integration/test_ratelimit.py:47-58` (`_assert_rate_limited`); no unit test for `store.hit`'s `retry_after`
- **Category:** tests
- **Problem:** Every test freezes the database clock at `T0 = 12:07:30`, so the expected values are known exactly: 450 s for the 15-minute window and 30 s for the 1-minute windows. Yet the assertion is only `1 <= retry <= 900`. The `retry_after` arithmetic in `store.py:52-59` (window end minus `now`, `ceil`, maximum over the exceeded rules, clamp) is the part most likely to regress, and nothing pins it.
- **Scenario:** A regression that always returns 900, or one that uses `window_start - now`, or the shortest instead of the longest window, would still pass all 62 SL-03b tests.
- **Suggested fix:** Assert `retry == 450` in `test_ac_001_9_…`, `retry == 30` in the 301st-request and 61st-write tests, and a value just under 900 at `T0 = hh:00:00.5`. Optionally, add one `db`-tier test of `hit()` with two exceeded rules of different lengths, which must return the longer remainder.
- **Verification:** `make test-int` is green, and a deliberate mutation of `retry_after` (for example, returning `MAX_WINDOW_SECONDS`) makes it fail.
- **Status:** RESOLVED (re-check 2026-10-23). `_assert_rate_limited` now asserts `retry == retry_after` (default 30) and `params.retryAfterSeconds == retry`; the start tests pass `START_WAIT = 450`, and the window test checks `START_WAIT - 60 = 390` after one minute. A mutation returning `MAX_WINDOW_SECONDS`, `window_start - now` or a constant would now fail. The optional two-rules-of-different-length test was not added; no current request combines rules of different windows, so this is acceptable.

### CR-SL03b-005 · LOW · BACKLOG
- **Location:** `backend/src/menu/ratelimit/middleware.py:102-114`
- **Category:** maintainability
- **Problem:** The event carries only `crossing[0]`. In the most common case (a single device writing in a loop), `write_session` and `write_account` both reach 61 in the same request, and the event records only `write_account` because of the alphabetical sort. Separately, `details_json` is built as `'{"rule":"' + name + '"}'`. That is safe today because rule names are constants, but it becomes fragile as soon as a name contains a quote.
- **Scenario:** An operator reading the security log cannot tell that the session limit was also hit. A future rule name containing `"` would produce invalid JSON.
- **Suggested fix:** Use `json.dumps({"rules": [e.rule.name for e in crossing]})`.
- **Verification:** A unit test with two simultaneous crossings checks that both names appear in `details`.
- **Status:** OPEN

### CR-SL03b-006 · LOW · BACKLOG
- **Location:** `backend/src/menu/ratelimit/middleware.py:75`, `backend/src/menu/identity/sessions.py:86-94`, `app/factory.py:95`
- **Category:** performance
- **Problem:** For every authenticated `/api/v1` request the middleware runs `session_resolve` in its own transaction, then the counter upsert in a second transaction, and then the route guard resolves the same session again. That is three pool checkouts per request before any domain work, and every request also occupies a threadpool slot for the middleware's work.
- **Scenario:** No problem at the expected load (ADR-0006 already estimates 1-3 ms). Under the pool's 5+5 connections and with the Supabase pooler, the extra checkouts are the first thing to show up in p95.
- **Suggested fix:** Later, store the `SessionRef` in `scope["state"]` and let the guard reuse the ID: it still has to load the row to renew it. Or merge the identify and upsert steps into one transaction. Not now.
- **Verification:** A perf-tier p95 comparison of `GET /session` with and without the change.
- **Status:** OPEN

### CR-SL03b-007 · LOW · BACKLOG
- **Location:** `backend/src/menu/platform/config.py:72`, `.env.example:24-26`, `Makefile:110`, `backend/scripts/export_openapi.py:13`
- **Category:** maintainability
- **Problem:** The secret is the HMAC pepper for the `rate_counter` keys (architecture §446: "pepper HMAC dei limiti di frequenza"), but it is called `SESSION_PEPPER`. The name was inherited from an old placeholder. Session tokens are plain SHA-256 and do not use it.
- **Scenario:** In SL-10b, devops creates a Secret Manager entry named after sessions. A later "rotate the session pepper" runbook step, or a future feature that does pepper sessions, would then rotate or reuse the wrong secret.
- **Suggested fix:** Rename it to `RATE_LIMIT_PEPPER` before the first deploy (SL-10b), when the change costs only a few edited lines.
- **Verification:** `grep -rn SESSION_PEPPER` returns nothing, and the config tests still refuse a missing or placeholder value.
- **Status:** OPEN

### CR-SL03b-008 · LOW · BACKLOG
- **Location:** `backend/src/menu/ratelimit/middleware.py:78-80`
- **Category:** design (contract)
- **Problem:** Plan §4 "Errori" says `/api/v1` errors are RFC 9457 problem+json with a `code`. The fail-closed path returns `JSONResponse({"status": "unavailable"}, 503)`, copied from `/healthz`. `ErrorCode` has no 503 code. The web client falls back to `error.generic`, so users see no difference, but it is a second error shape under `/api/v1`.
- **Scenario:** A future client or monitoring rule that keys on `content-type: application/problem+json` for API errors misses limiter outages.
- **Suggested fix:** Either document the exception in plan §4 next to `/healthz`, or add a `service_unavailable` code (ADR-0010 change) and use `problem_response`. Documenting it is enough.
- **Verification:** The plan text, or a contract test, matches the response.
- **Status:** OPEN

### CR-SL03b-009 · INFO · BACKLOG
- **Location:** `backend/src/menu/ratelimit/middleware.py:31-39`, `app/factory.py:91-96`; `docs/07-plan.md` §2.2 and the SR-070 traceability row
- **Category:** design
- **Problem:** The layering is correct: `ratelimit` (layer 4) does not import `identity` (layer 5), and `app` wires `identity.identify_session` in through the `SessionIdentifier` protocol. But §2.2 lists every upward protocol, and this one is missing. Separately, `WRITE_ACCOUNT` (SR-070, 60 writes/min per account) is delivered here, although the plan and I-T5 place it in SL-05. That is welcome, but the traceability row "SR-070: SL-03b (20 sessioni), SL-05 (per account e per famiglia)" is now out of date.
- **Scenario:** Nothing breaks today. However, SL-05 could implement `WRITE_ACCOUNT` a second time, or the tester could look for it there.
- **Suggested fix:** The tech-lead adds `SessionIdentifier` to §2.2 and moves "per account" to SL-03b in the traceability table.
- **Verification:** Read the plan.
- **Status:** RESOLVED (re-check 2026-10-23): plan §2.2 lists `SessionIdentifier`; the SR-070 traceability row and SL-05 now place the per-account limit in SL-03b.

### CR-SL03b-010 · INFO · BACKLOG
- **Location:** `backend/src/menu/ratelimit/store.py:20-28`, `rules.py:9-14`
- **Category:** design
- **Problem:** `Rule` has only `window_seconds`, and the upsert bins with `date_bin(..., UTC origin)`. The SR-070 family limit (5,000 tracked writes per day) is specified in 05-data §13 as a local day in the family's time zone (`family_today()`). Fixed-second bins in UTC cannot express that.
- **Scenario:** If SL-05 adds `Rule("tracked_family", 5000, 86400)` as is, the window would reset at 00:00 UTC, which is 01:00 or 02:00 in Rome, and not at local midnight.
- **Suggested fix:** Handle this in SL-05: allow a per-hit `window_start` expression (for example, pass the bin start computed from `family_today()`) instead of deriving it from the rule. Recorded here so SL-05 does not discover it late.
- **Verification:** In SL-05, a test with the family in `Europe/Rome` shows that the counter resets at local midnight.
- **Status:** OPEN

## Re-check · cycle 2 (2026-10-23)

**Scope.** Only CR-SL03b-001 … 004 and the diff of their fixes (anti-loop rule), plus a sanity read of the code added in this cycle: `client_ip.limit_subject` (IPv6 /64, IPv4-mapped), `rules.WRITE_EXEMPT` and its use in `middleware._hits`, `TRUSTED_PROXY_HOPS >= 1` in strict environments (`config.py`), and their tests in `tests/security/test_ratelimit_security.py` and `tests/unit/test_ratelimit_config.py`. Base `c026d42`, uncommitted and untracked files included.

| ID | Cycle-1 class | Outcome |
|---|---|---|
| CR-SL03b-001 | FIX-IN-SLICE | RESOLVED: ADR-0006 rev. 6 and CHG-021 (D1) |
| CR-SL03b-002 | FIX-IN-SLICE | RESOLVED: deferral recorded, CHG-021 (D2) |
| CR-SL03b-003 | FIX-IN-SLICE | RESOLVED: bottom nav Piano/Altro, unit and e2e tests |
| CR-SL03b-004 | FIX-IN-SLICE | RESOLVED: exact `Retry-After` assertions (30, 450, 390) |
| CR-SL03b-009 | BACKLOG | RESOLVED as a side effect of the plan update |

**Sanity read of the new code: no new BLOCKER.**
- `limit_subject`: checked by direct call: `2001:db8::1` and `2001:db8::ffff:1` → `2001:db8::/64`; `::ffff:1.2.3.4` → `1.2.3.4`; `unknown` → `unknown`; `fe80::1%eth0` → `fe80::/64` (no exception, so no spurious 503). The security event still stores the full address (`client_ip_from`), only the counter key is reduced. Correct.
- `WRITE_EXEMPT`: logout still counts in `api_session` (300/min), skips only `write_session` and `write_account`. Exact `(method, scope["path"])` match; a variant path such as a trailing slash does not reach the logout handler, so it cannot be used to write without counting. Correct.
- `TRUSTED_PROXY_HOPS`: no default, refused when empty, and `< 1` refused in `staging`/`production` while `0` is still allowed in `dev`/`test`. Tested.
- Observation, not a finding (anti-loop rule, not a BLOCKER): in `test_sec_sl03b_001_different_ipv6_64_prefixes_are_independent` (`tests/security/test_ratelimit_security.py:310-311`) the loop does `assert browser.start_login(...)` on the response object, which is always truthy; the status of the first 30 is not checked. The following `429` still proves they were counted, so coverage is intact. Worth `.status_code == 200` the next time the file is touched.

**Notes for the orchestrator.**
- `docs/STATUS.md` does not yet log D1 and D2 (CHG-021) or the DD-06 bottom bar now living in SL-03b ("Piatti" to follow with its slice, per the `base.css` comment). The STATUS log is the orchestrator's; please add the line when closing the slice.
- CR-SL03b-005, 006, 007, 008, 010 stay OPEN as BACKLOG, unchanged by this cycle (`details_json` is still concatenated, `SESSION_PEPPER` still has its old name). They should appear in the STATUS debt table.

**Verdict after re-check: APPROVED.** No BLOCKER or FIX-IN-SLICE finding is open.

## Tools run
| Tool | Command | Result |
|---|---|---|
| ruff | `uv run --frozen ruff check src tests` and `ruff format --check src tests` (backend) | All checks passed, 175 files already formatted |
| mypy | `uv run --frozen mypy src tests` (backend) | Success: no issues found in 175 source files |
| pytest (unit) | `uv run --frozen pytest -q tests/unit/test_ratelimit_store.py tests/unit/test_ratelimit_config.py` | 15 passed |
| pytest (db, int, sec, conc) | `pytest -q tests/integration/test_ratelimit.py tests/integration/test_session_cap.py tests/security/test_ratelimit_security.py tests/concurrency/test_ratelimit_race.py tests/db/test_rate_counter_schema.py` (local cluster, `MENU_TEST_PG_*`) | 62 passed in 47.00s |
| vitest | `npx vitest run tests/unit/session/login-rate-limit.test.tsx tests/unit/app/s08-altro.test.tsx` | 2 files, 14 tests passed |
| ruff (re-check) | `uv run --frozen ruff check src tests`, `ruff format --check src tests` | All checks passed; 176 files already formatted |
| mypy (re-check) | `uv run --frozen mypy src tests` | Success: no issues found in 176 source files |
| pytest (re-check) | `pytest -q tests/integration/test_ratelimit.py tests/integration/test_session_cap.py tests/security/test_ratelimit_security.py tests/concurrency/test_ratelimit_race.py tests/db/test_rate_counter_schema.py tests/unit/test_ratelimit_store.py tests/unit/test_ratelimit_config.py tests/unit/test_platform_config.py` (local cluster, `MENU_TEST_PG_*`) | 104 passed in 42.96s |
| vitest (re-check) | `npx vitest run tests/unit/app/nav.test.tsx tests/unit/app/s08-altro.test.tsx tests/unit/session/login-rate-limit.test.tsx` | 3 files, 16 tests passed |
| tsc, eslint (re-check) | `npx tsc --noEmit -p .`; `npx eslint src/app/RootLayout.tsx tests/unit/app/nav.test.tsx tests/e2e/altro.spec.ts` | no output (clean) |

The full suite and e2e were run by the tester (green, per the orchestrator). I did not re-run them in either cycle; in particular `altro.spec.ts` with the new `openAltro()` click was not executed by me (needs the e2e stack).

## What was done well
- **Atomic counting.** One `INSERT … SELECT unnest … ORDER BY key … ON CONFLICT DO UPDATE … RETURNING` per request, with keys de-duplicated in Python (so there is no "cannot affect row a second time"), a stable lock order (so there are no deadlocks), and the database clock for both window and `Retry-After`. The 60-parallel-starts test proves exactly 30 get through.
- **Fail closed.** Any error in the limiter path, including session identification, returns `503` with no details and no handler execution, and the tests cover it.
- **Session cap.** The cap is enforced in the login transaction:
  - a per-account advisory lock under READ COMMITTED means the second concurrent login sees the first one's session;
  - the eviction runs after `drop_session_of_cookie`, so re-login does not cost another device;
  - expired sessions are excluded;
  - the `session.evicted` event is in the same transaction, and the parallel-logins test checks the result.
- **Privacy and layering.** The layering is clean (the protocol is injected by `app`), the keys are HMACs with the pepper and the rule name, and `identify_session` is read-only, so it does not renew sessions (consistent with the CR-SL03a-002 fix).
- **Tests.** Every test uses a frozen DB clock, so none of them can flake on a minute boundary. They include a real restart (a new app on the same database) and the forged `X-Forwarded-For` cases, and the e2e suite isolates IPs per context in the RFC 2544 range.

## Report — code-reviewer
**Outcome:** DONE
**Scope:** SL-03b, re-check (cycle 2)
**Files changed:** docs/reviews/SL-03b-code.md
**Summary:** Re-checked CR-SL03b-001 … 004 and the diff of their fixes. All four are RESOLVED: ADR-0006 rev. 6 and CHG-021 record the fixed window (D1) and the deferral of the callback and failed-login rows (D2), with plan, traceability and test strategy aligned; the authenticated layout has a Piano/Altro bottom nav with unit and e2e coverage; `Retry-After` is pinned to exact values. CR-SL03b-009 is also resolved by the plan update. The sanity read of IPv6 /64 keying, the logout write exemption and the strict `TRUSTED_PROXY_HOPS` check found no new BLOCKER. Verdict: APPROVED.
**Evidence:** ruff and format: all passed, 176 files; mypy: no issues in 176 files; SL-03b backend tests plus config tests: 104 passed in 42.96s; vitest nav, S-08, 429: 16 passed; tsc and eslint clean; `limit_subject` exercised directly (outputs in the re-check section).
**Traceability:** AC-001.4, AC-001.9, AC-047.4, FR-004, SR-003, SR-059 (active rows; deferred rows per CHG-021), SR-070 (20 sessions, 60 writes/min per account), THR-011, THR-012, THR-013, THR-103.
**Decisions needed:** none
**Risks and technical debt:** CR-SL03b-005, 006, 007, 008, 010 remain BACKLOG. Weak assertion in `test_sec_sl03b_001_different_ipv6_64_prefixes_are_independent` (observation only). e2e `altro.spec.ts` not run by me. `docs/STATUS.md` still lacks the CHG-021 / DD-06 log line and the backlog entries.
**Suggested next step:** Orchestrator logs CHG-021, the DD-06 bottom bar and the SL-03b BACKLOG items in `docs/STATUS.md`, confirms the security review is also closed, and runs the full suite including e2e before closing SL-03b.
