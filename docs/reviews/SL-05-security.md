# SL-05: security review

| Field | Value |
|---|---|
| Slice | SL-05: change events and dish status; migration `0008` (`change_event`), `POST /dishes/{dishId}/status`, codec v1, `tracked_family` cap |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-24 |
| Diff base | `374f08f` (nothing committed: `git diff 374f08f` plus the untracked files from `git status`; root `package.json`, `pnpm-lock.yaml` and `node_modules` ignored as unrelated) |
| SRs in scope | SR-022, SR-047, SR-057, SR-070 |
| THRs in scope | THR-013 (account), THR-046, THR-100, THR-117 |
| User decisions taken as given | payload limit 20,480 bytes; `after` NOT NULL; a same-status request bumps the version and writes an event; status change on an archived dish is allowed |
| Verdict (first pass) | **CHANGES REQUESTED: 0 BLOCKER, 2 FIX-IN-SLICE** (1 MEDIUM, 1 LOW contextual), 1 LOW BACKLOG, 5 INFO |
| Verdict (re-check cycle 1, 2026-10-24) | **APPROVED, CONDITIONAL ON THE FILELOCK BUMP.** SEC-SL05-001 RESOLVED. SEC-SL05-002: happy-dom part RESOLVED, filelock part OPEN until the bump to 4.2.1 (blocked by the cooldown until 2026-10-24 16:48 UTC, user decision to wait). SEC-SL05-003 OPEN as BACKLOG (SL-09). No BLOCKER; no new finding from the fix diff. See §5. |

The core of the slice is sound. The status route takes the family only from the session. It locks the row with an explicit `family_id` predicate and RLS on top, answers `404` before `412`, and consumes the cap only after every precondition. The cap, the update and the event all sit in one transaction, so `403`, `404`, `412`, `422` and any failure leave no event and no counter increment. `change_event` is properly append-only. `menu_app` has only `SELECT`/`INSERT` and split `FOR SELECT`/`FOR INSERT` policies. The immutability trigger also stops the owner. There is no `SECURITY DEFINER` function, and the `coalesce` fix closes the NULL hole in the size check. Events and logs carry only IDs and codes, and a canary test proves it. The cap itself is an atomic upsert under an HMAC key, and it holds under a race.

One real defect needs a fix. When a family is at its cap, the `429` path takes a **second** pooled connection while it still holds the first one and the lock on the family counter row. A burst of concurrent writes from the capped family then exhausts the pool. That family gets `500` instead of `429`, and so do the requests of **other families** served by the same instance (SEC-SL05-001, reproduced). Separately, the dependency scan currently fails on two advisories published yesterday in dev-only packages (SEC-SL05-002). SL-05 did not introduce them, but the slice cannot close with a red scan.

## 1. What was checked and how

**Files read in full:**
- new: `migrations/versions/0008_change_event.py`, `menu/history/{__init__,codec,record,export}.py`, `menu/ratelimit/tracked.py`;
- changed: `menu/catalog/{api,dishes,schemas}.py`, `menu/access/matrix.py`, `menu/app/factory.py`, `menu/platform/http/problem.py`, `menu/ratelimit/__init__.py`, `docs/05-data.md` (v10);
- re-checked for the new callers: `menu/tenancy/engine.py` (`family_tx`, `system_tx`, pool settings), `menu/ratelimit/store.py` (`counter_key`), `menu/audit/cap.py`, `menu/family/access.py` (`session_guard` on writes), `menu/platform/http/if_match.py`, `app.family_today()` in `0002`;
- tests: `security/test_tracked_family_limit.py`, `security/test_change_event_security.py`, `concurrency/test_dish_status_races.py`, the test list of `integration/test_dish_status*.py` and `db/test_change_event_schema.py`, and `support/tracks.py`.

**Tools run (fresh output, 2026-10-24):**

