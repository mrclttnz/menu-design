# Code review · SL-05

- **Date:** 2026-10-24 (cycle 1 review; re-check of fix cycle 1 on the same day)
- **Reviewer:** code-reviewer
- **Scope:** `git diff 374f08f` (uncommitted) plus untracked files: migration `0008_change_event.py`; `history` (`__init__.py`, `codec.py`, `record.py`, `export.py`); `ratelimit` (`tracked.py`, `__init__.py`); `access/matrix.py`; `app/factory.py`; `catalog` (`api.py`, `dishes.py`, `schemas.py`); `platform/http/problem.py`; `openapi.json`; `web/src/api/schema.gen.ts`; every new and modified backend test, `tests/fixtures/codec_v1/*`; docs `05-data.md`, `08-test-strategy.md`, `STATUS.md`. Read alongside: `family/access.py`, `platform/http/if_match.py`, `tenancy/engine.py`, `ratelimit/store.py`, `ratelimit/rules.py`, `ratelimit/middleware.py`, `audit/cap.py`, `catalog/export.py`, `web/src/features/dishes/{DishPage,DishFormPage,formModel}`. **Re-check:** `ratelimit/tracked.py` (`TrackedCapExceeded`, `tracked_write`), `catalog/dishes.py::set_status`, `catalog/api.py`, `access/matrix.py`, `history/record.py`, `tests/concurrency/test_dish_status_races.py`, `tests/db/test_history_export.py`, `tests/integration/test_dish_status.py` (`test_dish_status_edges.py` deleted), `docs/05-data.md` §4.2 and the v10 notes, `web/src/features/dishes/StatusCommand.tsx`, `DishPage.tsx`, `web/src/api/dishes.ts`, `web/tests/unit/dishes/s06-status.test.tsx`, `web/tests/e2e/dishes.spec.ts`. Root `package.json`, `pnpm-lock.yaml` and `node_modules` are out of scope (unrelated).
- **User decisions applied (not reopened):** payload cap 20,480 bytes; `after NOT NULL`; a same-status request bumps the version and writes an event; changing the status of an archived dish is allowed.
- **Verdict:** APPROVED (re-check, cycle 2; cycle 1 was REJECTED with 1 BLOCKER, CR-SL05-001). No BLOCKER or FIX-IN-SLICE finding is open. CR-SL05-004 stays in BACKLOG and CR-SL05-008 is INFO.
- **Cycle:** 2

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL05-001 | HIGH | BLOCKER | `web/src/features/dishes/DishPage.tsx:86`, `DishFormPage.tsx:269-286` | No UI path to change a dish's status after creation: US-005 cannot be performed by the user, and no other slice owns the S-06 command | RESOLVED (cycle 2) |
| CR-SL05-002 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/ratelimit/tracked.py:66-73,77-81` | On the 429 path the alarm opens a second pooled connection while still holding the dish row lock and the family counter row lock: can starve the 10-connection pool | RESOLVED (cycle 2) |
| CR-SL05-003 | LOW | FIX-IN-SLICE | `docs/05-data.md:855-856`, `backend/src/menu/history/codec.py` | 05-data says the v1 keys live in `history/event_format.py` and are validated by a Pydantic model per `unit_type`; the code has a hand-written validator in `history/codec.py`. The v1 format is permanent, so the doc must match before the data-architect review | RESOLVED (cycle 2) |
| CR-SL05-004 | LOW | BACKLOG | `backend/migrations/versions/0008_change_event.py:91-107`, `backend/src/menu/history/record.py:41-72` | `ck_change_event_meal_slot` passes with `meal_type NULL` and a non-null slot; the key CK and `record_change` accept key columns that don't belong to the unit type | OPEN (backlog; planned for the first migration after `0008`, at the latest SL-06a, see 05-data) |
| CR-SL05-005 | LOW | BACKLOG | `backend/src/menu/catalog/api.py:165-197` | Only this route lists explicit error responses; the 429 text covers only the family cap (the SR-059/SR-070 middleware 429s also apply), and 403 omits the CSRF failure | RESOLVED (cycle 2) |
| CR-SL05-006 | LOW | BACKLOG | `backend/src/menu/access/matrix.py:21`, `backend/src/menu/history/record.py:51`, `backend/tests/integration/test_dish_status_edges.py` | Stale comments and docstrings, and a test file that duplicates two tests | RESOLVED (cycle 2) |
| CR-SL05-007 | LOW | BACKLOG | `backend/src/menu/history/export.py:39-42`, `backend/tests/db/test_history_export.py` | `HistoryExport.export_self` (author-or-subject perimeter, `person_id=None`) has no test | RESOLVED (cycle 2) |
| CR-SL05-008 | INFO | – | `backend/src/menu/catalog/dishes.py:385-400`, `backend/src/menu/history/codec.py:166-176` | By user decision, a same-status event has `before == after`. Future KPI-5 readers must not count `st→st` as "became tested" | ACKNOWLEDGED (rule documented in 05-data §4.2) |

## Findings

### CR-SL05-001 · HIGH · BLOCKER
- **Location:** `web/src/features/dishes/DishPage.tsx:86` (status shown only as a badge); `web/src/features/dishes/DishFormPage.tsx:269-286` (`{existing ? null : <fieldset ...status...>}`: the status radio exists only in create mode); `web/src/features/dishes/formModel.ts:121-128` (`updateBody` has no `status`, as it must, because `PUT` no longer touches it)
- **Category:** correctness (unmet user story)
- **Problem:** The slice adds `POST /dishes/{id}/status` and regenerates the client, but nothing in the web app calls it. After a dish is created, nobody can change its status from the app. `docs/03-ux.md` §S-06 specifies the command ("il cambio di stato è immediato, con avviso e «Annulla» (registra l'evento per KPI-5)", string `dish.status.markTested`), and the UX traceability maps US-005 → S-06 in M0. The plan maps US-005 only to SL-05 (AC-005.4 is reconfirmed in SL-17), lists `frontend-developer` among the SL-05 agents, and no later slice mentions this S-06 command.
- **Scenario:** A planner opens "Pasta e ceci" (to try) after cooking it and wants to mark it "collaudato" (AC-005.1). S-06 has no command, and S-07 in edit mode hides the status field. The only way is a hand-crafted API call. The AC is satisfied by the API tests but not by the product, and KPI-5 (which the event exists for) never gets data from real use.
- **Suggested fix:** Add the S-06 command for A and P (hidden for M, DD-04): `setDishStatus(id, version, status)` in `web/src/api/dishes.ts` with `If-Match` from the loaded detail; an immediate change with the "Annulla" notice (the undo is a second `POST` with the new ETag); `412` → the generic conflict message as in S-07; `429` → the generic rate-limit message. **Alternative (needs a decision):** if the user or tech-lead prefers to keep SL-05 backend-only, amend `docs/07-plan.md` so that a named slice (for example SL-08, which already adds the archive and restore commands to S-06) owns the S-06 status command, and update the US-005 traceability. That change of scope resolves this finding without code.
- **Verification:** A vitest on S-06: A/P see the command and M does not; the click sends `POST /dishes/{id}/status` with `If-Match: "<n>"` and refreshes the detail; "Annulla" sends the reverse with the new version; a 412 shows the conflict message. Optionally a Playwright e2e: to try → collaudato → the badge changes.
- **Status:** RESOLVED (cycle 2). What was checked:
  - `DishPage.tsx` renders `StatusCommand` only when `canWrite` (DD-04).
  - `StatusCommand.tsx` sends `setDishStatus(id, version, NEXT_STATUS[status])`. `api/dishes.ts` builds the body from the generated `StatusChange` type and sends `If-Match`. A `useRef` guard means a double click sends only one request.
  - On success the detail cache takes the response (so the next `If-Match` is the new version) and the list is invalidated. The toast offers "Annulla", which sends the previous status with the new version and offers no further undo.
  - Error handling:
    - 412: conflict message plus a reread of the detail.
    - 403: the session is reread.
    - 404: the not-found state.
    - 429: the button is disabled for `retryAfterSeconds`, capped at 1 h.
  - The i18n keys `dish.status.markToTry` and `dish.status.changed.toast` exist and match 03-ux.
  - Tests:
    - `web/tests/unit/dishes/s06-status.test.tsx` has 10 cases: the Member sees no command, both directions, undo with the new version, double click, list refresh, 412, 403, 404 and 429.
    - `web/tests/e2e/dishes.spec.ts` adds an AC-005.1-.3 flow (mark, undo, state persists after reload) and a 412 flow.
  - The unit tests are green (see Tools). I did not run the e2e tests.

### CR-SL05-002 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/ratelimit/tracked.py:66` (`_CONSUME` inside the caller's `family_tx`), `:73` (`_alarm_once(...)` still inside it), `:81` (`with system_tx() as own:`); caller `backend/src/menu/catalog/dishes.py:381-387` (`SELECT … FOR UPDATE` on the dish, then `consume_tracked_write`); pool `backend/src/menu/tenancy/engine.py:41-43` (`pool_size=5, max_overflow=5, pool_timeout=3`)
- **Category:** performance / availability
- **Problem:** `INSERT … ON CONFLICT DO UPDATE … WHERE c.count < :limit` locks the conflicting row even when the `WHERE` is false (PostgreSQL docs, INSERT: "all rows will be locked when the ON CONFLICT DO UPDATE action is taken"). So a request that gets the 429 still holds the family's counter row lock and its dish row lock. In that state, `_alarm_once` takes a **second** pooled connection (`system_tx`) to bump the alarm counter and, the first time, write `security_event`. This happens on **every** 429, not only the first one. All of the family's other tracked writes are queued on the counter row, each one holding its own pooled connection. Once 10 requests for the instance are in flight (1 holder plus 9 waiters), the holder cannot get its second connection. It blocks for `pool_timeout` (3 s), the alarm fails and is swallowed, then the lock is released and the next waiter repeats the cycle. While this goes on, the pool is exhausted for **every** family on that instance.
- **Scenario:** A family has reached 5,000 tracked writes today (a runaway client or a malicious planner; the per-account limit still allows 60 writes/min, in bursts, from up to 20 sessions). The client sends 10 or more concurrent status changes. Each 429 now takes about 3 s instead of milliseconds, the security alarm may never be written (every attempt times out), and other families' reads and writes on that instance wait or fail with pool timeouts. This is the THR-046/THR-100 cap turning into a mild availability amplifier. The nested-connection pattern is new in this slice: `cross_family` and `audit/cap.bump` run outside the family transaction.
- **Suggested fix:** Emit the alarm only after the family transaction has rolled back. For example, `consume_tracked_write` raises a dedicated `TrackedCapExceeded(window_start, retry)` (or an `AppError` carrying a private marker), and `set_status` (or a small `tracked_write(ctx)` context manager in `ratelimit` that wraps `family_tx`, so future tracked routes inherit it) catches it **outside** the `with tenancy.family_tx(...)` block, calls `_alarm_once`, then raises the `429` `AppError`. That way no request ever holds two pooled connections. This also gives future tracked routes (SL-06a onwards) a single entry point instead of a manual call they could forget.
- **Verification:** A concurrency test: a family at the cap, `pool_size + 2` concurrent `POST /status` (or a test engine with `pool_size=2, max_overflow=0`). Assert that every response is 429 within well under `pool_timeout`, that exactly one `rate_limit.exceeded` exists, and that no `ratelimit.event_unrecorded` is logged. Keep `test_the_429_is_logged_once_for_the_manager_without_personal_data` and `test_the_daily_cap_is_atomic_under_a_race` green.
- **Status:** RESOLVED (cycle 2). What was checked:
  - `consume_tracked_write` (`tracked.py:88-100`) now raises `TrackedCapExceeded(window_start, retry)` and opens no connection of its own.
  - `tracked_write` (`:77-85`) turns that exception into the alarm plus the 429 `AppError`.
  - `set_status` uses `with ratelimit.tracked_write(ctx), tenancy.family_tx(ctx) as tx:` (`dishes.py:381`). The family transaction is the inner context, so it has rolled back and returned its connection, and the row locks are released, before `_alarm_once` opens `system_tx`.
  - Regression test: `test_more_writes_than_pool_connections_at_the_cap_all_get_429_and_other_families_are_served` sends 16 concurrent tracked writes to a capped family (more than the 10-connection pool) plus one read from beta. All 16 get 429, beta gets 200, and exactly one `rate_limit.exceeded` is written. Green in all 3 concurrency repetitions.
  - The earlier 429, alarm and race tests are still green.
  - Note, not a new finding: if a future tracked route calls `consume_tracked_write` without wrapping it in `tracked_write`, `TrackedCapExceeded` will surface as a 500, not a 429. The `assert_tracks` inventory does not cover the at-cap path. Consider adding an architecture test, or extending `assert_tracks` with a "capped family → 429" case, when SL-06a adds the next tracked route.

### CR-SL05-003 · LOW · FIX-IN-SLICE
- **Location:** `docs/05-data.md:855-856` ("lo valida un modello Pydantic per `unit_type`", "un'unica tabella nel codice (`history/event_format.py`)"); `docs/07-plan.md:845` ("codec v1, modelli per `unit_type`/`op`/`v`"); code `backend/src/menu/history/codec.py:36-52` (`KEYS`, `OPERATIONS`) and `:140-271` (hand-written `validate`)
- **Category:** design / documentation
- **Problem:** The design documents describe a validation mechanism (Pydantic models, file `event_format.py`) that does not exist. The implementation is a hand-written validator in `codec.py`. It is functionally fine and well tested (unit, golden fixtures, Hypothesis). But the v1 format is permanent (AC-028.5), and the plan requires a data-architect review of the format before the slice closes, so the reference document must describe what was actually built.
- **Scenario:** In SL-22 (history) a developer looks for `history/event_format.py` or the Pydantic models to decode events. They don't exist, and a second, divergent definition of the keys could be written next to `codec.KEYS`.
- **Suggested fix:** The data-architect updates `05-data.md` §4.2 to name `menu.history.codec` (`KEYS`, `OPERATIONS`, `validate`, `diff`, `apply`, `revert`) as the single source of truth, and records that validation is hand-written (or the code is changed to Pydantic models if the data-architect prefers it). Ideally, the golden fixtures in `tests/fixtures/codec_v1/` are cited as the frozen contract.
- **Verification:** `grep -n "event_format\|Pydantic per" docs/05-data.md` returns nothing that contradicts the code. The data-architect's sign-off on the v1 format is noted in `05-data.md`.
- **Status:** RESOLVED (cycle 2). What was checked:
  - `05-data.md` §4.2 (around lines 859-915) names `menu.history.codec` as the single source of truth.
  - It states that `event_format.py` and the Pydantic models do not exist, and records the hand-written validation with its rationale.
  - It cites `tests/fixtures/codec_v1/` as the frozen contract.
  - It carries the data-architect's sign-off: "APPROVATO", 2026-10-24.
  - The remaining mentions of `event_format` only explain that the module does not exist.
  - `07-plan.md:845` still says "modelli per `unit_type`/`op`/`v`". That is the tech-lead's document, and 05-data now takes precedence. Optional wording fix, not blocking.

### CR-SL05-004 · LOW · BACKLOG
- **Location:** `backend/migrations/versions/0008_change_event.py:91-94` (`ck_change_event_meal_slot`), `:95-107` (`ck_change_event_key`); `backend/src/menu/history/record.py:41-72` (`EventKey` accepted as is)
- **Category:** correctness (defense in depth)
- **Problem:** (a) With `meal_type IS NULL` and `meal_slot = 3`, both branches of `ck_change_event_meal_slot` evaluate to NULL, so the CHECK passes. (b) `ck_change_event_key` requires the key columns of each unit type but does not forbid the others. A `dish` event with `meal_date` set is accepted, and it would then appear in `ix_change_event_family_day` and in the per-day history (Q7). `record_change` does not check that `EventKey` matches `unit_type` either. Neither case can be reached by current code (one caller, `EventKey(dish_id=...)`), but SL-06a and SL-06b add several new callers.
- **Scenario:** A future `meal_content` caller passes `EventKey(meal_date=d, meal_slot=0)` and forgets `meal_type`. The DB rejects it (good). A `dish` archive caller that copies a meal key by mistake writes `dish_id` plus `meal_date`, and the DB accepts it. The event then shows up in the day's history.
- **Suggested fix:** `check (meal_slot is null or (meal_type is not null and ((meal_type <> 'other' and meal_slot = 0) or (meal_type = 'other' and meal_slot between 0 and 4))))`. In `record_change`, validate the `EventKey` fields against a per-unit allow-list (for example `dish → {dish_id}`, `attendance → {meal_date, meal_type, meal_slot, subject_person_id}`) and raise `ValueError` otherwise. A schema-level "exactly these columns" CK is optional. If the migration is not changed before release, do it in a later additive migration (`NOT VALID` + `VALIDATE`).
- **Verification:** Add cases to `tests/db/test_change_event_schema.py::test_check_constraints_refuse_malformed_events` (`meal_type NULL, meal_slot 3`) and a unit test for `record_change` with a mismatched key.
- **Status:** OPEN (backlog, as agreed). `05-data.md` (around line 1481) schedules the additive CHECK for the first migration after `0008`, at the latest in SL-06a. Record it in the technical debt list in `docs/STATUS.md`.

### CR-SL05-005 · LOW · BACKLOG
- **Location:** `backend/src/menu/catalog/api.py:165-197` (`_problem` helper and the `responses=` map); `openapi.json` `/api/v1/dishes/{dishId}/status`
- **Category:** maintainability (API contract)
- **Problem:** This is the only route that lists explicit error responses. The other routes rely on the shared `default` problem response, so the contract is inconsistent. The 429 description says "Tetto di scritture tracciate della famiglia", but this route can also get the middleware's 429 for the SR-059 session limit and the SR-070 per-account limit (`ratelimit/middleware.py:85-87`). The 403 description says "Membro" only, while a CSRF failure (`session_guard`) is also a 403. `_problem` is a local helper that other modules will copy.
- **Scenario:** The frontend reads the generated description and handles the 429 as a "daily family cap" message. A user who is just over 60 writes/min is told the family is blocked for the rest of the day.
- **Suggested fix:** Either drop the per-route list (keep `default`), or move `_problem` to `menu.platform.http` and use it on every route with accurate texts ("Limite di frequenza: sessione, account o tetto giornaliero della famiglia; `Retry-After`", "Ruolo senza permesso o CSRF non valido"). The client should tell the cases apart by `params`/`code`, not by the description.
- **Verification:** `make openapi && cd web && pnpm run api:check` stays green; the contract test still asserts the response set.
- **Status:** RESOLVED (cycle 2). The descriptions are now accurate:
  - 403: "Ruolo senza permesso (Membro) o token CSRF non valido".
  - 429: "Limite di frequenza (sessione, account) o tetto giornaliero di scritture tracciate della famiglia".
  - `api:check` is green.

  `_problem` stays local to `catalog/api.py`, and this is still the only route with an explicit list. That is acceptable for now. Move the helper to `platform.http` when a second module needs it.

### CR-SL05-006 · LOW · BACKLOG
- **Location:** `backend/src/menu/access/matrix.py:21` ("Operazioni future dell'archivio (SL-05, SL-08)": `set_status` is no longer future); `backend/src/menu/history/record.py:51` ("`before` e `after` vengono da `codec.diff`": the only caller, `catalog/dishes.py:392-400`, builds them by hand, and has to, because `codec.diff` refuses an unchanged state, which the user decision on same-status requires); `backend/tests/integration/test_dish_status_edges.py` (both tests duplicate `test_dish_status.py:480-510`, and the docstring still says "Vedi il report della slice (NEEDS_DECISION)" although the decision is made); `backend/tests/integration/test_dish_status.py:485` (import inside the test function)
- **Category:** maintainability
- **Problem:** Comments and docstrings that no longer match the code, plus duplicated tests that will drift.
- **Scenario:** A later slice copies `record_change`'s docstring advice and passes `codec.diff` output for a same-status request, which raises `CodecError` and gives a 500.
- **Suggested fix:** Update the matrix comment (only archive and restore are future, SL-08). Reword the `record_change` docstring ("`before`/`after` in formato v1, di solito da `codec.diff`; validati qui"). Delete `test_dish_status_edges.py`, or merge any assertion it has that the other file lacks (the `412` replay check in its first test). Move the `tracked_count` import to the top of the module.
- **Verification:** `make lint-py` and `make test-int` stay green with the same count minus the removed duplicates.
- **Status:** RESOLVED (cycle 2). What was checked:
  - The matrix comment now marks only archive and restore as future (SL-08).
  - The `record_change` docstring explains that `codec.diff` refuses an unchanged state and that the payload is then built by hand.
  - `test_dish_status_edges.py` is deleted.
  - `tracked_count` is imported at the top of `test_dish_status.py`.
  - The integration count went from 436 to 434, which is the two removed duplicates.

### CR-SL05-007 · LOW · BACKLOG
- **Location:** `backend/src/menu/history/export.py:39-42` (`export_self`), `:20-26` (`_SELF`); `backend/tests/db/test_history_export.py` (only `export_family` is tested)
- **Category:** tests
- **Problem:** The `self` perimeter (05-data §9.3: "eventi di cui è autore o soggetto") has no test. Neither the `actor_person_id OR subject_person_id` filter, the exclusion of the other people's events, nor the `person_id is None → {}` branch is covered. The export job arrives in SL-23a and will take this contributor as already proven.
- **Scenario:** A typo in `_SELF` (for example only `actor_person_id`) would leave out the events where the person is the subject (attendance, typical week, role changes) from their own GDPR export, and nothing would fail.
- **Suggested fix:** Add a DB test: three events in family alfa (author = P1; subject = P1 with author P2; author = P2 with no subject) plus one in beta. `export_self(tx, account, P1)` returns exactly the first two, and `export_self(tx, account, None)` returns `{}`.
- **Verification:** `make test-db` passes with the new test; reverting the `or subject_person_id` clause makes it fail.
- **Status:** RESOLVED (cycle 2). `test_self_export_has_events_authored_or_about_the_person_only` (`tests/db/test_history_export.py:103`) sets up the four events as suggested. It asserts that exactly the authored-by-P1 and about-P1 rows come back, and that `person_id=None` returns `{}`. Green (`test-db` went from 631 to 632).

### CR-SL05-008 · INFO
- **Location:** `backend/src/menu/catalog/dishes.py:385-400`; `backend/src/menu/history/codec.py:166-176` (`_validate_single` accepts equal values)
- **Category:** design
- **Problem:** By user decision, a same-status request writes `before={"st":"tested"}`, `after={"v":1,"st":"tested"}`. The codec accepts this for single-value units, while its module docstring says payloads carry "solo ciò che è cambiato" and `diff` refuses no-op changes. This is consistent with the decision, but the two contracts now differ.
- **Scenario:** KPI-5 (dishes that became tested) counted as "events with `after.st = 'tested'`" would double count repeated taps.
- **Suggested fix:** None in code. Note in `05-data.md` §4.2 (`dish` row) that `before` may equal `after` for `status_change`, so that KPI-5 counts transitions with `before.st <> after.st`.
- **Verification:** n/a
- **Status:** ACKNOWLEDGED. `05-data.md` (around lines 883-884) now says that `codec.diff` refuses the unchanged state, so the dish service builds that payload itself, and that KPI-5 counts "became tested" only when `before.st <> after.st`.

## Re-check notes (fix cycle 1)
- **No new BLOCKER was introduced by the fixes** (anti-loop rule).
- I looked at three changes in the diff that are not fixes for my findings. They appear to come from the security review (SEC-SL05-002) and are left to the security-engineer:
  - `web/package.json`: `happy-dom` 21.0.1 → 21.0.4.
  - `web/pnpm-workspace.yaml`: a dated `minimumReleaseAgeExclude` for that version.
  - `backend/uv.lock`: `filelock` 4.1.1 → 4.2.0.
- One small inconsistency there: the workspace comment says to remove the exception "entro il 2026-10-30", but `web/tests/unit/supply-chain.test.ts` sets `EXCEPTION_UNTIL = "2026-10-31"`, so the test only starts failing on the 31st. Align the two dates.

## Tools run
| Tool | Command | Result |
|---|---|---|
| Lockfile, ruff, format, mypy, bandit | `make lint-py` | Cycle 1: all clean (227 files, mypy 218 files). Re-check: `ruff check` all checks passed; `ruff format --check` 226 files already formatted; `mypy` no issues in 217 source files; bandit clean |
| Unit and architecture | `make test-unit` | Cycle 1: 1042 passed, 7 deselected. Re-check: 1042 passed, 7 deselected |
| Contract | `make test-contract` | 55 passed (both runs) |
| DB | `make test-db` | Cycle 1: 631 passed. Re-check: 632 passed |
| Integration | `make test-int` | Cycle 1: 436 passed. Re-check: 434 passed (2 duplicates removed) |
| Security | `make test-sec` | 322 passed (both runs) |
| Property | `make test-prop` | 51 passed (both runs) |
| Concurrency | `make test-conc` (3 repetitions) | Cycle 1: 17 passed ×3. Re-check: 18 passed ×3 (new pool regression test) |
| Web lint, format, types, i18n, unit | `cd web && pnpm run lint && pnpm run format:check && pnpm run typecheck && pnpm run i18n:check && pnpm run test` | Re-check: all passed; vitest 29 files, 579 tests passed |
| Generated web client | `cd web && pnpm run api:check` | `src/api/schema.gen.ts` matches `openapi.json` (both runs) |

Not run: the Playwright e2e tests (`make e2e`, which builds `web/dist`). The two new e2e flows for AC-005.1-.3 and 412 are UNVERIFIED by this reviewer.

## What was done well
The event and the change share one transaction, the family cap is a single atomic upsert counted only on success (403/404/412/422/429 don't consume it, and a race test proves this), the window is the family's local day including DST, and the `tracks` inventory with its closed list of untracked writes is a strong guard against forgetting events in future slices. The codec has golden fixtures and Hypothesis round-trip and rebuild properties. In the fix cycle, `tracked_write` gives future tracked routes one entry point that cannot hold two pooled connections, and the S-06 command covers every error status with focused unit tests.
