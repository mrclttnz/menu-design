# SL-06a: security review

| Field | Value |
|---|---|
| Slice | SL-06a: week plan, ranges, meals of the day. Migration `0009` (`meal`, `meal_item`, `ix_meal_item_dish`, `app.effective_meals()`, `change_event` CK redefinition), `GET /plan`, `GET /meals/{date}/{mealType}/{slot}`, `PUT …/presence`, `planning` export contributor, web S-02 / D-05 / S-03 |
| Reviewer | security-engineer (mode B) |
| Date | 2026-11-07 |
| Diff base | `70cb367` (nothing committed: `git diff 70cb367` plus the untracked files from `git status`). Out of scope by brief: `backend/uv.lock`, `backend/pyproject.toml`, `web/pnpm-workspace.yaml`, `web/pnpm-lock.yaml`, `Dockerfile`, `.trivyignore.yaml`, `docs/adr/ADR-0018*`, `backend/tests/tools/*`, the trivy/certifi lines of `Makefile`. The one exception is the ADR-0018 zlib claim, covered in §5 |
| SRs in scope | SR-008, SR-060 (62 days), plus SR-022, SR-047, SR-057, SR-070 for the tracked presence write |
| THRs in scope | THR-020 (meals), THR-105, THR-046 / THR-100 / THR-117 (tracked write), THR-101 (cost) |
| Verdict | **APPROVED: 0 BLOCKER, 0 FIX-IN-SLICE**, 1 LOW BACKLOG, 6 INFO. ADR-0018 zlib claim **confirmed** (§5) |

The slice is sound. A meal is addressed only by `(date, mealType, slot)` and the family always comes from the session (ADR-0009). There is no foreign identifier to tamper with, so the classic IDOR does not exist. On top of that, every query carries an explicit `family_id = :family` predicate, with forced RLS on both new tables as the second line. The presence write follows the SL-05 pattern exactly:
- `tracked_write` sits outside `family_tx`;
- the row is created on demand and locked with `FOR UPDATE`;
- `412` comes before the cap, then the write and the event, all in one transaction;
- the lock order is meal row, then counter row (SL-05 INFO-2).

The body is a closed model with a `StrictBool`, so there is no mass assignment. The new `_check_key` allow-list and the redefined `ck_change_event_key` (`else false`) close the hole where an event of one unit carried the key columns of another, in both Python and the database. `app.effective_meals` is `SECURITY INVOKER`, schema-qualified and `EXECUTE`-revoked from `PUBLIC`. The web pages render all user text as React text nodes.

The one point worth scheduling is the cost of `GET /plan` in the worst case (SEC-SL06a-001). Reads are limited per session only, and the heaviest read is now about 1.25 MB of uncompressed JSON and about 100 ms of CPU.

## 1. What was checked and how

**Files read in full:**
- new: `migrations/versions/0009_meal.py`, `menu/planning/{__init__,api,export,meals,schemas}.py`, `menu/views/plan.py`;
- changed: `menu/access/matrix.py`, `menu/app/factory.py`, `menu/catalog/{__init__,dishes,schemas}.py` (`read_refs`, `DishRef`, `CourseRef`), `menu/history/record.py` (`_check_key`), `menu/views/{__init__,schemas}.py`;
- re-checked for the new callers: `menu/family/access.py` (`family_access`: `session_guard` on writes, `session_reader` on reads), `menu/ratelimit/tracked.py` (`tracked_write`, `consume_tracked_write`), `menu/ratelimit/{rules,middleware}.py` (which limits apply to reads), `menu/platform/http/problem.py` (`_translate`: no input reflected), `menu/platform/http/static.py` (gzip, for §5);
- tests: `tests/security/authz_matrix.yaml` (diff), `support/{tracks,inventory}.py` (diff), the test lists of `security/test_meals_access.py`, `security/test_meals_isolation.py`, `db/test_effective_meals.py`, `integration/test_meal_read.py` (malformed keys, slot bounds);
- web: `web/src/api/{plan.ts,client.ts}` (diff), `features/plan/{MealPage,PlanPage,shared}.tsx/ts` (URL parameters and rendering of user text), `lib/{pasto-id,aria-style,dates}.ts`, `app/routes.tsx`, `main.tsx` (diff);
- docs: STATUS, plan §SL-06a and §4.3, threat model (THR-020, THR-046, THR-100, THR-101, THR-105), the SRs in scope, `SL-06a-verification.md`, ADR-0018.

**Tools run (fresh output, 2026-11-07):**

