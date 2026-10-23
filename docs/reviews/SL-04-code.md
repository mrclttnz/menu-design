# Code review · SL-04

- **Date:** 2026-10-23
- **Reviewer:** code-reviewer
- **Scope:** `git diff 8add827` (uncommitted) plus untracked files: migration `0007_dish.py`; `access` (`matrix.py`, `rules.py`); `family/access.py`; `identity/guards.py` (`session_reader`); `platform/http/problem.py`; `catalog` (`api.py`, `dishes.py`, `schemas.py`, `text.py`, `export.py`); `audit/catalog.py`; web `TextField.tsx`, `features/dishes/*`, `api/dishes.ts`, `RootLayout.tsx`, `providers.tsx`, `routes.tsx`, `base.css`; every new and modified backend and web test; docs `05-data.md`, `08-test-strategy.md`, `03-ux.md`.
- **Verdict:** APPROVED (re-check, cycle 2; cycle 1 was APPROVED WITH FIXES)
- **Cycle:** 2

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL04-001 | MEDIUM | FIX-IN-SLICE | `web/src/features/dishes/DishFormPage.tsx:69,112-116,182` | The edit form reads `If-Match` from the live query, so a background refetch silently moves it to the newer version and overwrites someone else's change | RESOLVED (cycle 2) |
| CR-SL04-002 | LOW | FIX-IN-SLICE | `web/src/i18n/messages.ts:372` | Out-of-date "da ratificare" comment: the keys are now in `03-ux.md` | RESOLVED (cycle 2) |
| CR-SL04-003 | LOW | BACKLOG | `backend/src/menu/catalog/dishes.py:275-280` | `read_dish` checks existence and loads the row in two statements: a delete between them gives 500 (from SL-08 on) | OPEN |
| CR-SL04-004 | LOW | BACKLOG | `backend/src/menu/family/access.py:3-4`, `backend/src/menu/catalog/api.py:3-4` | The docstrings say the permission is checked before the body is read. Malformed JSON gets 422 before 401/403/CSRF | RESOLVED (cycle 2) |
| CR-SL04-005 | LOW | BACKLOG | `web/src/components/TextField.tsx`, `web/tests/e2e/dishes.spec.ts:283` | TextField works around a regex on `innerHTML` that can give false positives. The search box still mirrors its value into the attribute, and no test pins TextField's behaviour | OPEN |
| CR-SL04-006 | LOW | BACKLOG | `backend/src/menu/catalog/schemas.py:204,211-214` | Optional texts (`notes`, `page`, `note`) that are blank or only spaces are stored as `''` or `'  '` instead of `NULL` | OPEN |
| CR-SL04-007 | INFO | BACKLOG | `web/src/styles/base.css:12-24`, `web/src/features/dishes/dishes.css:175-177` | `#root` scroll layout: content now scrolls inside `<main>`, and the "visible with the keyboard open" claim is unverified | OPEN |
| CR-SL04-008 | INFO | – | `backend/src/menu/catalog/dishes.py:127-129` | The cursor is base64 JSON that contains the normalized dish name, so it is not confidential (same exposure as `q` in the URL) | OPEN |

## Findings

