# Code review · SL-01

- **Date:** 2026-10-22
- **Reviewer:** code-reviewer
- **Scope:** `git diff 08d6432` (working tree, uncommitted) plus untracked files: `backend/src/menu/platform/http/static.py`, `platform/logging.py`, `platform/config.py`, `platform/routing.py`, `platform/http/middleware.py`, `app/factory.py`, `__main__.py`; new backend tests (`tests/unit/test_static_*.py`, `test_stdlib_log_redaction.py`, `tests/tools/test_web_shell.py`, `test_container_web.py`, `test_ci_tiers.py`, `tests/support/assets.py`); `web/` (sources, config, scripts, tests; excluding `node_modules`, `dist`, `coverage`, `test-results`); `Dockerfile`, `.dockerignore`, `Makefile`, `scripts/ci.sh`, `.github/workflows/ci.yml`, `.semgrep/`, `osv-scanner.toml`, ADR-0017, edits to `docs/03`, `04`, `07`, `08`, `STATUS`.
- **Verdict:** APPROVED WITH FIXES (re-check, cycle 2: CR-SL01-004 still open)
- **Cycle:** 2

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL01-001 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/platform/logging.py:118` | A malformed stdlib log call bypasses redaction: `handleError` prints the raw message and arguments to stderr | FIXED |
| CR-SL01-002 | LOW | FIX-IN-SLICE | `backend/src/menu/platform/logging.py:79-82` | `exc_info=True` with no active exception logs `"exception": "NoneType"` | FIXED |
| CR-SL01-003 | LOW | FIX-IN-SLICE | `backend/src/menu/platform/logging.py:81,87-89,102-108,129-130` | Dead branches and untested branches in the new stdlib routing | FIXED |
| CR-SL01-004 | LOW | FIX-IN-SLICE | `docs/03-ux.md:1339-1357` | The new key table was inserted in the middle of the S-01 table, which leaves 8 rows orphaned | OPEN (fix incomplete) |
| CR-SL01-005 | LOW | FIX-IN-SLICE | `backend/src/menu/app/factory.py:25` | `_PROBLEM_REF` is still unused (CR-SL00a debt scheduled for SL-01) | FIXED (STATUS row to update) |
| CR-SL01-006 | LOW | BACKLOG | `web/src/main.tsx:15-23`, `web/src/i18n/index.ts:8` | If the lazy catalog chunk fails to load, the page stays blank with an unhandled rejection | OPEN |
| CR-SL01-007 | LOW | BACKLOG | `web/src/api/client.ts:20-26,118` | The "generated client" is not typed against `paths`, and no view calls the API | OPEN |
| CR-SL01-008 | LOW | BACKLOG | `web/playwright.config.ts:44-58`, `Makefile` `e2e` | The e2e tests run on local uvicorn, not on the image, PostgreSQL and the OIDC stub as plan §6.1/§6.2 and 08 §2 state | OPEN |
| CR-SL01-009 | LOW | BACKLOG | `backend/src/menu/platform/http/static.py:119-151` | Synchronous file read and gzip on the event loop on every request; `If-Modified-Since` and in-root symlink branches are untested | OPEN |
| CR-SL01-010 | LOW | BACKLOG | `web/tests/e2e/csp.spec.ts:153-175` | The frame-ancestors test passes by default on timeout | OPEN |
| CR-SL01-011 | LOW | BACKLOG | `web/scripts/i18n-check.mjs:19-35` | The check rewrites the committed catalog when it fails | OPEN |
| CR-SL01-012 | LOW | BACKLOG | `web/package.json:6`, `Dockerfile` (web stage), `ci.yml` | `packageManager: pnpm@12.14.0` has no integrity hash, so corepack downloads pnpm without pinning its content | OPEN |
| CR-SL01-013 | INFO | BACKLOG | `backend/src/menu/__main__.py:23`, `logging.py:129` | uvicorn errors are reduced to the logger name (e.g. a bind failure), and INFO lines from uvicorn are suppressed | OPEN |
| CR-SL01-014 | INFO | BACKLOG | `docs/adr/ADR-0017-…`, `test_web_shell.py:687` | Observations on the accepted HIGH-severity advisory and the date-based test | OPEN |

## Findings

### CR-SL01-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/platform/logging.py:118` (`structlog.stdlib.ProcessorFormatter(...)`, default `use_get_message=True`)
- **Category:** security (CWE-532)
- **Problem:** For foreign records, `ProcessorFormatter.format` calls `record.getMessage()` (structlog 26.1.0, `stdlib.py:1168`) before `_foreign_event` replaces the text. If formatting raises (wrong number of args, or an argument whose `__str__` raises), `logging.Handler.handleError` prints a traceback to stderr that includes `Message: '…'` and `Arguments: (…)`. This is exactly the free text that SEC-SL00b-006 wants to keep out of the logs. On Cloud Run, stderr goes to Cloud Logging as well.
- **Scenario:** Verified: `logging.getLogger("uvicorn.error").error("bad format %s %s", "SECRET-ARG")` → stderr contains `Arguments: ('SECRET-ARG',)`. A third-party library with a buggy log call, or a parameter object whose `__str__` fails, would print SQL values or user data.
- **Suggested fix:** pass `use_get_message=False` to `ProcessorFormatter`: the text is thrown away anyway, so this removes both the formatting cost (SQL parameters are rendered and then dropped) and the failure path. As defense in depth, also consider `logging.raiseExceptions = False` in `_configure_stdlib`.
- **Verification:** a unit test that logs `log.error("x %s %s", CANARY)` and an argument with a `__str__` that raises, and asserts with `capfd` that `CANARY` appears in neither `out` nor `err`.
- **Status:** FIXED (re-check 2026-10-22). `ProcessorFormatter(use_get_message=False, ...)` plus `logging.raiseExceptions = False` in `_configure_stdlib`. I re-ran the reproduction probe with: missing argument, an argument whose `__str__`/`__repr__` raises, `%d` with a string, a mapping argument, and `log.exception` with a secret in the exception message. stdout contained only `event`/`severity`/`timestamp`(/`exception`: type name), and **stderr was empty**. The regression test `test_bad_format_arguments_leak_nothing_on_stdout_or_stderr` checks both `out` and `err` with `capfd`.

