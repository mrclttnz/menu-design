# SL-00a: security review

| Field | Value |
|---|---|
| Slice | SL-00a: repository, backend skeleton, CI with blocking scans |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-21 |
| Diff base | `44a5a03` (nothing committed yet: modified and untracked files read directly) |
| SRs in scope | SR-009, SR-021, SR-023, SR-046, SR-060, SR-076 |
| THRs in scope | THR-025, THR-090, THR-091, THR-093, THR-102, THR-106, THR-107, THR-110, THR-134 |
| Verdict | **No BLOCKERs.** 3 MEDIUM FIX-IN-SLICE, 1 LOW FIX-IN-SLICE, 5 LOW BACKLOG, INFO notes. The gate can close once the FIX-IN-SLICE findings are fixed and checked. |

Controls are kept proportionate to a low-stakes app, as the user asked. No finding below asks for new infrastructure. Every fix is a few lines.

## 1. What was checked and how

Files read in full: `backend/src/menu/**` (platform, app, common), `backend/tests/support/probe.py`, `backend/tests/conftest.py`, the limit, header, logging and error tests, `.github/workflows/ci.yml`, `Makefile`, `scripts/ci.sh`, `backend/pyproject.toml`, `backend/uv.lock` (header and package list), `.pre-commit-config.yaml`, `.gitleaks.toml`, `.semgrep/*.yaml`, `.semgrepignore`, `.gitignore`, `.env.example`, `backend/scripts/export_openapi.py`.

Tools run (fresh output, 2026-10-20/21):

| Command | Result |
|---|---|
| `make ci` (lint, unit, contract, scan tiers) | all tiers green: 267 unit/arch/tools tests and 10 contract tests passed; ruff, mypy strict and bandit clean |
| `gitleaks git .` + `gitleaks dir .` (in `make scan`) | 1 commit scanned, working tree about 1.75 MB: **no leaks found** |
| `semgrep` p/python, p/owasp-top-ten, p/typescript, p/react + `.semgrep` | 0 findings |
| `pip-audit` on the exported lock | No known vulnerabilities found |
| `osv-scanner scan source --lockfile backend/uv.lock` | 63 packages, no issues found |
| `zizmor` (default) / `zizmor --persona=auditor` | 0 findings / 5 informational (`anonymous-definition`, cosmetic) |
| `git ls-remote` on the action tags | `actions/checkout` v7.0.1 → `3d3c42e5…` and `astral-sh/setup-uv` v10.3.0 → `1c37ad07…`: **pins match the upstream tags** (no impostor commit) |
| Upstream checksum files for gitleaks 8.30.1 (`linux_x64.tar.gz`) and osv-scanner 2.7.0 (`linux_amd64`) | **both SHA-256 values in `ci.yml` match** the published checksums |
| OSV `GHSA-6q48-6c7w-9gw2` + PyPI upload times | advisory is real (CRITICAL, CWE-295, fix in certifi 2026.10.19, uploaded 2026-10-20T02:24Z). certifi is **dev-only** (httpx, requests ← pip-audit) |
| PyPI upload times of the CI tools | semgrep 1.181.0: 2026-10-14T21:32Z. zizmor 1.31.1: 2026-10-15T23:12Z (see SEC-SL00a-003) |
| Hand-written probes against the real app plus the probe router (scratchpad scripts, nothing written to the repo) | results cited in the findings |

## 2. Findings

### SEC-SL00a-001 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/platform/http/middleware.py:37-56` (`_JSON_TOKENS`, `json_depth_exceeds`) and `:41-42` (`is_json_content_type`)
- **Category:** security (CWE-1284 improper validation of a specified quantity; CWE-400)
- **Problem:** the depth guard scans raw bytes as if they were UTF-8. FastAPI then parses the body with `json.loads(bytes)`, which auto-detects UTF-16 and UTF-32. In UTF-16 a character inside a string can contain the byte `0x22` (`"`). For example, U+2200 is `00 22` in UTF-16LE. That byte desynchronises the scanner's view of where strings start and end, so real brackets get skipped as if they were string content. The guard accepts `application/json; charset=utf-16` and any non-UTF-8 body.
- **Scenario (verified):** body `["∀",` + `[`×N + `]`×N + `,"∀"]` encoded UTF-16LE, `Content-Type: application/json`, sent to `POST /_probe/echo`. Results: N=50 → `200`, handler reached. N=2000 → `200`. N=15000 (60 KB, under the 64 KB cap) → `200`. The same nesting in UTF-8, or plain (not hidden) UTF-16/32, is correctly rejected with `422`. Impact today is small: the body is still capped at 64 KB, and Python's JSON parser handles that depth. But SR-060/THR-102 ("depth ≤ 10") can be bypassed. Any later code that walks a payload recursively (Pydantic `dict[str, Any]` fields, `jsonable_encoder`, the change-event codec) can hit `RecursionError` → `500` or burn CPU.
- **Suggested fix (pick one, both are a few lines):**
  1. Reject any body that contains a NUL byte (`b"\x00" in body` → `422 invalid_value`). Valid UTF-8 JSON never has a raw NUL, while UTF-16/32 JSON always does, because the structural characters are ASCII. Also reject a `charset` parameter other than `utf-8`, with `415`.
  2. Or decode the body the same way the parser does, then scan the text: `text = body.decode(json.detect_encoding(body))`, with the regex compiled for `str`.