### CR-SL04-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `web/src/features/dishes/DishFormPage.tsx:69` (`useQuery({...dishQuery(...)})`), `:112-116` (`existing={dish.data}`, `key={dish.data?.id}`), `:182` (`updateDish(existing.id, existing.version, ...)`); `web/src/features/dishes/DishPage.tsx:27` (`staleTime: 0`)
- **Category:** correctness (optimistic concurrency, ADR-0008)
- **Problem:** The form state is frozen at mount (`useState(initial)`), but the version sent in `If-Match` is read from the live query on every render. The detail query has `staleTime: 0`, and the `QueryClient` turns off only `refetchOnWindowFocus`, so `refetchOnReconnect` (TanStack default `true`) is still on. A refetch while the form is open replaces `dish.data`. The `DishForm` key (the dish id) does not change, so the user's edits stay in the form while `existing.version` silently moves to the server's newer version.
- **Scenario:** A planner opens `/piatti/X/modifica` at version 3 on a phone and edits the notes. The network drops briefly (common on mobile). Meanwhile the admin saves the same dish (version 4). On reconnect the query refetches and `existing.version` becomes 4. The planner taps "Salva", which sends `PUT If-Match: "4"` and gets `200`: the admin's change is lost with no `412`. This is exactly the silent overwrite that ADR-0008 and `test_two_puts_with_the_same_if_match_one_wins_one_gets_412` exist to prevent. The backend is correct; the client defeats it.
- **Suggested fix:** Freeze the base version together with the form state. For example, in `DishForm`: `const [baseVersion] = useState(existing?.version);` and `updateDish(existing.id, baseVersion, ...)`. After a `412` the user then gets the generic conflict message as intended for M0. In addition, or as an alternative, turn off background refetches for the edit query (`refetchOnReconnect: false`, `refetchOnMount: false` once loaded) while keeping the reread on every opening.
- **Verification:** A vitest in `s07-form.test.tsx`: open the edit form with version 3 and edit a field. Make the stub return version 4, then trigger `onlineManager.setOnline(false)` → `true` (or `queryClient.refetchQueries(KEYS.detail(id))`) and submit. Assert that the PUT carries `If-Match: "3"` and that the UI shows the conflict message.
- **Status:** RESOLVED (cycle 2): `DishForm` freezes `openedVersion` with `useState(existing?.version)` at mount (`DishFormPage.tsx:144`) and sends it at `:185`. Regression test `web/tests/unit/dishes/s07-form-frozen-version.test.tsx`; a mutation check confirmed it fails if the fix is reverted.

### CR-SL04-002 · LOW · FIX-IN-SLICE
- **Location:** `web/src/i18n/messages.ts:372` (and the convention described at `:4`)
- **Category:** maintainability
- **Problem:** The comment "Voci nuove di SL-04, non presenti nella UX (da ratificare)" is out of date. The tester added the six keys to `docs/03-ux.md` (verification §5), and the verification report itself asks for the comment to be removed.
- **Scenario:** A later slice reads the comment and opens a UX question that is already settled, or treats the keys as provisional.
- **Suggested fix:** Remove the "da ratificare" marker above the SL-04 keys. This is a comment-only change.
- **Verification:** `grep -n "ratificare" web/src/i18n/messages.ts` no longer matches the SL-04 block. `make lint-web` passes.
- **Status:** RESOLVED (cycle 2): line 372 now reads `// Voci di SL-04: sezione Piatti e selettore.`, and `grep ratificare` matches only the general convention at `:4`.

### CR-SL04-003 · LOW · BACKLOG
- **Location:** `backend/src/menu/catalog/dishes.py:275-280` (`read_dish`), `:186-187` (`_load` → `.one()`)
- **Category:** correctness (race)
- **Problem:** `read_dish` runs `_DISH_EXISTS` and then `_load`, which calls `.mappings().one()`. These are two statements under READ COMMITTED with no row lock. If a concurrent transaction deletes the dish between them, `.one()` raises `NoResultFound` and the response is `500` instead of `404`.
- **Scenario:** Today nothing deletes dishes. From SL-08 (`DELETE /dishes/{id}`, and also the family cascade) a reader who opens the dish while it is being deleted gets a 500, logged as an unexpected error.
- **Suggested fix:** Use one source of truth. `_load` returns `None` when `_DETAIL` finds no row, and `read_dish` raises `MissingReference` on `None`; then drop `_DISH_EXISTS` (one query fewer). Schedule it at the latest with SL-08.
- **Verification:** In SL-08, a concurrency test that runs GET and DELETE on the same dish in a loop and asserts that every GET is `200` or `404`, never `500`.
- **Status:** OPEN