| Command | Result |
|---|---|
| `make scan-secrets` (gitleaks `git` + `dir`, `--redact`) | **no leaks found** (11 commits ~3.72 MB; working tree ~9.40 MB, untracked files included) |
| `make scan-rules` + `make scan-sast` (semgrep `p/python p/owasp-top-ten p/typescript p/react .semgrep` on `backend web`) | rule tests passed (23 path cases OK); scan **exit 0** |
| `semgrep --no-git-ignore` (same rule sets + `.semgrep`) on the **untracked** SL-05 files and `catalog/` | 161 rules, 22 targets, **0 findings** (see INFO-4: the default scan skips untracked files) |
| `bandit -q -r` on `history/`, `ratelimit/tracked.py`, `catalog/`, `0008`, `problem.py` | no issues |
| `make scan-deps`: pip-audit | **FAIL**: 6 known vulnerabilities in `filelock 4.1.1` (fix 4.2.1) → SEC-SL05-002 |
| `osv-scanner` on `uv.lock` + `pnpm-lock.yaml` | **FAIL**: 7 vulnerabilities: `filelock 4.1.1` ×6 (max CVSS 7.1, GHSA-v4x8-3wr5-3wq8), `happy-dom 21.0.1` ×1 (CVSS 8.8, GHSA-834v-8h66-3h79) → SEC-SL05-002; unused ignore GHSA-vfj7-8cjw-p6xm (known, SL-04 INFO) |
| `make scan-web` (`pnpm audit`, high+) | exit 0 (the npm registry does not list the happy-dom advisory yet) |
| SL-05 tests against the local PostgreSQL 17 (`test_tracked_family_limit`, `test_change_event_security`, `test_dish_status`, `test_dish_status_edges`, `test_dish_status_races`, `test_change_event_schema`, `test_history_export`; `-n 4`) | **175 passed** |
| Probe against the real app and local DB (scratch test outside the repo, run with the project `conftest` fixtures, not committed): family Alfa **at** the cap, 24 concurrent `POST /status` from Alfa + 4 concurrent `GET /dishes` from family Beta | Alfa: **17 × 500**, 7 × 429, all ~3.6-4.0 s. Beta: **3 × 500**, 1 × 200 after 3.7 s. Logged cause: `TimeoutError` at pool checkout, in `set_status`, `membership_for`, `resolve_session` and **Beta's `list_dishes`** |
| Control probe, same shape, Alfa at 100/5,000 (below the cap) | Alfa: 24 × 200 (1.5-2.2 s); Beta: 4 × 200. No pool timeouts |

## 2. Findings

### SEC-SL05-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/ratelimit/tracked.py:73` (`_alarm_once` called inside `consume_tracked_write`) and `:81` (`system_tx()`); caller `backend/src/menu/catalog/dishes.py:381-387` (`consume_tracked_write` inside `family_tx`)
- **Category:** security (CWE-833 Deadlock; CWE-400 Uncontrolled Resource Consumption)
- **Problem:** when the cap is reached, the request already holds a pooled connection. In that transaction it also holds the dish row lock and the family counter row lock. PostgreSQL locks the conflicting row of `ON CONFLICT DO UPDATE` even when the `WHERE count < :limit` is false. The request then opens `system_tx()`, which needs a **second** connection from the same pool (`pool_size=5`, `max_overflow=5`, `pool_timeout=3 s`). This happens on every denied request, not only the first: `_ALARM_BUMP` runs every time. Meanwhile every other tracked write of the family holds its own connection while it waits on that counter row lock. Once 10 or more such requests are in flight, the pool is full of waiters, and the lock holder cannot get its second connection until the 3 s pool timeout. Every other request on the instance also queues for the pool and fails with `500`, whatever its family.
- **Scenario:** a malicious or compromised Planner or Admin (the THR-100 actor) pushes the family to 5,000 tracked writes. At 60 writes/min per account that takes about 84 minutes. Then they send bursts of about 20 concurrent `POST /dishes/{id}/status`, which stays within 60 writes/min. Measured: each burst produces about 4 s of pool exhaustion, the attacker's family gets `500` instead of the `429` that AC-049.5 promises, and 3 of 4 concurrent reads of **another family** fail with `500`. The burst can repeat every minute for the rest of the local day, and more accounts in the family mean more bursts. The cap is meant to protect the other families (THR-046, THR-100). Here it gives one of them a lever on their availability. MEDIUM rather than HIGH: it needs an authenticated insider, the outage lasts seconds per burst and recovers on its own, and the same insider has already triggered the `rate_limit.exceeded` alarm.
- **Suggested fix:** never acquire a second connection while inside `family_tx`. Raise a dedicated exception from `consume_tracked_write`, for example `TrackedCapReached(retry_after, window_start)`, a subclass of or wrapper around `AppError(RATE_LIMITED)`. Record the alarm only **after** the family transaction has rolled back and released its connection. For example, catch it in `set_status` outside the `with tenancy.family_tx(...)` block (as `api.py` already does for `MissingReference` → `access.cross_family`), call `_alarm_once`, then re-raise the `429`. Better still, put this in a small helper that every future tracked-write service reuses. Optional: bump the alarm counter only when it is still 0. This is not needed for the fix.
- **Verification:** a concurrency test with the family at `DAILY_LIMIT` and **more concurrent tracked writes than the pool size** (for example 24): every response is `429` with `Retry-After` (no `500`); a concurrent read from another family returns `200`; exactly one `rate_limit.exceeded` event exists. Keep the existing `test_the_daily_cap_is_atomic_under_a_race` and `test_the_429_is_logged_once...` green.
- **Status:** RESOLVED (re-check cycle 1, 2026-10-24; see §5)