### CR-SL01-002 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/platform/logging.py:79-82`
- **Category:** correctness
- **Problem:** With `exc_info=True` and no active exception, stdlib normalizes it to `(None, None, None)`. The tuple is truthy, so `exc = None`, and the record gets `"exception": "NoneType"` (tester note, reproduced).
- **Scenario:** `logging.getLogger("uvicorn.error").error("x", exc_info=True)` outside an `except` block → `{"event":"stdlib.uvicorn.error","exception":"NoneType",…}`. It is misleading in alerts and searches.
- **Suggested fix:** `exc = exc_info[1] if isinstance(exc_info, tuple) else exc_info` followed by `if isinstance(exc, BaseException): event_dict["exception"] = type(exc).__name__`.
- **Verification:** a test that calls `log.error("x", exc_info=True)` with no exception and asserts that `"exception"` is not in the record.
- **Status:** FIXED (re-check 2026-10-22). `exc = exc_info[1] if isinstance(exc_info, tuple) else None` plus a guard of `isinstance(exc, BaseException)`. The probe shows no `exception` key for `exc_info=True` outside `except`, and `test_exc_info_true_without_active_exception_logs_no_exception_field` covers it.

### CR-SL01-003 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/platform/logging.py:81` (non-tuple branch), `:87-89` (`warn`/`exception` keys), `:102-108` (`stream` setter), `:129-130` (root level)
- **Category:** tests / maintainability
- **Problem:** For foreign records, `method_name` is always `record.levelname.lower()` and `exc_info` is always a tuple, so the `"warn"` and `"exception"` keys in `_stdlib_severity` and the non-tuple branch can never run. Branch coverage measured by the unit tests is 94%, and line 130 (`root.setLevel(WARNING)`) is never run. The redirection of the root logger level, which decides what reaches the logs, has no test.
- **Scenario:** A future change to the root level (for example `NOTSET` set by a library) has no test that catches it.
- **Suggested fix:** remove the dead branches (or reduce `_stdlib_severity` to `record.levelname`), and add tests for: root at `NOTSET` or `ERROR` → `WARNING`; `INFO` from a library not emitted; output written to the current `sys.stdout`.
- **Verification:** `pytest tests/unit --cov=menu.platform.logging --cov-branch` → 100% on the new functions.
- **Status:** FIXED (re-check 2026-10-22). `_stdlib_severity` is reduced to `method_name.upper()`, and the `warn`/`exception` keys are gone. New tests cover: the root level pulled to WARNING from NOTSET/ERROR/CRITICAL, INFO suppressed while WARNING/CRITICAL are mapped, the `stream` setter ignored, and writes to the current `sys.stdout`. Coverage of `logging.py` is 97% with branches. The only miss is line 66 (`redact` non-scalar → type name), which is pre-existing SL-00a code outside this finding's scope.

