# Code review · SL-06a

- **Date:** 2026-11-07
- **Reviewer:** code-reviewer (combined mode: also baseline security per the secure coding checklist)
- **Scope:** `git diff 70cb367` (uncommitted) plus untracked files: migration `0009_meal.py`; `planning` (`api.py`, `export.py`, `meals.py`, `schemas.py`, `__init__.py`); `views/plan.py`, `views/schemas.py`, `views/__init__.py`; `history/record.py`; `catalog` (`dishes.py::read_refs`, `schemas.py`, `__init__.py`); `access/matrix.py`; `app/factory.py`; `openapi.json`; `web/src/api/{plan,client}.ts`, `schema.gen.ts`; `web/src/features/plan/*`; `web/src/components/ActionMenu.tsx`; `web/src/lib/{dates,aria-style}.ts`; `web/src/app/routes.tsx`, `main.tsx`, `i18n/format.ts`, `styles/base.css`; the new and changed backend and web tests (`tests/architecture/test_tracked_writes_are_capped.py`, `tests/support/tracked_scan.py`, `tests/unit/test_record_change_key.py`, `tests/integration/test_{plan_read,meal_read,meal_presence}.py`, `tests/security/test_meals_*.py`, `tests/concurrency/test_meal_presence_races.py`, `tests/db/test_{meal_schema,effective_meals,planning_export,change_event_schema}.py`, `web/tests/e2e/plan.spec.ts`, `web/tests/unit/plan/*`). Read alongside: `ratelimit/tracked.py`, `platform/http/if_match.py`, `lib/pasto-id.ts`, `docs/05-data.md` §7.1 and §12, `docs/07-plan.md` §2, §3, §4.3 and SL-06a, `docs/reviews/SL-06a-verification.md`.
- **Out of scope (per brief):** `backend/uv.lock`, `backend/pyproject.toml`, `web/pnpm-workspace.yaml`, `web/pnpm-lock.yaml`, `Dockerfile`, `.trivyignore.yaml`, `docs/adr/ADR-0018*`, `backend/tests/tools/*`, Makefile trivy/certifi lines. The dead-end controls listed under "SL-06a debt" in `docs/STATUS.md` are known and scheduled and are not re-reported.
- **Verdict:** APPROVED WITH FIXES (no BLOCKER; one LOW FIX-IN-SLICE, CR-SL06a-001)
- **Cycle:** 1

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL06a-001 | LOW | FIX-IN-SLICE | `backend/src/menu/views/plan.py:60-64` | `GET /plan` serializes unset item fields as `null` (`dishId: null` on free-text items), `GET /meals` and the `412` body omit them: two shapes for the same `MealItemView`, against the rule stated in `planning/schemas.py:4` | OPEN |
| CR-SL06a-002 | LOW | BACKLOG | `backend/src/menu/planning/api.py:29` | The `{date}` path parameter accepts more than `AAAA-MM-GG` (unix timestamps, datetimes), unlike `GET /plan` | OPEN |
| CR-SL06a-003 | LOW | BACKLOG | `backend/src/menu/planning/meals.py:76-81,214-215` | `_RANGE_ITEMS` reads the items of every meal row in the range (removed and hidden rows included) and drops them in Python | OPEN |
| CR-SL06a-004 | LOW | BACKLOG | `backend/src/menu/planning/meals.py:33-43` | `planning` reads `app.family` and `app.family_default_meal` directly, while plan §2.1 forbids reading another module's tables and §3 lists `family.default_meal_types(tx)` | OPEN |
| CR-SL06a-005 | LOW | BACKLOG | API responses (no compression outside `platform/http/static.py`) | `GET /plan` JSON is never compressed; worst case 1.2 MB per request | OPEN |
| CR-SL06a-006 | LOW | BACKLOG | `web/src/features/plan/MealPage.tsx:182-201` | S-03 resolves each dish name with its own `GET /dishes/{id}` (up to 10) plus the full course list; harmless now (no content yet), relevant from SL-06b | OPEN |
| CR-SL06a-007 | LOW | BACKLOG | `backend/src/menu/planning/meals.py:30,73-74` | `MEAL_ORDER` is dead code; the order lives in a SQL literal instead | OPEN |
| CR-SL06a-008 | INFO | – | `backend/src/menu/planning/meals.py:187-201` | `?from=X` without `to`, with X after the current week, gives `422 range_order` | ACKNOWLEDGED |
| CR-SL06a-009 | INFO | – | `web/tests/e2e/plan.spec.ts:20-23` | e2e AC-001.1 computes the expected week from the host clock; can flake across midnight Europe/Rome | ACKNOWLEDGED |
| CR-SL06a-010 | INFO | – | plan SL-06a "Test" item 3; plan §2.2 `MealLifecycleListener` | Cross-family 404 on a meal cannot happen by design (ADR-0009); the re-add hook for attendance is not wired yet | ACKNOWLEDGED |
| CR-SL06a-011 | INFO | – | repository root | Untracked unrelated files (`package.json`, `pnpm-lock.yaml`, `istruzioni-run-manuale.txt`) must stay out of the slice commit | ACKNOWLEDGED |

