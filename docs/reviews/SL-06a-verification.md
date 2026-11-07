# SL-06a verification (tester, mode C)

Date: 2026-11-07. Slice: SL-06a Week plan: view, ranges, meals of the day (US-008 AC-008.1/.3/.4/.5/.7 read, US-001 AC-001.1 end-to-end, AC-052.7, SR-008, SR-060, THR-020, THR-105). Base commit 70cb367; slice work uncommitted in the working tree. Outcome: **VERIFIED** (DONE_WITH_CONCERNS: one test gap found and closed, one plan item that cannot be met as written, see sections 4 and 7).

## 1. Suite results

Per the brief, the whole suite was not rerun. The orchestrator ran `make ci` on this tree today: lint, unit 1062, contract 67, scan, db tier 749/591/375/51/24x3, container, web 640, all green; e2e 200 passed, 2 failed. The 2 failures are SL-04 `dishes.spec.ts` (SR-060 60 dishes, AC-004.5 axe) timing out under load; they pass when rerun alone. That is the load sensitivity already recorded in SL-04-verification §1/§6, so it is not an SL-06a regression.

Targeted fresh runs (tester, this session):

| Command (from `backend/` unless noted; DB env as in `make` `PG_ENV`) | Result |
|---|---|
| `pytest -n 4 tests/db/test_meal_schema.py tests/db/test_effective_meals.py tests/db/test_planning_export.py tests/db/test_change_event_schema.py tests/integration/test_plan_read.py tests/integration/test_meal_read.py tests/integration/test_meal_presence.py tests/security/test_meals_access.py tests/security/test_meals_isolation.py tests/concurrency/test_meal_presence_races.py tests/contract/test_plan_contract.py tests/contract/test_authz_inventory.py tests/architecture/test_tracked_writes_are_capped.py tests/unit/test_record_change_key.py -rs` | **417 passed**, 0 skipped (228 s) |
| `pytest -n 4 tests/db/test_inventory_rls.py tests/db/test_sql_functions.py tests/db/test_inventory_secdef.py tests/db/test_console_privileges.py tests/db/test_migrations.py tests/db/test_export_inventory.py tests/integration/test_access_authorize.py` | **167 passed** |
| `pytest tests/integration/test_meal_read.py` (after adding the gap test, §4) | **37 passed** |
| `mypy` (project config) after the test edit | no issues in 236 source files; `ruff check` / `ruff format --check` clean on the edited file |
| `web/`: `pnpm exec vitest run tests/unit/plan tests/unit/lib` | 7 files, **122 passed** |
| `web/`: `pnpm run build && pnpm exec playwright test tests/e2e/plan.spec.ts` (desktop + mobile-360, axe) | **20 passed** (18.6 s) |

Quality check on the SL-06a test files: no `skip`/`xfail`/`.only`/`.todo`. The one exception is the conditional `test.skip(!STUB_AVAILABLE, ...)` in `plan.spec.ts`, which follows the stack convention and did not trigger (all 20 ran). The tests make exact assertions on status, code, `params`, versions and event rows. They use a real PostgreSQL and a DB-side fake clock (`frozen_now`). No mocks hide the behavior under test.

## 2. AC -> test -> result

Backend files are under `backend/tests/`, web files under `web/tests/`. Every row passed in the runs above.

