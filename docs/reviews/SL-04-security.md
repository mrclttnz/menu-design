# SL-04: security review

| Field | Value |
|---|---|
| Slice | SL-04: dish archive (create, edit, read, search); `GET /courses`, `GET/POST /dishes`, `GET/PUT /dishes/{dishId}` |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-23 |
| Diff base | `8add827` (nothing committed: `git diff 8add827` plus the untracked files from `git status`) |
| SRs in scope | SR-008, SR-009, SR-010, SR-024, SR-032, SR-041, SR-060 |
| THRs in scope | THR-020, THR-021, THR-022, THR-023, THR-025, THR-070, THR-071 (also THR-046/THR-100 for storage growth, THR-107 for error reflection) |
| Verdict (first pass) | **APPROVED WITH ONE FIX-IN-SLICE** (1 MEDIUM FIX-IN-SLICE, 1 LOW BACKLOG, 3 INFO). No BLOCKER. |
| Verdict (re-check, 2026-10-23) | **APPROVED.** SEC-SL04-001 is RESOLVED (see §5). SEC-SL04-002 stays OPEN as BACKLOG. No BLOCKER and no FIX-IN-SLICE left open. |

The slice gets the important parts right. Every query is a constant `text()` statement with bound parameters. The family comes only from the membership, which is re-read on every request, and it is enforced twice: by an explicit `family_id` predicate and by RLS. The `access` matrix is deny-by-default, and the routes derive their `x-authz` from that same table. Request bodies are closed (`extra='forbid'`, camelCase only). Link sources are restricted to http/https on the server, in the database and in the client. The `404` for a foreign resource is byte-identical to the `404` for a missing one. I found no IDOR, injection, mass-assignment or XSS path. One fix is needed: every `404` by id and every `403` writes one row to `security_event` with no cap. Any authenticated account can turn that into a storage-exhaustion attack on the shared 500 MB database (SEC-SL04-001).

## 1. What was checked and how

**Files read in full:**
- `menu/access/{__init__,matrix,rules}.py`, `menu/family/access.py`;
- `menu/catalog/{api,dishes,schemas,text,export}.py`;
- `migrations/versions/0007_dish.py`;
- `menu/platform/http/problem.py` (with the diff);
- the diffs of `identity/guards.py` (`session_reader`), `audit/catalog.py`, `app/factory.py`, `family/__init__.py`, `identity/__init__.py` and `pyproject.toml`/`uv.lock`;
- re-checked for the new callers: `family/membership.py`, `tenancy/engine.py` (`family_tx`), `platform/http/if_match.py`, `audit/log.py`, `ratelimit/{rules,middleware}.py`, and `search_norm` in `0001`;
- web: `api/dishes.ts`, `features/dishes/DishPage.tsx` (source rendering), `shared.ts`, the grep of all `features/dishes/*` for `href`, `dangerouslySetInnerHTML`, `innerHTML`, `window.open`, `localStorage` and navigation, and the diffs of `routes.tsx`, `RootLayout.tsx` and `providers.tsx`;
- tests: `support/crossfamily.py`, `architecture/test_unsafe_routes_have_guards.py`, the list of `security/test_dishes_*`, and the XSS and URL-scheme cases in `web/tests/unit/dishes/*` and `e2e/dishes.spec.ts`;
- test-only support: the diffs of `e2e_stack.py` (the `__seed` stub, never in `src/`) and `conftest.py`.

**Tools run (fresh output, 2026-10-23):**