### SEC-SL05-002 · LOW (contextual; upstream HIGH) · FIX-IN-SLICE
- **Location:** `backend/uv.lock` (`filelock 4.1.1`, dev only: `pip-audit[filecache]` → `cachecontrol[filecache]`), `web/package.json:40` / `web/pnpm-lock.yaml` (`happy-dom 21.0.1`, dev only: unit-test DOM)
- **Category:** security (CWE-1395 Dependency on Vulnerable Third-Party Component)
- **Problem:** `make scan-deps` fails. pip-audit reports 6 vulnerabilities in `filelock`, and osv-scanner reports the same 6 plus GHSA-834v-8h66-3h79 in `happy-dom` ("incomplete fix for CVE-2026-33943: unsanitized import alias leads to host code execution", CVSS 8.8). All were published on 2026-10-23. SL-05 did not change either lockfile, but under the protocol's DoD the slice cannot close with a red dependency scan.
- **Scenario:** in this project the impact is low. happy-dom runs only the project's own test code, never untrusted HTML or JS. The filelock issues need a local attacker who can plant symlinks next to the pip-audit cache on the developer machine or CI runner. Neither package ships in the production image.
- **Suggested fix:**
  - `filelock`: `cd backend && uv lock --upgrade-package filelock`. Version 4.2.1 was published on 2026-10-17 16:48 UTC, so it passes the 7-day cooldown on 2026-10-24 16:48 UTC. *(Corrected at the re-check: the first pass said "already passes", which was wrong by about 14 hours.)*
  - `happy-dom`: 21.0.4 was published on 2026-10-20 and passes the cooldown on **2026-10-27**. Options: (a) wait and bump on 2026-10-27, with a dated osv-scanner ignore of this single GHSA until then (same pattern as ADR-0017); (b) a dated cooldown exception for happy-dom now (same pattern as certifi). Recommendation: (a) if the slice can wait three days for the commit, otherwise (b). Both are a user decision.
- **Verification:** `make scan-deps` exit 0; `osv-scanner scan source --lockfile backend/uv.lock --config osv-scanner.toml --lockfile web/pnpm-lock.yaml` with no findings (or only the dated, documented ignore).
- **Status:** OPEN, partially resolved: happy-dom RESOLVED; filelock OPEN until the bump to 4.2.1 after 2026-10-24 16:48 UTC (user decision: wait, no exception). See §5.

