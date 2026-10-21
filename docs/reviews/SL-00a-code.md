# Code review · SL-00a

- **Date:** 2026-10-20
- **Reviewer:** code-reviewer
- **Scope:** `git diff 44a5a03` (`.gitignore`, `docs/07-plan.md`, `docs/STATUS.md`) plus all untracked files of the slice: `backend/` (pyproject, uv.lock, `src/menu/**`, `scripts/export_openapi.py`, `tests/**`), `Makefile`, `scripts/ci.sh`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`, `.gitleaks.toml`, `.semgrep/**`, `.semgrepignore`, `.env.example`, `openapi.json`
- **Verdict:** APPROVED WITH FIXES
- **Cycle:** 1

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL00a-001 | LOW | FIX-IN-SLICE | `backend/tests/unit/test_platform_authz_route.py:22,39,58`; `backend/src/menu/platform/routing.py:28-32,45-48` | The "refuses to start" tests accept any exception, and two rejection branches (bad `operationId`, `family` with no roles) are never tested | OPEN |
| CR-SL00a-002 | LOW | FIX-IN-SLICE | `backend/tests/contract/test_openapi_contract.py:82-89`; `backend/tests/support/probe.py:114-116` | No test shows the public-route inventory check can fail; the `/rogue-public` probe route is dead | OPEN |
| CR-SL00a-003 | LOW | FIX-IN-SLICE | `backend/tests/unit/test_platform_headers.py:52,64`; `backend/tests/unit/test_platform_if_match.py:85-90`; `backend/tests/unit/test_platform_logging.py:99-101` | Some test cases don't test what their names say (the "405" case is a 415, the "If-Match before body" case is a JSON decode error, and the forged-severity value gets dropped) | OPEN |
| CR-SL00a-004 | LOW | FIX-IN-SLICE | `Makefile:25-26,34-38`; `backend/tests/tools/test_supply_chain.py:34-37` | `uv sync/run --frozen` never checks that `uv.lock` still matches `pyproject.toml` | OPEN |
| CR-SL00a-005 | LOW | FIX-IN-SLICE | `.github/workflows/ci.yml:78-81`; `.semgrep/sql.py`; `.semgrep/migrations-now.yaml` | Only 1 of the 4 custom semgrep rules (2 of its 6 patterns) has a `semgrep --test` fixture; the path-scoped rules silently stop matching outside a git root | OPEN |
| CR-SL00a-006 | LOW | FIX-IN-SLICE | `backend/src/menu/app/factory.py:22-30`; `openapi.json` (`default` response) | The OpenAPI contract publishes errors as both `application/problem+json` and `application/json`. Removing one after SL-01 would be a non-additive change | OPEN |
| CR-SL00a-007 | LOW | BACKLOG | `backend/src/menu/platform/http/middleware.py:78-81` | `BodyGuardMiddleware` skips the size and depth limits when there is no `Content-Length` and no `Transfer-Encoding` (fail-open branch) | OPEN |
| CR-SL00a-008 | LOW | BACKLOG | `backend/src/menu/platform/http/client_ip.py:31-34`; `backend/src/menu/platform/http/problem.py:126-133,158`; `backend/src/menu/platform/logging.py:65` | Platform branches with no tests: `client_ip(request)`, the `too_long`/URL/date translations, other HTTP statuses mapped to 500 | OPEN |
| CR-SL00a-009 | LOW | BACKLOG | `Makefile:92-96` | In `scan-deps`, the `rc=$?; rm -f …; exit $rc` sequence never runs on failure because of `-e` | OPEN |
| CR-SL00a-010 | LOW | BACKLOG | `.pre-commit-config.yaml:11,17` | The hooks call `uv run` without `--frozen`, so a commit can relock or sync | OPEN |
| CR-SL00a-011 | LOW | BACKLOG | `backend/pyproject.toml:37-41`; `docs/STATUS.md`; `backend/tests/tools/test_supply_chain.py` | The certifi cooldown exception is not in the STATUS technical debt, and no test limits `exclude-newer-package` to certifi | OPEN |
| CR-SL00a-012 | INFO | BACKLOG | `backend/src/menu/platform/http/middleware.py:126,142`; future server entrypoint | `correlation_id` is only in structlog contextvars, not in `scope["state"]`; uvicorn's access log, once enabled, logs query strings | OPEN |
| CR-SL00a-013 | INFO | BACKLOG | `.github/workflows/ci.yml:127`; `Makefile:21` | The `pull_request_target` grep misses `on: pull_request_target` (zizmor still covers it); `make help` lists `test` as active although it fails by design | OPEN |

## Findings

### CR-SL00a-001 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/unit/test_platform_authz_route.py:22`, `:39`, `:58`; `backend/src/menu/platform/routing.py:28-32` (`_family_needs_roles`), `:45-48` (`operation_id` format)
- **Category:** tests
- **Problem:** The slice requires a test that "an app with a route without `authz` does not start". The three tests use `pytest.raises(Exception)` with `B017/PT011` suppressed, so any error passes them, including a `TypeError` from a wrong fixture or a typo in the test itself. Coverage also shows that `routing.py:31` (family scope with no roles) and `routing.py:46` (missing or malformed `operation_id`) never run.
- **Scenario:** a regression makes `validate_authz` stop checking the `operationId` format, or makes the family validator a no-op. Every test stays green. Separately, if a test breaks in a way that raises `TypeError` (for example a wrong keyword argument to `router.get`), the test still passes without checking authz at all.
- **Suggested fix:** use `pytest.raises(ValueError, match="x-authz")` (or `match="AuthzRoute"` / `match="operation_id"` as appropriate). `routing.py` always raises `ValueError` with a stable message. Add these parametrized cases: `{"scope": "family"}` (no roles), `{"scope": "public", "extra": 1}` (unknown key), `operation_id=None`, `operation_id="health"`, `operation_id="Platform.Health.Read"`.
- **Verification:** `uv run pytest tests/unit/test_platform_authz_route.py --cov=menu.platform.routing --cov-report=term-missing` shows lines 31 and 46 as covered.
- **Status:** OPEN

### CR-SL00a-002 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/contract/test_openapi_contract.py:82-89`; `backend/tests/support/probe.py:114-116`
- **Category:** tests
- **Problem:** The closed public-route inventory (plan §4.1, SR-009) is only checked against the real app, which has only `/healthz`, so the test can't fail today. The probe router defines `/_probe/rogue-public`, clearly meant to show that the check catches an extra public route, but no test uses it.
- **Scenario:** a refactor of `test_public_routes_are_exactly_the_closed_inventory_subset` (or of `_operations`) breaks the comparison, for example by reading `x-authz` from the wrong level. The test stays green. The first real extra `public` route (for example in SL-03a) would then pass unnoticed.
- **Suggested fix:** factor the inventory check into a helper (for example `public_routes_outside_inventory(schema) -> set`) and add a test that builds `create_app(extra_routers=[build_probe_router([])]).openapi()` and asserts `("get", "/_probe/rogue-public")` is in the result. Otherwise delete the dead route.
- **Verification:** the new test fails if the helper returns `set()` unconditionally.
- **Status:** OPEN

### CR-SL00a-003 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/unit/test_platform_headers.py:52` (id `"405"` at `:64`); `backend/tests/unit/test_platform_if_match.py:85-90`; `backend/tests/unit/test_platform_logging.py:99-101`
- **Category:** tests
- **Problem:** Three test cases claim more than they check:
  1. `("POST", "/healthz", {})` has no `Content-Type`, so `BodyGuardMiddleware` answers **415** before routing. The 405 → `not_found` path never runs in the header test. I confirmed that `POST /healthz` with `Content-Type: application/json` gives 404 via `http_exception_handler`, but no header test covers it.
  2. `test_if_match_checked_before_body_validation_order_is_stable` sends `{bad`. FastAPI rejects it as `json_invalid` while reading the body, before `expected_version` runs. The test proves nothing about If-Match ordering.
  3. In `test_newlines_in_values_are_neutralised`, the `detail=` value (the one carrying `severity=CRITICAL`) is dropped by the allow-list, so only `path` actually tests newline neutralisation.
- **Scenario:** a regression in the security headers on the 405 path, or in If-Match handling with a well-formed body, would not be caught.
- **Suggested fix:** (1) add `"headers": {"Content-Type": "application/json"}, "content": b"{}"` to the 405 case. (2) Rename the test, or send a valid `{}` body with `If-Match: *` and assert `errors[0].field == "If-Match"`. (3) Put the forged value in an allowed field (for example `event` or `path`), or call `redact` directly.
- **Verification:** the 405 case returns 404 `not_found` with the headers; the If-Match case asserts the `If-Match` field error.
- **Status:** OPEN

### CR-SL00a-004 · LOW · FIX-IN-SLICE
- **Location:** `Makefile:25-26` (`sync`), `Makefile:9` (`RUN`), `Makefile:34-38`; `backend/tests/tools/test_supply_chain.py:34-37`
- **Category:** design (supply chain, SR-076)
- **Problem:** `--frozen` installs from `uv.lock` without checking that it still matches `pyproject.toml`. Nothing in `make lint` or `make ci` detects a stale lock.
- **Scenario:** a developer adds `"sqlalchemy"` to `dependencies` (SL-00b) and forgets `uv lock`. Local and CI runs go green on the old lock, and the declared dependencies and the audited lock drift apart. pip-audit and osv-scanner then audit something other than what the project declares.
- **Suggested fix:** add `cd $(BACKEND) && $(UV) lock --check` as the first step of `lint-py` (keeping `--frozen` as plan §6.2 requires), and assert in `test_supply_chain.py` that the Makefile contains `lock --check`. `uv lock --check` passes today with the relative `exclude-newer` (`Resolved 63 packages`), so this is compatible with V-7. Re-check it over a few days, since the relative span is recorded in the lock as `exclude-newer-span = "P7D"`.
- **Verification:** add a dependency to `pyproject.toml` without relocking, then run `make lint`, which must fail.
- **Status:** OPEN

### CR-SL00a-005 · LOW · FIX-IN-SLICE
- **Location:** `.github/workflows/ci.yml:78-81`; `.semgrep/sql.py`; `.semgrep/sql.yaml:13-35`; `.semgrep/migrations-now.yaml`
- **Category:** tests (THR-025)
- **Problem:** The "Verify custom semgrep rules" step only tests `menu-sqlalchemy-text-formatted` (the f-string and `.format` patterns, not `+` or `%`) and the frontend rules. It has no fixture for `menu-set-config-session-scope`, `menu-sqlalchemy-session-outside-tenancy` or `menu-bare-now-in-migrations`, which are the controls plan §6.2 lists for this slice. I ran the rules on a synthetic tree: all four fire **inside a git repository**, but the two path-scoped rules (`paths.include: "**/backend/..."`) **produce no results when the target is not under a git root**. That is exactly the kind of silent failure a fixture would catch.
- **Scenario:** a semgrep upgrade or an edit to `paths.include` makes the migrations rule match nothing. The first migration in SL-00b ships `DEFAULT now()` and CI stays green. The catalog test in SL-00b is the second net, but the semgrep rule itself is not covered.
- **Suggested fix:** add fixtures with `# ruleid:` / `# ok:` annotations for each rule and pattern (`text("…" + x)`, `text("…" % x)`, `set_config(…, false)`, `SET app.x`, `SET ROLE`, `SET LOCAL` as ok, `Session()` / `create_engine()`, `now()` / `current_timestamp` / `app.now_utc()` as ok), and run `semgrep --test .semgrep` in CI. If `paths.include` blocks the fixtures under `.semgrep/`, use a `tests/semgrep/backend/src/...` and `.../migrations/versions/...` layout. TO VERIFY: check how `semgrep --test` applies `paths` (I didn't test this).
- **Verification:** `semgrep --test --metrics=off .semgrep` reports a test for every rule ID, and removing a pattern makes it fail.
- **Status:** OPEN

### CR-SL00a-006 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/app/factory.py:22-30`; `openapi.json` → `paths./healthz.get.responses.default.content`
- **Category:** design (contract)
- **Problem:** Because `_PROBLEM_RESPONSE` has `"model": ProblemDetails`, FastAPI adds `application/json` next to the declared `application/problem+json`. Plan §4.1 and ADR-0010 say errors are `application/problem+json` only, and the server never sends `application/json` for errors. The committed contract therefore advertises a media type that never happens.
- **Scenario:** in SL-01 `openapi-typescript` generates a client from this file. Since contract changes after a slice are additive only (plan §4.1), removing `application/json` later counts as a non-additive change. This slice is the cheap point to fix it.
- **Suggested fix:** publish only `application/problem+json`. For example, keep `model` so that `ProblemDetails` and `ErrorCode` stay in `components.schemas`, then post-process the schema once in `create_app` (a custom `app.openapi` that deletes `content["application/json"]` from `default` responses). Or declare the components explicitly. Regenerate `openapi.json`.
- **Verification:** contract test asserting `set(op["responses"]["default"]["content"]) == {"application/problem+json"}` for every operation, plus `ErrorCode` still present in `components.schemas`.
- **Status:** OPEN

### CR-SL00a-007 · LOW · BACKLOG
- **Location:** `backend/src/menu/platform/http/middleware.py:78-81`
- **Category:** security (CWE-770), defense in depth
- **Problem:** When the request has neither a numeric `Content-Length` nor `Transfer-Encoding`, the middleware passes the request on with no size or depth check. This branch fails open, against plan §5.2's fail-closed rule.
- **Scenario:** with uvicorn on HTTP/1.1 (h11 or httptools), a request without either header has no body, so this can't be exploited today. It becomes exploitable if the server changes (HTTP/2 or h2c end-to-end on Cloud Run, Hypercorn), where a body can arrive without `Content-Length`. In that case a 10 MB or deeply nested body would reach the handler.
- **Suggested fix:** always wrap `receive` with a counting reader (stream until `more_body` is false, enforce `MAX_BODY_BYTES`). Skip buffering only for requests that are body-less by method, never based on headers.
- **Verification:** an ASGI-level unit test that sends `http.request` messages totalling more than 64 KB with no `content-length` header in the scope expects 413.
- **Status:** OPEN

### CR-SL00a-008 · LOW · BACKLOG
- **Location:** `backend/src/menu/platform/http/client_ip.py:31-34`; `backend/src/menu/platform/http/problem.py:126-133`, `:158`; `backend/src/menu/platform/logging.py:65`
- **Category:** tests
- **Problem:** Coverage (94% overall) shows these branches never run: `client_ip(request)`, which reads `TRUSTED_PROXY_HOPS` from `app.state.settings` (only the pure function is tested); the `too_long` → `limit_reached`, URL and date translations; `http_exception_handler` for statuses other than 400/404/405; and turning non-scalar log values into a type name.
- **Scenario:** a typo in `request.app.state.settings.trusted_proxy_hops` would only show up in SL-03b, when the rate limit first uses it. A Pydantic upgrade that renames `too_long` would silently change `limit_reached` to `invalid_value`.
- **Suggested fix:** add a probe route that returns `client_ip(request)`, tested with `TRUSTED_PROXY_HOPS=1` and an `X-Forwarded-For`. Add probe fields with `max_length` on a list, an `HttpUrl` and a `date`.
- **Verification:** the lines listed above show as covered in `make test-unit`.
- **Status:** OPEN

### CR-SL00a-009 · LOW · BACKLOG
- **Location:** `Makefile:92-96`
- **Category:** maintainability
- **Problem:** The recipe runs under `.SHELLFLAGS := -eu -o pipefail -c`, so when `pip-audit` fails (the case that matters) the shell exits at once and `rc=$$?; rm -f .pip-audit-requirements.txt; exit $$rc` never runs. The exit code is still correct, but the cleanup is dead code and the file stays behind (it is git-ignored).
- **Scenario:** pip-audit finds a CVE, `backend/.pip-audit-requirements.txt` is left in place, and the recipe doesn't behave the way it reads.
- **Suggested fix:** use `trap 'rm -f .pip-audit-requirements.txt' EXIT` at the start of the line, or `pip-audit … || rc=$$?`. Or write the file under `$(mktemp -d)`.
- **Verification:** inject a failing pip-audit (for example an invalid `-r` path) and check that the file is removed and the exit code is non-zero.
- **Status:** OPEN

### CR-SL00a-010 · LOW · BACKLOG
- **Location:** `.pre-commit-config.yaml:11`, `:17`
- **Category:** design (supply chain)
- **Problem:** The `ruff` and `ruff-format` hooks call `uv run` without `--frozen`. `uv run` may relock and sync, so a commit can rewrite `uv.lock` or install packages as a side effect, unlike the Makefile, which always uses `--frozen`.
- **Suggested fix:** `uv run --frozen ruff …` in both hooks.
- **Verification:** `grep -n "uv run --frozen" .pre-commit-config.yaml` returns 2 lines.
- **Status:** OPEN

### CR-SL00a-011 · LOW · BACKLOG
- **Location:** `backend/pyproject.toml:37-41`; `docs/STATUS.md` (technical debt); `backend/tests/tools/test_supply_chain.py`
- **Category:** design (SR-076)
- **Problem:** The narrow certifi cooldown exception (GHSA-6q48-6c7w-9gw2, to be removed by about 2026-10-27) is recorded in `pyproject.toml` and in the plan's risks, but not as technical debt in `docs/STATUS.md`. No test stops `exclude-newer-package` from quietly growing beyond certifi.
- **Scenario:** a later slice adds another package to `exclude-newer-package` "temporarily" and the cooldown erodes, or the certifi line outlives its deadline.
- **Suggested fix:** the orchestrator records the item, with its removal date, in the STATUS technical debt. Add a test `assert set(tool.uv["exclude-newer-package"]) <= {"certifi"}`, to be emptied when the line is removed. The comment says "decisione utente": make sure that consent is recorded where the user's decisions live.
- **Verification:** the STATUS entry is present; the new test fails if a second package is added.
- **Status:** OPEN

### CR-SL00a-012 · INFO · BACKLOG
- **Location:** `backend/src/menu/platform/http/middleware.py:126`, `:142`; future `__main__ serve` / container entrypoint (SL-00b)
- **Category:** design
- **Problem:** (a) The correlation ID is created in `EnvelopeMiddleware` but stored only in structlog contextvars. `RequestContext.correlation_id` (plan §3) will need to read it from `scope["state"]`. (b) Once uvicorn runs the app, its default access log (stdlib logging, plain text, not redacted) prints the full request line including the query string, which conflicts with plan §5.3. Neither applies yet, because there is no server entrypoint in this slice.
- **Suggested fix:** set `scope.setdefault("state", {})["correlation_id"] = correlation_id` in the envelope. Start uvicorn with `access_log=False` (the envelope already logs `http.request`) and route stdlib logging through structlog.
- **Verification:** in SL-00b, a canary test runs the real server command with `?code=CANARY` and checks that the canary does not appear on stdout.
- **Status:** OPEN

### CR-SL00a-013 · INFO · BACKLOG
- **Location:** `.github/workflows/ci.yml:127`; `Makefile:21`
- **Category:** maintainability
- **Problem:** The grep `^\s*(on:.*)?pull_request_targe[t]\s*:` misses `on: pull_request_target` and `on: [push, pull_request_target]` (no colon after the trigger). zizmor's `dangerous-triggers` audit still covers these, so it's only a redundant check with gaps. Separately, `make help` lists `test` as active, but `make test` fails because it chains placeholder targets, as intended until SL-00b.
- **Suggested fix:** `grep -RnE '\bpull_request_target\b' .github/workflows`. In `help`, move `test` to the placeholder line, or say it is active from SL-00b.
- **Status:** OPEN

## Tools run
| Tool | Command | Result |
|---|---|---|
| ruff | `cd backend && uv run --frozen --no-sync ruff check .` | All checks passed |
| ruff format | `uv run --frozen --no-sync ruff format --check .` | 55 files already formatted |
| mypy | `uv run --frozen --no-sync mypy` | Success: no issues found in 55 source files |
| bandit | `uv run --frozen --no-sync bandit -q -c pyproject.toml -r src` | no output (no issues) |
| pytest (all) | `uv run --frozen --no-sync pytest -q -p no:cacheprovider tests` | 277 passed, 1 warning (Starlette httpx deprecation) |
| coverage | `pytest tests/unit tests/architecture tests/tools --cov=menu --cov-branch` | TOTAL 94%; gaps listed in CR-001 and CR-008 |
| openapi check | `APP_ENV=test uv run python -I scripts/export_openapi.py --check` | rc=0 (committed contract matches the generated one) |
| uv lock check | `uv lock --check` | Resolved 63 packages, lock up to date |
| gitleaks | `gitleaks git .` and `gitleaks dir .` with `.gitleaks.toml` | no leaks found (both) |
| zizmor | `zizmor --no-progress --offline .github/workflows` | No findings (5 suppressed) |
| semgrep custom-rule tests | `semgrep --test --config .semgrep/sql.yaml .semgrep/sql.py` | 1/1 All tests passed |
| semgrep custom rules (synthetic tree) | `semgrep scan --config .semgrep backend` on a scratch tree | all 4 rules fire inside a git repository; the path-scoped rules don't fire outside a git root (CR-005) |
| semgrep SAST | `make scan-sast` | no findings reported |
| pip-audit | `uv export --frozen … && pip-audit -r … --no-deps --disable-pip` | No known vulnerabilities found |
| osv-scanner | `osv-scanner scan source --lockfile uv.lock` | No issues found |
| behaviour probe | scratch script against `create_app` + probe router | body-less `DELETE`/`POST` with no Content-Type → 415 (matches ADR-0004/ADR-0010); `POST /healthz` JSON → 404; unhandled exception logged with `severity: ERROR` and `correlation_id` |
| git | `git branch --show-current`; `git remote -v` | `main`; `origin` = `https://github.com/mrclttnz/menu-design` (nothing pushed) |

## What was done well
The platform layer is careful and testable. The layer checker's own tests prove it detects violations. ErrorCode is checked against the ADR-0010 table. If-Match follows ADR-0008 exactly. Middleware-generated errors keep the security headers. Every scan in CI is pinned (actions by SHA, binaries by SHA-256) and calls the same Makefile targets used locally.

## Re-check cycle 1

- **Date:** 2026-10-21
- **Scope:** only CR-SL00a-001..006 and the fix diff (working tree vs `44a5a03`, nothing committed): `backend/tests/unit/test_platform_authz_route.py`, `test_platform_headers.py`, `test_platform_if_match.py`, `test_platform_logging.py`, `backend/tests/contract/test_openapi_contract.py`, `backend/tests/tools/test_supply_chain.py`, `backend/src/menu/app/factory.py`, `openapi.json`, `Makefile` (`lint-py`, `scan-rules`, `tools-semgrep`, `tools-zizmor`), `.github/workflows/ci.yml`, `.semgrep/sql.yaml`, `.semgrep/sql.py`, `.semgrep/migrations-now.{yaml,py}`, `scripts/check_semgrep_rules.py`
- **Verdict:** APPROVED (no BLOCKER or FIX-IN-SLICE finding open; no BLOCKER introduced by the fixes)
- **Cycle:** 2 (re-check of fix cycle 1)

| ID | Status | Evidence |
|---|---|---|
| CR-SL00a-001 | CLOSED | Every refusal test now uses `pytest.raises(ValueError, match=...)` with the stable message from `routing.py`. New parametrized cases: `{"scope": "family"}`, `{"scope": "family", "roles": []}`, `{"scope": "public", "extra": 1}`, and `operation_id` in `None, "", "health", "platform.health", "Platform.Health.Read"`. Both branches flagged in the review (family without roles, missing or malformed `operation_id`) now run. |
| CR-SL00a-002 | CLOSED | `public_routes_outside_inventory(schema)` helper; `test_inventory_check_catches_an_extra_public_route` asserts `("get", "/_probe/rogue-public")` is reported, so the test fails if the helper returns `set()`. The probe route is no longer dead. |
| CR-SL00a-003 | CLOSED | (1) The 405 case now sends `{}` with `Content-Type: application/json`. Probe run: `POST /healthz` returns 404 `not_found` with `nosniff`, so the routing path runs, not the 415 middleware. (2) The misleading test was removed (no `order_is_stable` left) and replaced by `test_malformed_if_match_with_valid_body_is_422_on_if_match_field` (valid `{}` body, `If-Match: *`, `errors[0].field == "If-Match"`, handler not called). (3) The forged `severity=CRITICAL` now sits in `event`, which is always emitted, and the test asserts the escaped form and that every line containing the canary parses as JSON. |
| CR-SL00a-004 | CLOSED | `lint-py` runs `cd $(BACKEND) && $(UV) lock --check` before ruff and keeps `--frozen` everywhere else; `test_supply_chain.py:46` asserts it is present. `uv lock --check` returns `Resolved 63 packages`. |
| CR-SL00a-005 | CLOSED | Fixtures cover every pattern of `menu-sqlalchemy-text-formatted` (f-string, `.format`, `+`, `%`, plus an ok case), the 3 constructors of `menu-sqlalchemy-session-outside-tenancy`, `set_config(…, false)` / `SET app.x` with `true` / `SET LOCAL` as ok, and `now()` / `CURRENT_TIMESTAMP` with `app.now_utc()` as ok. `make scan-rules` (a prerequisite of `scan-sast`, which CI calls) runs all 3 `semgrep --test` commands plus `scripts/check_semgrep_rules.py`, a real scan over a temporary tree with the repository layout that checks the `paths` filters. Mutation checks in the scratchpad: removing `text($A + $B)` gives `semgrep --test` rc=1 (`missed lines: [11]`); a wrong `tenancy` exclude and a wrong `migrations/versions` include each make the script exit 1 with a per-file error. The script passes on the real rules (`8 casi di percorso OK`), so the earlier "outside a git root" silent failure no longer hides a broken `paths` filter. |
| CR-SL00a-006 | CLOSED | `_problem_json_only` wraps `app.openapi` and drops `application/json` from `default` responses, editing the cached schema in place. `openapi.json` → `/healthz` `default.content` is `{application/problem+json}` only. `test_errors_are_published_only_as_problem_json` asserts this for every operation and that `ProblemDetails` and `ErrorCode` are still in `components.schemas`. `export_openapi.py --check` returns rc=0. |

### Notes on the fix diff (not findings, under the anti-loop rule: no BLOCKER introduced)
- `.semgrep/sql.yaml` `text($A + $B)` is now broad. On a scratch file it also matches constant-only concatenation (`text("select 1 " + "from t")`) and `text(PREFIX + "b")`. That is a false positive on the safe side: compile-time constants can be merged, or the line suppressed with a `# nosemgrep` that gives the reason. No action required.
- The `menu-set-config-session-scope` fixture has no case for `SET ROLE`, `SET search_path` or `SET SESSION app.x`, so those regex alternatives have no fixture. Worth adding when the rule is next touched (SL-00b, first real `SET LOCAL`).
- `backend/src/menu/app/factory.py:21` `_PROBLEM_REF` is defined but not used: `_PROBLEM_RESPONSE` repeats the literal `$ref`. This is dead code; use the constant or delete it.
- `scan-rules` runs the checker with system `python3 -I` (stdlib only, no repository imports). It runs on the CI runner and complies with the venv rule, because nothing is installed.

### Tools run (re-check)
| Tool | Command | Result |
|---|---|---|
| pytest (all) | `uv run --frozen --no-sync pytest -q -p no:cacheprovider tests` | 311 passed, 1 warning (Starlette httpx deprecation) |
| ruff / format / mypy | `ruff check .`; `ruff format --check .`; `mypy` | All checks passed; 55 files already formatted; no issues in 55 files |
| uv lock check | `uv lock --check` | Resolved 63 packages |
| openapi check | `APP_ENV=test uv run --frozen --no-sync python -I scripts/export_openapi.py --check` | rc=0 |
| semgrep fixtures | `semgrep --test --metrics=off --config .semgrep/{sql,frontend,migrations-now}.yaml …` (1.180.0) | 3/3, 2/2, 1/1 passed |
| path checker | `python3 -I scripts/check_semgrep_rules.py` | 8 path cases OK, rc=0 |
| mutations (scratchpad copy) | remove `text($A + $B)`; wrong tenancy exclude; wrong migrations include | rc=1 in all three cases, with a precise message |
| behaviour probe | `POST /healthz` with a JSON body | 404 `not_found`, security headers present |