### CR-SL04-004 · LOW · BACKLOG
- **Location:** `backend/src/menu/family/access.py:3-4` ("Il permesso si controlla qui, prima della validazione del corpo"), `backend/src/menu/catalog/api.py:3-4` ("prima di leggere il corpo")
- **Category:** design / documentation
- **Problem:** The claim holds for *schema* validation (FastAPI resolves sub-dependencies before body fields), and `test_a_denied_member_write_is_refused_before_any_validation_leak` covers that case. It does not hold for the JSON *decode*: in `fastapi/routing.py` the handler calls `await request.json()` and turns a `JSONDecodeError` into a 422 (lines 452-464) **before** `solve_dependencies` (line 499).
- **Scenario:** An anonymous request, or a member, sends `POST /api/v1/dishes` with body `{` and gets `422 validation` instead of `401`, `403 forbidden` or `403 csrf_failed`. There are no side effects and no business rule is revealed (only "the JSON is malformed"), so the impact is negligible. The comments, however, state an invariant that the code does not guarantee.
- **Suggested fix:** Make the docstrings precise ("before schema validation; malformed JSON is rejected earlier by the framework"). If the strict order is needed, it has to move into a middleware, which is not worth it here.
- **Verification:** Reading the code, or a test asserting the documented behaviour for an invalid body sent anonymously.
- **Status:** RESOLVED (cycle 2): both docstrings now state that malformed JSON is rejected with `422` by FastAPI before the dependency runs, and that the permission check comes before *field* validation (`family/access.py:3-6`, `catalog/api.py:3-5`).

### CR-SL04-005 · LOW · BACKLOG
- **Location:** `web/src/components/TextField.tsx:17-46`; `web/tests/e2e/dishes.spec.ts:283` (`expect(body.innerHTML()).not.toMatch(/\sonerror=|\sonload=/)`); `web/src/features/dishes/DishesPage.tsx:278-284`
- **Category:** tests / maintainability
- **Problem:** TextField leaves idiomatic React controlled inputs behind (the value is set imperatively in a `useLayoutEffect`) so that the user's text never lands in the `value` attribute. Text inside an attribute value that React has escaped is not executable, so the real job of this component is to satisfy the e2e regex on `innerHTML`, which matches ` onerror=` *inside* an attribute value. The defence is also partial: the search box is still a controlled `<input value={search}>`, and React mirrors its value into the attribute. The e2e test passes only because it clears the search box (`fill("")`) before the check. No unit test pins TextField's property ("the value is never in the markup"), so a later refactor back to `value=` would fail only through the e2e regex, for the wrong reason.
- **Scenario:** A future test types a payload into the search box and checks `innerHTML` without clearing it first: it fails with a false positive. Or someone simplifies TextField and nobody notices that the component's documented property is gone.
- **Suggested fix:** Make the e2e assertion precise: no element has an attribute whose *name* starts with `on`, no `script:not([src])`, no `javascript:` href. For example, `page.$$eval('*', els => els.flatMap(e => [...e.attributes].map(a => a.name)).filter(n => n.startsWith('on')))` must return `[]`. Then pick one of two: keep TextField and add a unit test (`container.innerHTML` does not contain the value) plus a line in the frontend conventions, or go back to normal controlled inputs.
- **Verification:** The precise e2e test is green with the payload still present in the search box. The unit test fails if `TextField` passes `value` to the DOM.
- **Status:** OPEN

### CR-SL04-006 · LOW · BACKLOG
- **Location:** `backend/src/menu/catalog/schemas.py:204` (`_Notes`), `:211` (`_Page`), `:212-214` (`_SourceNote`); `backend/src/menu/catalog/dishes.py:205-206`, `:210-211`
- **Category:** correctness (data hygiene)
- **Problem:** `name` and `reference` are stripped and must not be empty. The optional texts are neither stripped nor normalized: `""` or `"   "` is stored as is. `_present` and `_load` drop only `None`, so the API returns `notes: "   "` or `page: ""`. The web client trims and sends `null`, so only direct API calls (or future clients, CSV import in SL-44) produce these values.
- **Scenario:** `POST /dishes` with `"notes": "   "` stores the spaces. S-06 (`data.notes ? …`) shows a "Note" section that is empty to the eye. The export carries meaningless strings.
- **Suggested fix:** In the optional `Annotated` types, add an `AfterValidator` that turns a blank string into `None` (after `strip` for `page`; for `notes`, decide whether to keep the inner text and reject only all-blank values).
- **Verification:** An integration test: POST with `notes: "  "`, `sources[0].page: ""` and `note: " "` gives a GET without those keys.
- **Status:** OPEN

