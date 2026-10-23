# SL-04 verification (tester, mode C)

Date: 2026-10-23. Slice: SL-04 Dish archive (US-004, US-006). Outcome: **DONE**.

## 1. Suite results (fresh runs)

| Command | Result |
|---|---|
| `make test-unit` (unit + architecture + tools, cov) | 920 passed, 7 deselected (container), rc=0 |
| `make test-contract` | 50 passed |
| `make test-db` | 574 passed |
| `make test-int` | 383 passed |
| `make test-sec` | 236 passed |
| `make test-prop` | 6 passed |
| `make test-conc` (3 repetitions) | 13 passed x 3 |
| `make lint-py` (uv lock --check, ruff check, ruff format --check, mypy, bandit) | all clean; mypy: no issues in 201 files |
| `make lint-web` (eslint --max-warnings 0, prettier, tsc, i18n:check, i18n:compile) | clean |
| `make test-web` (vitest + api:check) | 27 files, 564 tests passed; coverage stmts 95.95%, branches 91.15%; schema.gen.ts up to date |
| `make web-build` + budget | initial bundle 139,947 B gzip, limit 153,600 |
| `make e2e` (Playwright, desktop + mobile-360, axe) | 178 passed (57 s) |
| `make scan` (gitleaks git+dir, semgrep rules + SAST, pip-audit, osv-scanner, zizmor, pnpm audit) | rc=0, no findings |

No skipped tests in any backend tier (0 SKIPPED lines).

Notes on two non-clean first runs, both caused by the verification itself, not by the product:
- First `make e2e`: 177 passed, 1 failed (`dishes.spec.ts` SR-060 60-dish pagination, desktop, `__seed` request timed out at 30 s) because I ran `make scan` (gitleaks/semgrep) concurrently on the same machine. The test passes alone 3/3 (about 6.5 s) and the full e2e rerun without concurrent load passed 178/178. Not a product bug. Residual risk: that spec seeds 60 dishes through the stub in about 6 s; under heavy host load it could flake in CI (INFO).
- First `make scan`: `gitleaks dir` reported 194 "generic-api-key" hits, all in `web/test-results/artifacts/*/traces` (Playwright trace zips of the e2e still running, git-ignored, transient). After e2e finished the scan was clean.

## 2. Orchestrator test fixes: legitimate, not weakened

- `tests/support/matrix.py`: stale `type: ignore` removed (mypy `warn_unused_ignores`), no behavior change.
- `test_dishes_update.py`: `../session` replaced by `..%2Fsession` in the bad-id parametrization. Still a path-traversal-style id that must give 4xx and never 5xx (the raw `..` is normalized by the HTTP client before it is sent, so the old case did not test what it claimed). Equivalent or stronger. Accepted.
- `test_console_privileges.py`: `dish_course` added to `_UPDATE_COLUMN` (a table with a composite PK and no generated column needs a column to attempt the UPDATE). Privilege assertions unchanged; the new table is checked by the same loop. Accepted.
- `test_rate_counter_schema.py`: `test_the_migration_is_revision_0006_after_0005` no longer asserts that 0006 is the head (the head is now 0007) and reads revision `"0006"` directly, still asserting `revision == "0006"` and `down_revision == "0005"`. The check on the revision chain is preserved; "head" is covered by `test_migrations.py` (updated for 0007, passing). Accepted.

## 3. AC -> test -> result (all passing in the runs above)

Backend files are under `backend/tests/integration/`; web under `web/tests/`.

### US-004