- **Verification:** add to `tests/unit/test_platform_limits.py` cases for UTF-16LE, UTF-16BE, UTF-32 and a hidden-nesting body (the payload above with N=11 and N=15000) → `422`, handler not called. Also `charset=utf-16` → `415` (if option 1).
- **Status:** OPEN

### SEC-SL00a-002 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/platform/routing.py:170-174` (`assert_all_routes_declare_authz`) and `:158-167` (`_walk`)
- **Category:** security (CWE-862 missing authorization; fail-open inventory)
- **Problem:** the startup check only looks at `APIRoute` instances (`isinstance(route, APIRoute) and not isinstance(route, AuthzRoute)`). Any other route type passes silently: a plain Starlette `Route`, a `Mount` (sub-app or static files) and a `WebSocketRoute`. Routes inside a mounted sub-app are never inspected either. SR-009 asks for deny-by-default: an app with an undeclared endpoint must not start.
- **Scenario (verified):**
  - (A) `APIRouter(route_class=AuthzRoute).add_route("/plain", handler)` → the app starts and `GET /plain` → `200`.
  - (B) `router.mount("/sub", FastAPI())` with a `GET /x` → the app starts and `GET /sub/x` → `200`.
  - (D) `@router.websocket("/ws")` → the app starts.
  - In each case the endpoint has no `x-authz` and does not appear in `openapi.json`, so the contract test does not see it either.
  - A plain `APIRouter()` without `route_class` (C) is correctly refused.
- **Suggested fix:** invert the check to allow-list: every route yielded by `_walk` must be an `AuthzRoute`. The only exceptions go in an explicit, tested list (for SL-01, the static-files `Mount` at a known path), for example `assert_all_routes_declare_authz(app, allowed_non_api={"/assets"})`. Anything else, including `Mount`, `Route`, `WebSocketRoute` and `Host`, makes startup fail.
- **Verification:** add the three cases A, B, D to `tests/unit/test_platform_authz_route.py`, each expecting `create_app` to raise.
- **Status:** OPEN

### SEC-SL00a-003 · MEDIUM · FIX-IN-SLICE
- **Location:** `.github/workflows/ci.yml:22-23, 77, 119` (`uv tool install "semgrep==…"`, `uv tool install "zizmor==…"`)
- **Category:** security (CWE-829 inclusion of functionality from an untrusted control sphere; SR-076, THR-090)
- **Problem:** the 7-day cooldown (`exclude-newer = "7 days"`) only applies to the `backend/` project. CI tools are installed outside it:
  - their **transitive dependencies are resolved fresh on every run, with no lock, no hashes and no cooldown** (semgrep pulls in dozens of packages);
  - the pinned top-level versions are themselves newer than 7 days. semgrep 1.181.0 was uploaded on 2026-10-14 and zizmor 1.31.1 on 2026-10-15. `uv pip compile --exclude-newer "7 days"` for `semgrep==1.181.0` fails with "filtered by exclude-newer", which confirms it.
- **Scenario:** a compromised release of any semgrep dependency is published, and the next CI run installs it within minutes. The job has `contents: read` and no secrets. However, code running on a GitHub-hosted runner (which has sudo) can read the runner's memory and get the `GITHUB_TOKEN`, then exfiltrate the private source code, or quietly turn the SAST gate green. Impact is limited (private repo, no deploy secrets in this workflow) but real. It is exactly the worm pattern THR-090 describes.
- **Suggested fix:** add `--exclude-newer "7 days"` to both `uv tool install` lines and pick tool versions at least 7 days old. For a tool fix that has to be urgent, use an explicit `--exclude-newer-package <tool>=<timestamp>` with a comment and a removal date, as for certifi. Optional: a small locked `tools/` requirements file installed with `--require-hashes`.
- **Verification:** extend `tests/tools/test_supply_chain.py` so that every `uv tool install` / `uvx` in `.github/workflows/*.yml` and the `Makefile` carries `--exclude-newer`. Then run the `sast` and `workflows` jobs locally (`act`, or the same commands).
- **Status:** OPEN