### SEC-SL05-003 · LOW · BACKLOG (SL-09)
- **Location:** `backend/src/menu/ratelimit/tracked.py:32-39` (`_CONSUME`: `window_start = cast(app.family_today() as timestamp) at time zone f.timezone`); asserted as intended by `tests/security/test_tracked_family_limit.py::test_changing_the_family_timezone_moves_the_window_for_the_next_request`
- **Category:** security (CWE-770 Allocation of Resources Without Limits or Throttling)
- **Problem:** the counter row is keyed on the **instant** of local midnight, so changing the family timezone to one with a different UTC offset opens a fresh window of 5,000.
- **Scenario:** once SL-09 ships the timezone setting, an Admin who wants to fill the database can cycle through timezones with different offsets (Europe/London, Europe/Rome, Europe/Athens, …), and each one opens a new 5,000-write window on the same day. The family cap then gives no protection beyond the per-account 60/min (up to 86,400/day per account). Nothing to fix in SL-05: the timezone cannot change yet.
- **Suggested fix (SL-09):** key the window on the local **date** (for example `cast(app.family_today() as timestamp)` stored as is, or a date-derived `window_start`). A timezone change on the same local date then keeps the same row, and switching across the date line yields at most one extra window. Update the test above to assert this. Keep `Retry-After` computed from the real local midnight.
- **Verification:** an SL-09 test: at the cap, switching the timezone to another one on the same local date still gives `429`.
- **Status:** OPEN (BACKLOG, SL-09)

## 3. INFO (no action required in SL-05)

- **INFO-1 · Storage arithmetic with the 20,480-byte limit (THR-046, THR-100).** In the worst case, 5,000 tracked writes/day × about 17.6-20 KB (a valid `meal_content` event, uncompressed) is about 85-100 MB per family per day, against 500 MB shared by everyone. Status events are tiny (fixed `{"st"}` payload), so SL-05 is not affected. The case becomes reachable with the `meal_content` writes of SL-06b and SL-07. Proportionate response: no new mechanism now. The NFR-017 alarm at 70% and the per-family daily space metric (`maint_db_size`, SL-10a) must exist before the M0 release, and the residual risk is now recorded in THR-046 and THR-100 (threat model updated). If SL-06b measures realistic worst-case rows after TOAST, record the figure there.
- **INFO-2 · Lock order for future tracked writes.** `consume_tracked_write` takes the family counter row lock and holds it to commit, which serializes every tracked write of a family (fine at 5,000/day). Every future service must call it **after** taking its own row locks, as `set_status` does, and must never lock domain rows after it. Otherwise two writes can deadlock: PostgreSQL detects this, but the user gets a `500`. The docstring says "after the preconditions"; also state the lock order there.
- **INFO-3 · Pepper reuse.** The tracked counter key uses `SESSION_PEPPER`, like the denial cap and the rate limits, with domain separation by rule name (`tracked_family`, `tracked_family_alarm`). That is acceptable. Rotating the pepper resets the daily family counters, which is harmless but belongs in the rotation note of CR-SL03b-007 (rename before SL-10b). If the pepper is missing, the route fails closed with `500` (`RuntimeError`).
- **INFO-4 · semgrep and untracked files.** The default `semgrep scan` only scans files tracked by git, and all the new SL-05 modules are still untracked, so `make scan-sast` did not see them. I scanned them with `--no-git-ignore` (0 findings). CI scans committed files, so nothing to change. Just do not read a local `make scan-sast` before the commit as covering new files.
- **INFO-5 · Exports and free text.** `HistoryExport._FAMILY` relies only on RLS, with no explicit `family_id` predicate, the same as the `catalog` contributor. The SL-23a export job must therefore run as `menu_app` inside `family_tx`, never as `menu_backup` or the owner. Also, `meal_content.t` and `meal_guests.gn` are user-typed free text and can contain names typed by family members. That is allowed by design (05-data §4.2: "testi liberi del pasto"), but the SL-27/SL-30 erasure work should not count on `change_event` being name-free beyond the profile identifiers.

## 4. Threats and requirements