### CR-SL01-004 · LOW · FIX-IN-SLICE
- **Location:** `docs/03-ux.md:1339-1357`
- **Category:** maintainability (documentation)
- **Problem:** The "Guscio dell'applicazione" block (heading, table and note) was inserted after the `auth.cancelled` row, inside the "Accesso (S-01)" table. The rows from `auth.failed` to `auth.removed.body` now follow the "Note:" paragraph without a header row, so they no longer render as a table.
- **Scenario:** Anyone reading the catalog (and `tests/support/ux-catalog.ts`, if it parses the tables) loses 8 S-01 keys.
- **Suggested fix:** move the new block after `auth.removed.body` (the ux-designer owns the file).
- **Verification:** markdown preview; `pnpm test` (catalog.test) stays green.
- **Status:** OPEN (re-check 2026-10-22, fix incomplete). The "Guscio dell'applicazione" block was moved after `auth.removed.body` (correct), but the **blank line it left behind is still there** at `docs/03-ux.md:1338`, between the `auth.cancelled` row (1337) and the `auth.failed` row (1339). In GFM, a blank line ends the table, so the 8 rows from `auth.failed` to `auth.removed.body` still render as a paragraph with no header or delimiter row. `web/tests/support/ux-catalog.ts` parses line by line, so `pnpm test` stays green and does not detect this. **Fix:** delete line 1338 (one blank line). **Verification:** markdown preview shows a single S-01 table with 13 rows.

### CR-SL01-005 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/app/factory.py:25`
- **Category:** maintainability
- **Problem:** The constant `_PROBLEM_REF` is unused. The debt row "CR-SL00a-007..013" in `docs/STATUS.md` schedules it for SL-01.
- **Suggested fix:** remove it, and update the debt row.
- **Verification:** `grep -rn _PROBLEM_REF backend/src` returns nothing; ruff and mypy stay green.
- **Status:** FIXED (re-check 2026-10-22). The constant was removed, and `grep -rn _PROBLEM_REF backend/src` returns nothing. Ruff and mypy are clean. Leftover bookkeeping: the debt row "CR-SL00a-007..013" in `docs/STATUS.md:96` still lists "unused `_PROBLEM_REF` in factory.py". The orchestrator should remove that item when it updates STATUS.

### CR-SL01-006 · LOW · BACKLOG
- **Location:** `web/src/main.tsx:15-23`, `web/src/i18n/index.ts:8`
- **Category:** correctness (robustness) / performance
- **Problem:** The catalog is a separate lazy chunk (`messages-*.js`), loaded in series after the main bundle. If loading fails (unstable network, or a deploy that removed the previous hash), `activateLocale()` rejects, nothing is rendered and there is no `catch`, so the page stays blank.
- **Scenario:** A user with an `index.html` cached before a deploy (`no-cache` reduces the risk but does not remove it) or with a flaky connection sees a white page.
- **Suggested fix:** with a single language, use `import.meta.glob(..., { eager: true })`. This adds about 2.4 KB gzip to the initial bundle, removes one round trip and removes the failure. When a second language arrives, add a `catch` that renders a minimal state.
- **Verification:** an e2e test that aborts the `messages-*.js` request (`page.route(...).abort()`) and expects visible content or a minimal error.
- **Status:** OPEN

### CR-SL01-007 · LOW · BACKLOG
- **Location:** `web/src/api/client.ts:20-26`, `:118`
- **Category:** design
- **Problem:** `get<T>(path: string)` accepts any path and any `T`. The generated `schema.gen.ts` constrains only `ErrorCode` and `ValidationCode` (useful), not the paths or the response types. The `api` singleton is not used by any view, so the objective "chiama l'API tramite il client generato" (the SPA calls the API through the generated client) is covered only by unit tests with an injected `fetch`.
- **Scenario:** In SL-03a, a typo in a path or a wrong DTO type compiles without errors, and the contract check (`api:check`) does not protect it.
- **Suggested fix:** before the first real consumer (`GET /session`, SL-03a), constrain the methods to `keyof paths` and derive the response type from `paths[P][M]["responses"][200]` (with a typed helper, without new dependencies).
- **Verification:** a `tsc` test with `// @ts-expect-error` on a non-existent path.
- **Status:** OPEN