### SEC-SL00a-004 · LOW · FIX-IN-SLICE
- **Location:** `.gitleaks.toml:9` (`paths` allow-list contains `(^|/)\.env\.example$`)
- **Category:** security (CWE-798 / CWE-540; THR-093)
- **Problem:** the whole `.env.example` is excluded from secret scanning. It is the one versioned file where someone is most likely to paste a real value by mistake ("copy .env to .env.example and blank it… forgot one"). The allow-list is also unnecessary: I ran gitleaks without it on the current `.env.example` and found no leaks, because the `CHANGE_ME` placeholders do not trigger any rule.
- **Suggested fix:** remove that path from the allow-list. If a future placeholder triggers a rule, allow-list the placeholder **value** (for example `regexes = ['''CHANGE_ME''']`), not the file.
- **Verification:** `make scan-secrets` stays green, and a temporary fake high-entropy key in `.env.example` gets detected (do not commit it).
- **Status:** OPEN

### SEC-SL00a-005 · LOW · BACKLOG (scheduled: SL-03b, when `client_ip` is first used)
- **Location:** `backend/src/menu/platform/config.py:18` (`trusted_proxy_hops: int = Field(default=0, …)`), `.env.example:3`
- **Category:** security (CWE-1188 insecure default)
- **Problem:** on Cloud Run the peer address is always the Google front end. If `TRUSTED_PROXY_HOPS` is forgotten in staging or production, it silently defaults to `0`, and every client shares one "IP". Not spoofable (good, the code never takes the leftmost entry), but the per-IP limits of SR-059 (30 OIDC starts/IP/15 min) become a global limit. One anonymous client can then lock everyone out of login.
- **Suggested fix:** no default, so a missing value fails startup like `APP_ENV` already does. This does not make `APP_ENV` change any control (A-25). Set it explicitly in `.env.example` and in the deploy configuration (1 for Cloud Run).
- **Verification:** a config test where a missing `TRUSTED_PROXY_HOPS` makes startup fail. The SL-03b test "forged `X-Forwarded-For` → last entry" with `hops=1`.
- **Status:** OPEN

### SEC-SL00a-006 · LOW · BACKLOG (scheduled: SL-00b, first DB code)
- **Location:** `backend/src/menu/platform/http/middleware.py:146` (`_log.exception`), `backend/src/menu/platform/logging.py:38` (`exception` in `ALLOWED_FIELDS`)
- **Category:** security (CWE-532 sensitive information in logs; SR-021, THR-110)
- **Problem:** the response is correctly generic (verified: `CANARY-EXC-MESSAGE`, `Traceback` and `File "` do not appear in the `500` body). The server log, however, keeps the full traceback **including the exception message**. That is fine today. From SL-00b on, though, the typical messages carry values:
  - SQLAlchemy appends `[parameters: …]`;
  - psycopg `DETAIL: Key (…)=(…)`;
  - Pydantic `ValidationError` includes `input_value`.

  Those values can be family names, notes or hashes.
- **Suggested fix:** in SL-00b, create the engine with `hide_parameters=True`. Add a logging test that raises a DB integrity error and a Pydantic error built from canary values, and checks that no canary reaches stdout. If needed, log only `type(exc).__name__` plus the traceback frames for known DB/validation exception types.
- **Verification:** the canary test above in `tests/unit/test_platform_logging.py` (or `tests/db`).
- **Status:** OPEN

### SEC-SL00a-007 · LOW · BACKLOG (scheduled: SL-00b, before the first SQL)
- **Location:** `.semgrep/sql.yaml:3-12` (`menu-sqlalchemy-text-formatted`), `:24-35` (`menu-sqlalchemy-session-outside-tenancy`)
- **Category:** security (CWE-89; THR-025)
- **Problem:** the `text()` rule only matches a formatted string written **inline**. These forms pass:
  - `q = f"… {x}"; text(q)`;
  - `sa.text("…" + x)` (the `$F.` variants lack `+` and `%`);
  - `text(x + "…")`;
  - `literal_column(f"…")`;
  - `conn.exec_driver_sql(f"…")`.

  The session rule does not cover `create_async_engine`, `AsyncSession` or `async_sessionmaker`.
