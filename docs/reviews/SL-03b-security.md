# SL-03b: security review

| Field | Value |
|---|---|
| Slice | SL-03b: rate limits, 20-session cap, S-08 "Altro" (minimal) |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-23 |
| Diff base | `c026d42` (nothing committed: `git diff c026d42` plus the untracked files from `git status`) |
| SRs in scope | SR-003, SR-059, SR-070 |
| THRs in scope | THR-011, THR-012, THR-013, THR-103 (and THR-100 for storage growth) |
| ADRs checked | ADR-0006 (rev. 5), ADR-0004 (session cap), 05-data v8 (`rate_counter`) |
| Verdict (first pass) | APPROVED WITH ONE FIX-IN-SLICE (1 MEDIUM FIX-IN-SLICE, 1 LOW FIX-IN-SLICE doc-only, 3 LOW BACKLOG, 4 INFO). No BLOCKER. |
| Re-check | 2026-10-23, see §6 |
| **Final verdict** | **APPROVED.** SEC-SL03b-001 … 005 all RESOLVED; no new finding; no BLOCKER. Residual risks R-12 and R-13 accepted by the user (2026-10-23, CHG-021). |

The limiter is small, fails closed, and does what ADR-0006 asks: one ordered upsert per request, peppered HMAC keys, the database clock, and one event per rule and window. The session cap is account-scoped twice over (explicit `WHERE` and RLS) and serialised per account. I found no way to bypass the IPv4 limits or to affect another account. The one fix asked for in this slice is the IPv6 key granularity (SEC-SL03b-001). It is a few lines and it matters for the per-IP limits of later slices too.

## 1. What was checked and how

**Files read in full:**
- `menu/ratelimit/{__init__,middleware,rules,store}.py`;
- `migrations/versions/0006_rate_counter.py`;
- `menu/platform/http/client_ip.py` and `identity/clientinfo.py` (unchanged, re-checked for the new caller);
- diffs of `identity/{sessions,login,__init__}.py`, `platform/config.py`, `app/factory.py`, `audit/catalog.py`;
- the login callback path `identity/login.py:92-220`, and `session_resolve` in `0005_identity.py:195-217`;
- web: `features/altro/AltroPage.tsx`, the `routes.tsx` diff, `api/session.ts` (`requestLogout`);
- test support: diffs of `e2e_stack.py`, `stub.ts`, `test_server_process.py`, `Makefile`, `.env.example`, `export_openapi.py`;
- test lists of `security/test_ratelimit_security.py`, `integration/test_{ratelimit,session_cap}.py`, `unit/test_ratelimit_{config,store}.py`, `concurrency/test_ratelimit_race.py`, `db/test_rate_counter_schema.py`.

**Tools run (fresh output, 2026-10-23):**