### CR-SL01-008 · LOW · BACKLOG
- **Location:** `web/playwright.config.ts:44-58`, `Makefile` target `e2e`, `ci.yml` job `e2e`
- **Category:** design / tests
- **Problem:** Plan §6.1 (`e2e`: "build dell'immagine, compose con PostgreSQL e stub OIDC") and 08 §2 ("container completo") call for e2e tests on the image. The implementation starts `uv run python -m menu serve` with `web/dist` and a placeholder database. The image is covered separately by `test_container_web.py` (tier `container`). This is acceptable for a static shell, but it is a deviation that is not recorded in "Decisions during build".
- **Suggested fix:** record the deviation in STATUS or align the plan, and switch to the image (`E2E_BASE_URL`) in SL-03a, when the OIDC stub and the database become necessary.
- **Verification:** the plan or STATUS row is updated; from SL-03a, `make e2e` uses the image.
- **Status:** OPEN

### CR-SL01-009 · LOW · BACKLOG
- **Location:** `backend/src/menu/platform/http/static.py:119-151`, `:102`, `:161-164`
- **Category:** performance / tests
- **Problem:** Every request (including 304 and HEAD responses, and cache hits) runs `file.read_bytes()`. The first gzip of each file (`compresslevel=9`, ~350 KB of JS) runs synchronously on the event loop. Coverage shows the `If-Modified-Since` branch (161-164) and the rejection of an in-root symlink (102) untested. Edge case: a "naive" date (`-0000`) in `parsedate_to_datetime` is interpreted in local time.
- **Scenario:** With low traffic the impact is small. During a burst of first visits after a deploy, requests queue behind the compression.
- **Suggested fix:** precompute `(bytes, gzip, etag)` per file at startup (the dist is immutable in the image), or cache the body as well, keyed on `(path, mtime, size)`. Add tests for `If-Modified-Since` (including an invalid header) and for an in-root symlink.
- **Verification:** new tests; branch coverage of `static.py` at 100%.
- **Status:** OPEN

### CR-SL01-010 · LOW · BACKLOG
- **Location:** `web/tests/e2e/csp.spec.ts:153-175` (`setTimeout(() => resolve("bloccata"), 3000)`)
- **Category:** tests
- **Problem:** If the `load` event does not arrive within 3 s, for whatever reason, the test concludes "bloccata" (blocked) and passes. The assertion fails open.
- **Suggested fix:** on timeout, resolve to `"timeout"` and fail, or check the `frame-ancestors` violation or the frame's URL (`chrome-error://`). The header is already checked by `security-headers.spec.ts` and the pytest tests, so this is a refinement.
- **Verification:** temporarily remove `frame-ancestors` from `SECURITY_HEADERS` and confirm that the test goes red.
- **Status:** OPEN

### CR-SL01-011 · LOW · BACKLOG
- **Location:** `web/scripts/i18n-check.mjs:19-35`
- **Category:** maintainability
- **Problem:** The check runs `lingui extract --clean` on the committed catalog. When the catalog differs, it leaves the file rewritten ("ora aggiornato") and exits with 1. A verification step that changes the tree can mask the difference on a second run (in local use).
- **Suggested fix:** extract into a temporary copy (or restore `before` in every case) and print the diff.
- **Verification:** a test that runs the script on a misaligned catalog and checks that the file is unchanged.
- **Status:** OPEN

### CR-SL01-012 · LOW · BACKLOG
- **Location:** `web/package.json:6`, `Dockerfile` (stage `web`, `corepack enable && pnpm install`), `.github/workflows/ci.yml` (`corepack enable`)
- **Category:** security (supply chain, SR-076). To be confirmed by the security-engineer.
- **Problem:** `packageManager` pins the version but not the hash (`pnpm@12.14.0+sha512.<…>`), so corepack downloads pnpm without checking its integrity against a committed value. The base images are pinned by digest and the dependencies by the lockfile, but the tool that installs them is not.
- **Suggested fix:** add the `+sha512.…` suffix (corepack verifies it).
- **Verification:** `corepack pnpm --version` with a deliberately wrong hash fails.
- **Status:** OPEN

### CR-SL01-013 · INFO · BACKLOG
- **Location:** `backend/src/menu/__main__.py:23`, `backend/src/menu/platform/logging.py:129`
- **Category:** maintainability (operability)
- **Problem:** With `log_config=None` and redaction of the text, a startup error from uvicorn (for example "address already in use") becomes `{"event":"stdlib.uvicorn.error","severity":"ERROR"}` without the cause. The INFO messages ("Application startup complete") are no longer emitted. This is a deliberate trade-off for SEC-SL00b-006, but it should be documented.
- **Suggested fix:** a note in the runbook (`docs/09-release.md`, SL-10b) on how to diagnose startup locally. Alternatively, a narrow allow-list of uvicorn messages that carry no data.
- **Status:** OPEN