- **Suggested fix:** turn the rule around: `text($X)` with `pattern-not: text("...")`, so only a string literal is allowed. Add `literal_column`, `exec_driver_sql` and the async variants. Extend `.semgrep/sql.py` with positive and negative cases.
- **Verification:** `semgrep --test --config .semgrep/sql.yaml .semgrep/sql.py`.
- **Status:** OPEN

### SEC-SL00a-008 · LOW · BACKLOG (deadline 2026-10-27)
- **Location:** `backend/pyproject.toml:41` (`exclude-newer-package = { certifi = "2026-10-21T00:00:00Z" }`)
- **Category:** security (SR-076 exception management)
- **Problem:** the exception is justified, verified (real CRITICAL advisory, certifi dev-only) and narrow. Two things to keep in mind:
  1. It has **no tracking entry**: the technical debt table in `docs/STATUS.md` is empty. Because the timestamp is fixed, from 2026-10-21 certifi is not "cooled down" but **frozen**, so a future certifi security fix would be silently excluded until the line is removed.
  2. A cutoff of `2026-10-20T03:00:00Z`, just after the 2026.10.19 upload, would have been tighter than end of day 2026-10-21. That window has now passed, so this only matters for the next exception.
- **Suggested fix:** the orchestrator records "remove the certifi `exclude-newer-package` by 2026-10-27" in the STATUS debt table. Remove the line, run `uv lock`, check `certifi >= 2026.10.19` is still picked.
- **Verification:** `grep exclude-newer-package backend/pyproject.toml` returns nothing after 2026-10-27, and `make scan-deps` is green.
- **Status:** OPEN

### SEC-SL00a-009 · LOW · BACKLOG (scheduled: SL-10b or earlier)
- **Location:** `.github/` (no `dependabot.yml`), `Makefile:100` (`zizmor` runs in offline mode)
- **Category:** security (THR-090, THR-091)
- **Problem:** THR-090 lists "automatic updates with review", and there are none. SHA pins make that more important: pinned actions and the downloaded binaries (gitleaks, osv-scanner) never receive fixes unless someone updates them by hand. zizmor runs offline, so its online audits (`impostor-commit`, `known-vulnerable-actions`, `ref-confusion`) are off. I checked the two current pins by hand (they match the upstream tags).
- **Suggested fix:** a minimal `.github/dependabot.yml` for `github-actions` and `uv` (`backend/`), with `cooldown: default-days: 7` (consistent with SR-076). Optionally pass `GH_TOKEN: ${{ github.token }}` (read-only) to the zizmor step to turn on the online audits.
- **Verification:** Dependabot opens its PRs after the first push. zizmor logs no "offline mode" warning.
- **Status:** OPEN

## 3. Informational notes (no action required in SL-00a)

- **INFO-1 (SL-00b, container):** start uvicorn with `--no-server-header`. Keep the default `forwarded_allow_ips` (never `*`), so that `request.client` stays the real peer that `client_ip` relies on. Add `.env*` to `.dockerignore`: `Settings` reads `.env` from the working directory (`env_file=".env"`). Real environment variables override it, but a `.env` baked into the image must never be able to supply `APP_ENV`.
- **INFO-2 (code review, functional):** `BodyGuardMiddleware` returns `415` for every `POST/PUT/PATCH/DELETE` without `application/json`, including body-less calls (for example `POST /auth/logout`, `…/revoke`). Good for CSRF defense in depth. The SPA client must always send the header.
- **INFO-3:** with no `Content-Length` and no `Transfer-Encoding`, the guard forwards the original `receive`. That is correct for HTTP/1.1 (no body), and uvicorn does not serve HTTP/2. If the server ever changes (hypercorn/h2c), read the body for every unsafe method.
- **INFO-4:** `unknown_field` errors repeat the attacker-supplied key name in `errors[].field` (verified). This is intended by the contract: `application/problem+json` with `nosniff`, at most 50 errors, body ≤ 64 KB. No XSS risk.
- **INFO-5 (SL-01):** CSP `style-src 'self'` and `require-trusted-types-for 'script'` are strict. Check them against React Aria and React Router before relaxing anything; do not add `unsafe-inline`. `Permissions-Policy` and `Cross-Origin-Opener-Policy: same-origin` would be cheap extras, but are not required.
- **INFO-6:** the workflow SHA-pin grep (`ci.yml:124`) does not look at `docker://` references. There are none today, and zizmor's `unpinned-uses` covers them.
- **INFO-7:** `.gitignore` could also cover `*.dump`, `*.sql.gz`, `*.age` and `.envrc` before the backup and restore drills (ADR-0015) run on the developer PC. gitleaks already catches key material.
- **INFO-8:** before the first push, run `make scan-secrets` again on the full history (STATUS already says so).