| Command | Result |
|---|---|
| `make scan-secrets` (gitleaks `git` + `dir`, `--redact`) | **no leaks found** (8 commits ~3.08 MB; working tree ~7.05 MB) |
| `make scan-sast` (custom rule tests, then semgrep `p/python p/owasp-top-ten p/typescript p/react .semgrep`) | rule tests passed; scan **rc=0, 0 findings** |
| `uv run bandit -r src -c pyproject.toml` | rc=0, "No issues identified" |
| `make scan-deps` / `make scan-web` | rc=0. Only the already-accepted GHSA-vfj7-8cjw-p6xm is filtered (ADR-0017). **No new dependencies** in this slice (no lockfile change) |
| `make test-unit` / `test-sec` / `test-int` / `test-conc` / `test-db` | **892 / 148 / 165 / 6 / 509 passed** |
| `make test-web` | 21 files, **485 tests passed** |
| Pydantic probe: `Settings()` with a 25-char pepper | `ValidationError` message has no input value; `repr(Settings)` shows `SecretStr('**********')` |
| Probe tests against the real app and test DB (scratch file outside the repo, run with the project's fixtures, not committed) | see §2 and SEC-SL03b-001/002 |

**Probe results (real app, real PostgreSQL):**
- **Path variants** of `POST /api/v1/auth/google/start`: trailing `/` → `307` to the canonical path (no handler, no flow row). `//api/v1/...`, `/api/v1//...`, `/API/v1/...` and `;x` → `404`. `HEAD`, `GET` and `OPTIONS` → `404`; `PUT` → `415`. The limited route can be reached only by its exact path and method, which is the exact key in `ROUTE_RULES`. **No bypass.**
- **Spoofed `X-Forwarded-For`** with `hops=1` (`198.51.100.7, 2001:db8:1:2::1` after 32 requests from `2001:db8:1:2::1`) → `429`: the client-supplied entry is ignored.
- **40 starts from 40 IPv6 addresses inside one `/64`** → 0 × `429`. A control run of 32 starts from one IPv6 address → 2 × `429`. See SEC-SL03b-001.
- **Logout after 60 writes in the same minute** → `429`, `Retry-After: 30`. See SEC-SL03b-002.

## 2. Checks against THRs, SRs and the brief

| Item | Result |
|---|---|
| **THR-012: `X-Forwarded-For`** (`client_ip.py:21-28`) | One function, used by the limiter, the security log and `session.ip_prefix`. With `hops=n` it takes the n-th entry from the right, across all `X-Forwarded-For` headers. Entries the client controls are never used. An invalid entry falls back to the peer address, never to another entry. uvicorn `proxy_headers=False`. Tests cover a forged header, real-IP separation, `hops=0` ignoring the header, an invalid last entry, and the real IP in the 429 event. **Met.** Residual: V-3 in staging (devops), and `hops=0` is still accepted in staging/production (SEC-SL03b-003). |
| **`TRUSTED_PROXY_HOPS` without a default** (`config.py:70`) | `Field(ge=0, le=10)` with no default: startup fails if it is missing or empty (unit tests, plus `test_startup_is_refused_when_trusted_proxy_hops_is_not_set`). This closes SEC-SL00a-005. **Met.** |
| **Pepper** (`config.py:72, 88-94`; `factory.py:91-96`; `store.py:212-213`) | `SecretStr`, mandatory, at least 32 characters, `CHANGE_ME` refused. The validation error text has no input value (probe). `repr`, `str` and `model_dump_json` are masked (test). The raw bytes live only in the middleware instance and are passed to `hmac.new`. They are never logged: every `except` logs only `type(error).__name__`. Key = `HMAC-SHA256(pepper, rule.name || 0x00 || identifier)`, 32 bytes, and the DB CHECK enforces the length. The rule name in the key keeps rules apart. Different peppers give different keys (test). Dummy peppers appear only in test and dev tooling and are not secrets. gitleaks is clean. **Met.** |
| **Fail closed, THR-103** (`middleware.py:67-80`) | Any exception in IP parsing, session lookup or the upsert → `503`, with body `{"status":"unavailable"}` and no detail. The handler does not run (test: the write is not executed). The log line has the exception type only (test: no connection details). A failure to *record* the 429 event keeps the `429`. **Met.** (INFO-2 on the body format.) |
| **429 contract and leaks** | `problem+json` `rate_limited`, `Retry-After` in 1..900 s from the DB clock, and `params.retryAfterSeconds` only. No rule name, key, count or identity in the response (test `test_the_429_body_and_headers_reveal_nothing_about_who_is_limited`). **Met.** |
| **Bypass via method, path, case, slash, HEAD/OPTIONS, content type** | The limiter runs before `BodyGuardMiddleware` and before every guard, so requests with a wrong content type, a failed CSRF check or a failed validation still count. Path and method variants are listed in §1: none reaches a handler without being counted. **No bypass (IPv4).** |
| **Unauthenticated vs invalid cookie** | No cookie, or a cookie that is malformed, unknown or expired: `identify_session` returns `None` and only the route's per-IP rules apply. The request then gets `401` from the handler, so no authenticated work happens without a valid session. A forged cookie cannot borrow or burn another session's counter: the key is the session ID of a *valid* token. **Fine.** Anonymous API traffic in general has no limit (INFO-1). |
| **Read-only session lookup in the middleware** (`sessions.py:86-94`) | `session_resolve` is `STABLE` and only runs a `SELECT` (0005:195-217). It does not touch `last_used_at`, so the limiter cannot extend a session; renewal still happens only in `session_guard`. It returns IDs only, never the CSRF hash. **Met.** |
| **Counter flooding, DoS amplification** | Rows are created only (a) per IP on `POST /auth/google/start`, and (b) per valid session/account, about 3 per minute while a session is active. With IPv4, a flooding client hits one row (an HOT update), so there is no growth. With IPv6 address rotation, each request creates a new `rate_counter` row *and* a new `auth_flow` row (SEC-SL03b-001). Keys are deduplicated before the upsert (no "cannot affect row a second time"), and rows are ordered by key, so there is no deadlock (concurrency test: 60 parallel → exactly 30). Events are written once per rule and window (`first_crossing`), so a flood does not flood `security_event`. Cleanup arrives in SL-10a (INFO-3). |
| **THR-013, SR-070: session cap** (`sessions.py:39-49, 97-105`; `login.py:211-218`) | The eviction runs in the sign-in transaction, after `bind_context(account)`. It is filtered by `account_id = :account_id` *and* by RLS `p_session_self`. The expired-row policies need no context (SEC-SL03a-001), so they do not apply here. It counts only live sessions, keeps the 19 most recently used, then inserts the new one: 20. The per-account `pg_advisory_xact_lock` serialises concurrent logins of the same account. A `hashtextextended` collision between two accounts only makes them wait for each other; it cannot evict across accounts. Only the account's own login can evict its sessions. Tests: the 21st login, the event, other accounts untouched, expired rows not counted, a relogin from the same browser not evicting, 10 extra logins → 20, and the parallel-login race. **Met.** |
| **SR-070: 60 writes/min per account** | `WRITE_ACCOUNT` keyed by account ID, added for every unsafe method that has a valid session (test: writes from two sessions add up). **Met.** The per-family daily limit belongs to SL-05 (plan I-T5). |
| **Logout under the limit** | Logout is a `POST` and counts as a write. After 60 writes in a minute it gets `429` (probe). See SEC-SL03b-002. |
| **Events and logs (no PII)** | `rate_limit.exceeded`: `details_json` is built only from a code constant (`rule.name`), plus the account ID when there is one, the IP and the correlation ID. The IP is truncated in the log line (test). `session.evicted`: account, role, family, the evicted session ID as target, and the IP of the new login. No email, `sub`, token, key or pepper. Same IP handling as the accepted SL-02 security log. **Met.** |
| **Grants on `rate_counter`** (`0006`) | `menu_app` gets `SELECT/INSERT/UPDATE/DELETE`. `menu_backup` gets `SELECT`. `menu_console` gets nothing. No `TRUNCATE`/`ALTER` for `menu_app` (test). No SECURITY DEFINER. No RLS, which is correct: the table is global, and its rows are peppered HMACs, windows and counts with no personal data. Downgrade drops the table. **Met.** |
| **S-08 frontend** (`AltroPage.tsx`) | It shows the display name, role and family name through Lingui `_()`, rendered as React text (auto-escaped). No `innerHTML`, `dangerouslySetInnerHTML` or storage use (grep). It shows no email and no IDs. Logout goes through `requestLogout` → `api.post` with the session CSRF header (same path verified in SL-03a). The double-click guard is client-side only, which is harmless: the server ends the session idempotently. A failure is shown as a generic, translated message. **Met.** |
| **e2e support changes** | `TRUSTED_PROXY_HOPS=1` plus random `198.18.0.0/15` addresses are used only in the test stack (`APP_ENV=test`, loopback). No production surface. **Fine.** |

**Done well:** the one-statement upsert sorts its keys, so concurrent requests take locks in the same order and cannot deadlock. Duplicate keys are collapsed before the statement. Windows and `Retry-After` come from the database clock, so instances cannot disagree and tests can freeze time. The 429 event is written once per window, so the security log cannot be flooded. The middleware's session lookup is read-only, so rate limiting can never extend a session. The eviction relies on both the explicit filter and RLS.

## 3. Findings

### SEC-SL03b-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/ratelimit/middleware.py:93` (`Hit(rule, ip)` with the full address); `backend/src/menu/platform/http/client_ip.py:14-18`
- **Category:** security (CWE-799 improper control of interaction frequency; CWE-770 allocation without limits)
- **Problem:** the per-IP key is the full IP string. An IPv6 client normally controls at least a `/64` (2^64 addresses; any cheap VPS gets one). Every address gets its own counter, so the 30/IP/15 min limit on the login start (AC-001.9, THR-011) is bypassed. The same key will be reused by the per-IP rules of later slices: invitation links and codes (M1), and creation codes (M2).
- **Scenario (verified with the real app):** with `hops=1`, 40 `POST /auth/google/start` requests from `2001:db8:1:2::1` … `::28` all pass the limiter (0 × `429`). The control run, 32 requests from one address, gets 2 × `429`. At scale, each request inserts a new `rate_counter` row *and* a new `auth_flow` row instead of updating one counter. That is unbounded growth on the 500 MB database shared by every family (THR-100) until the SL-10a purge, and the purge only removes what is expired. **Precondition (TO VERIFY by devops with V-3):** IPv6 must reach the service. The default `run.app` front end, a custom domain or a load balancer may each publish AAAA records. If production is IPv4-only, the finding drops to LOW, but the fix is still worth it because the topology can change without a code change.
- **Suggested fix (simple):** derive the *rate-limit* identifier, not the logged IP, by collapsing IPv6 to its `/64`. Keep IPv4 as a single address. IPv4-mapped IPv6 maps back to IPv4.
  ```python
  def limit_subject(ip: str) -> str:
      try:
          addr = ipaddress.ip_address(ip)
      except ValueError:
          return ip  # "unknown"
      if addr.version == 6 and addr.ipv4_mapped is not None:
          return str(addr.ipv4_mapped)
      if addr.version == 6:
          return str(ipaddress.ip_network(f"{addr}/64", strict=False))
      return str(addr)
  ```
  Use it in `_hits` for every per-IP rule. Event and log IPs stay as they are (they are already truncated to /48 in the log).
- **Verification:** `tests/security/test_ratelimit_security.py`: 31 starts from 31 different addresses in the same `/64` → the 31st gets `429`; an address in another `/64` is not limited; `::ffff:198.51.100.7` and `198.51.100.7` share a counter. Unit tests for `limit_subject`.
- **Status:** RESOLVED (re-check 2026-10-23, §6)

### SEC-SL03b-002 · LOW · BACKLOG (before SL-25 "My sessions")
- **Location:** `backend/src/menu/ratelimit/middleware.py:96-98` (every unsafe method counts toward `write_session` and `write_account`)
- **Category:** security (CWE-400; availability of a security control)
- **Problem:** `POST /auth/logout` is limited like a domain write. Once the account has made 60 writes in a minute, from any of its sessions, logout returns `429` for up to 60 s.
- **Scenario (verified):** after 60 probe writes, logout gets `429`, `Retry-After: 30`. Today the impact is small: the user can retry within a minute, and a flood from another session of the same account can only delay the logout of *one's own* session. It becomes a real problem in SL-25 and SL-28. A thief holding a stolen session cookie can keep `write_account` saturated with cheap invalid writes (they still count, because the limiter runs before validation). The victim would then be unable to use "revoke other sessions", the one control meant to evict the thief.
- **Suggested fix:** a small allow-list of "exit" routes that are never denied by the write rules: `POST /auth/logout` now, and session revocation in SL-25. They can still count toward `api_session`, or be skipped entirely; logout is cheap and needs CSRF and a valid session anyway.
- **Verification:** after 60 writes, logout → `204`/`200` and the session no longer resolves. The same test for revocation in SL-25.
- **Status:** RESOLVED (fixed in this slice; re-check 2026-10-23, §6)

### SEC-SL03b-003 · LOW · BACKLOG (before SL-10b, the first deploy)
- **Location:** `backend/src/menu/platform/config.py:70`
- **Category:** security (CWE-1188 insecure default configuration; CWE-770)
- **Problem:** `TRUSTED_PROXY_HOPS` is now mandatory (good), but `0` is accepted in `staging` and `production`. On Cloud Run, `0` makes every client share the address of Google's front end, so each per-IP rule becomes a single global counter.
- **Scenario:** a deploy copied from `.env.example` (`TRUSTED_PROXY_HOPS=0`). Any one client sending 31 `POST /auth/google/start` in 15 minutes blocks the login start for **every** family until the window ends, and can repeat it forever. This fails closed, so there is no bypass, but it is a trivial denial of service on login.
- **Suggested fix:** one line in the existing strict-environment validator: in `staging`/`production`, require `trusted_proxy_hops >= 1`. Devops V-3 then confirms whether the right value is 1 or 2 (2 behind a load balancer).
- **Verification:** unit test: `APP_ENV=production`, `TRUSTED_PROXY_HOPS=0` → startup refused; `1` → accepted.
- **Status:** RESOLVED (fixed in this slice; re-check 2026-10-23, §6)

### SEC-SL03b-004 · LOW · FIX-IN-SLICE (documentation, architect)
- **Location:** `docs/adr/ADR-0006-store-limiti-di-frequenza.md` ("Algoritmo") vs `backend/src/menu/ratelimit/rules.py:1-6` and `store.py:172-180`
- **Category:** design (tracked decisions, protocol §3.5)
- **Problem:** the ACCEPTED ADR specifies a fixed window *with the sliding-window estimate*, which weights the previous window. The code implements a plain fixed window. The decision is fine (see D1 in the report below), but it is an untracked deviation from an accepted ADR.
- **Suggested fix:** ADR-0006 rev. 6: "plain fixed window aligned on `date_bin` in the DB clock; a burst of up to 2× the limit is possible across a boundary; accepted (D1)".
- **Verification:** the ADR text matches `rules.py`.
- **Status:** RESOLVED (ADR-0006 rev. 6; re-check 2026-10-23, §6)

### SEC-SL03b-005 · LOW · BACKLOG (decision record, product-analyst)
- **Location:** `backend/src/menu/ratelimit/rules.py:31-33` (only `POST /auth/google/start` has a per-IP rule); SR-059 rows "Callback OIDC e avvio del login" and "Login fallito … 20 per IP"
- **Category:** security (SR traceability; CWE-799)
- **Problem:** SR-059 lists the OIDC callback and failed logins (20/IP/15 min) in the M0 scope. The slice limits only the start, and the deferral is not recorded anywhere in requirements or an ADR.
- **Scenario / impact (my analysis, see D2):** low. Every callback that does real work (flow claim, Google token exchange, outcome and event rows) needs a flow created by a *limited* start, and each flow can be claimed once. A callback without a live flow does one indexed `UPDATE` that matches nothing, writes nothing (no event: `login.py:143-145`) and returns `302`. In a Google-only MVP a "failed login" *is* a failed callback, so it is bounded by the 30 starts per IP. This holds only once SEC-SL03b-001 is fixed.
- **Suggested fix:** record the decision. Either amend SR-059 (product-analyst) with "Google-only MVP: callback and failed login are bounded by the start limit; the per-IP failed-login limit returns with FR-002", or note it in ADR-0006 rev. 6 together with SEC-SL03b-004. If a separate callback rule is ever wanted, use its own rule name (e.g. `oidc_callback_ip`). Sharing `oidc_start_ip` would halve the logins per IP.
- **Verification:** the document change; no code.
- **Status:** RESOLVED (CHG-021 and ADR-0006 rev. 6; re-check 2026-10-23, §6)

### INFO notes (no action required unless stated)
- **INFO-1 (anonymous API traffic):** anonymous `GET /session`, `GET /auth/google/callback`, unknown `/api/v1/*` paths, and requests carrying a well-formed but invalid session cookie are not counted anywhere. Each costs one or two indexed DB queries and writes nothing. SR-059 does not require a general anonymous limit. The backstop is Cloud Run `max-instances` plus the budget alerts (ADR-0005). No action for M0.
- **INFO-2 (503 body):** the fail-closed response is plain `{"status":"unavailable"}` with no `problem+json` and no `Retry-After`. It leaks nothing. For consistency with the rest of the API, `problem_response(ErrorCode.UNAVAILABLE)` would do, if such a code exists. Optional.
- **INFO-3 (growth before SL-10a):** each active session adds about 3 `rate_counter` rows per minute (about 150 bytes each with indexes). The hourly purge (48 h) and the `auth_flow` purge in SL-10a are **required before the M0 release** (SL-10b), together with SEC-SL03b-001. 05-data v8 already says so.
- **INFO-4 (naming and rotation):** `SESSION_PEPPER` peppers rate-limit keys, not sessions. The name is misleading but harmless. Rotating it only resets the counters (by design), and devops should list it in the rotation plan in `docs/09-release.md` (SL-10b) as "rotate freely, side effect: counters reset". Production must use a value generated per environment (≥ 32 random bytes from a CSPRNG, e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`) in Secret Manager.

## 4. Opinions requested

### D1: fixed window vs ADR-0006's sliding estimate
**Accept the fixed window.** The 2× boundary burst does not change long-run throughput: each window still caps at the limit, so over any hour an account still makes at most 60 writes per minute on average. That is what THR-100 (storage) and THR-013 care about. What the sliding estimate buys is burst smoothing: at worst 60 login starts within 2 s, or 120 writes / 600 requests in about one minute around a boundary. None of these limits protects a secret against guessing. The Google-only login has no password to brute-force, and the codes that will need tight limits (M1 invitations, M2 creation codes) are high-entropy. So the burst gives an attacker nothing. Fixed windows are also simpler to test (frozen DB clock), and `Retry-After` is exact. Record it in ADR-0006 (SEC-SL03b-004). Revisit only if a future rule protects a low-entropy secret, such as a 6-digit OTP; that rule can use a longer window instead.

### D2: OIDC callback and per-IP "failed login" limits deferred
**Acceptable to defer, provided the deferral is recorded (SEC-SL03b-005) and SEC-SL03b-001 is fixed.** The reasoning is in SEC-SL03b-005: all expensive or state-creating callback work is bounded by the limited start, flows are single-use, and a callback without a flow writes nothing. A per-IP callback limit would also hurt UX for little gain: a `429` on a top-level navigation in the middle of the Google redirect shows a raw error page instead of the login outcome. The per-identity progressive delay belongs to the password login (CHG-020) and stays deferred with it.

## 5. Threat model status (06-threat-model)
I updated the status column in `docs/06-threat-model.md`:
- **THR-011:** the start limit is verified. Still open: IPv6 `/64` (SEC-SL03b-001) and the SL-10a purges.
- **THR-012:** the forged-header integration test is verified and `TRUSTED_PROXY_HOPS` is mandatory. Still open: V-3 in staging and `≥ 1` in strict environments (SEC-SL03b-003).
- **THR-013:** verified (AC-047.4, the parallel-login race, and 60 writes per minute per account).
- **THR-103:** unchanged (accepted, fail-closed behaviour tested).

No new THR. No new SR proposed: SEC-SL03b-001 is an implementation detail of SR-059, not a new requirement.

## 6. Re-check (2026-10-23)

Scope per the fix cycle: the five open findings, the fix diff, and a quick scan of the new code for defects the fix may have introduced. Files re-read in full: `platform/http/client_ip.py`, `ratelimit/middleware.py`, `ratelimit/rules.py`, the `platform/config.py` diff, the new regression tests (`security/test_ratelimit_security.py` §SEC-SL03b-001/002, `unit/test_client_ip_limit_subject.py`, `unit/test_ratelimit_config.py` §SEC-SL03b-003), ADR-0006 rev. 6, CHG-021 and the SR-059 row in `02-requirements.md`.

**Tools (fresh output, 2026-10-23):**

| Command | Result |
|---|---|
| `make scan-secrets` | **no leaks found** (history and working tree, ~7.14 MB) |
| `make scan-sast` (custom rule tests + semgrep) | rc=0, 0 findings |
| `uv run bandit -r src -c pyproject.toml` | "No issues identified" |
| `make test-sec` / `test-unit` / `test-int` / `test-conc` | **153 / 901 / 165 / 6 passed** |
| No lockfile change since the first pass | dependency audit not re-run (no new dependencies) |

**Re-probes** (scratch test outside the repo, run with the project's fixtures against the real app and the test PostgreSQL; not committed):

| Probe | Result |
|---|---|
| 40 `POST /auth/google/start` from 40 addresses in `2001:db8:1:2::/64`, alternating compressed and fully expanded upper-case forms, each behind a different forged left-most `X-Forwarded-For` entry (`hops=1`) | **30 × 200, then 10 × 429**; one `rate_counter` row (was 0 × 429 and 40 rows before the fix) |
| Next start from another `/64` (`2001:db8:1:3::1`) | 200 (independent counter) |
| `limit_subject` on edge inputs | `::ffff:203.0.113.9` → `203.0.113.9`; zone ID `fe80::1%eth0` → `fe80::/64` (no exception, so no spurious 503); `unknown` unchanged; IPv4 unchanged |
| Account with two sessions: session A makes 70 writes (60 × 200, 10 × 429); session B then writes | B write → 429 (`write_account` shared, as intended by SR-070) |
| Session B logout right after | **204**; B's cookie then gets `authenticated:false` on `/session` and 401 on an authenticated read. A's logout → 204 |
| `POST /auth/logout/` (trailing slash) | 307 to the canonical path; the exemption is keyed on the exact `(method, path)` and grants nothing else |

**Findings:**

| Finding | Re-check | Status |
|---|---|---|
| SEC-SL03b-001 (IPv6 /64) | `limit_subject` (`client_ip.py:31-41`) collapses IPv6 to its /64 and IPv4-mapped to IPv4; `middleware.py:96` applies it to every per-IP rule; events and logs keep the real address (test `the_event_keeps_the_real_ipv6_address`). Four regression tests plus a unit table. Re-probe above. | **RESOLVED** |
| SEC-SL03b-002 (logout under write limits) | `rules.WRITE_EXEMPT = {("POST", "/api/v1/auth/logout")}`; logout still counts toward `api_session`, which is per session, so another session of the same account (e.g. a thief) cannot saturate it. Logout keeps its CSRF and session checks. Regression test plus re-probe across two sessions. SL-25 must add session revocation to `WRITE_EXEMPT` (noted for the SL-25 review). | **RESOLVED** |
| SEC-SL03b-003 (`hops=0` in strict envs) | `config.py` strict validator refuses `TRUSTED_PROXY_HOPS < 1` in `staging`/`production`; unit tests for both strict envs, and `0` still accepted in `dev`/`test`. `.env.example` keeps `0`, which is right for local runs only and now cannot reach a strict environment. | **RESOLVED** |
| SEC-SL03b-004 (ADR vs code) | ADR-0006 rev. 6 records the plain fixed window aligned on `date_bin` in the DB clock, the 2× boundary burst and the revisit trigger (low-entropy secrets). Matches `rules.py` and `store.py`. | **RESOLVED** |
| SEC-SL03b-005 (SR-059 deferral) | CHG-021 records D1 and D2; SR-059's row notes the deferred "Callback OIDC" and "Login fallito per IP" rows; ADR-0006 rev. 6 gives the rationale and the revisit point (SL-12 or FR-002). | **RESOLVED** |

**Quick scan of the new code:** no new defect. The exemption set is exact-match and only removes the two write rules; the IPv6 reduction cannot raise on any value `client_ip_from` returns; the strict-env check sits in the existing fail-closed validator. Nothing in the fix touches secrets, logs or responses.

**Residual risks accepted by the user on 2026-10-23** (recorded in `docs/06-threat-model.md` §12 and §15.2):
- **R-12 (D1):** fixed window, so up to 2× a limit can pass across a window boundary. Low: no current limit protects a low-entropy secret. Revisit if one ever does.
- **R-13 (D2):** OIDC callback and failed logins have no per-IP limit. Low in a Google-only MVP: callback work needs a flow from the limited start, and a callback without a flow writes nothing. Revisit with SL-12 or FR-002.

**Still open outside this slice (unchanged, not findings of this review):** V-3 in staging (`TRUSTED_PROXY_HOPS` 1 or 2), and the SL-10a purge of `rate_counter` and `auth_flow`, required before the M0 release (INFO-3).

**Threat model updated:** THR-011 (IPv6 closed, purge still open), THR-012 (`≥ 1` enforced, V-3 remains), F-03 and the attack-surface row (only the start is limited), and R-12/R-13 added.

**Final verdict: APPROVED.** No open BLOCKER, FIX-IN-SLICE or BACKLOG finding from this review.