| Command | Result |
|---|---|
| `make scan-secrets` (gitleaks `git` + `dir`, `--redact`) | **no leaks found** (12 commits ~3.99 MB; working tree ~10.91 MB, untracked files included). Root `istruzioni-run-manuale.txt` and `package.json` (untracked) also checked by hand: no credentials |
| `make scan-rules` | rule tests passed; 23 path cases OK |
| `semgrep --no-git-ignore` (`p/python p/owasp-top-ten p/typescript p/react .semgrep`) on `0009`, `planning/`, `views/`, `history/`, `catalog/`, `access/`, `web/src/{features/plan,api,components/ActionMenu.tsx,lib,app,main.tsx,i18n}` | 239 rules, 71 targets, **0 findings** (the default scan skips untracked files, see SL-05 INFO-4) |
| `bandit -q -c pyproject.toml -r` on `planning/`, `views/`, `history/`, `catalog/`, `0009` | no issues |
| `grep` for `innerHTML`, `dangerouslySetInnerHTML`, `eval(`, `new Function`, `createHTML` in `web/src` | none (only the two existing `href`s from SL-01/SL-04) |
| `osv-scanner` on `uv.lock` + `pnpm-lock.yaml` (project config) | **No issues found** (79 + 382 packages; the known unused ignore GHSA-vfj7-8cjw-p6xm) |
| `pytest -n 4` `security/test_meals_access.py security/test_meals_isolation.py security/test_change_event_security.py db/test_effective_meals.py db/test_meal_schema.py architecture/test_tracked_writes_are_capped.py unit/test_record_change_key.py` (local PostgreSQL 17, TLS) | **208 passed** |
| `trivy image` on the latest built image `menu-design-test:f87c5303` (2026-11-07 17:20 UTC), project flags (`--ignorefile .trivyignore.yaml --severity HIGH,CRITICAL --ignore-unfixed`) | exit 0; without the ignore file: **2 HIGH, both `zlib1g`** (CVE-2026-76844, CVE-2026-85091), nothing else. See §5 |
| Image filesystem export + `readelf -d` / `nm -D` on every ELF file that links `libz.so` | gz* imports **only** in `/usr/bin/dpkg-deb` and `libapt-pkg.so` (§5) |

The tester's evidence is taken as given (brief): `make ci` green, 417 SL-06a backend tests, 10 of 12 access-rule mutations killed with the gap closed, and the worst-case `GET /plan` at 1,245,568 bytes and p95 125 ms. I did not rerun the full suite.

## 2. Findings