## Findings

### CR-SL06a-001 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/views/plan.py:60-64` (`@router.get("/plan", response_model=PlanView, response_model_by_alias=True, ...)`, no `response_model_exclude_unset`); compare `backend/src/menu/planning/api.py:62,90` (`response_model_exclude_unset=True`) and `planning/meals.py:233-235` (`model_dump(..., exclude_unset=True)` for the 412 `current`); rule stated in `backend/src/menu/planning/schemas.py:4` ("Le risposte omettono i campi facoltativi non impostati ... una voce imposta solo i campi del suo tipo").
- **Category:** design (API contract)
- **Problem:** The same `MealItemView` is serialized in two shapes. In `GET /plan` a free-text item carries `"dishId": null, "courseId": null`, and a dish item carries `"freeText": null`. In `GET /meals/...`, in `PUT .../presence` and in the 412 `params.current` those keys are absent. Verified with a TestClient probe on the real models: plan item `{..., 'dishId': None, 'courseId': None, 'freeText': 'x', ...}`, meal item `{..., 'freeText': 'x', ...}`.
- **Scenario:** SL-06b's client code and any future consumer (the offline cache in SL-43, history `refs`) read `item.dishId !== undefined` to tell a dish from a free-text item. That works on S-03 and fails on S-02. The extra nulls also add to the worst-case 1.2 MB of `GET /plan` (5,580 items x 2 null keys). The contract is new in this slice, so changing it now costs nothing, while changing it after SL-06b means touching two clients.
- **Suggested fix:** Add `response_model_exclude_unset=True` to the `GET /plan` route (all `PlanView`, `DayView` and `MealView` fields are always set, so only the item's foreign fields disappear), regenerate `openapi.json` and `schema.gen.ts` if they change.
- **Verification:** One assertion in `tests/integration/test_plan_read.py` (or the contract test): in a plan with a dish item and a free-text item, the free-text item has no `dishId`/`courseId` key and the dish item has no `freeText` key, the same as `GET /meals` for the same meal.
- **Status:** OPEN

### CR-SL06a-002 · LOW · BACKLOG
- **Location:** `backend/src/menu/planning/api.py:29` (`Day = Annotated[dt.date, Path(alias="date")]`); compare `backend/src/menu/views/plan.py:27,214-220` (strict `AAAA-MM-GG`, ASCII digits).
- **Category:** design (input validation consistency)
- **Problem:** Pydantic's lax `date` parsing accepts more than the documented `format: date`. Verified on the project venv: `'1762473600'` is parsed as `2025-11-07` (unix timestamp at midnight UTC) and `'2026-11-07T00:00:00'` as `2026-11-07`. `GET /plan` rejects both with `date_invalid`.
- **Scenario:** `GET /api/v1/meals/1762473600/dinner/0` returns the dinner of 2025-11-07. There is no security impact (the family still comes from the session, RLS applies), but the meal has several URLs. `PUT .../presence` follows the same parser, and the plan says the dates are calendar strings only (ADR-0009).
- **Suggested fix:** Use the same parser as `views/plan.py` for the path segment: a `str` path parameter with `pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"`, then `date.fromisoformat`; map failures to `422 validation` `date_invalid` as in `/plan`. Moving `_parse` to a shared helper in `platform` avoids two copies.
- **Verification:** Parametrized test on `GET /meals/{date}/dinner/0` and `PUT .../presence`: `1762473600`, `2026-11-07T00:00:00`, `2026-1-7`, `２０２６-11-07` give 422 `date_invalid`; `2026-11-07` gives 200.
- **Status:** OPEN

### CR-SL06a-003 · LOW · BACKLOG
- **Location:** `backend/src/menu/planning/meals.py:76-81` (`_RANGE_ITEMS`, filter only on family and date), `:214-215` (all rows loaded into `items`), `:219-223` (only keys from `effective_meals` are used).
- **Category:** performance
- **Problem:** Confirmed the tester's note. The item query is not joined to `effective_meals`, so it reads the items of removed meals and of hidden `inherit` rows (frozen days, defaults removed). The result is correct (`_view` only receives the items of present keys, and the removed-meal tests cover it), but the request reads and holds content that is never shown.
- **Scenario:** A family that removes many dinners with content (or, after SL-09, freezes days with hidden `inherit` rows) pays for those rows on every `GET /plan`. The bound is the same as the worst case already measured (5,580 items), so this is waste, not a risk.
- **Suggested fix:** Restrict the items to present meals in SQL: `... from app.meal_item i join app.effective_meals(:start, :end) e using (meal_date, meal_type, meal_slot) where i.family_id = :family ...` (or `where exists`). Keep the EXPLAIN inlining check.
- **Verification:** The existing `test_plan_read.py` removed-meal tests stay green; optionally count rows fetched in the probe used for NFR-002.
- **Status:** OPEN

### CR-SL06a-004 · LOW · BACKLOG
- **Location:** `backend/src/menu/planning/meals.py:33-35` (`_FAMILY_CLOCK`: `select timezone ... from app.family`), `:36-43` (`_ENSURE_ROW` reads `app.family_default_meal`).
- **Category:** design (module boundaries)
- **Problem:** Plan §2.1: "Un modulo non legge né scrive le tabelle di un altro: ne chiama i servizi". `family` owns `family` and `family_default_meal`, and §3 lists `family.default_meal_types(tx) -> set[MealType]` for this purpose. The published SQL contracts (§2.3: `family_today()`, `effective_meals()`) are the only exception, and the two queries above go beyond them. `ratelimit/tracked.py:42,50` already reads `app.family` (precedent from SL-05), and `test_layers.py` checks imports only, so nothing fails.
- **Scenario:** SL-09 changes how defaults are stored or adds per-weekday defaults; `planning` silently keeps the old rule in `_ENSURE_ROW` (the `inherit` vs `removed` choice for a new row), and the presence written on a new row no longer matches what `effective_meals` shows.
- **Suggested fix:** Either add `family.default_meal_types(tx)` and `family.clock(tx) -> (timezone, today)` and call them (one extra round trip at most, inside the same transaction), or have the tech-lead record in plan §2.3 that `app.family.timezone` and `family_default_meal` are published read contracts. The second option is cheaper and consistent with `ratelimit`.
- **Verification:** `grep -rn "app.family\b\|family_default_meal" backend/src/menu --include=*.py` outside `family/` returns only entries listed in §2.3.
- **Status:** OPEN

### CR-SL06a-005 · LOW · BACKLOG
- **Location:** no compression on `/api/v1` (only `backend/src/menu/platform/http/static.py:125-140` gzips static files); `GET /plan` in `views/plan.py`.
- **Category:** performance
- **Problem:** The tester measured 1,245,568 bytes for the worst-case `GET /plan` (62 days x 9 meals x 10 items). JSON of this shape compresses about 10x, but the app never compresses API responses, and Cloud Run does not do it for the app (TO VERIFY on staging: send `Accept-Encoding: gzip` and check `Content-Encoding`).
- **Scenario:** A planner opens a two-month view on a mobile connection: 1.2 MB instead of about 100 KB. A realistic plan is about 20x smaller (around 60 KB), so this matters only for heavy families or for NFR-002 under load.
- **Suggested fix:** When the staging check confirms no compression, add gzip for `GET /api/v1/plan` (and later `GET /history`) above a size threshold. Keep it off for responses that carry secrets next to reflected input (`GET /session` returns the CSRF token), to stay clear of BREACH; `GET /plan` carries no secret.
- **Verification:** A test on `GET /plan` with `Accept-Encoding: gzip` and a large plan: `Content-Encoding: gzip`, `Vary: Accept-Encoding`; `GET /session` stays uncompressed.
- **Status:** OPEN (to schedule with the NFR-002 staging measurement, SL-10a/SL-10b)

### CR-SL06a-006 · LOW · BACKLOG
- **Location:** `web/src/features/plan/MealPage.tsx:182-201` (`useQueries` with one `readDish(id)` per dish item, plus `listCourses()`), `:216` (falls back to "…" forever if a dish read fails).
- **Category:** performance / design
- **Problem:** `MealView` carries only `dishId`/`courseId`, so S-03 fetches the full `DishDetail` of every dish (up to 10 requests) and the whole course list, only to show a name, the archived flag and a course label. `GET /plan` already solves the same problem with `refs`. In SL-06a meals have no content yet, so this code path is barely exercised; it becomes the normal path in SL-06b.
- **Scenario:** In SL-06b a dinner with 6 dishes opens with 8 requests instead of 1; on a slow network the names arrive one by one, and a dish that fails to load (for example a 404 race with SL-08 deletion) stays as "…" with no error.
- **Suggested fix:** Before SL-06b, have the tech-lead decide whether `MealView` (or a `MealPage` composite in `views`) carries `refs` like `PlanView`, reusing `catalog.read_refs`. Otherwise, seed the dish names from the plan cache. In both cases show an explicit "piatto non disponibile" instead of "…" on failure.
- **Verification:** A vitest on S-03 with 3 dish items: one `GET` for the meal (with refs) and no `GET /dishes/{id}`.
- **Status:** OPEN (decision for tech-lead before SL-06b)

### CR-SL06a-007 · LOW · BACKLOG
- **Location:** `backend/src/menu/planning/meals.py:30` (`MEAL_ORDER`, never referenced in `src/` or `tests/`), `:73-74` (the order repeated as a SQL array literal).
- **Category:** maintainability
- **Problem:** Dead constant. The real ordering source is the SQL literal in `_RANGE_MEALS`, and the web has a third copy (`web/src/api/plan.ts:32`, which also defines S-02 ordering).
- **Scenario:** A future change to the order (custom courses do not affect it, but SL-40 named "Altro pasto" might) is made in `MEAL_ORDER` and has no effect.
- **Suggested fix:** Remove `MEAL_ORDER`, or build the SQL array from it with a bound parameter (`array_position(cast(:order as text[]), e.meal_type)`).
- **Verification:** `grep -rn MEAL_ORDER backend/src` returns either nothing or the place where it is used.
- **Status:** OPEN

### CR-SL06a-008 · INFO
- **Location:** `backend/src/menu/planning/meals.py:187-201` (`_resolve_range`).
- **Category:** design (API contract)
- **Problem:** Confirmed: a missing `to` takes the current Sunday, so `?from=<date after this week>` without `to` is `422 range_order`. It matches the contract text ("un estremo mancante vale quello della settimana corrente") and the web client always sends both ends, so no action is required. If the contract is revisited, a missing `to` = `from + 6` is the less surprising default.
- **Status:** ACKNOWLEDGED

### CR-SL06a-009 · INFO
- **Location:** `web/tests/e2e/plan.spec.ts:20-23` (`romeToday()` from the host clock), used at `:76`, `:85`, `:104`, `:152`.
- **Category:** tests
- **Problem:** Confirmed: the server computes "today" from the real `now_utc`, the test from the host clock. A run that straddles midnight Europe/Rome (or a slow run at Sunday 23:59) expects the wrong week. Low probability; a cheap fix is to read `today` from `GET /api/v1/plan` through the `request` fixture and derive the expected week from it.
- **Status:** ACKNOWLEDGED

### CR-SL06a-010 · INFO
- **Location:** `docs/07-plan.md` SL-06a "Test" item 3; plan §2.2 `MealLifecycleListener.on_meal_readded`; `backend/src/menu/planning/meals.py:293-301`.
- **Category:** design
- **Problem:** (a) I agree with the tester: a meal is addressed by `(date, mealType, slot)` and the family comes only from the session, so "pasto di altra famiglia → 404 ed evento" cannot be produced. ADR-0009 addressing plus RLS is the mitigation of THR-020 for meals, and `test_meals_isolation.py` proves it. The tech-lead should amend the Test line, and SL-06b must test the body-reference case (dish or course of another family in `PUT .../content` → 404 + `access.cross_family`, SR-041). (b) The re-add path empties content and guests but has no hook for `attendance` yet. That is correct today (the attendance tables arrive in SL-14/SL-15), but the hook point is the `if empty:` branch; SL-15 must add `MealLifecycleListener.on_meal_readded` there, inside the same transaction.
- **Status:** ACKNOWLEDGED

### CR-SL06a-011 · INFO
- **Location:** repository root: untracked `package.json` (an `npm init` stub), `pnpm-lock.yaml`, `istruzioni-run-manuale.txt` (manual run notes with a stub-OIDC identity cookie for `marco@example.test`; not a secret, gitleaks clean).
- **Category:** maintainability
- **Problem:** Unrelated to SL-06a (already noted as out of scope in SL-05). They must not be swept into the slice commit with `git add -A`.
- **Status:** ACKNOWLEDGED

## Tools run
| Tool | Command | Result |
|---|---|---|
| gitleaks | `gitleaks dir --no-banner -v . --redact` (working tree, untracked files included) | no leaks found (10.91 MB scanned) |
| semgrep | `semgrep scan --metrics=off --error --quiet --config p/python --config p/owasp-top-ten --config p/typescript --config p/react --config .semgrep backend web` (project `scan-sast` configuration) | exit 0, no findings |
| pytest | `.venv/bin/python -m pytest -q tests/architecture tests/unit/test_record_change_key.py` | 107 passed |
| Pydantic probe | `TypeAdapter(date)` on `'1762473600'`, `'2026-11-07T00:00:00'`, `'20261107'`, full-width digits | first two accepted (CR-SL06a-002), the others rejected |
| FastAPI probe | TestClient on the real `PlanView` / `MealView` models, one free-text item | `/plan`-style route emits `dishId: null, courseId: null`; `/meals`-style route omits them (CR-SL06a-001) |
| Dependency audit | not rerun: the slice adds no dependency (no change to `web/package.json`; `pyproject.toml`/locks are out of scope), and `make ci` (which runs `scan-deps`: pip-audit + osv-scanner, and `scan-web`) was green today per the brief | not rerun |
| Full suite, mypy, ruff, e2e | not rerun: fresh green evidence in the brief (`make ci` today; tester mode C 417 + 167 backend, 122 web unit, 20 e2e, mypy/ruff clean) and the diff has not changed since | not rerun |

Secure coding checklist on the changed code: every new route declares `x-authz` and goes through `family_access` (deny by default; reads A/P/M, presence A/P; role reread per request); the write route has the CSRF and session guards (`writes=True`, covered by mutant M2); object-level isolation by session-only family plus RLS forced on `meal` and `meal_item`; bodies closed (`extra='forbid'`, `StrictBool`); all SQL is `text()` with bound parameters, the f-strings in `0009` interpolate only module constants; no `innerHTML` or `dangerouslySetInnerHTML` in the new web code, names and free text are text nodes; problem+json without internals; no meal content in logs; no new dependency; `If-Match` bounded to 18 digits. No violation found.

## What was done well
The presence write is careful: the row is created and locked in the same transaction (`ON CONFLICT DO NOTHING` then `FOR UPDATE`), the order is 412, then cap, then write and event, the cap is taken after the row lock as SL-05 asked, and the re-add records the removed items in full in `before`. CR-SL05-004 is closed in both layers (exact-column `ck_change_event_key` with `NOT VALID` + `VALIDATE` and a reversible downgrade, plus `_check_key` in `record_change`), and the new AST architecture test proves it can fail on synthetic trees.

## Report — code-reviewer
**Outcome:** DONE
**Scope:** SL-06a (combined mode: code and baseline security)
**Files changed:** docs/reviews/SL-06a-code.md
**Summary:** Reviewed the SL-06a diff against 70cb367 plus the untracked slice files, reading changed files in full with their callers. The migration, `effective_meals`, the presence write (locking, versioning, cap order, events, re-add emptying), the CR-SL05-004 carry-over and the web S-02/S-03/D-05/D-07 are correct and well tested. One LOW FIX-IN-SLICE: `GET /plan` serializes item fields as `null` where `GET /meals` omits them. Six LOW BACKLOG items (lenient path date, `_RANGE_ITEMS` waste, direct reads of `family` tables, no API compression, per-dish reads in S-03, dead `MEAL_ORDER`) and four INFO notes.
**Evidence:** gitleaks dir: no leaks found; semgrep (project scan-sast config): exit 0; pytest tests/architecture + test_record_change_key: 107 passed; Pydantic and FastAPI probes as in "Tools run".
**Traceability:** US-008 (AC-008.1, .3, .4, .5, .7 read), US-001 (AC-001.1 e2e), AC-052.7, SR-008, SR-060, THR-020, THR-105, CR-SL05-004
**Decisions needed:** CR-SL06a-004: publish `family.timezone`/`family_default_meal` as read contracts in plan §2.3 (cheap, matches ratelimit) or add `family` services (cleaner boundary); recommendation: publish them in §2.3. CR-SL06a-006: should `MealView` carry `refs` before SL-06b (contract change, one request per S-03) or should the client reuse the plan cache; recommendation: `refs` on `MealView`.
**Risks and technical debt:** CR-SL06a-002..007 to record in STATUS.md (SL-06b for 006, SL-10a/10b for 005, SL-09 for 004); plan Test item 3 needs the tech-lead's amendment (CR-SL06a-010).
**Suggested next step:** backend-developer fixes CR-SL06a-001 (one line plus one assertion, regenerate OpenAPI if it changes); the orchestrator closes it on evidence, records the BACKLOG items, and sends the slice to the security review.