### CR-SL04-007 · INFO · BACKLOG
- **Location:** `web/src/styles/base.css:12-24` (`#root` flex with `height: 100dvh`, `main { overflow-y: auto }`), `web/src/features/dishes/dishes.css:175-177` (`.form-actions` sticky, comment "anche con la tastiera aperta")
- **Category:** design (frontend)
- **Problem:** The change is coherent: the nav stays out of the content area (WCAG 2.5.8), and the sticky save bar now sticks to `main`. It does, however, change a global invariant: the document no longer scrolls. `window.scrollTo`, browser scroll restoration and any future "scroll to top" have to act on `#contenuto`. On top of that, with `<meta name="viewport" content="width=device-width, initial-scale=1">` and no `interactive-widget=resizes-content`, current mobile browsers lay the on-screen keyboard over a `100dvh` layout. The save bar at the bottom of `main` therefore probably ends up *under* the keyboard, so the CSS comment's claim is unverified. TO VERIFY on a real device or in a Chromium emulation with a virtual keyboard.
- **Scenario:** In the future, someone writes `window.scrollTo(0, 0)` after a navigation and nothing happens. On Android the "Salva" bar is not visible while typing in the notes.
- **Suggested fix:** Record "the scroll container is `main#contenuto`" in the frontend conventions. Check the keyboard case. If it matters, add `interactive-widget=resizes-content` to the viewport, or fix the comment.
- **Verification:** A manual check on mobile-360 with the keyboard open. A grep for `window.scroll` in later slices.
- **Status:** OPEN