| Command | Result |
|---|---|
| `make scan-secrets` (gitleaks `git` + `dir`, `--redact`) | **no leaks found** (9 commits ~3.27 MB; working tree ~8.60 MB) |
| `make scan-sast` (custom rule tests, then semgrep `p/python p/owasp-top-ten p/typescript p/react .semgrep` on `backend web`) | rule tests passed (23 path cases OK); scan **rc=0, 0 findings** |
| `bandit -q -r` on `catalog/`, `access/`, `family/access.py`, `identity/guards.py`, `problem.py` and `0007_dish.py` | rc=0, no issues |
| `make scan-deps` (pip-audit + osv-scanner on `uv.lock` and `pnpm-lock.yaml`) | rc=0, "No known vulnerabilities found" / "No issues found" (see INFO-3 on the unused ignore) |
| `make scan-web` (`pnpm audit`, high+) | rc=0 |
| `make test-sec` | **236 passed** |
| Probe against the real app and the local test DB (scratch file outside the repo, run with the project's `conftest` fixtures, not committed) | 100 `GET /api/v1/dishes/<random uuid>` as a Member → 100 × `404`, **100 new `access.cross_family` rows**, average row `pg_column_size` **177 bytes**. 20 Member `POST /api/v1/dishes` → **20 new `access.denied` rows**. |

**New dependencies (SS §11 [MUST] check):**

| Package | Registry check | Use | Verdict |
|---|---|---|---|
| `pyyaml` 6.0.3 (dev group) | Exists on PyPI as `PyYAML`, latest 6.0.3, MIT, maintained (yaml org). It was already in the lock as a transitive dependency; the slice only declares it directly. No advisories in pip-audit or OSV. | `tests/support/matrix.py:13`: `yaml.safe_load` on a repository file (`tests/security/authz_matrix.yaml`) | OK. Safe loader, trusted input, dev-only. |
| `types-pyyaml` 6.0.12.20260906 (dev group) | Exists on PyPI as `types-PyYAML` (typeshed, python/typeshed), hash-pinned in `uv.lock`, published 2026-09-06 (outside the 7-day cooldown) | type stubs for mypy | OK. |

## 2. Checks against THRs, SRs and the brief

| Item | Result |
|---|---|
| **THR-020 / SR-008: IDOR on `{dishId}`** (`dishes.py:275-280, 311-325`) | The family comes from `context_for`, which re-reads the person by `account_id` with `status='active'`, never from the client. Each read and write runs in one `family_tx`, with `family_id = :family` in every statement **and** RLS `p_family` (ENABLE + FORCE, `0007:154-166`). A foreign id behaves exactly like a missing id: `MissingReference` → `access.cross_family(ctx, op)` → `404 not_found`. The test helper checks identical body and content type, the attacker's identity in the event, no victim data in `details`/`target_type`, and no state change on the victim. In `update_dish` the existence check comes **before** the version check, so a `412` never reveals a foreign dish. **Met.** |
| **`access.cross_family` content** (`rules.py:12-23`) | `details` = `{"operation": "<op>"}` only. `target_id` and `target_type` are not set; `family_id`, `actor_account_id` and `actor_role` are the attacker's. No victim ids, no IP. **Met.** Volume: see **SEC-SL04-001**. |
| **THR-021 / SR-041: references in the body and query** (`dishes.py:158-161, 247-251`) | `courseIds` (de-duplicated) are checked with `family_id = :family and id = any(:ids)` in the same transaction as the write. Any foreign or unknown id → `404` + event, and the transaction rolls back. The composite FKs `(family_id, course_id)` and `(family_id, created_by/modified_by)` are the DB second line. The `courseId` filter on `GET /dishes` gets the same check. **Met.** |
| **THR-023 / SR-009: matrix, Member read-only** (`matrix.py:15-25`, `family/access.py`) | Deny by default: an unknown operation, `family_id is None` or a role outside the set → `403` + `access.denied`. Member is allowed only the three reads; create and update are A/P. Future operations already have rows. The routes' `x-authz` is generated from the same table (`family_authz`), so declaration and check cannot drift. The permission check runs as a dependency, before body validation (a Member does not learn the validation rules). **Met.** |
| **CSRF and guards on unsafe routes** (`family/access.py:17`) | `writes=True` → `session_guard` (Origin/`Sec-Fetch-Site` + per-session CSRF token); reads → `session_reader`. The new architecture test (`test_unsafe_routes_have_guards.py`) walks every included router and fails on any unsafe route without the guard of its scope, and it is proven to fail on synthetic apps. This closes SEC-SL03a-003. **Met.** Reads without a site check: see **SEC-SL04-002**. |
| **THR-022 / SR-010: mass assignment** (`schemas.py:59-114`) | `Body` uses `extra='forbid'` with a camelCase alias generator and **no** `populate_by_name`, so `family_id`, `created_by`, `courseIds` in snake_case, `version`, `archived` and `everPlanned` are all `422 unknown_field`. `DishUpdate` (PUT) has no `status`. `DishWrite` (POST) allows `status` only for A/P, because Members cannot create in M0. The SQL writes only an explicit column list; `version`, `modified_by` and `modified_at` are server-set. **Met.** |
| **THR-025: SQL** (`dishes.py:39-104`) | All statements are module-level constants with bound parameters. There is no string building and the optional filters use `cast(:x as …) is null or …`. `ORDER BY` is fixed and `LIMIT` is bound. The LIKE pattern is `app.search_norm(:q)` with `\`, `%` and `_` escaped (in that order) and `ESCAPE '\'` (standard_conforming_strings). `q` is ≤ 120 characters, NUL and lone surrogates are refused, and the `%`, `_` and `'` cases are tested (integration + e2e). semgrep and bandit are clean. **Met.** |
| **Cursor tampering** (`dishes.py:127-151`) | An opaque cursor of ≤ 1024 chars, base64url, a JSON object with exactly `{n, i}` (`n` ≤ 1000 chars, no NUL, encodable; `i` a UUID). Every defect → `422 invalid_value`, never `500` (`KeyError`, `TypeError`, `ValueError`/`UnicodeError` and `binascii.Error` are caught). The decoded values are only bound parameters inside the caller's own family's keyset, so a forged cursor can only reposition within one's own data. **Met.** |
| **ETag / If-Match (ADR-0008, THR-107)** | `expected_version` is unchanged (anchored regex, ≤ 18 digits, `428` when missing, `422` otherwise, value never reflected). The version is compared in Python, so there is no int4 overflow. `SELECT … FOR UPDATE` serialises concurrent PUTs (a race test exists). The `412` params hold the caller's own family's dish and person id only. **Met.** |
| **SR-060: quota and limits** (`dishes.py:283-308`) | `pg_advisory_xact_lock(hashtextextended('dish_quota:'||family))` is taken before the count and the insert in the same transaction, so concurrent creates cannot exceed 2,000 (concurrency test). A hash collision between two families would only serialise them, which is harmless. Page `limit` is 1..100, `courseIds` ≤ 50, `sources` ≤ 10, and the field lengths match ASM-034 (DB `varchar`/CHECK as the last line). The global 64 KB body/depth guard applies. **Met.** |
| **THR-070 / SR-024: XSS** | React text rendering only. A grep of the feature finds no `dangerouslySetInnerHTML`, `innerHTML` or `window.open`. Payloads are covered in component tests (archive, detail, form) and in the e2e "i payload si vedono come testo…". CSP and Trusted Types come from SL-01. **Met.** |
| **THR-071 / SR-024: links** (`text.py:188-197`, `api/dishes.ts:132-146`, `DishPage.tsx:119-129`, `0007:120`) | Server: `kind=link` requires an `http`/`https` scheme (urlsplit lowercases it), a non-empty host, no `@` in the netloc, and no whitespace or control characters. DB: `CHECK (kind <> 'link' or reference ~* '^https?://')`. Client: an `href` is rendered **only** for `kind === "link"` **and** `isHttpUrl` (the same rules via `URL`), with `target="_blank" rel="noopener noreferrer"`. Any other kind or value is shown as text. `javascript:`, `JaVaScRiPt:`, leading-space and `data:` cases are tested on both sides. The server never fetches the link (no SSRF). **Met.** |
| **Error body reflection (`problem.py` change, SR-021, THR-107)** | For `extra_forbidden`, the client-chosen key is echoed only if it matches `[A-Za-z][A-Za-z0-9_]{0,39}`; otherwise the parent path is reported. Other Pydantic types map to closed codes, and `ctx.max_length` is a schema constant. The input value is never echoed and `title` is the generic HTTP phrase. **Met.** |
| **SR-032** | The notes field shows `dish.field.notes.hint` ("Non scrivere informazioni sulla salute…"), with an e2e test. **Met.** |
| **Migration 0007: privileges and RLS** | All three tables have RLS ENABLE + FORCE with `p_family` (`using` and `with check`) for `menu_app`, `p_owner`, and `p_backup` SELECT. `menu_app` gets DML, `menu_backup` SELECT and `menu_console` nothing, which matches 05-data §3.2/§6.1. No SECURITY DEFINER. The trigger function has EXECUTE revoked from PUBLIC. The composite FKs make cross-family links impossible even for a buggy writer. The downgrade drops everything. The privilege and schema tests cover this (`test_dish_schema`, `test_console_privileges`). **Met.** |
| **Export (SR-072)** | Explicit column lists. `name_search` (derived) is excluded. Rows are limited by RLS. `export_self` is empty for catalog data, which is correct (family data). **Met.** |

## 3. Findings

### SEC-SL04-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/access/rules.py:38-46` (`cross_family`) and `:26-35` (`authorize`), called from `backend/src/menu/catalog/api.py:98, 116, 134, 156`. The volume follows from `backend/src/menu/ratelimit/rules.py:24` (300 req/min per session) and `identity/sessions.py:22` (20 sessions per account).
- **Category:** security (CWE-779 Logging of Excessive Data; CWE-400 Uncontrolled Resource Consumption)
- **Problem:** every `404` by id writes one `security_event` row in its own transaction (and one structured log line), with no cap. The same is true for every `403` from `authorize`. SL-04 adds the first **read** route whose failure path writes to the database on every call. Reads are limited only to 300 per minute per session, and THR-100/SR-070 bounded write volume but never covered security-log volume.
- **Scenario:** any authenticated account, including a Member or an account with a stolen session, loops `GET /api/v1/dishes/<random uuid>`. Verified with the probe: 100 requests gave 100 rows of about 177 bytes each, before index and page overhead. One session at the 300/min limit → about 432,000 rows a day, roughly **100 MB/day**. With the 20 allowed sessions → about **2 GB/day**. The shared Supabase Free 500 MB fills within hours to a few days, and the service stops for **all** families (THR-046, RDP-09). Cloud Logging gets the same number of lines. A Member POSTing creates adds `access.denied` rows at up to 60/min per account (about 20 MB/day). The SL-10a storage alarm does not exist yet, and the security log cannot be pruned for 12 months (SR-019).
- **Suggested fix (proportionate, reuses what exists):** cap the denial events per account and window with the existing `rate_counter` store, using the same "first crossing" pattern as `rate_limit.exceeded` (`ratelimit/middleware.py:109-125`). For example, a rule `access_denied_log` with a limit of 20 per 3600 s keyed on `account_id`, shared by `access.cross_family` and `access.denied`:
  - while under the limit, write the event as today;
  - on the first crossing, write one event with `details = {"operation": …, "suppressed": true}`;
  - after that, write nothing until the window ends;
  - the response stays `404`/`403` in all cases. If the counter store fails, still answer `404`/`403` and skip the event (never `500`, never allow).

  Twenty per hour keeps the SR-058 alarm (> 10 cross-family denials per account per hour) detectable. A simpler alternative, if the user prefers it, is a per-process in-memory throttle (LRU keyed on account, with the same limit). That is weaker across instances but bounded by `max-instances`.
- **Verification:**
  - a security test: one session sends 50 foreign/missing `GET /dishes/{id}` → all `404`, at most 21 `access.cross_family` rows for that account in the window, the last one with `"suppressed": true`, and the first one still passes `assert_cross_family`;
  - the same test for 50 Member `POST /dishes` and `access.denied`;
  - a test that a failing counter still returns `404`.
- **Status:** RESOLVED (re-check 2026-10-23, see §5)

### SEC-SL04-002 · LOW · BACKLOG
- **Location:** `backend/src/menu/identity/guards.py:78-90` (`session_reader`)
- **Category:** security (CWE-352, a cross-site request that has a side effect, namely the security-log write; CWE-117-like false attribution)
- **Problem:** authenticated `GET`s do not check `Sec-Fetch-Site`. The session cookie is `SameSite=Lax`, so it is sent on a **cross-site top-level navigation**. Because `cross_family` writes an event naming the caller, a third-party page can make a victim's browser produce `access.cross_family` events attributed to the victim.
- **Scenario:** an attacker's page opens `https://<app>/api/v1/dishes/<random uuid>` in a new window 11 times (or chains redirects). Each request carries the victim's cookie, gets a `404`, and logs an event with the victim's account. Once SR-058 (SL-26) is built, this crosses the "> 10 cross-family denials per hour" alarm for an innocent user and misleads the operator. No data leaves: the response goes to the victim's own browser and the CSP/CORS model stays intact.
- **Suggested fix:** in `session_reader`, reject `Sec-Fetch-Site: cross-site` (and `same-site`) on `/api/v1` with `403 csrf_failed`, writing no event; keep `same-origin` and `none` (a typed URL). Alternatively, log `cross_family` only when the request is same-origin. Do this before SL-26 turns the event into an alarm.
- **Verification:** a test where `GET /api/v1/dishes/{uuid}` with `Sec-Fetch-Site: cross-site` and a valid cookie gives `403` and no new `security_event`, and a same-origin request is unchanged.
- **Status:** OPEN

### INFO-1: good choices worth keeping
`x-authz` is generated from the matrix (one source of truth). The existence check comes before the version check, so `412` cannot be used as an existence oracle. `check_storable` turns NUL and lone surrogates into `422` instead of driver `500`s. The defensive link rendering requires both `kind === "link"` and a URL check on the client. The test helper `assert_cross_family` compares the full `404` bodies and checks the victim's state hash.

### INFO-2: future Member rules (SL-17)
`authorize(…, facts)` accepts `facts` but ignores them. When `member_own_to_try` arrives, the facts (owner and status) must be read **inside the same `family_tx` as the write, under `FOR UPDATE`**, not in the dependency. Otherwise a Member could race a status change (TOCTOU). Record this for SL-17.

### INFO-3: osv-scanner reports the ignore `GHSA-vfj7-8cjw-p6xm` as unused
`osv-scanner.toml has unused ignores: GHSA-vfj7-8cjw-p6xm`, while `braces@3.0.3` is still in `web/pnpm-lock.yaml`. OSV may have withdrawn or re-scoped the advisory. This is not caused by SL-04. Check it when you revisit the ADR-0017 exception (due 2026-11-21); if the advisory is withdrawn, remove both exceptions.

## 4. Summary

| ID | Severity | Class | Status |
|---|---|---|---|
| SEC-SL04-001 | MEDIUM | FIX-IN-SLICE | RESOLVED (re-check) |
| SEC-SL04-002 | LOW | BACKLOG | OPEN |
| INFO-1..3 | INFO | – | – |

No BLOCKER. The slice may close once SEC-SL04-001 is fixed, and that fix needs only a targeted re-check. Alternatively, the user may accept SEC-SL04-001 through a risk-acceptance ADR (a MEDIUM may be accepted) with a review date and a compensating control. A suitable control would be the SL-10a storage alarm, delivered before M0.

Threat model touched: the THR-100 row in `docs/06-threat-model.md` now notes the security-log growth path (SEC-SL04-001).

## 5. Re-check of SEC-SL04-001 (2026-10-23)

Scope, following the anti-loop rule: only SEC-SL04-001 and the diff of its fix. That diff is `backend/src/menu/audit/cap.py` (new), `audit/__init__.py` (exports `bump`), `access/rules.py` (`_record_denial`, `configure_denial_cap`, the `DENIAL_LOG_*` constants), `access/__init__.py`, `app/factory.py:81`, and `tests/security/test_access_denial_log_cap.py` (new). Callers re-read: `catalog/api.py:99, 117, 135, 157`, `family/access.py`, `family/membership.py` (`membership_for`), `identity/models.py` (`SessionInfo`), `ratelimit/store.py` and `ratelimit/rules.py` (key format), `tenancy/engine.py` (`system_tx`), and the `rate_counter` cleanup policy (`0006`, 05-data §5).

| Check | Result |
|---|---|
| **The cap bounds rows per account and window** | `bump` makes one atomic upsert on `app.rate_counter (key, window_start)` with `count = c.count + 1 … returning`. Concurrent requests serialise on the row, so each count value is handed out once. Counts 1-20 write the event, count 21 writes one `suppressed: true` event, and counts above 21 write nothing (`rules.py:60-62`). The window is a fixed hour from `date_bin(3600 s, app.now_utc(), 2000-01-01)`. The worker cleanup removes only windows older than 48 h, so a live 1 h window cannot be reset mid-window. **Bound: 21 `security_event` rows (and 21 structured log lines) per account per clock hour, at most 42 in a burst that straddles a boundary.** That is about 504 rows a day, roughly 90 KB a day per account, against the ~2 GB a day measured before the fix. The cap is per account, not per session, so the 20 sessions add nothing. `access.denied` and `access.cross_family` share one bucket, so the bound covers both event types together. Test: 100 random-id reads → all `404`, exactly 21 rows, the last one `{"operation":"catalog.dish.read","suppressed":true}`; 50 Member creates → all `403`, exactly 21 `access.denied` rows. **Met.** |
| **No raw ids in the counter key** | The key is `HMAC-SHA-256(session_pepper, "access_denied_log\0<account uuid>")`, 32 bytes (`cap.py:26`; the `ck_rate_counter_key` CHECK enforces 32 bytes). This is the same construction as `ratelimit/store.py:61`, and the rule name keeps the domains apart: no current `Rule` is called `access_denied_log`. Nothing else is stored in `rate_counter`. **Met.** |
| **Fail-safe on the log path** | `_record_denial` wraps `bump` and `security_log` in `try/except Exception`, and on failure logs only `access.denial_unrecorded` with the exception type: no message, no ids. The decision is outside that block. `authorize` always `raise AppError(FORBIDDEN)` after `_record_denial`, and `cross_family` always returns `AppError(NOT_FOUND)`. **No path turns a counter or log failure into an allow or a `500`.** Every call site runs after `family_tx` has exited (the exception has already left the `with`), so the separate `system_tx` connection does not nest inside a held family transaction. Test: with `bump` monkeypatched to raise → `404 not_found`, and no event. Losing events during a DB outage is acceptable: the request would fail anyway. **Met.** |
| **Can the anonymous shared bucket be abused to silence a victim's events?** | **No.** The bucket identifier is the literal `"anonymous"` only when `ctx.account_id is None`, and that key can never equal an account's key (a UUID string). So anonymous traffic cannot use up any account's budget. It is also unreachable today: `authorize` is called only from `family_access`, behind `session_guard`/`session_reader`; `cross_family` is called only from catalog routes that depend on it; and `SessionInfo.account_id` is a non-optional `UUID`. Test `test_the_cap_is_per_account_one_flooder_does_not_silence_another`: one account floods `CAP+5`, and another account's event is still written. **Met.** (Forward note below.) |
| **The SR-058 threshold (> 10 per account per hour) stays detectable** | The limit is 20 > 10, so the first 11 denials in any hour are always written, and once the limit is crossed the `suppressed` marker shows that more followed. Test `test_the_sr_058_threshold_stays_detectable`: 12 denials → 12 rows. **Met**, with the SL-26 note below. |
| **Layering** | `cap.py` (audit, layer 3) imports only `menu.tenancy` (`system_tx`), and `access` (layer 4) imports `bump` from `menu.audit`. The architecture suite (layer table, cycles, sessions only in tenancy) passes: 85 tests. `configure_denial_cap` is called once in `create_app` with the required `session_pepper` (`Settings` refuses weak peppers), so the cap is always on in the real app. `None` (no cap) is reachable only by not calling it. **Met.** |

**Tools (fresh output, 2026-10-23):**

| Command | Result |
|---|---|
| `make test-sec` | **241 passed** (236 + the 5 new cap tests) |
| `pytest tests/architecture` | **85 passed** |
| `bandit -q` on `audit/cap.py`, `audit/__init__.py`, `access/rules.py`, `access/__init__.py`, `app/factory.py` | rc=0, no issues (on the test file, only B101 `assert` in pytest tests, which is expected) |
| `semgrep --config p/python --config p/owasp-top-ten --config .semgrep` on the 5 changed `src` files | 0 findings, 0 errors, 5 files scanned |
| `gitleaks dir --redact` on each changed file | no leaks found |

No new dependencies.

**Notes for later (not findings: neither is a BLOCKER introduced by the fix, so the anti-loop rule applies):**
- **For SL-26 (SR-058 alarm):** `access.denied` and `access.cross_family` share one bucket. A Member can spend the 21 slots with forbidden `POST /dishes` and then probe foreign ids without producing any `access.cross_family` row in that hour, so an alarm that counts only `access.cross_family` rows would not fire. The real-world impact today is low: UUID v4 ids cannot be enumerated, RLS plus the explicit predicate hold, and the burst stays visible as `access.denied` plus a `suppressed` marker. When building SL-26, either count **any** `suppressed: true` denial event as crossing the threshold (no code change here), or give each event type its own bucket (`f"{DENIAL_LOG_NAME}:{event_type}"`, which doubles the bound to 42 per hour per account, still negligible). The first option is the simpler one.
- **Forward note for any future anonymous caller** of `authorize`/`cross_family` (for example invitation links): the shared `"anonymous"` bucket would let one anonymous flooder suppress every other anonymous caller's denial events for the hour. Key anonymous callers on the client IP (HMAC, as `oidc_start_ip` already does) before such a route ships.

**Final verdict for SL-04 security: APPROVED.** SEC-SL04-001 is RESOLVED. SEC-SL04-002 (LOW, BACKLOG) remains OPEN and should be recorded in `docs/STATUS.md` and fixed before SL-26 turns `access.cross_family` into an alarm. No BLOCKER is open.