## 4. Requirement and threat coverage

| ID | Verdict | Evidence |
|---|---|---|
| SR-009 / AuthzRoute fail-closed | **Partial**: `APIRoute` without `AuthzRoute` and invalid `x-authz` are refused; non-API routes are not (SEC-SL00a-002) | probe A/B/C/D |
| SR-021 / THR-110 logging | Met for SL-00a: field allow-list, forbidden keys, `\r\n` neutralised, JSON output, path only (no query string), no IPs. Future risk in SEC-SL00a-006 | canary tests, code reading |
| SR-023 headers | Met: HSTS 2 years, nosniff, Referrer-Policy, strict CSP with `frame-ancestors 'none'` and Trusted Types. Present on 200/404/413/415/422/500 (verified on 404, 500 and the method-mismatch case). No CORS middleware, so same-origin only (CORS [MUST] satisfied) | probe, `test_platform_headers` |
| SR-046 `no-store` | Met: set by default on every response, including `/healthz` and errors | probe |
| SR-060 / THR-102 | 64 KB: met, including chunked and a lying `Content-Length`. Depth 10: **bypassable with UTF-16** (SEC-SL00a-001). `Content-Type`: met | probe, tests |
| THR-107 If-Match | Met: `fullmatch`, ≤ 18 digits, missing → `428`. These all → `422`, never `500`: `*`, `W/"3"`, `"-1"`, `"01"`, 19 digits, spaces, `"1", "2"`, two headers, empty, NUL. Value not reflected | probe |
| THR-106 `/healthz` | Met for SL-00a: public, body `{"status":"ok"}` only, `no-store`, no cookie; DB part in SL-00b | code, tests |
| THR-134 | Met: `APP_ENV` required and does not switch any control; `debug=False`, docs and OpenAPI URL off in every environment | `config.py`, `factory.py` |
| THR-025 | Semgrep in CI and green; rule gaps in SEC-SL00a-007 | `make scan-sast` |
| THR-090 / SR-076 | Lockfile with hashes, `--frozen` everywhere, 7-day relative cooldown (V-7 verified: `exclude-newer-span = "P7D"` in `uv.lock`), pip-audit and osv-scanner blocking. Gaps: CI tools (SEC-SL00a-003), no update bot (SEC-SL00a-009) | scans, lock header |
| THR-091 | Met: top-level `permissions: contents: read`, `persist-credentials: false`, actions pinned to SHAs and checked against upstream, no `pull_request_target`, no `${{ }}` in `run:` (no injection), downloaded binaries verified by SHA-256 against upstream, cache disabled, zizmor clean | zizmor, ls-remote, checksum files |
| THR-093 | Met: `.env`/`.env.*` ignored (checked with `git check-ignore`), `.env.example` has placeholders only, gitleaks in pre-commit and in CI on full history (`fetch-depth: 0`). Allow-list too broad (SEC-SL00a-004) | gitleaks, check-ignore |
| Makefile / scripts | No untrusted input reaches a shell. `ci.sh` uses a fixed tier map with `:?` on unknown tiers. `scan-deps` keeps the exit code under `-e -o pipefail` | code reading |
| Error handling | Generic RFC 9457, no `detail`, no stack trace or path in responses (verified with a canary exception) | probe, tests |

**Done well:** strict, tested `If-Match` parsing that never returns `500`. Header and `no-store` envelope applied even to middleware-generated errors. Verified checksums and SHA pins in CI, with `persist-credentials: false`. A narrow, documented certifi exception.