| ID | Status after SL-05 | Evidence |
|---|---|---|
| THR-117 (repudiation/alteration of history) | **Mitigated and verified.** Event in the same transaction (`record_change` inside `family_tx`), author and role from the session context, trigger also for `menu_owner`, no `UPDATE`/`DELETE`/`TRUNCATE` for `menu_app`, no route that writes history, `tracks` inventory with a closed list of untracked writes | `test_change_event_schema.py` (privileges, trigger, RLS split), `test_change_event_security.py` (AC-049.3 contract and HTTP, `tracks` inventory with a negative control), `test_ac_049_4_...` |
| THR-100 / THR-046 (storage exhaustion) | **Family cap implemented and verified** (5,000/day, local day, atomic, `429` + `Retry-After`, a single alarm event). Open: SEC-SL05-001 (availability on the `429` path), SEC-SL05-003 (timezone hop, SL-09), INFO-1 (payload × cap arithmetic) | `test_tracked_family_limit.py`, `test_the_daily_cap_is_atomic_under_a_race`; probe in §1 |
| THR-013 (account) | Unchanged: per-account limit from SL-03b applies to the new write route (`family_access(..., writes=True)` → `session_guard`) | `authz_matrix.yaml`, architecture guard test |
| SR-022 | Immutability and family-only reads in place (visible history is M1) | as for THR-117 |
| SR-047 | Only IDs and closed codes in `change_event`. No name, email or dish content in the events, the security log or the logs | `test_no_column_can_hold_a_name_or_an_email`, `test_ac_049_2_...`, `test_status_changes_never_log_event_content_names_or_emails` |
| SR-057 | Append-only extended to `change_event` (`menu_app` `SELECT`/`INSERT` only) | `test_privileges_on_change_event`, `test_menu_app_cannot_update_or_delete_an_event` |
| SR-070 | Family part done (5,000/day). The per-account part is from SL-03b | as for THR-100 |

Other checks with no finding:
- **IDOR/cross-family:** `_LOCK_FOR_STATUS` filters by `family_id` from the session, with RLS on top. A foreign dish returns `404` even with a wrong `If-Match` (never `412`, so nothing about its version leaks), and writes `access.cross_family`, raised outside the transaction. A foreign family header is ignored.
- **CSRF:** the route uses `session_guard`.
- **If-Match:** missing → `428`, malformed → `422` without reflecting the value.
- **Body:** a closed `StatusChange` with a `Literal` status and the DB `CHECK` on top. A non-object body or extra fields → `422`.
- **Grants and functions:** `revoke all` from `menu_app`, `menu_console` and `menu_backup` before the explicit grants. The trigger function is `SECURITY INVOKER`, references no objects (so `search_path` is not a concern), and its `EXECUTE` is revoked from `PUBLIC`.
- **`Retry-After`:** set only for `RATE_LIMITED` with an integer value, computed with the DB clock, at least 1 s, and never past the local midnight (tested). The body `params.retryAfterSeconds` matches the header.
- **Logging:** `_alarm_once` logs only the exception type. The security event carries IDs and the rule name. `before` and `after` are never logged (canary test).

What is done well: the precondition order (404 → 412 → cap → write → event) in one transaction means a refused or failed request never consumes the cap and never leaves an event. Splitting the policies into `FOR SELECT` and `FOR INSERT`, instead of a `FOR ALL` policy, makes append-only hold even if a grant is added by mistake later.

## 5. Re-check (cycle 1, 2026-10-24)

Scope: only SEC-SL05-001, SEC-SL05-002 and the diff of the fix (`ratelimit/tracked.py`, `catalog/dishes.py:set_status`, the new regression test, `web/package.json`, `web/pnpm-lock.yaml`, `web/pnpm-workspace.yaml`, `web/tests/unit/supply-chain.test.ts`). As the coordinator asked, I also checked the new web status command (`web/src/features/dishes/StatusCommand.tsx`, `web/src/api/dishes.ts`, the `DishPage.tsx` diff).

