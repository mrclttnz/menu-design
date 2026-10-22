# SL-01: security review

| Field | Value |
|---|---|
| Slice | SL-01: web shell end-to-end, i18n, generated client (SPA served by FastAPI from the same container) |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-22 |
| Diff base | `08d6432` (nothing committed: `git diff 08d6432` plus the untracked files; `web/node_modules`, `dist`, `coverage`, `test-results` ignored) |
| SRs in scope | SR-023 (CSP with Trusted Types, headers), SR-031 (no third-party scripts, `connect-src 'self'`), SR-046 (`no-cache` / `immutable` / `no-store`), SR-076 (`web/pnpm-workspace.yaml`) |
| THRs in scope | THR-070 (base), THR-074, THR-075, THR-090 |
| Debt assigned to SL-01 | SEC-SL00a INFO-10, INFO-12; SEC-SL00b-006; SL-00a note (415 without `Content-Type`, CSP `style-src 'self'`) |
| Verdict | **APPROVED.** No BLOCKERs and no FIX-IN-SLICE findings. 2 LOW BACKLOG findings and 4 INFO notes. All 4 debt items assigned to SL-01 are resolved. |

The controls are proportionate to a low-stakes app, as the user asked. Both LOW fixes are one-line changes.

## 1. What was checked and how

**Files read in full:**
- backend: `platform/http/static.py` (new), `platform/http/middleware.py`, `platform/logging.py`, `platform/routing.py`, `platform/config.py`, `app/factory.py`, `__main__.py`;
- container, CI and supply chain: `Dockerfile`, `.dockerignore`, `.gitignore`, `.env.example`, `.github/workflows/ci.yml`, `Makefile` (web, e2e and scan targets, `WEB_AUDIT_VERDICT`), `scripts/ci.sh`, `osv-scanner.toml`, `web/package.json`, `web/pnpm-workspace.yaml`, the `web/pnpm-lock.yaml` header and its sources;
- web: `index.html`, `vite.config.ts`, `playwright.config.ts`, `eslint.config.js` (security rules), `src/main.tsx`, `src/api/client.ts`, `src/api/errors.ts`, `src/app/{providers,routes}.tsx`, `src/i18n/index.ts`, `src/features/auth/LoginPage.tsx`, `src/components/Toast.tsx`; `.semgrep/frontend.{yaml,tsx}`;
- tests: `tests/e2e/csp.spec.ts`, plus the list of the e2e security, header, third-party and XSS specs, and the backend static and log-redaction tests;
- decision: `docs/adr/ADR-0017-rischio-accettato-braces-strumenti-lingui.md`.

**Tools run (fresh output, 2026-10-22):**