## Report — security-engineer
**Outcome:** DONE_WITH_CONCERNS
**Scope:** SL-00a
**Files changed:** /home/marco/work/menu-design/docs/reviews/SL-00a-security.md
**Summary:** Mode B review of the repository skeleton, platform middleware and CI. No CRITICAL or HIGH findings and no [MUST] violation. Three MEDIUM findings to fix in the slice: a JSON-depth guard bypass via UTF-16 bodies, an AuthzRoute inventory that fails open for non-API routes, and CI tools installed without the 7-day cooldown. One LOW in-slice fix (gitleaks allow-list too broad). Five LOW backlog items, each with a target slice.
**Evidence:** `make ci` all tiers green (267 + 10 tests; gitleaks, semgrep, pip-audit, osv-scanner, zizmor clean). Probes: UTF-16 hidden nesting N=15000 → 200 (bypass), UTF-8 deep → 422. `add_route`/`mount`/`websocket` without x-authz → app starts. `git ls-remote` pins match. gitleaks and osv-scanner SHA-256 values match upstream. semgrep 1.181.0 rejected by `--exclude-newer "7 days"`.
**Traceability:** SR-009, SR-021, SR-023, SR-046, SR-060, SR-076; THR-025, 090, 091, 093, 102, 106, 107, 110, 134
**Decisions needed:** none
**Risks and technical debt:** SEC-SL00a-005..009 for the STATUS debt table (certifi exception removal by 2026-10-27 is the one with a date)
**Suggested next step:** backend-developer fixes SEC-SL00a-001, 002 and 004; devops fixes SEC-SL00a-003, each with a regression test. Then security-engineer re-checks only those findings. Orchestrator records the backlog items in docs/STATUS.md.

## Re-check cycle 1 (2026-10-21)

Scope: only SEC-SL00a-001..004 and the fix diff (charset `415` rule, NUL check, routing allow-list, Makefile `tools-*` targets, `ci.yml` changes, `.gitleaks.toml`). Per the fix-cycle rule, new findings are opened only if they are BLOCKERs introduced by the fix. Everything else is recorded as INFO.

### Evidence (fresh, 2026-10-21)

| Check | Result |
|---|---|
| `make ci` | all tiers green: 299 unit/arch/tools tests, 12 contract tests; ruff, mypy, bandit, gitleaks (history and tree), semgrep rule tests and scan, pip-audit, osv-scanner, zizmor clean |
| Probe script against `create_app` plus the probe router (scratchpad, nothing written to the repo) | results per finding below |
| `uv tool install --exclude-newer "7 days"` in an isolated `UV_TOOL_DIR` | `semgrep==1.180.0` and `zizmor==1.30.1` install. `semgrep==1.181.0` is refused ("filtered by exclude-newer"). The receipt records `exclude-newer-span = "P7D"` |
| PyPI upload times | semgrep 1.180.0: 2026-10-07T23:22Z. zizmor 1.30.1: 2026-09-09T05:26Z. Both are older than 7 days |
| `osv-scanner` on the resolved semgrep tool environment (66 packages, `uv pip compile --exclude-newer "7 days"`) | **certifi 2026.7.22: GHSA-6q48-6c7w-9gw2 / PYSEC-2026-4320 (CRITICAL, 9.1)**. mcp 1.29.0: GHSA-84m7-p3x7-pcfv (HIGH, 7.5). zizmor has no dependencies |
| gitleaks with the repo config on a scratch copy of `.env.example` plus two fake high-entropy keys | `leaks found: 2`. The file is now scanned |

### Status per finding