| Command | Result |
|---|---|
| Same scratch probe as §1 (family at the cap, 24 concurrent `POST /status` + 4 concurrent `GET /dishes` of another family) | Alfa: **24 × 429** in 0.34-0.54 s (before the fix: 17 × 500 at about 4 s). Beta: **4 × 200** in about 0.23 s (before: 3 × 500). Exactly 1 `rate_limit.exceeded`. No pool `TimeoutError` |
| SL-05 backend tests (`test_dish_status_races`, `test_tracked_family_limit`, `test_change_event_security`, `test_dish_status`, `test_change_event_schema`; `-n 4`) | **172 passed** |
| `vitest run tests/unit/dishes/s06-status.test.tsx tests/unit/supply-chain.test.ts` | **20 passed** |
| `make scan-deps`: pip-audit | FAIL: 6 known vulnerabilities in `filelock 4.2.0` (fix 4.2.1). Expected: the user decided to wait for the cooldown |
| `osv-scanner` on both lockfiles | 6 vulnerabilities, **all `filelock 4.2.0`**. happy-dom is no longer reported |
| `make scan-web` (`pnpm audit`, high+) | exit 0 |
| semgrep (`p/python p/owasp-top-ten p/typescript p/react .semgrep`, `--no-git-ignore`) on `ratelimit/`, `catalog/`, `history/`, `web/src/features/dishes`, `web/src/api/dishes.ts` | exit 0, no findings |
| `make scan-secrets` | no leaks found (git history and working tree) |
| npm registry check of `happy-dom@21.0.4` | the lockfile `integrity` matches the registry's `dist.integrity`; same publisher as 21.0.1 (`GitHub Actions`) |

**SEC-SL05-001: RESOLVED.**
- `consume_tracked_write` now only raises `TrackedCapExceeded(window_start, retry_after)` inside the transaction.
- `set_status` uses `with ratelimit.tracked_write(ctx), tenancy.family_tx(ctx) as tx:`. Context managers exit in reverse order, so the family transaction rolls back and returns its connection, releasing the dish and counter row locks, **before** `tracked_write` opens `system_tx()` for the alarm and turns the signal into `429` with `retryAfterSeconds`.
- If a future tracked write forgets the wrapper, `TrackedCapExceeded` (not an `AppError`) surfaces as a generic `500`: it fails closed and leaks nothing.
- `set_status` is the only caller today. The regression test `test_more_writes_than_pool_connections_at_the_cap_all_get_429_and_other_families_are_served` (16 writes, more than the pool of 10, plus a read from another family) covers the scenario, and my 24-request probe confirms it.
- The rest of the cap behaviour is unchanged and still green: 5,000th write passes and 5,001st gets `429`, a single alarm, no consumption on `403`/`412`.

**SEC-SL05-002: happy-dom RESOLVED, filelock OPEN.**
- happy-dom is at 21.0.4. The cooldown exception is narrow: one exact version in `minimumReleaseAgeExclude`, a comment with the GHSA, the reason and the removal date. `supply-chain.test.ts` allows only that entry and fails from 2026-10-31.
  - Minor inconsistency: the comment says "remove by 2026-10-30" while the test expires on 2026-10-31. Harmless; align when the exception is removed.
- filelock moved from 4.1.1 to 4.2.0, which is still affected (all 6 advisories, fixed in 4.2.1). 4.2.1 clears the 7-day cooldown on 2026-10-24 16:48 UTC, and the user chose to wait rather than add an exception. Contextual severity stays LOW: dev-only (pip-audit cache), never in the image. **Closing condition:** `cd backend && uv lock --upgrade-package filelock` after that time, then `make scan-deps` exit 0. Only this targeted check is needed, not a new review.

**Web status command (no new finding):**
- **XSS:** the dish name reaches the toast through Lingui interpolation and is rendered as a React text node (`<span>{item.message}</span>` in `components/Toast.tsx`). Error text comes from `resolveProblem`, which maps only known `code` values to catalog keys and accepts only parameters that pass a type check (`retryAfterSeconds` must be a count). Anything else becomes the generic message, so no server text is reflected. No `innerHTML` or `dangerouslySetInnerHTML` anywhere in `web/src`.
- **CSRF:** `api.post` adds the CSRF header for every non-GET request (from the session hook or the `__Host-csrf` cookie), with `credentials: "same-origin"`.
- **If-Match:**
  - The version is sent through `ifMatchHeader`, which validates it as an integer and quotes it. The tests assert `"4"`, `"7"` and `"5"`.
  - "Annulla" (undo) uses the latest version, not the stale one.
  - `412` re-reads the card, `403` reloads the session, and `404` shows "not found".
- **429:** the button is disabled for `retryAfterSeconds`, capped client-side at 3,600 s. A server value of up to about 24 h therefore only means the user can retry earlier and get another `429`. That is harmless and a reasonable UX choice.
- **Visibility:** the command is shown only to A/P (`canWrite`). The server stays authoritative (AC-005.4, tested).