| AC | Backend test(s) | Web test(s) | Result |
|---|---|---|---|
| AC-004.1 | `test_dishes_create.py::test_ac_004_1_the_planner_saves_a_dish_with_all_its_data` (+ admin default, duplicates, notes/time bands) | `unit/dishes/s07-form.test.tsx` "AC-004.1"; `e2e/dishes.spec.ts` "AC-004.7 + AC-004.1 + AC-004.2" | PASS |
| AC-004.2 | `test_ac_004_2_link_and_book_sources_are_saved_in_order`, `..._http_and_other_kinds_of_source_are_accepted` | `s07-form` "AC-004.2"; `s06-detail` "AC-004.2" (new tab, noopener/noreferrer); e2e same spec | PASS |
| AC-004.3 | `test_ac_004_3_missing_required_field_is_refused_and_named`, `..._blank_name_...`, `..._no_course_...` | `s07-form` "AC-004.3" x3; e2e "AC-004.3 + .4 + .5" | PASS |
| AC-004.4 | `test_ac_004_4_a_link_that_is_not_http_or_https_is_refused` (javascript:, data:, etc.), `..._url_error_is_attached_to_the_right_source`, `test_malformed_sources_...` | `s07-form` "AC-004.4" (parametrized); e2e | PASS |
| AC-004.5 | `test_ac_004_5_a_name_of_120...`, `..._notes_of_2000...`, `..._ten_sources_..._eleventh_is_refused`, `test_source_field_limits`; contract `test_dishes_contract.py` (limits in schema) | `s07-form` "AC-004.5" x3; e2e "AC-004.5: la 11a fonte" | PASS |
| AC-004.6 | `test_ac_004_6_markup_in_name_and_notes_is_stored_and_returned_literally`; `security/test_dishes_canaries.py` | `s05-archive`, `s06-detail`, `s07-form` "AC-004.6"; e2e "THR-070 / AC-004.6" | PASS |
| AC-004.7 | `test_ac_004_7_an_empty_archive_lists_no_dishes` | `s05-archive` "AC-004.7: archivio vuoto"; e2e first scenario | PASS |

### US-006

| AC | Backend test(s) | Web test(s) | Result |
|---|---|---|---|
| AC-006.1 | `test_dishes_search.py::test_ac_006_1_partial_case_insensitive_search_finds_the_dish`, `..._a_query_that_matches_nothing...` | `s05-archive` "AC-006.1"; e2e "AC-006.1 + AC-006.2" | PASS |
| AC-006.2 | `test_ac_006_2_search_ignores_accents_in_both_directions`, `..._an_unaccented_name_is_found_with_an_accented_query` | e2e "AC-006.1 + AC-006.2" | PASS |
| AC-006.3 | `test_ac_006_3_course_and_status_filters_combine_and_exclude_archived`, `test_filters_combine_with_the_search_text` | `s05-archive` "AC-006.3"; e2e "AC-006.3" | PASS |
| AC-006.4 | `test_ac_006_4_an_archived_dish_is_hidden_unless_the_filter_is_on` (archived rows from fixtures: archiving itself is SL-08) | `s05-archive` "AC-006.4"; e2e "AC-006.4" | PASS |
| AC-006.5 | `test_ac_006_5_no_result_is_an_empty_page_the_client_can_turn_into_create` | `s05-archive` "AC-006.5" (create link carries the name); e2e "AC-006.5" | PASS |

Every AC of US-004 (7) and US-006 (5) has at least one backend test and one web test (unit and/or e2e). Gap check: none.

Security and negative coverage present in the suites (all green): role matrix and 401/403 (`security/test_dishes_access.py`, `integration/test_access_authorize.py`, `contract/test_authz_inventory.py`), cross-family 404 with `access.cross_family` and IDOR/cursor tampering (`security/test_dishes_cross_family.py`, search tests), log/body canaries (`security/test_dishes_canaries.py`), CSRF/origin/media type, mass assignment (`created_by`), SQL wildcard/injection search, oversized/deep JSON, NUL, optimistic concurrency and races (`concurrency/test_dish_races.py`), schema/RLS/export (`db/test_dish_schema.py`, `test_dish_export.py`), unsafe routes need guards (`architecture/test_unsafe_routes_have_guards.py`).

## 4. Manual mutation spot-check on `access` (production files restored after each run; verified)

Each mutation applied to one file, run of `tests/security tests/contract tests/architecture tests/integration/test_access_authorize.py` with `-x`, then restored.

| # | Mutation | Result | First failing tests |
|---|---|---|---|
| M1 | `matrix.py`: `catalog.dish.create` ADMIN_PLANNER -> EVERYONE (flip a role) | RED (4 failed) | `test_declared_cells_of_the_archive[catalog.dish.create-member-403]`, `test_the_member_cannot_create_a_tested_dish...` |
| M2a | `family/access.py`: `access.authorize(...)` replaced by `pass` (drop the guard) | RED (2 failed) | `test_role_matrix[catalog.dish.create-member]`, `test_dish_content_never_reaches_logs...` |
| M2b | `catalog/api.py`: update uses the reader (no CSRF) instead of `session_guard` | RED (3 failed) | `test_the_csrf_token_of_another_session_is_refused[catalog.dish.update]`, CSRF/origin attack cases |
| M3a | `rules.py`: remove `access.cross_family` security event | RED (1 failed with -x) | `test_reading_a_dish_of_another_family_is_404[alfa-beta]` |
| M3b | `rules.py`: remove `access.denied` event | RED (2 failed) | `test_role_matrix[catalog.dish.create-member]`, `test_declared_cells_of_the_archive[catalog.dish.update-member-403]` |
| M4 | `rules.py`: default-allow (`allowed is None or family_id is not None`) | RED (1 failed with -x) | `test_dish_content_never_reaches_logs...` (more would fail without `-x`) |