| Finding | Status | Evidence |
|---|---|---|
| SEC-SL00a-001 (UTF-16/32 hidden nesting) | **CLOSED** | Hidden nesting with N=11, 50 and 15000 in UTF-16LE, UTF-16BE and UTF-32LE → `422`, handler not called. UTF-16 with a BOM → `422`. Chunked body over 64 KB with hidden nesting → `422`. `charset=utf-16`, `latin-1` and a duplicated `charset=utf-8; charset=utf-16` → `415`. `charset="UTF-8"` → `200`. No regression: UTF-8 depth 10 → `200`, depth 11 → `422`, UTF-8 BOM shallow → `200`, escaped `\u0000` inside a string (legitimate) → `200`, invalid UTF-8 → `422`. Regression tests are present in `test_platform_limits.py` (`:132-178`). The NUL rule is sound: valid UTF-8 JSON never contains a raw `0x00`, and in UTF-8 the bytes `"` and `\` never occur inside multibyte sequences, so the byte-level scanner cannot be desynchronised any more. |
| SEC-SL00a-002 (non-API routes fail open) | **CLOSED** | These all make `create_app` raise: (A) `add_route`, (B) `mount` of a sub-app, (D) `@websocket`, `add_websocket_route`, a plain route nested two `include_router` levels deep, and `add_api_route(route_class_override=APIRoute)`. A `Host` route is refused. A plain `APIRouter` (C) is still refused. The allow-list is empty by default and admits only the exact listed path (`/assets` accepted, `/assets2` refused). Regression tests are present (`test_platform_authz_route.py:125-142`). |
| SEC-SL00a-003 (CI tools without cooldown) | **CLOSED** (see the new SEC-SL00a-010, a side effect of this fix) | Single source in the `Makefile` (`tools-semgrep`, `tools-zizmor`, `TOOL_COOLDOWN := 7 days`). `ci.yml` calls only `make tools-*` (no `uv tool install` left in the workflow). The cooldown also applies to transitive dependencies (verified in the receipt). The versions are older than 7 days. Guard tests are in `test_supply_chain.py`. |
| SEC-SL00a-004 (`.env.example` allow-listed) | **CLOSED** | The path has been removed from `.gitleaks.toml`, a test checks that `.env` does not appear in the config, a fake key in `.env.example` is detected, and `make scan-secrets` stays green on the real file. |

### SEC-SL00a-010 · MEDIUM · BLOCKER (introduced by the fix of SEC-SL00a-003)
- **Location:** `Makefile` target `tools-semgrep` (`$(UV) tool install --force --exclude-newer "$(TOOL_COOLDOWN)" "semgrep==$(SEMGREP_VERSION)"`). It is used by `ci.yml` job `sast` and by developers.
- **Category:** security (CWE-1395 dependency on a vulnerable third-party component; CWE-295; security standard §11 [MUST] "no known critical CVEs"; SR-076, THR-090)
- **Problem:** with the 7-day cooldown, the semgrep tool environment now resolves **certifi 2026.7.22**. That version is affected by the CRITICAL advisory GHSA-6q48-6c7w-9gw2 (emSign root with compromised intermediate keys). The fixed certifi 2026.10.19 was uploaded on 2026-10-20, so the cooldown filters it out. This is the same CVE the backend lock already handles with an explicit `exclude-newer-package` exception, but the tool environment does not get that exception. Before the fix, an unconstrained install would have picked the fixed certifi. The tool environments are also not covered by `scan-deps`, so CI stays green.
- **Scenario:** `semgrep scan --config p/python --config p/owasp-top-ten …` downloads the registry rules over HTTPS through `requests`/`httpx`, which trust the certifi bundle. An on-path attacker holding one of the compromised eMudhra intermediate keys can present a valid-looking certificate for the semgrep registry and serve empty or weakened rule sets. The SAST gate then turns green silently. The likelihood is low (it needs network position on a GitHub-hosted runner, or on the developer PC, plus a compromised CA key), and the job has no secrets. Because the impact is limited, the severity is MEDIUM. The class is BLOCKER because it violates a [MUST] rule.
- **Suggested fix:** one flag, mirroring the backend exception and sharing its removal date (SEC-SL00a-008, 2026-10-27):
  `$(UV) tool install --force --exclude-newer "$(TOOL_COOLDOWN)" --exclude-newer-package "certifi=2026-10-21T00:00:00Z" "semgrep==$(SEMGREP_VERSION)"`
  I verified it in an isolated tool dir: the environment then contains certifi 2026.10.19. Better still, and cheap: add a step that audits the tool environment, for example `uv pip compile --exclude-newer "7 days" …` piped to `osv-scanner`, or `pip-audit` with the tool's Python. That way the next CVE in a tool dependency fails CI instead of being found by hand.
- **Verification:** `~/.local/share/uv/tools/semgrep/bin/python -I -c "import importlib.metadata as m; print(m.version('certifi'))"` prints `>= 2026.10.19`. `test_supply_chain.py` checks the flag (and its removal date, together with the backend one). Optional: the tool audit step is green.
- **Status:** OPEN

### INFO (no action required in this cycle)
- **INFO-9 (mcp in the semgrep environment):** `mcp==1.29.0` (GHSA-84m7-p3x7-pcfv, HIGH) is pinned by semgrep 1.180.0. It only affects a Streamable HTTP MCP **server**, which `semgrep scan` never starts, so it is not reachable here. When semgrep is next bumped, check that the pin moves to `mcp >= 1.30.0`.
- **INFO-10 (allow-list matches the router-relative path):** `_walk` yields routes from `original_router`, so `route.path` is the path **without** the `include_router` prefix. A `Mount("/assets")` inside a router included with `prefix="/x"` is therefore admitted by `allowed_non_api={"/assets"}` (verified). This is harmless today: the allow-list is empty and any entry is explicit and reviewed. When SL-01 adds the static-files mount, admit allow-listed entries only from top-level `app.routes`, or compare against the effective prefixed path.
- **INFO-11 (checked once at assembly):** routes added to the app after `create_app` returns are not inspected (verified: `app.add_route` afterwards → `200`). `create_app` is the single assembly point, so this is acceptable. Keep it that way, for example with an architecture test that forbids `add_route`/`mount`/`include_router` outside `menu.app.factory`.
- **INFO-12 (pre-existing, not from the fix):** the depth guard runs only when `Content-Type` is `application/json`. FastAPI also parses a body as JSON when the header is missing or is `application/*+json`. For unsafe methods the `415` rule closes this gap. For a `GET` endpoint that declares a `Body()` parameter it does not: depth-11 JSON without `Content-Type` → `200` (verified with a scratch route). No such endpoint exists or is planned. Optionally, forbid `Body()` on `GET` with a semgrep rule, or apply the depth/NUL check to every body that is read.

**Done well:** the NUL rule plus the `charset` rule is the smallest correct fix, and its tests cover every encoding and the oversize path. The allow-list inversion is fail-closed, including for unknown FastAPI internals. Tool versions and the cooldown now have a single source in the `Makefile`, guarded by tests.

**Re-check verdict:** SEC-SL00a-001..004 are CLOSED. **One new BLOCKER (SEC-SL00a-010), introduced by the fix of SEC-SL00a-003**, with a one-flag fix. The gate stays closed until it is fixed and re-checked (fix cycle 2).

## Re-check cycle 2 (2026-10-21)

Scope: SEC-SL00a-010 only, plus the fix diff (`Makefile` `TOOL_CERTIFI_EXCEPTION`, `backend/tests/tools/test_supply_chain.py`). Code was not changed.

| Finding | Status | Evidence |
|---|---|---|
| SEC-SL00a-010 (vulnerable certifi in the semgrep tool environment) | **CLOSED** | `Makefile`: `TOOL_CERTIFI_EXCEPTION := certifi=2026-10-21T00:00:00Z`, passed as `--exclude-newer-package` on `tools-semgrep` only. It is the same value as the backend exception in `pyproject.toml` and has the same removal note (~2026-10-27). I ran a fresh `make tools-semgrep` in an isolated `UV_TOOL_DIR`, and it resolves **certifi 2026.10.19** (the fixed version, uploaded 2026-10-20T02:24Z). The installed `~/.local/share/uv/tools/semgrep` receipt shows `exclude-newer-span = "P7D"` plus the certifi exception, and the environment contains certifi 2026.10.19. `osv-scanner` on the full semgrep environment (66 packages) finds only `mcp 1.29.0` (GHSA-84m7-p3x7-pcfv), which is already covered by INFO-9 as not reachable. The zizmor environment contains only `zizmor 1.30.1` (Rust binary, no Python dependencies, no certifi). `osv-scanner` reports no issues there. `test_supply_chain.py`: 10 passed. |

**Cooldown guard after the relaxation (verified with mutation checks on the regexes):** removing `--exclude-newer "$(TOOL_COOLDOWN)"` from either install line still makes `test_scan_tools_installed_with_pinned_version_and_cooldown` fail, and so does setting `TOOL_COOLDOWN` below 7 days. The cooldown itself is still guarded.

INFO only (the anti-loop rule applies: these are not BLOCKERs introduced by the fix, and nothing is vulnerable today):
- **INFO-13 (the certifi regression test's lower bound is one day too early):** `test_semgrep_install_pins_certifi_past_ghsa_6q48` accepts any date `>= "2026-10-19"`. The fixed certifi was uploaded on **2026-10-20T02:24Z**, and certifi **2026.10.18** (uploaded 2026-10-18, still affected: the fix is `2026.10.19`) also exists. I verified the gap. With `certifi=2026-10-19T23:59:59Z`, uv resolves the vulnerable certifi 2026.10.18 and the test still passes. Suggested change: compare the full timestamp against `2026-10-20T02:24:16Z`, or simply require `>= "2026-10-21"`. Better still, add the tool-environment audit step suggested in SEC-SL00a-010 (`osv-scanner` on the tool environment's package list), which would catch this and any future tool CVE by behaviour instead of by string matching.
- **INFO-14 (the relaxed regex admits any single package exception on any tool):** `optional_exception = '(?:--exclude-newer-package "[^"]+" )?'` would also accept, for example, `--exclude-newer-package "requests=2099-01-01T00:00:00Z"` on the zizmor or semgrep line, which bypasses the cooldown for that package (verified on the regex). Suggested change: allow only the literal `"$(TOOL_CERTIFI_EXCEPTION)"` (and only on the semgrep line). Also assert that its date equals the backend `exclude-newer-package.certifi`, so that both exceptions are removed together.

**Re-check cycle 2 verdict:** SEC-SL00a-010 is **CLOSED**. No security BLOCKER is open on SL-00a. INFO-13 and INFO-14 are recommended hardening of the guard tests and do not gate.