| AC / req | Backend test(s) | Web test(s) | Result |
|---|---|---|---|
| AC-008.1 | `integration/test_plan_read.py::test_ac_008_1_the_default_view_is_the_current_week_monday_to_sunday_with_default_meals`, `..._meals_of_a_day_come_in_the_order_of_the_day...`, `..._past_days_are_flagged...`, `..._the_week_starts_on_monday_for_every_day_of_the_week`, `test_the_week_follows_the_family_timezone_not_utc_when_now_utc_is_shifted`, `..._in_the_other_direction`, `test_a_week_with_a_daylight_saving_change...` | `unit/plan/s02-week.test.tsx` "S-02: la settimana corrente (AC-008.1)" (7 days, defaults, "Oggi" badge, past); `e2e/plan.spec.ts` "login con Google -> settimana da lunedì a domenica" (today badge, not colour only) | PASS |
| AC-008.3 | `test_plan_read.py::test_ac_008_3_a_snack_added_to_one_day_appears_only_on_that_day`; `test_meal_presence.py::test_ac_008_3_adding_a_snack_creates_the_row_and_shows_it_only_that_day`, `test_adding_an_other_meal_in_slot_two...` | `s02-week` "AC-008.3"; `d05-range.test.tsx` "D-07: aggiungi un pasto a un giorno (AC-008.3)" (If-Match from the read, refetch) | PASS (no e2e for adding; unit + API cover it) |
| AC-008.4 | `test_plan_read.py::test_ac_008_4_a_default_meal_removed_from_one_day...`; `test_meal_presence.py::test_ac_008_4_removing_a_default_meal_records_one_event_and_hides_it_only_that_day` (`assert_tracks` with 6 failing paths) | `s02-week` "AC-008.4"; `s03-meal.test.tsx` "S-03: togliere il pasto dal giorno (AC-008.4)"; e2e "togliere la cena da un giorno la toglie solo da quel giorno" | PASS |
| AC-008.5 | `test_plan_read.py::test_ac_008_5_a_range_from_the_1st_to_the_10th...`, `test_ac_008_5_and_sr_060_63_days_or_more_are_refused_with_the_limit[0,1,400]`, `test_a_huge_range...`, leap-year boundary, `range_order`, `date_invalid` | `d05-range` (10 days, 62 accepted, 63 refused in the client with no request, server `range_too_large` shown); e2e "oltre 62 giorni l'errore indica il limite", "un intervallo di 10 giorni" | PASS |
| AC-008.7 (read) | `security/test_meals_isolation.py` (canaries of the other family never appear in plan or meal; same key changes only the own family; no client parameter or header chooses the family; body `familyId` refused whole; RLS hides Beta to `menu_app`); `db/test_meal_schema.py::test_an_item_cannot_reference_a_dish_or_a_course_of_another_family`, `test_a_meal_cannot_point_to_a_person_of_another_family`; `db/test_effective_meals.py::test_each_family_sees_only_its_own_defaults_and_rows` | - | PASS, with the deviation in §3 item 3 |
| AC-001.1 (e2e part) | (SL-03a: redirect + session) | `e2e/plan.spec.ts` "AC-001.1: ..." x3 (login via OIDC stub -> `/piano`, current week Mon-Sun, defaults, Oggi; navigation; no third-party requests, no page errors, no CSP violations), desktop + 360 px | PASS; AC-001.1 now complete (SL-03a + SL-06a) |
| AC-052.7 | `db/test_meal_schema.py::test_ac_052_7_two_other_meals_of_the_same_day_are_accepted`, `test_five_other_meals_fit_in_a_day_and_the_sixth_slot_does_not`; `test_plan_read.py::test_ac_052_7_two_other_meals_of_the_same_day_are_both_listed_in_slot_order` | - | PASS |
| SR-008 | isolation file above; `security/test_meals_access.py` (deny by default, role matrix, role reread every request, removed person, unknown operation denied); `db/test_inventory_rls.py` (meal, meal_item) | - | PASS |
| SR-060 (62 days) | `test_sr_060_62_days_are_accepted`, the 63+ day tests, `test_the_plan_of_62_days_with_content_answers_in_one_request`; `db/test_effective_meals.py::test_sixty_two_days_come_back_in_one_call` | `d05-range` "62 giorni sono accettati" / "63 giorni" | PASS |
| THR-020 | as SR-008 + `contract/test_authz_inventory.py` (3 new ops in matrix and inventory) | - | PASS |
| THR-105 | "today" comes from `app.family_today()`: the shifted-`now_utc` tests in both timezone directions, `test_ac_008_1_past_days_are_flagged...`, `test_meal_read.py::test_a_past_day_is_flagged_past`; no client date parameter defines "today" (range params don't change `today`: `test_ac_008_5_a_range_from_the_1st_to_the_10th...` asserts `today` stays the family one) | `s02-week` "«Settimana precedente» e poi «Oggi» riportano alla settimana del `today` del server" | PASS (mutant M7 killed) |

Gap check: every AC in scope has at least one passing test. Nothing is uncovered.

## 3. Plan "Test" list, item by item

1. **Week from Monday in the family timezone with a shifted `now_utc`**: covered. `test_the_week_follows_the_family_timezone_not_utc_when_now_utc_is_shifted` (Sunday 23:30 UTC is already Monday in Rome, DST end) and `..._in_the_other_direction` (New York), plus all 7 weekdays.
2. **63 days -> `422 range_too_large`**: covered. Exact `code`, `params == {maxDays: 62}`, `application/problem+json`; 63, 64 and 463 days and `0001-01-01..9999-12-31` (mutant M6 killed).
3. **Meal of another family -> `404` and event**: **cannot be met as written.** A meal is addressed by `(date, mealType, slot)` and the family always comes from the session (ADR-0009), so no route accepts another family's identifier and a cross-family 404 cannot happen. The tests instead prove what can be proven: the other family's data never crosses in either direction, a write with the "same key" touches only the own family (the 412/200 behavior proves it is the attacker's own row), there is no family selector in headers, query or body, RLS is the second layer, and no `access.*` event is written (`test_the_only_security_events_of_these_requests_are_none`). The `404 + access.cross_family` requirement becomes testable in SL-06b, for a dish or course of another family in `PUT .../content` (contract row in plan §4.3). **Action: tech-lead should amend the SL-06a Test line, and product-analyst should check the AC-008.7 wording ("indicandone l'identificativo"). This is already raised as N-2 in mode B.**
4. **Re-added meal reuses the row with growing versions**: covered. `test_re_adding_a_removed_meal_reuses_the_row_and_versions_keep_growing` (remove/add/remove/add -> versions 1,2,3,4, one row, 4 events, cap 4), `..._empties_content_special_name_and_guests` (removed items complete in `before`, a `meal_guests` event only if guests change), `..._invalidates_a_version_read_before_the_removal`, `test_a_stale_write_racing_a_re_add_never_writes_on_the_new_meal` (concurrency). Mutant M9 killed.
5. **`meal_content` event per presence change**: covered. `assert_tracks` in the AC-008.4 test (exact key columns, actor, `occurred_at`, and no event on 6 failing paths), `test_each_request_writes_its_own_event_with_a_correlation_id`, `test_if_the_event_cannot_be_written_the_presence_change_is_rolled_back`, `test_the_event_holds_no_name_no_email...`, race test "six meals, six events". Mutants M5 and M8 killed.
6. **Empty plan state**: covered. `test_an_empty_plan_has_seven_days_and_no_meals_when_the_family_has_no_default_meals`, `test_an_added_meal_is_still_shown...`; web `s02-week` "nessun pasto di default (AC-003.3)" and Member variant (AC-024.4); e2e "una famiglia senza pasti di default vede lo stato vuoto".

## 4. Mutation spot-check (production files restored after each run, verified with md5)

Each mutation was applied to one file. The selected test files were run with `-x -n 4` and the file was restored. Runner: `/tmp/claude-1000/-home-marco-work-menu-design/6f2709e1-9455-4880-ba46-1af5b46425d5/scratchpad/mut/run.py`. After the run, `md5sum -c`: `matrix.py`, `api.py`, `meals.py` all OK.

| # | Mutation | Result | First failing test(s) |
|---|---|---|---|
| M1 | `matrix.py`: `meal.presence.write` ADMIN_PLANNER -> EVERYONE | KILLED | `test_plan_contract.py::test_reads_allow_every_role_and_the_write_is_for_admin_and_planner` |
| M2 | `api.py`: presence guard `writes=True` -> `False` (no CSRF) | KILLED | `test_meals_access.py::test_the_presence_write_rejects_csrf_and_media_type_attacks[senza token...]` |
| M3 | `api.py`: presence authorized as `meal.view.read` | KILLED | `test_a_demoted_planner_loses_the_write...`, `test_ac_008_8_a_member_is_refused...` |
| M4 | `matrix.py`: `plan.view.read` -> ADMIN_PLANNER | KILLED | `test_reads_allow_every_role...` |
| M5 | `matrix.py`: `TRACKS` entry of `meal.presence.write` removed | KILLED | `test_only_the_presence_write_tracks_and_it_tracks_meal_content` |
| M6 | `meals.py`: `MAX_DAYS` 62 -> 63 | KILLED | `test_ac_008_5_and_sr_060_63_days_or_more_are_refused_with_the_limit[0,1]` |
| M7 | `meals.py`: today from host UTC clock instead of `family_today()` (THR-105) | KILLED | shifted-`now_utc` test, past-flag test, AC-008.4 plan test |
| M8 | `meals.py`: `consume_tracked_write` removed (SR-070) | KILLED | `test_the_presence_change_consumes_one_unit_of_the_daily_cap...`, AC-008.3 presence test |
| M9 | `meals.py`: re-add does not empty content | KILLED | `test_re_adding_a_removed_meal_empties_content_special_name_and_guests` |
| M10 | `meals.py`: version check disabled (`If-Match` ignored) | KILLED | AC-008.4 `assert_tracks` (412 path) |
| M11 | `meals.py` `_view`: `items if present else []` -> `items` | survived (equivalent: `_load` already skips the item query for absent meals) | - |
| M11b | `_load` and `_view`: both guards removed (a removed meal's items returned by `GET /meals/...`) | **survived the existing suite** (94 passed). After adding the test below: KILLED | `test_meal_read.py::test_a_removed_meal_never_shows_the_content_left_in_its_row` |

**Gap found and closed (tests only).** The plan view had a "removed meal shows no content" test, but the single-meal read did not. I added `backend/tests/integration/test_meal_read.py::test_a_removed_meal_never_shows_the_content_left_in_its_row`. It covers a removed dinner with a dish item, a free-text canary and `special`, plus a removed `other` slot 2 with a name canary, and asserts `items == []`, `special` / `name` null and no canary or dish id in the body. It passes on the real code and fails on M11b. It is not a product bug: the current code is correct, but the double guard was not protected.

## 5. NFR-002 risk: `GET /plan` over 62 days

The measurement used a temporary probe test (deleted after use). Worst case for one family: 62 days x 9 meals (5 types + 4 extra "Altro pasto") x 10 dish items = 558 meals and 5,580 items, 100 dishes. The probe called `GET /plan` in-process (TestClient + local PostgreSQL 17 with TLS) and counted SQL statements with a SQLAlchemy `before_cursor_execute` listener.

- **Statements per request: 16, constant** (no N+1). 10 are session, rate limit and context (`session_resolve` x2, `rate_counter`, `set_config` x4, session touch, account, person, family). 6 are the plan itself: family clock, `meal_item` range, `effective_meals` joined to `meal`, dish refs, course refs.
- **Timing (20 requests after warm-up):** median 95.8 ms, p95 125.5 ms, max 130.7 ms, end to end including Python serialization. The NFR-002 limit is p95 <= 500 ms.
- **Response size:** 1,245,568 bytes in the worst case. A realistic plan (3 meals, 2-3 items) is about 20x smaller.
- The `effective_meals` inlining and its PK-prefix access are already asserted by `db/test_effective_meals.py::test_the_function_is_used_inline_in_a_from_clause` (EXPLAIN).

Verdict on the risk: **Low**. The official measurement (Locust, 25 users, `load` dataset of 50 families, staging) stays **UNVERIFIED** until SL-10a and staging (08 §14.1). This probe is a trend only: one family, no concurrency, local host.

## 6. Notes for the code reviewer and the security engineer

- **Plan item 3 / AC-008.7** (§3): the "404 + event" for a meal of another family cannot be produced by design. Confirm that ADR-0009 addressing is the accepted mitigation for THR-020 on meals, and make sure SL-06b tests the body-reference case (dish or course of another family -> 404 + `access.cross_family`, SR-041).
- **Response size:** the worst case is about 1.2 MB for a single authenticated `GET /plan`. It is bounded by the schema (62 days, 5 "other" slots, 10 items) and by the per-session rate limit, so the amplification is limited. Check whether the response is compressed and whether a declared size limit is needed (08 §14.1 "dimensione della risposta").
- `_RANGE_ITEMS` (`planning/meals.py`) reads the items of every meal row in the range, including removed meals and hidden `inherit` rows on frozen days, and drops them in Python. The result is correct (tested), but it does wasted reads and holds content in memory that is never shown. Joining on `effective_meals` would avoid it (LOW, perf/hygiene).
- `GET /plan?from=X` without `to` uses the current Sunday as `to`. For an `X` after the current week, that gives `422 range_order`. This matches the contract text ("un estremo mancante vale quello della settimana corrente"), but it may surprise clients (INFO, UX/contract).
- e2e `AC-001.1` computes the expected week from the host clock (`romeToday()`), while the server uses the real `now_utc`. A run that straddles midnight Europe/Rome could flake (INFO).
- SL-04 e2e load sensitivity (SR-060 60 dishes, axe) is still present under `make ci` load. It is carried over from SL-04 and is not caused by this slice.

## 7. Verdict

**VERIFIED.** Every AC in scope (AC-008.1, .3, .4, .5, .7 read; AC-001.1 e2e; AC-052.7) and SR-008, SR-060, THR-020, THR-105 have passing tests. The plan "Test" list is covered except item 3, which cannot be met by design (§3, decision for tech-lead and product-analyst). The existing suite killed 10 of 12 mutants (M1-M10). M11 is equivalent. M11b survived, which exposed a test gap that is now closed, and the new test kills it.