### CR-SL01-014 · INFO · BACKLOG
- **Location:** `docs/adr/ADR-0017-rischio-accettato-braces-strumenti-lingui.md`, `backend/tests/tools/test_web_shell.py:687`
- **Category:** design
- **Problem:** (a) The review contract says HIGH security findings "cannot be accepted". ADR-0017 accepts an upstream advisory rated HIGH (CVSS) in dev-only tooling, with residual risk assessed as low, a single-GHSA scope and an expiry date. This is consistent with the existing certifi pattern, but the security-engineer should confirm that the contract's rule does not apply to it. (b) `test_real_expiry_date_is_in_the_future_or_the_audit_goes_red` makes the suite go red from 2026-11-21. This is intentional and should be in the debt row (it is).
- **Status:** OPEN

## Tools run
| Tool | Command | Result |
|---|---|---|
| ruff | `uv run --frozen ruff check src tests` | All checks passed |
| ruff format | `uv run --frozen ruff format --check src tests` | 101 files already formatted |
| mypy | `uv run --frozen mypy` | Success: no issues found in 102 source files |
| bandit | `uv run --frozen bandit -q -c pyproject.toml -r src` | no output (clean) |
| pytest | `pytest tests/unit tests/architecture tests/tools/test_web_shell.py tests/tools/test_ci_tiers.py` | 644 passed |
| coverage | `pytest tests/unit --cov=menu.platform.logging --cov=menu.platform.http.static --cov-branch` | logging 94% (missing 66, 130), static 92% (missing 70, 102, 115, 161-164) |
| logging probe | scratch script (`exc_info=True` without an exception, wrong args) | `"exception": "NoneType"`; `Arguments: ('SECRET-ARG',)` on stderr |
| StaticSite probe | scratch script (websocket, IMS, 405, `/docs`) | WS denied 404; IMS 304; garbage IMS 200; POST 404 problem+json; `/docs` → index.html |
| eslint | `pnpm run lint` | 0 warnings |
| prettier | `pnpm run format:check` | All matched files use Prettier code style |
| tsc | `pnpm run typecheck` | clean |
| vitest | `pnpm run test` | 16 files, 413 passed; statements 97.85%, branches 95.18% |
| api:check | `pnpm run api:check` | schema.gen.ts is up to date |
| build + budget | `pnpm run build && pnpm run budget` | 109,056 B gzip, limit 153,600 |
| semgrep rule tests | `make scan-rules` | All tests passed; 16 path cases OK |
| Playwright | `E2E_PORT=8765 pnpm exec playwright test` | 38 passed, 76 failed. **All failures are environmental:** `chrome-headless-shell: libnspr4.so: cannot open shared object file` (system library missing on this host). Browser tests UNVERIFIED by the reviewer; the request-only tests pass |