### CR-SL04-008 · INFO
- **Location:** `backend/src/menu/catalog/dishes.py:127-129` (`encode_cursor`)
- **Category:** security (information) — for the security-engineer
- **Problem:** The cursor is "opaque" to the client but readable: base64url of `{"n": name_search, "i": id}`. It travels in the query string just as `q` does. The app does not log it (the request log records only `scope["path"]`, `platform/http/middleware.py:207`; uvicorn's `access_log=False`), but the platform's request logs (Cloud Run) keep the full URL. Tampering is handled well (strict validation → 422, test `test_a_tampered_cursor_is_a_422_and_leaks_nothing`; RLS makes a cursor from another family harmless).
- **Scenario:** The normalized name of the last dish on a page ends up in the infrastructure logs. This is the same class of exposure as `q`, which the plan accepts.
- **Suggested fix:** None needed now. If the security-engineer wants it, sign or encrypt the cursor, or use only `id` with a lookup of the name.
- **Verification:** n/a.
- **Status:** OPEN

## Tools run
| Tool | Command | Result |
|---|---|---|
| uv, ruff, mypy, bandit | `make lint-py` | lock OK; ruff check: "All checks passed!"; ruff format: "209 files already formatted"; mypy: "Success: no issues found in 201 source files"; bandit with no output (clean) |
| pytest security tier | `make test-sec` | `236 passed, 10 warnings in 104.65s` |
| pytest concurrency tier | `make test-conc CONC_REPEAT=1` | `13 passed, 6 warnings in 24.48s` |
| eslint, prettier, tsc, lingui | `make lint-web` | clean; "Catalogo coerente con il codice."; `lingui compile --strict` OK |
| vitest + api:check | `make test-web` | `Test Files 27 passed (27)`, `Tests 564 passed (564)` |
| FastAPI source (read only) | `grep` in `fastapi/routing.py` | `request.json()` at lines 452-464, `solve_dependencies` at 499 (evidence for CR-SL04-004) |

Not rerun by me (fresh evidence in `docs/reviews/SL-04-verification.md`): `test-unit`, `test-contract`, `test-db`, `test-int`, `test-prop`, `e2e`, `scan`.

The four test edits by the orchestrator were checked one by one on the diff: `matrix.py` (unused `type: ignore` removed), `test_dishes_update.py` (`..%2Fsession`, which really reaches the server, unlike `../`), `test_console_privileges.py` (UPDATE column for `dish_course`, privilege assertions unchanged), `test_rate_counter_schema.py` (still checks `0006 → 0005`; the head is covered by `test_migrations.py`, updated for 0007 with stronger assertions on the three tables). **None weakens the suite.** No `skip` or `xfail` in the new backend files.

New dependencies: `pyyaml` (already in the lockfile as a transitive dependency) and `types-pyyaml==6.0.12.20260906` (dev only), both pinned in `uv.lock`. Use is `yaml.safe_load` only (`tests/support/matrix.py:13`).

## What was done well
- **Migration 0007:** composite FKs plus the direct FK `family_id → family CASCADE` on the parts, with the reason (breadth-first RI cascade order) documented and tested; trigger `ever_planned` SECURITY INVOKER with `EXECUTE` revoked; clean, reversible downgrade; inventories and the `ExportContributor` (explicit allow-list without `name_search`, deterministic order) updated in the same slice.
- **`access`:** a declarative matrix that is the single source of both `x-authz` and the check, so declaration and enforcement cannot diverge. Default-deny. Events carry only the operation name. The matrix in `tests/security/authz_matrix.yaml` is independent of the code, and the access mutants were all killed.
- **Backend:** advisory lock per family around count and insert (quota exact under contention, proved with 2 and 6 contenders); `FOR UPDATE` plus version check in Python (no bigint overflow); a foreign dish with a wrong version still gets 404, never 412; one constant SQL statement for the list with literal LIKE escaping; keyset cursor on `(name_search, id)` validated strictly. `problem.py`: client keys that are not identifiers are no longer echoed back.
- **Tests:** broad and meaningful coverage (CSRF and origin per operation, mass assignment, cross-family with an event, canaries in logs and bodies, wildcards and injection, ties across pages, races). Assertions check effects (state hash, event counts), not just status codes.

## Re-check · cycle 2
Scope (anti-loop rule): the open FIX-IN-SLICE findings CR-SL04-001 and CR-SL04-002, the fix-cycle diff, and the docstring fix for CR-SL04-004. The fix-cycle diff includes the new `backend/src/menu/audit/cap.py`, the denial cap in `backend/src/menu/access/rules.py` (`_record_denial`, `configure_denial_cap`), the `audit`/`access` exports, the `factory.py` wiring, and `tests/security/test_access_denial_log_cap.py`. In this cycle I may open new findings only if they are BLOCKERs introduced by the fix.

**CR-SL04-001: RESOLVED.**
- **The fix:** the version is frozen at mount with `const [openedVersion] = useState(existing?.version)`, and the PUT sends `openedVersion ?? existing.version`. The `?? existing.version` fallback cannot be reached on the edit path: `DishForm` is keyed by the dish id and mounts only once `dish.data` exists, so `openedVersion` is always set when `existing` is.
- **The test:** `s07-form-frozen-version.test.tsx` covers the reconnect path. The stub returns v3 and then v4, `onlineManager` goes off and back on, the test asserts that a refetch really happened (`gets > 1`), and the PUT must carry `If-Match: "3"`.
- **Mutation check:** in a scratch copy, I reverted the fix to `existing.version`. The test then fails, so it really guards the fix.
- **Minor gap (no finding):** the test does not assert the conflict message after a `412`. That UI path predates the fix and is unchanged.

**CR-SL04-002: RESOLVED.** The "da ratificare" marker is gone from the SL-04 block.

**CR-SL04-004: RESOLVED** (it was BACKLOG; fixed early). The docstrings are now accurate.

**Fix-cycle diff: no new defects that need a finding.**
- `audit/cap.py` reuses the `rate_counter` table, the HMAC key format and the DB clock window of `ratelimit/store.py`. The name `access_denied_log` separates its keys from the rate-limit keys.
- It runs in its own `system_tx`. The grants already allow it (0006: full DML for `menu_app`).
- The hourly window fits inside the planned 2-day purge (SL-10a).
- The pepper (`session_pepper`) is already a secret.
- `_record_denial` caps events at 20 per account per hour, then writes exactly one `suppressed` event.
- The `403`/`404` responses do not change, and a failing counter or log never turns into a 500.

These behaviours are pinned by five security tests: the cap of 20+1 for both event types, the SR-058 threshold, the per-account isolation, and counter failure giving 404.

Two observations; neither is a BLOCKER, so neither is opened as a finding:
- If `bump` fails, the event is dropped rather than written without a cap. This is documented in the docstring and consistent with the security log living in the same database.
- All anonymous actors would share one bucket. In practice this cannot happen: `family_access` answers `401` before `authorize` and `cross_family` run.

**Tools run (cycle 2)**
| Tool | Command | Result |
|---|---|---|
| uv, ruff, mypy, bandit | `make lint-py` | ruff "All checks passed!"; "211 files already formatted"; mypy "Success: no issues found in 203 source files"; bandit clean |
| eslint, prettier, tsc, lingui | `make lint-web` | clean; "Catalogo coerente con il codice."; `lingui compile --strict` OK |
| vitest + api:check | `make test-web` | `Test Files 28 passed (28)`, `Tests 565 passed (565)` |
| mutation check (scratch copy, removed afterwards) | revert to `existing.version`; `vitest run tests/unit/dishes/s07-form-frozen-version.test.tsx` | `1 failed`: the test detects the regression |
| pytest security tier | `make test-sec` | `241 passed` (236 + 5 cap tests) |
| pytest integration tier | `make test-int` | `383 passed` |
| pytest concurrency tier | `make test-conc CONC_REPEAT=1` | `13 passed` |

**Verdict after re-check: APPROVED.** No BLOCKER or FIX-IN-SLICE findings remain open. CR-SL04-003, -005, -006 and -007 stay OPEN as BACKLOG. CR-SL04-008 stays INFO for the security-engineer.

## Report — code-reviewer (cycle 2, re-check)
**Outcome:** DONE
**Scope:** SL-04 re-check: CR-SL04-001, CR-SL04-002, the fix-cycle diff (denial cap: `audit/cap.py`, `access/rules.py`, `factory.py`) and the CR-SL04-004 docstrings
**Files changed:** docs/reviews/SL-04-code.md
**Summary:** CR-SL04-001, CR-SL04-002 and CR-SL04-004 are RESOLVED. The regression test for 001 was checked by mutation and fails when the fix is reverted. The denial-cap change introduces no new defects. Final verdict: APPROVED.
**Evidence:** `make lint-py` and `make lint-web` clean; `make test-web` 565 passed; `make test-sec` 241 passed; `make test-int` 383 passed; `make test-conc CONC_REPEAT=1` 13 passed; mutation run 1 failed as expected.
**Traceability:** ADR-0008 (If-Match), SEC-SL04-001 / SR-058 (denial cap), US-004, US-006.
**Decisions needed:** none
**Risks and technical debt:** CR-SL04-003 (fix by SL-08), CR-SL04-005, CR-SL04-006 and CR-SL04-007 go to STATUS.md as debt. CR-SL04-008 is for the security-engineer.
**Suggested next step:** the orchestrator closes the SL-04 code review and moves on to the slice's remaining gates.

<details><summary>Report — cycle 1</summary>

**Outcome:** DONE
**Scope:** SL-04 (diff `8add827`, uncommitted, plus untracked files)
**Files changed:** docs/reviews/SL-04-code.md
**Summary:** Full review of the migration, export, access, family_access, problem.py, the catalog API and service, the web dish pages, TextField, the layout, and the new and modified tests. No BLOCKER. 2 FIX-IN-SLICE: the client loses optimistic concurrency because the edit form takes the version from the live query, which refetches on reconnect (MEDIUM); and an out-of-date i18n comment (LOW). 4 LOW/INFO items for the backlog and 2 INFO. The orchestrator's test edits are legitimate and weaken nothing.
**Evidence:** `make lint-py` clean (mypy "no issues found in 201 source files"); `make test-sec` 236 passed; `make test-conc CONC_REPEAT=1` 13 passed; `make lint-web` clean; `make test-web` 27 files / 564 tests passed.
**Traceability:** US-004 (AC-004.1-.7), US-006 (AC-006.1-.5), SR-008, SR-009, SR-010, SR-024, SR-041, SR-060, ADR-0008, THR-020/021/023/025/070.
**Decisions needed:** none
**Risks and technical debt:** CR-SL04-003 (read_dish race to fix by SL-08), CR-SL04-004, CR-SL04-005, CR-SL04-006, CR-SL04-007 to record in STATUS.md as debt; CR-SL04-008 for the security-engineer.
**Suggested next step:** frontend-developer fixes CR-SL04-001 (freeze `version` at the form's mount, with a vitest regression test) and CR-SL04-002; then a targeted re-check by the code-reviewer on that diff only.

</details>