| Command | Result |
|---|---|
| `make scan-secrets` (`gitleaks git` + `gitleaks dir`) | **no leaks found** (history ~1.8 MB, working tree ~4.2 MB) |
| `make scan-sast` (custom-rule tests, then semgrep p/python, p/owasp-top-ten, p/typescript, p/react, `.semgrep` on `backend web`) | rc=0. Rule tests green, 0 findings. The new `menu-dom-html-sink` and `menu-dynamic-code-eval` rules have positive and negative fixtures |
| `make scan-web` (`pnpm audit --json` + dated filter) | rc=0. The raw report has exactly 1 advisory: high GHSA-vfj7-8cjw-p6xm `braces` <=3.0.3, only through `micromatch` <- `@lingui/cli` / `@lingui/vite-plugin` / `eslint-plugin-lingui` (all devDependencies). 0 low, moderate or critical. 381 packages |
| `make scan-web WEB_AUDIT_EXCEPTION_UNTIL=2026-10-01` (simulated expiry) | **fails**: `audit: eccezione … scaduta`, Error 1 |
| `osv-scanner` on `web/pnpm-lock.yaml` + `backend/uv.lock` with `osv-scanner.toml` | No issues found (1 vulnerability filtered: the same GHSA) |
| `osv-scanner` with a copy of the config set to `ignoreUntil = 2026-10-01` | reports `braces 3.0.3` GHSA-vfj7-8cjw-p6xm: the expiry works |
| `pnpm-lock.yaml` inspection | 381 `integrity:` entries. No `tarball:`, `git+` or `github:` sources. pnpm 12.14.0 itself is pinned with `sha512` (`packageManagerDependencies`). `pnpm config get minimumReleaseAge` = 10080, `onlyBuiltDependencies` = `["esbuild"]`. Install output: "Lockfile passes supply-chain policies" |
| Adversarial probe of `StaticSite` (scratchpad script, temporary copy of `dist`, with planted symlinks, `.env`, `.map` and an out-of-root secret) | 29 paths, **0 leaks**: `..`, `%2e%2e`, `%2f`, `//`, `\`, NUL, `./`, symlinked file, symlinked dir, `.git/config`, `.env`, `.map`, `/ASSETS/…`, `/x.php` → 404. SPA routes → `index.html`. `/api`, `/api/*` → 404. `POST /` → 405 |
| Live server (`python -m menu serve`, dummy DB, `WEB_DIST_DIR=web/dist`) + `curl` | `/`: `no-cache`, ETag, full CSP with `require-trusted-types-for 'script'`, HSTS, `nosniff`, `Referrer-Policy`. Hashed asset: `public, max-age=31536000, immutable`, gzip. `/api/nope`: problem+json with `no-store`. `--path-as-is` traversal → 404. `/openapi.json` → 404; `/docs` → SPA HTML, not Swagger |
| `pnpm exec playwright test` (all 114 e2e, mobile-360 + desktop, with axe) | **114 passed (13.8 s).** This includes: no CSP violations or console errors on every view; Trusted Types blocks `innerHTML`, `insertAdjacentHTML`, `document.write` and script text; `eval` / `new Function` blocked; cross-origin `connect` and `img` blocked; `frame-ancestors`; same-origin-only requests; hostile URLs execute nothing; nothing in storage; no service worker. See INFO-4 for how the local run was done |
| Built bundle grep (`dist/assets/*.js`) | no `eval(`, `new Function`, `createPolicy` or `document.write`. 5 `innerHTML` occurrences, all inside React DOM internals (reachable only through `dangerouslySetInnerHTML`, which ESLint and semgrep forbid). The only absolute URLs are XML namespaces and React/React Router error-doc strings: no third-party endpoints |
| `pytest` on `test_static_files`, `test_static_dot_segments`, `test_static_mount_and_body_guard_gaps`, `test_stdlib_log_redaction` | 103 passed |
| Stdlib redaction probe (`configure_logging()`, then a sqlalchemy warning carrying an email, and `uvicorn.error.exception` with a password in the exception message) | output is only `{"event": "stdlib.sqlalchemy.engine", …}` and `{"event": "stdlib.uvicorn.error", "exception": "ValueError", …}`: no message text, args, extras or traceback. `INFO` from uvicorn is filtered (root at WARNING) |
| `vitest` on `supply-chain`, `eslint-rules`, `api/client` | 132 passed |
| `make tier-container` (hadolint, build, `trivy image` HIGH/CRITICAL with fix, `trivy config`, container tests) | rc=0. 7 container tests passed (4 new in `test_container_web.py`). In the image: uid 10001; `/app/web-dist` holds only `index.html`, `favicon.svg` and 3 hashed assets, owned by root and read-only for the app user |
| `zizmor .github/workflows` | No findings (8 suppressed, offline mode as before) |
| `hadolint Dockerfile`, `trivy config Dockerfile` | clean / 0 misconfigurations |

## 2. Findings

### SEC-SL01-001 · LOW · BACKLOG
- **Location:** `backend/src/menu/platform/http/middleware.py:30-34` (`SECURITY_HEADERS["Content-Security-Policy"]`)
- **Category:** security (CWE-1021 / defense in depth for CWE-79, THR-070)
- **Problem:** the CSP turns on Trusted Types enforcement (`require-trusted-types-for 'script'`) but does not restrict policy creation with a `trusted-types` directive. Any code on the page can therefore call `trustedTypes.createPolicy("default", { createHTML: s => s })`, and a permissive `default` policy silently turns every HTML sink back into a plain string sink. Separately, `img-src` still allows `data:`, which the SPA does not use: `assetsInlineLimit: 0`, and there are no `data:` URIs in `src/` or in the CSS.
- **Scenario:** a future dependency, or a convenience shim written to "fix" a Trusted Types error, registers a `default` policy. Today nothing reports it, and the guarantee verified in this slice (`innerHTML` with a string throws `TypeError`) quietly disappears. The bundle creates no policies today (`createPolicy` occurs 0 times), so restricting this costs nothing.
- **Suggested fix:** add `trusted-types 'none'` to the CSP. If a policy is needed later, name it explicitly (`trusted-types menu-safe`) and never allow `default` or `'allow-duplicates'`. Drop `data:` from `img-src` (`img-src 'self'`).
- **Verification:** extend the header assertions in `tests/unit/test_static_files.py` / `tests/e2e/security-headers.spec.ts` with `trusted-types 'none'` and `img-src 'self'`. Add an e2e case: `trustedTypes.createPolicy("default", …)` throws. The existing "no CSP violations" e2e tests must stay green.
- **Status:** OPEN (BACKLOG; natural home is SL-03a, which touches headers for CSRF and cookies, or now if convenient)

### SEC-SL01-002 · LOW · BACKLOG
- **Location:** `.dockerignore:3-6` (`.env`, `.env.*` match only at the root of the context), and no `web/coverage` entry
- **Category:** security (CWE-538 / CWE-200: local files leaking into a build artifact; SR-076, THR-092)
- **Problem:** the `web` build stage runs `COPY web/ ./` and then `vite build`. Vite loads `web/.env`, `web/.env.local` and `web/.env.production[.local]` and inlines every `VITE_*` variable into the public bundle. These files are ignored by git (`.gitignore` `.env*` applies at any depth), but they are not excluded from the Docker context, because `.dockerignore` patterns without `**/` only match at the root. `web/coverage/` (lcov with source paths) is also copied into the build stage. It does not reach the final image, but it does reach the context.
- **Scenario:** a developer creates `web/.env.local` with a `VITE_…` value for a local experiment. A local `make tier-container`, or a manual release build from that machine, embeds the value in `index-*.js`, which is served to everyone. CI is not affected (clean checkout). Low likelihood, low impact.
- **Suggested fix:** in `.dockerignore`, use `**/.env` and `**/.env.*` with `!.env.example`, and add `web/coverage`.
- **Verification:** in `tests/tools/test_container_web.py`, create a temporary `web/.env.local` with `VITE_CANARY=…`, build, then grep `/app/web-dist` for the canary: expect 0 matches. Alternatively, a static test that `.dockerignore` contains `**/.env*`.
- **Status:** OPEN (BACKLOG, SL-10b at the latest)

## 3. Notes (INFO, no action required in this slice)

- **INFO-1 · ADR-0017 (braces).** The upstream advisory is rated HIGH (CVSS 8.7), but in this context the risk is **LOW**:
  - the package is dev-only (`pnpm why braces`: only through `micromatch` <- Lingui CLI / Vite plugin / ESLint plugin);
  - it is not in the bundle;
  - the glob patterns are repository-controlled;
  - the CI jobs have `contents: read`, `persist-credentials: false` and no secrets.

  So the acceptance does not conflict with the review contract, which forbids accepting HIGH *findings*: the contextual finding is LOW. I verified the 3 controls the ADR asks for:
  - the exception is limited to the single GHSA ID in both tools;
  - both tools go red after the expiry (simulated);
  - the debt is recorded in STATUS.

  Note that `@lingui/vite-plugin` also runs inside the Docker `web` build stage. That is still build time, and the ADR text covers it in substance. Suggested STATUS wording: "upstream HIGH, contextual LOW, accepted dev-only".
- **INFO-2 · Referrer-Policy on the invite page (THR-074, THR-032).** The policy is global `strict-origin-when-cross-origin`. THR-074 asks for `no-referrer` at least on `/invito`. The secret is in the fragment, so it never appears in `Referer`, but the threat-model control remains. Plan it in SL-11, either per-path in `StaticSite` or globally, since the SPA has no cross-origin links.
- **INFO-3 · Stdlib log redaction is total.** Every stdlib record (uvicorn, sqlalchemy) keeps only the logger name and the exception type. This closes SEC-SL00b-006 correctly. The operational trade-off is that a startup failure (for example a port bind error) shows only `stdlib.uvicorn.error` with `OSError`. That is acceptable for now. If diagnostics suffer, allow-list a few fixed uvicorn message templates, never formatted args.
- **INFO-4 · Local e2e prerequisites.** On this WSL machine headless Chromium lacks system libraries (`libnspr4`, `libnss3`, `libnssutil3`, `libasound2`), so `make e2e` fails before any test runs. The CSP and Trusted Types checks are browser-only evidence. Install the libraries once with `cd web && sudo pnpm exec playwright install-deps chromium`. For this review I extracted the 4 libraries from the pinned `node:24-slim` image into the scratchpad and ran the suite with `LD_LIBRARY_PATH`, which gave 114 passed. CI already uses `--with-deps`.

## 4. SR, THR and debt coverage

| Item | Verdict | Evidence |
|---|---|---|
| SR-023 / THR-070 (CSP, Trusted Types, no HTML sinks) | Met | CSP on every response (live `curl`, e2e header spec). TT enforced by the browser (e2e). ESLint `no-restricted-syntax`, `no-eval`, `no-new-func` and semgrep `menu-dom-html-sink` / `menu-dynamic-code-eval` on `src/**`. Client error mapping uses only `code` / `params`, never server `title` / `detail`. Hostile-URL e2e. Hardening: SEC-SL01-001 |
| SR-023 / THR-074 (clickjacking, sniffing, Referer, HSTS) | Met for M0 | `frame-ancestors 'none'` (e2e), `nosniff`, HSTS, `Referrer-Policy`. Content types come from an explicit map. INFO-2 for M1 |
| SR-031 (no third parties, `connect-src 'self'`) | Met | `third-party.spec.ts` (requests and built files), bundle grep, CSP `connect-src 'self'` enforced (e2e). Client `SAME_ORIGIN_PATH` regex, `credentials: "same-origin"`. No CORS middleware |
| SR-046 / THR-075 (`no-cache`, `immutable`, `no-store`) | Met | `index.html` and fallback `no-cache` + ETag. Only hashed assets are `immutable`. A missing `sw.js` is 404, never HTML. API keeps `no-store` (`setdefault` in `EnvelopeMiddleware`) |
| SR-076 / THR-090 (supply chain) | Met | Lockfile with integrity, frozen installs everywhere (Make, CI, Dockerfile). 7-day cooldown and build-script allow-list `[esbuild]` read back from pnpm 12. pnpm pinned with sha512. `pnpm audit` and osv-scanner on `pnpm-lock.yaml` are blocking in `make scan` / CI. Node base image pinned by digest. Actions pinned by SHA, `contents: read`, `persist-credentials: false`. New dependencies are all canonical registry names, and the audit is clean apart from the accepted GHSA |
| Static serving path handling | Met | Allow-list design (root file set, single-level `/assets/` with safe-segment regex and extension set), dot-segment / NUL / backslash / hidden rejection, `resolve(strict=True)` + parent check + `is_relative_to` + `is_symlink`. 29 adversarial probes gave 0 leaks. GET/HEAD only. `/api*` never falls back. Installed as `router.default`, so API routes always win. `dist` is read-only and root-owned in the image |
| Container / CI changes | Met | Node and pnpm stay out of the final image. Only `dist` is copied. Non-root user unchanged. trivy, hadolint and zizmor clean. The new CI jobs have no secrets. The upload artifact is limited to failure runs, 7 days, synthetic data only |
| SEC-SL00a INFO-10 (allow-list ignored router prefix) | Resolved | `assert_all_routes_declare_authz` applies `allowed_non_api` only to top-level routes. Every leaf of an included router must be `AuthzRoute`. Tests in `test_static_mount_and_body_guard_gaps.py` |
| SEC-SL00a INFO-12 (depth check skipped without `Content-Type`) | Resolved | `is_json_like_content_type` mirrors FastAPI (missing, `application/json`, `application/*+json`). The depth, NUL and charset checks now run for all of them. Tested |
| SEC-SL00b-006 (stdlib loggers bypass redaction) | Resolved | Root handler with `ProcessorFormatter` + `redact`. Uvicorn `log_config=None`. Probe output shown in section 1. INFO-3 |
| SL-00a note (415, `style-src 'self'`) | Resolved | The client always sends `Content-Type: application/json` on non-GET requests. No CSP violations on any view (e2e) with `style-src 'self'` unchanged |

**Done well:** the static server is an allow-list with fail-closed fallbacks and a symlink check. The audit exception filters on a single ID, expires on its own and fails closed on an unreadable report. The CSP and Trusted Types guarantees are proven in a real browser rather than only asserted as header strings.

## 5. Re-check

Not needed: there are no BLOCKER or FIX-IN-SLICE findings. The two LOW BACKLOG findings go into the technical debt table in `docs/STATUS.md` (orchestrator).