### SEC-SL06a-001 · LOW · BACKLOG (SL-10a, with the load measurement)
- **Location:** `backend/src/menu/ratelimit/middleware.py:99` (reads limited only by `API_SESSION`, 300/min **per session**; `WRITE_ACCOUNT` exists only for writes) together with `backend/src/menu/views/plan.py:78-113` (heaviest read: up to 62 days × 9 meals × 10 items, no response compression for the API)
- **Category:** security (CWE-770 Allocation of Resources Without Limits or Throttling; CWE-400)
- **Problem:** every response stays bounded by the schema (about 1.25 MB, tested). But the read budget is per session, and an account can hold 20 sessions. One account can therefore ask for up to 6,000 `GET /plan` per minute. Each one costs about 100 ms of Python CPU (the tester's single-request figure) and about 1.25 MB of uncompressed egress. Starlette's `GZipMiddleware` is not used, and `static.py` compresses only SPA files.
- **Scenario:** a Planner, the THR-100 insider, fills 62 days with 10 items per meal. That takes about 558 content writes in SL-06b, well inside the cap. They then run a script over a few sessions that loops on `GET /plan?from=…&to=…` (62 days). Arithmetic, not measured on Cloud Run:
  - about 6 sessions × 300/min × 0.1 s = 180 CPU-s/min, more than the 2 instances × 1 vCPU allowed by `max-instances=2` (THR-101), so other families' requests queue;
  - egress is about 375 MB/min per session, so a sustained run reaches a few euro per hour. The 1 € / 5 € budget alerts fire, but someone must act on them.

  Even a Member, who cannot write, can run the same loop over a plan that a Planner filled normally. With realistic plans (about 60 KB, the tester's estimate) the effect is roughly 20 times smaller.

  Why LOW: it needs an authenticated insider of a tester family, it leaves no data exposure, it stops when the script stops, and THR-101 bounds the bill.
- **Suggested fix (proportionate, pick one or both in SL-10a):**
  1. a per-account read budget that reuses the existing machinery: one more `Hit(rules.API_ACCOUNT, account_id)` in `middleware.py`, for example 600/min. Two sessions of normal use stay far below it, and the whole account can no longer multiply the per-session budget by 20;
  2. compression for `GET /plan` only, for example a route-level gzip of the JSON above 4 KB. Repetitive JSON shrinks about 10-20×. BREACH does not apply: the body carries no secret (no CSRF token) and no attacker-chosen reflected input from another party. Do not enable it globally without checking `GET /session`, which carries the CSRF token.

  Also add the scenario to the SL-10a Locust run (08 §14.1): one account, N sessions on a worst-case `GET /plan`, while another family's p95 is measured.
- **Verification:** a rate-limit test: the 601st read in a minute from one account across 3 sessions gets `429` with `Retry-After`, and another account is unaffected. If compression is chosen: a contract test that `GET /plan` with `Accept-Encoding: gzip` answers `Content-Encoding: gzip`, while `GET /session` does not. Load scenario recorded in `docs/08-test-strategy.md` §14.1.
- **Status:** OPEN (BACKLOG). Recorded in THR-101 (threat model updated).

## 3. INFO (no action required in SL-06a)

- **INFO-1 · THR-020 on meals: no "404 + `access.cross_family`" by design (tester N-2).** I confirm that ADR-0009 addressing is the right mitigation and is stronger than a `404` check. The family comes only from the session, every SQL statement in `planning/meals.py` and `catalog.read_refs` filters on `family_id = :family`, and forced RLS `p_family` is the second layer. `test_meals_isolation.py` proves it both ways, including the "same key, other family" write and the body `familyId` refused whole. SR-008's "404 + event" becomes testable in SL-06b for dish and course references in the body (SR-041). That test must be there. The SL-06a "Test" line in the plan should be amended (tech-lead).
- **INFO-2 · `effective_meals` has no internal range bound.** `generate_series(0, p_to - first_day)` would generate millions of rows if a future caller passed an unbounded range. Today the only callers pass `MAX_DAYS` ≤ 62 or a single day, and only `menu_app` can call it. If a later slice (SL-14 freeze, SL-21 copy) calls it with a range coming from data, cap it there.
- **INFO-3 · Removed content stays in the row and in the family export.** `_RANGE_ITEMS` reads the items of removed and hidden `inherit` rows and drops them in Python (bounded, about 5,580 rows maximum, never returned, tested by the new `test_a_removed_meal_never_shows_the_content_left_in_its_row`). `PlanningExport` exports them deliberately (05-data §4.2). Free text can contain names typed by the family (SL-05 INFO-5). The erasure work in SL-27/SL-30 must count `meal.name`, `meal_item.free_text` and `meal.guests_note` of removed meals as well.
- **INFO-4 · One tracked write, up to two events.** Re-adding a removed meal that had guests writes `meal_content` + `meal_guests` but consumes one unit of the cap. That is consistent with SR-070, which counts writes. It is reachable only from SL-15, when guests can be set, and the extra event is small. The INFO-1 arithmetic of SL-05 still holds.
- **INFO-5 · SEC-SL05-003 (timezone window) now also covers the presence write.** It is unchanged and still scheduled for SL-09.
- **INFO-6 · Trusted Types and CSP on the new pages.** No new sink. `reserveAriaStyleId()` stops React Aria from injecting an inline `<style>` (it would violate `style-src 'self'`) by occupying the id with an empty `<meta>`. That is harmless, and the rule lives in `base.css`. The lazy chunks load through `import()`, which is not a Trusted Types sink, and the e2e run asserts no CSP violations. URL parameters are validated before use (`isIsoDate`, `fromPastoId` with an anchored allow-list regex), the API path is built with `encodeURIComponent`, and `addRetryAfter` accepts only `^[0-9]{1,6}$`.

## 4. Threats and requirements

| ID | Status after SL-06a | Evidence |
|---|---|---|
| THR-020 (meals and plan) | **Mitigated and verified for reads and for the presence write.** No foreign identifier in the path. Explicit `family_id` predicate in every statement, forced RLS on `meal` and `meal_item`, composite FKs `(family_id, dish_id)` and `(family_id, course_id)` on `meal_item`, no family selector in query, header or body. Body references are SL-06b | `test_meals_isolation.py`, `test_meal_schema.py` (cross-family FKs), `test_effective_meals.py::test_each_family_sees_only_its_own_defaults_and_rows`, `test_inventory_rls.py`; fresh run in §1 |
| THR-105 | **Mitigated and verified.** `today` and `past` come from `app.family_today()`, and the range parameters never move `today`. Past meals stay editable by design (FR-041) | tester §2 (shifted `now_utc` in both directions, mutant M7 killed) |
| THR-100 / THR-046 / THR-117 | **Unchanged and holding for the new write.** `meal.presence.write` is in `TRACKS`, the architecture test checks that every tracked route uses `tracked_write`, the at-the-cap case in `assert_tracks` gives `429` with no state change, and the event is in the same transaction | `test_tracked_writes_are_capped.py`, `test_meal_presence.py` (`assert_tracks` with `window_start`) |
| THR-101 | Residual from SEC-SL06a-001 recorded | §2 |
| SR-008 | Met for SL-06a (see INFO-1 for the "404 + event" part) | as THR-020 |
| SR-060 | 62 days enforced on the server (`MAX_DAYS`) **before** any range query. 63+ days and `0001-01-01..9999-12-31` → `422 range_too_large {maxDays: 62}`. Dates parsed with an ASCII-anchored regex. Slot outside the allow-list → `404`, never `500` | tester §2, M6 killed; `test_meal_read.py` malformed keys |
| SR-022 / SR-057 | `change_event` stays append-only. The CK redefinition keeps the names, uses `NOT VALID` + `VALIDATE`, and restores the 0008 definitions on downgrade | `test_change_event_schema.py`, `test_migrations.py` |
| SR-047 | Events carry IDs and codes. Free text of removed items is in `before` by design (codec `t`, as in SL-05 INFO-5). No meal content in logs: `planning` logs nothing | `test_the_event_holds_no_name_no_email...` (tester §3.5) |
| SR-070 | The presence write consumes one unit, after `412` and before the write. A refused request consumes nothing | M8 killed; `assert_tracks` |

Other checks with no finding:
- **Authorization:** the three operations are in the matrix (A/P/M read, A/P write), deny by default for unknown operations, and the role is re-read on every request (demotion and removal tested). The permission check runs in the dependency, before body and `If-Match` validation, so a Member gets `403` with no validation leak (AC-008.8 test).
- **CSRF and CORS:** `writes=True` → `session_guard` (mutant M2 killed). No CORS headers on the new routes (tested).
- **Mass assignment:** `PresenceChange` is `extra="forbid"` with camelCase aliases only and `present: StrictBool`. `"true"`, `1` and extra fields → `422`.
- **SQL:** every statement is a SQLAlchemy `text()` with bound parameters, with no string building from input (semgrep custom SQL rules clean). `effective_meals`: `SECURITY INVOKER`, `STABLE`, every object qualified with `app.` or `pg_catalog.`, `EXECUTE` revoked from `PUBLIC` and granted only to `menu_app` (tested). The `SECURITY DEFINER` inventory is unchanged (empty for app functions). Grants on `meal` and `meal_item` follow the 0005/0007 pattern: `menu_app` CRUD, `menu_backup` SELECT, `menu_console` nothing.
- **Concurrency:** `INSERT … ON CONFLICT DO NOTHING` then `FOR UPDATE` means that of two first writes with version 0, one succeeds and the other gets `412` (race tests). No lock-order inversion with `set_status`.
- **Errors and logs:** invalid path values become `422` through `_translate`, which never echoes `input`. The `412` body carries only the caller's own meal through `_load`, which hides removed content. `_check_key` failures are a generic `500` (fail closed).
- **If-Match:** compared in Python against the version read, so a huge value can never overflow in SQL (THR-107).

What is done well: addressing meals by a natural key scoped by the session removes the IDOR class instead of guarding against it. The `tracks` inventory with the new at-the-cap check in `assert_tracks` turns "every tracked write is capped and leaves nothing on failure" into a property that future slices cannot silently break.

## 5. ADR-0018: does the app use the vulnerable zlib gz* functions?

**Claim confirmed. Contextual severity: LOW (upstream HIGH). The dated exception is consistent with the review contract.**

- **The CVEs.** trivy's descriptions put both in zlib's **gz\* file API**. CVE-2026-76844 is in `gz_write()` (stale `strm.next_in` after a failed `write()`, then a later `gz*` write). CVE-2026-85091 is in `gz_vacate()` (non-blocking `gzwrite()` / `gzprintf()`). Neither touches `deflate`/`inflate` used through `z_stream`. Side note: trivy's DB shows a wrong *title* for CVE-2026-76844 ("webpack-dev-middleware…"), but the description is the zlib one. The ADR summary ("overflow dell'heap in `gz_vacate()`") fits only the second CVE; the first is in `gz_write()`. Harmless, but worth one word in the ADR.
- **Who imports gz\* in the image** (filesystem export of `menu-design-test:f87c5303`, `nm -D --undefined-only` on every ELF that links `libz.so`):
  - `/usr/bin/dpkg-deb` and `libapt-pkg.so.7.0` use `gzdopen/gzread/gzwrite/…`. These are package-management tools. The app never runs them: no `subprocess` in the server code (the only `subprocess` is `console_client`, which runs on the operator's machine), the container runs as uid 10001 with a read-only filesystem, and there is no shell entry point;
  - CPython `zlib` and `binascii`, `libcrypto.so.3`, and psycopg's bundled `libssl`/`libcrypto` link `libz` but import **no** gz\* symbol. They use the stream API only. No wheel bundles its own copy of zlib (`libz.so.1.3.1` is the only library that defines the gz\* functions).
- **Where zlib processes data at runtime:**
  - `platform/http/static.py` calls `gzip.compress()` on SPA build files. Python's `gzip` module writes the gzip format in pure Python over `zlib.compressobj`, not `gzopen`, and the input is the trusted build output;
  - `httpx` inflates `Content-Encoding: gzip` responses from Google's OIDC endpoints over TLS (`zlib.decompressobj`, stream API);
  - `authlib`/`joserfc` have JWE `zip=DEF` support, but the app verifies JWS ID tokens only.

  **Request bodies never reach zlib.** No middleware decompresses request bodies, and the API sends no compressed responses (see SEC-SL06a-001). The ADR sentence "l'input non fidato che raggiunge zlib è il corpo di richieste e risposte" is therefore more pessimistic than reality. It could be corrected to "nessun corpo di richiesta raggiunge zlib; solo risposte di Google via TLS e file statici propri, sempre con l'API a flusso".
- **Conclusion:** the vulnerable code paths are not reachable from the application or its dependencies. Exploiting them would need code execution in the container first. The narrow, dated `.trivyignore.yaml` (two IDs, `expired_at: 2026-11-21`) is proportionate. Keep the reopening triggers in the ADR. A cheap alternative is option (a) or removing `dpkg`/`apt` from the final stage. I don't recommend either now. Replacing the base digest as soon as a fixed slim image appears is enough.

## Report — security-engineer
**Outcome:** DONE
**Scope:** SL-06a (mode B, security-sensitive)
**Files changed:** `docs/reviews/SL-06a-security.md` (new), `docs/06-threat-model.md` (SL-06a status for THR-020, THR-101, THR-105, and a header note)
**Summary:** I reviewed the plan and meal reads, the tracked presence write, migration 0009 (RLS, grants, `effective_meals`, the change_event CK redefinition), the EventKey allow-list, the export contributor, the authz matrix and the new web pages. There are no BLOCKER or FIX-IN-SLICE findings. One LOW BACKLOG finding: reads are limited per session only, so the about 1.25 MB / 100 ms worst-case `GET /plan` can be multiplied across 20 sessions per account (CPU and egress cost, THR-101). The proportionate fix is a per-account read budget and/or gzip on `/plan`, scheduled with the SL-10a load test. The ADR-0018 claim is confirmed: gz\* functions are used only by dpkg/apt, never by the app.
**Evidence:** gitleaks git+dir: no leaks; semgrep (`--no-git-ignore`, 239 rules, 71 targets): 0 findings; bandit: no issues; osv-scanner: no issues; 208 slice security/db tests passed; trivy (project flags) exit 0, 2 HIGH zlib1g without the ignore file; `nm -D` on the exported image: gz\* imports only in `dpkg-deb` and `libapt-pkg`.
**Traceability:** SR-008, SR-060, SR-022, SR-047, SR-057, SR-070; THR-020, THR-105, THR-046, THR-100, THR-101, THR-117; ADR-0009, ADR-0018
**Decisions needed:** none for SL-06a. For SL-10a: choose the control for SEC-SL06a-001: (a) per-account read budget (a few lines, stops multiplying across sessions), (b) gzip on `GET /plan` only (cuts egress 10-20×, not CPU), or (c) both. Recommendation: (a), plus (b) if the load test shows egress matters.
**Risks and technical debt:** SEC-SL06a-001 (LOW, SL-10a); SEC-SL05-003 still open for SL-09; ADR-0018 expires 2026-11-21.
**Suggested next step:** orchestrator: record SEC-SL06a-001 as debt in STATUS and close the SL-06a security gate. Tech-lead: amend the SL-06a "Test" line (INFO-1) and make sure SL-06b tests the body-reference "404 + `access.cross_family`". Devops: optionally correct the two ADR-0018 wording points in §5.