Not run: `make ci` in full, `tier-container` (docker), `scan-sast`, `scan-deps`, `scan-web` (the security-engineer's responsibility).

### Re-check (cycle 2, 2026-10-22)
| Tool | Command | Result |
|---|---|---|
| leak probe (CR-001/002) | scratch script: `error("bad format %s %s", SECRET)`, an argument whose `__str__` raises, `%d` with a string, a mapping argument, `exc_info=True` without an exception, `exception()` with a secret | stdout: 6 redacted JSON lines, no secret; **stderr empty**; no `"NoneType"` |
| coverage | `pytest tests/unit --cov=menu.platform.logging --cov-branch` | 459 passed; logging 97% (only miss: line 66, pre-existing) |
| pytest | `pytest tests/unit tests/architecture tests/tools/test_web_shell.py tests/tools/test_ci_tiers.py` | 651 passed |
| ruff / format / mypy | as in cycle 1 | clean / 101 formatted / no issues in 102 files |
| vitest | `pnpm test` | green (statements 97.85%, branches 95.18%) |
| grep | `_PROBLEM_REF` in `backend/src` | none |
| 03-ux check | `sed -n 1328,1342p docs/03-ux.md` | blank line at 1338 still splits the S-01 table |
| SEC-SL01-001 (CSP) | diff `middleware.py`, `test_platform_headers.py`, `security-headers.spec.ts`; grep `createPolicy`/`trustedTypes`/`data:` in `web/src`, `web/index.html`, `web/dist` | `img-src 'self'` (no `data:`) and `trusted-types 'none'`, both asserted in pytest and e2e; neither the app nor the build uses `data:` images or TT policies. No regression |
| SEC-SL01-002 (.dockerignore) | diff, compared with the Dockerfile `web` stage | `**/.env*` and `**/node_modules` are excluded, and web tests/dist/results/playwright config are excluded. The build is `vite build` only (no `tsc` over the excluded `tests`/`playwright.config.ts`), so the image build inputs are intact. No regression found by reading; `docker build` not run by the reviewer |

## What was done well
- `StaticSite` uses an explicit allow-list (root files, a single level in `/assets`, known extensions) with a symlink and traversal check after `resolve`. It never falls back to `index.html` for an `/api` path, a dot-segment or a path with an extension, and it has a broad traversal test battery (`%2e%2e`, `%5c`, `%00`, symlink).
- `WEB_DIST_DIR` fails closed. `make scan-web` filters the pnpm report on a single GHSA with an expiry date and fails closed on an unreadable report, with tests for each variant. The `ErrorCode` → key map is exhaustive at compile time (`Record<ErrorCode, …>`) and tested against `openapi.json`.
- The INFO-10 and INFO-12 debt is closed with targeted negative tests. The CSP with Trusted Types is tested in the browser (innerHTML, insertAdjacentHTML, script, eval).

## Report — code-reviewer (re-check, cycle 2)
**Outcome:** DONE_WITH_CONCERNS
**Scope:** SL-01, re-check of CR-SL01-001..005, plus a regression check of the SEC-SL01-001/002 changes
**Files changed:** docs/reviews/SL-01-code.md
**Summary:** CR-SL01-001 (stderr leak), 002, 003 and 005 are FIXED and verified. The leak probe now leaves stderr empty and stdout redacted. CR-SL01-004 is still OPEN: the block was moved, but the stray blank line at `docs/03-ux.md:1338` still splits the S-01 table. The fix is to delete one line. The CSP and .dockerignore changes show no regression. No new findings (anti-loop rule).
**Evidence:** see "Re-check (cycle 2)" under "Tools run".
**Traceability:** SL-01; SEC-SL00b-006; SEC-SL01-001/002.
**Decisions needed:** none.
**Risks and technical debt:** CR-SL01-006..014 (BACKLOG) still need to be recorded in STATUS. Also remove `_PROBLEM_REF` from the CR-SL00a-007..013 debt row.
**Suggested next step:** delete the blank line at `docs/03-ux.md:1338`. The orchestrator can confirm it with a look, and no further code-review cycle is needed. Then the security-engineer re-check.

---

## Report — code-reviewer (cycle 1)
**Outcome:** DONE_WITH_CONCERNS
**Scope:** SL-01
**Files changed:** docs/reviews/SL-01-code.md
**Summary:** Review of the SL-01 diff (static SPA serving, web shell, i18n, error map, CI/Makefile/Dockerfile, stdlib log redaction). No BLOCKERs. 5 FIX-IN-SLICE: redaction bypass through `handleError` (MEDIUM), `"NoneType"` with `exc_info=True`, dead or untested branches in `logging.py`, broken table in 03-ux.md, unused `_PROBLEM_REF`. 7 LOW BACKLOG and 2 INFO.
**Evidence:** see "Tools run". Backend 644 passed, lint/type/bandit clean. Web: eslint, prettier, tsc clean, vitest 413 passed, budget 109 KB/150 KB. Playwright: browser tests not runnable on this host (missing libnspr4), so UNVERIFIED by the reviewer.
**Traceability:** SL-01; NFR-001 (budget), NFR-008, NFR-009, NFR-011; SR-023, SR-031, SR-046, SR-076; THR-070, THR-074, THR-075, THR-090; SEC-SL00b-006; SEC-SL00a INFO-10/INFO-12.
**Decisions needed:** none for the code. To confirm with the security-engineer: CR-SL01-012 (pnpm hash) and CR-SL01-014(a).
**Risks and technical debt:** CR-SL01-006…014 to record in STATUS. The e2e evidence for the slice must come from an environment with Chromium dependencies (`playwright install --with-deps` or CI).
**Suggested next step:** backend-developer fixes CR-SL01-001/002/003/005 with regression tests. The ux-designer (or orchestrator) fixes CR-SL01-004. Then targeted re-check, and the security-engineer runs the SL-01 review.