All six mutants were killed.

## 5. Docs

`docs/03-ux.md` (message-key table): added the 6 keys not yet present: `dishes.filter.allCourses`, `dishes.filter.allStatuses`, `dishes.back`, `dish.source.type`, `dish.source.n`, `form.discard.keep`. `picker.create` was already in the UX table (line 1455) with the same text, so not duplicated. Note: `web/src/i18n/messages.ts` still carries the comment "da ratificare" above these keys; remove it (frontend-developer, comment only).

## 6. Findings

No failures and no production bug found. Observations (INFO):
- The SR-060 e2e spec (60 seeded dishes) is sensitive to host load (see section 1); consider a longer seed timeout or a bulk seed in the stub if CI flakes.
- Total unit-tier coverage is 69% (the unit tier excludes DB-dependent code; covered by the other tiers); the gate passed.
- `make e2e` must not run concurrently with `make scan` (trace artifacts trip `gitleaks dir`; load causes timeouts).

## 7. Re-run after fix cycle 1 (SEC-SL04-001, CR-SL04-001)

Whole suite re-run on the fixed tree; no production code changed by the tester (two temporary mutations, restored byte-for-byte, see below).

| Gate | Result |
|---|---|
| make test-unit | 920 passed (coverage gate OK, total 69%) |
| make test-contract | 50 passed |
| make test-db | 574 passed |
| make test-int | 383 passed |
| make test-sec | 241 passed |
| make test-prop | 6 passed |
| make test-conc | 13 passed |
| make lint-py (ruff, format, mypy, bandit) | clean (211 files formatted, 203 sources typed) |
| make lint-web (+ i18n catalog coherence) | clean |
| make test-web | 28 files, 565 tests passed; stmts 95.95%, branches 91.03%, lines 97.23%; api:check OK |
| make web-build + budget | 139951 B gzip initial bundle, limit 153600 |
| make e2e (desktop + mobile-360) | 178 passed (52 s) on a quiet host |
| make scan (secrets, SAST, deps, workflows, web) | exit 0, no findings |

e2e note: in three earlier attempts made while the host was still loaded by the preceding suites (load average 13-15), the SR-060 spec (seeds 60 dishes) timed out at 30 s on seeding (`Request context disposed`) in 1-3 cases (also AC-004.7 and AC-006.1/2 on mobile in the first attempt). After the load dropped, the same spec seeds in about 9 s and all 178 pass. Same load sensitivity already noted in section 6; not a regression. Suggestion (INFO): raise the SR-060 test timeout or bulk-seed.

### New tests: do they fail without the fix?
- `tests/security/test_access_denial_log_cap.py` (5 tests): mutant with the cap disabled in `access/rules.py` (`count > LIMIT+1` -> never, `suppressed` -> False) gives RED: `test_100_random_id_reads_write_at_most_cap_plus_one_events` and `test_50_member_creates_write_at_most_cap_plus_one_denied_events` fail; file restored (cmp identical). The other three guard the other properties and pass by design: SR-058 threshold still detectable (12 events < cap, CAP > 10 asserted), per-account isolation, and counter failure keeps 404 / never 500 with no event. Quality: exact counts (CAP+1), exact `suppressed` payload, status codes asserted, real DB, no tautologies.
- `web/tests/unit/dishes/s07-form-frozen-version.test.tsx`: mutant using `existing.version` instead of `openedVersion` gives RED (`Expected "3", Received "4"` on If-Match); restored. The test really triggers a refetch (waits for `gets > 1`) so it is not vacuous.

### AC coverage
Tables in sections 2 and 3 still hold: every AC of US-004 (7) and US-006 (5) has a passing backend and web test. Gap check: none. Verdict: DONE, no open failures.
