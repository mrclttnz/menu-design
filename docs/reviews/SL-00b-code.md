# Code review · SL-00b

- **Date:** 2026-10-22
- **Reviewer:** code-reviewer
- **Scope:** `git diff 022cb46` (tracked changes: `.github/workflows/ci.yml`, `.gitignore`, `.gitleaks.toml`, `.pre-commit-config.yaml`, `.semgrep/**`, `Makefile`, `scripts/ci.sh`, `scripts/check_semgrep_rules.py`, `backend/pyproject.toml`, `backend/uv.lock`, `backend/scripts/export_openapi.py`, `backend/src/menu/{app/factory.py,app/health.py,common/__init__.py,platform/config.py,platform/http/middleware.py,tenancy/__init__.py}`, `backend/tests/{conftest.py,tools/test_ci_tiers.py,tools/test_supply_chain.py,unit/test_platform_config.py,unit/test_platform_healthz.py}`, `docs/STATUS.md`) plus every untracked file of the slice: `Dockerfile`, `.dockerignore`, `compose.yaml`, `db/bootstrap.sql`, `backend/alembic.ini`, `backend/migrations/**`, `backend/src/menu/{__main__.py,common/context.py,seeding/command.py,seeding/guard.py,tenancy/engine.py}`, `backend/tests/{db,integration,concurrency,property,security}/**`, `backend/tests/support/{ctx,family_specs,inventory,owner,pg}.py`, `backend/tests/tools/test_container.py`, `backend/tests/unit/{test_asgi_body_guard,test_platform_db_config,test_platform_http_gaps,test_seed_guard}.py`, `backend/tests/architecture/test_no_bare_now_in_sql_strings.py`, `scripts/ci-pg-tls.sh`, `scripts/dev-certs.sh`. Reference: plan §2-§3, §5, §6, §7.1 SL-00b; `docs/05-data.md` §3, §6, §11, §12; ADR-0003; ADR-0014.
- **Verdict:** APPROVED (cycle 2 re-check: every FIX-IN-SLICE finding resolved, no new BLOCKER)
- **Cycle:** 2 (re-check of CR-SL00b-001..004 and 009 plus the fix diff)

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL00b-001 | LOW | FIX-IN-SLICE | `backend/tests/tools/test_ci_tiers.py:157-169`; `backend/tests/db/test_inventory_rls.py:287-298`; `backend/tests/property/test_search_norm.py:36-46` | Three tests can never fail, or don't check what their names say | RESOLVED |
| CR-SL00b-002 | LOW | FIX-IN-SLICE | `backend/src/menu/app/health.py:52-63`; `openapi.json` (`/healthz`) | The contract doesn't declare the `503 {"status":"unavailable"}` response; the `default` response says errors are `application/problem+json` | RESOLVED |
| CR-SL00b-003 | LOW | FIX-IN-SLICE | `backend/pyproject.toml:58-59` | `S608` is switched off for all of `tests/**`, which goes against plan §5.4 ("S also active in tests except S101") and the comment on the line above | RESOLVED |
| CR-SL00b-004 | LOW | FIX-IN-SLICE | `.env.example:4-9` | `.env.example` still lists `DB_HOST`/`DB_APP_PASSWORD`… The app now requires `DATABASE_URL_APP` (startup fails without it), and the slice reads `DATABASE_URL_OWNER`, `SEED_TARGET` and `SEED_ALLOWED_DB_HOSTS` | RESOLVED |
| CR-SL00b-005 | LOW | BACKLOG | `backend/src/menu/seeding/command.py:20-25`; `backend/src/menu/seeding/guard.py:58-74` | The seed guard checks the host of `DATABASE_URL_OWNER` only, not the URL(s) the seed will actually write through | OPEN |
| CR-SL00b-006 | LOW | BACKLOG | `backend/tests/support/pg.py:42,144-176,202-243,284-290` | Harness: `menu_owner` connections from the `alembic` subprocess skip `LOCK_OWNER_GATE` (cluster limit 3), and `set_role_passwords` skips `LOCK_BOOTSTRAP` | OPEN |
| CR-SL00b-007 | LOW | BACKLOG | `backend/src/menu/tenancy/engine.py:37-46` | No `pool_pre_ping`: after a DB or pooler restart, the first `family_tx`/`system_tx` on each stale pooled connection returns a 500. Only `ping()` retries | OPEN |
| CR-SL00b-008 | LOW | BACKLOG | `backend/tests/property/test_search_norm.py:27,36` | `max_examples=20` is hard-coded in `@settings`, so the plan §5.5 profiles `ci` (50) and `nightly` (500) can never take effect | OPEN |
| CR-SL00b-009 | LOW | BACKLOG | `Makefile:181`; plan §6.2 `container` job | `trivy config` only analyses the Dockerfile; `compose.yaml` and the workflows are not covered by trivy, although the plan says they are | RESOLVED |
| CR-SL00b-010 | INFO | BACKLOG | `db/bootstrap.sql:120-139` | Revocations target only `anon`/`authenticated`. Other Supabase roles (e.g. `service_role`) may hold `CREATE` on `public`. TO VERIFY on the real project (P-4) | OPEN |
| CR-SL00b-011 | INFO | BACKLOG | `Makefile:62-64`; plan §6.1 `dev` | `make dev` only starts PostgreSQL (no migrations, no server), and there is no local path to give the roles passwords for running the app outside the tests | OPEN |
| CR-SL00b-012 | INFO | BACKLOG | `backend/migrations/versions/0001_clock_context_search.py:36` | The `now_utc` body is the only unqualified call (`now()`); every other function is `pg_catalog`-qualified | OPEN |
| CR-SL00b-013 | INFO | BACKLOG | `last-modified-files.sh` (repo root, untracked) | An unrelated personal watch script sits in the working tree and would be swept into a `git add -A` slice commit | OPEN |

## Findings

### CR-SL00b-001 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/tools/test_ci_tiers.py:157-169` (`test_make_help_lists_activated_targets_as_active`); `backend/tests/db/test_inventory_rls.py:287-298` (`test_generic_isolation_catches_a_missing_with_check`); `backend/tests/property/test_search_norm.py:36-46`
- **Category:** tests
- **Problem:**
  - (a) `out.partition("segnaposto")` looks for the lowercase word, but `make help` prints `Segnaposto` (verified: `make help | grep -i segnaposto` → line 4, capitalised). So `placeholders == ""`, and `target not in "" or …` is always true. Even with the right case, `placeholders.split("\n")[0]` is the heading line, while the placeholder names sit on the next line. The assertion cannot fail.
  - (b) `assert problems == [] or any("accettato" in p ...)` passes for every outcome, so the test asserts nothing. The comment admits this.
  - (c) `test_search_norm_ignores_case_and_accents_of_plain_latin_letters` only checks case folding, and only for ASCII input. Accent removal is never asserted.
- **Scenario:** (a) Someone moves `test-db` back to the placeholder line of `help`, or makes `test-conc` a placeholder again: the test stays green. (b) A PostgreSQL change, or a policy written `FOR INSERT` without `WITH CHECK`: the test stays green. (c) A broken `unaccent` dictionary (e.g. `search_norm` loses `extensions.unaccent`): the property suite stays green. Only the example test in `test_sql_functions.py` would catch it.
- **Suggested fix:**
  - (a) Split on the `Segnaposto` line (case-insensitive), take the **following** line(s), and assert that each activated target is absent from them. Add a negative case on a mutated help text.
  - (b) Assert the actual PostgreSQL behaviour: `problems == []`, with a comment saying that `FOR ALL` reuses `USING` as the check. Or remove the test and rely on the inventory test that already forbids the shape.
  - (c) Add a property built from `st.sampled_from("àèéìòùÀÉç")` mixed with ASCII, asserting `search_norm(accented) == search_norm(stripped)`. Or rename the test to match what it checks.
- **Verification:** Mutate the help text, the policy shape and the function body: each test must go red.
- **Status:** RESOLVED (cycle 2)

### CR-SL00b-002 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/app/health.py:52-63`; `openapi.json` → `paths./healthz.get.responses` (only `200` and `default`: `application/problem+json`)
- **Category:** design (contract)
- **Problem:** Plan §4.3 fixes `503 {"status":"unavailable"}` with `application/json` for `/healthz`. The handler returns exactly that, but the OpenAPI document declares only `200` (Health) and a `default` problem+json response. The published contract is therefore wrong for the 503 path.
- **Scenario:** In SL-01 the generated client (or Schemathesis in nightly) receives a 503 with `application/json` and body `{"status":"unavailable"}`. It expects `application/problem+json` with `ProblemDetails`, so the response is flagged as non-conforming or decoded as an unknown error.
- **Suggested fix:** Declare it on the route, e.g. `responses={503: {"model": Health, "description": "Database non raggiungibile"}}`. Then regenerate `openapi.json` with `make openapi`.
- **Verification:** `test-contract` stays green with the regenerated file. Add an assertion that `/healthz` documents `503` with the `Health` schema.
- **Status:** RESOLVED (cycle 2)

### CR-SL00b-003 · LOW · FIX-IN-SLICE
- **Location:** `backend/pyproject.toml:58-59` (`"tests/**" = ["S101", "S608"]`)
- **Category:** maintainability (convention)
- **Problem:** Plan §5.4 says `S` stays active in tests except `S101`, and the comment on line 58 repeats that. Adding `S608` silences the SQL-string-construction check for every test file. `ruff check tests --select S608` reports 8 hits today, all identifiers taken from the catalog or generated by the test.
- **Scenario:** A future test builds SQL from a fixture parameter or a user-like value (for example a cross-family test). There's no lint signal, and in tests that matters because these tests are copied into application code.
- **Suggested fix:** Remove `S608` from the per-file ignore. For the 8 sites, either use `psycopg.sql.SQL(...).format(sql.Identifier(table))` (already used in `support/pg.py`) or add per-line `# noqa: S608` with a short rationale ("identifier from pg_catalog").
- **Verification:** `ruff check .` is green with the global ignore removed.
- **Status:** RESOLVED (cycle 2)

### CR-SL00b-004 · LOW · FIX-IN-SLICE
- **Location:** `.env.example:4-9`
- **Category:** maintainability (configuration contract)
- **Problem:** The placeholder file still documents `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_APP_USER` and `DB_APP_PASSWORD`, which nothing reads. It omits:
  - `DATABASE_URL_APP`: mandatory, startup fails closed without it, and it must carry `sslmode=verify-full` and `sslrootcert`;
  - `DATABASE_URL_OWNER`: used by `migrations/env.py` and the seed guard;
  - `SEED_TARGET` and `SEED_ALLOWED_DB_HOSTS`.

  The security standard §6 relies on `.env.example` as the one documented list of configuration.
- **Scenario:** A developer copies `.env.example` to `.env` and runs the server. Startup fails with `database_url_app: Field required`, and there is no hint of the expected form or of the `verify-full` requirement.
- **Suggested fix:**
  - Replace the `DB_*` lines with commented entries for `DATABASE_URL_APP` and `DATABASE_URL_OWNER`. Describe the shape in a comment (scheme `postgresql+psycopg`, role `menu_app` or `menu_owner`, query `sslmode=verify-full` plus `sslrootcert=db/dev-certs/ca.crt`), and use only the existing `CHANGE_ME` placeholder convention, never a real value.
  - Add `SEED_TARGET` and `SEED_ALLOWED_DB_HOSTS`.
- **Verification:** Add a `tests/tools` check that every `Settings` field and every `os.environ`/`env.get` key read under `src/` and `migrations/` appears in `.env.example`.
- **Status:** RESOLVED (cycle 2)

### CR-SL00b-005 · LOW · BACKLOG
- **Location:** `backend/src/menu/seeding/command.py:20-25`; `backend/src/menu/seeding/guard.py:58-74`
- **Category:** security (CWE-693, defense in depth)
- **Problem:** The allow-list compares only the host of `DATABASE_URL_OWNER`. The dataset library doesn't exist yet, so nothing defines which URL the seed will actually connect with. If it writes through `DATABASE_URL_APP` (or both), the guarded URL and the URL used can differ. The guard also accepts `APP_ENV=dev` together with `SEED_TARGET=staging`. That's harmless, but it isn't documented as intended.
- **Scenario:** `APP_ENV=staging`, `SEED_TARGET=staging`, `DATABASE_URL_OWNER` pointing at an allow-listed staging host, and `DATABASE_URL_APP` left pointing at production in a reused job definition. If the seed connects as `menu_app`, the guard passes and synthetic rows land in production (THR-133).
- **Suggested fix:** When the dataset library arrives (SL-10a), have `run()` validate **every** database URL the command will open, and pass that same validated URL to the writer. Never re-read the environment after the guard.
- **Verification:** Add a seed command test with an allow-listed owner URL and a non-allow-listed app URL: expect exit 2 and no connection on either listener.
- **Status:** OPEN

### CR-SL00b-006 · LOW · BACKLOG
- **Location:** `backend/tests/support/pg.py:42` (`LOCK_OWNER_GATE`), `:144-154` (`set_role_passwords`), `:157-176` (`alembic`), `:202-243` (`ensure_templates`), `:284-290` (`owner_connect`)
- **Category:** tests (harness race)
- **Problem:**
  - `owner_connect` serialises the helper's `menu_owner` connections so that the cluster-wide `CONNECTION LIMIT 3` is respected. But every `pg.alembic(...)` subprocess also connects as `menu_owner` without taking the gate. That includes the template build and the five scratch-database tests in `test_migrations.py`. With `-n 4` (`PG_WORKERS`), three migration tests plus a helper call can exceed 3 connections at once.
  - Separately, `set_role_passwords` runs `ALTER ROLE` under `LOCK_TEMPLATE` but not under `LOCK_BOOTSTRAP`. Meanwhile, `test_bootstrap_*` in another worker can run `run_bootstrap` (which also does `ALTER ROLE`) on a scratch DB without waiting for the template. That reopens the "tuple concurrently updated" race the comment on line 137 describes.
- **Scenario:** On a cold cluster, or as the suite grows, there are intermittent `FATAL: too many connections for role "menu_owner"` or `tuple concurrently updated` errors in `make test-db`. Not reproduced: 6 runs of `tests/db tests/integration -n 8` were all green (163 passed each).
- **Suggested fix:** Take `LOCK_OWNER_GATE` around `alembic(...)`, for example inside `pg.alembic` with a gate connection held for the subprocess's lifetime. Take `LOCK_BOOTSTRAP` inside `set_role_passwords`.
- **Verification:** Run `pytest tests/db -n 8` five times in a loop on a freshly reset cluster (`make db-reset dev`) with no failures.
- **Status:** OPEN

### CR-SL00b-007 · LOW · BACKLOG
- **Location:** `backend/src/menu/tenancy/engine.py:37-46`
- **Category:** correctness (resilience)
- **Problem:** The pool has no `pool_pre_ping`. `ping()` handles `connection_invalidated` with one retry, but `family_tx`/`system_tx` don't. After a Supavisor restart, a DB restart or an idle disconnect, each stale pooled connection (up to `pool_size=5`) fails the first business request with an `OperationalError`, which becomes a 500. `pool_recycle=300` only narrows the window.
- **Scenario:** Supabase restarts the pooler during maintenance. The next five requests that need the database return `500 internal`, although `/healthz` already says `ok`.
- **Suggested fix:** Set `pool_pre_ping=True` (one cheap round trip per checkout, in line with the pooler's transaction mode). Alternatively, apply the same single retry in `family_tx`/`system_tx` when the failure happens on `BEGIN`, before any statement of the caller.
- **Verification:** Mirror `test_ping_recovers_after_the_pooled_connection_was_killed` for `system_tx()`: terminate the `menu_app` backends, then a `system_tx` `select 1` must succeed.
- **Status:** OPEN

### CR-SL00b-008 · LOW · BACKLOG
- **Location:** `backend/tests/property/test_search_norm.py:27`, `:36`
- **Category:** tests
- **Problem:** `@settings(max_examples=20, derandomize=True, …)` on each test overrides any loaded Hypothesis profile. Plan §5.5 defines `ci-small` (20) for `make ci`, `ci` (50) for `make test`/`make full`, and `nightly` (500). With the current code, every level runs 20 examples.
- **Scenario:** `make full` at the end of M0 claims to run property profile `ci` (50) and `nightly` (500), but it actually runs 20 examples. The evidence overstates the coverage.
- **Suggested fix:** Register the profiles in `tests/conftest.py` (`settings.register_profile("ci-small", max_examples=20, derandomize=True, deadline=None)`, and the same for `ci` and `nightly`). Select them with `HYPOTHESIS_PROFILE` or `--hypothesis-profile` from the Makefile, and drop `max_examples` from the decorators.
- **Verification:** `pytest tests/property --hypothesis-profile=nightly --hypothesis-show-statistics` reports 500 examples.
- **Status:** OPEN

### CR-SL00b-009 · LOW · BACKLOG
- **Location:** `Makefile:181`; plan §6.2 (`container`: "`trivy config` su Dockerfile, `compose.yaml` e workflow")
- **Category:** design (plan fidelity)
- **Problem:** The `trivy config .` run in this review lists a single target, `Dockerfile │ dockerfile │ 0`. Trivy has no misconfiguration scanner for docker-compose or for GitHub Actions, so the plan's claim isn't met by this command. Workflows are covered by zizmor and the SHA-pin grep. `compose.yaml` is covered only by the regexes in `tests/tools/test_container.py` (digest, `127.0.0.1` binding, no literal password, `ssl=on`).
- **Scenario:** A future `compose.yaml` change adds `privileged: true` or publishes `0.0.0.0:5432`. No scanner flags it, and the `127.0.0.1` regex only checks for the presence of the good line, not for the absence of others.
- **Suggested fix:** Decision for the tech-lead: either amend plan §6.2 to "trivy config on Dockerfile; compose by `test_container`; workflows by zizmor", or extend `test_container.py` with negative checks on `compose.yaml` (no `privileged`, no `network_mode: host`, every `ports` entry bound to `127.0.0.1`).
- **Verification:** The plan text and the tooling agree, and a mutated `compose.yaml` makes the test fail.
- **Status:** RESOLVED (cycle 2)

### CR-SL00b-010 · INFO · BACKLOG
- **Location:** `db/bootstrap.sql:120-139`
- **Category:** security (THR-044), TO VERIFY
- **Problem:** `docs/05-data.md` §3.1 names only `anon` and `authenticated`, and the script follows it. A stock Supabase project also has `service_role`, and possibly other platform roles, with privileges on `public`. §6.4 requires that "no role other than `menu_owner` can `CREATE` in `app` and `public`". The local inventory can't see this, because those roles don't exist locally.
- **Scenario:** The §6.4 inventory run against the real Supabase project (P-4, ADR-0014 point 5) fails, or worse, isn't run, and `service_role` keeps `CREATE` on `public`.
- **Suggested fix:** Data-architect: verify on the real project with `select rolname from pg_roles where has_schema_privilege(rolname,'public','CREATE')`. If needed, extend the conditional revoke list (same `IF EXISTS` pattern) and §3.1.
- **Verification:** Run `test_schema_privileges.py` (or the equivalent catalog query) against the Supabase project and record the result in `docs/09-release.md`.
- **Status:** OPEN

### CR-SL00b-011 · INFO · BACKLOG
- **Location:** `Makefile:62-64` (`db-up dev: dev-certs`); plan §6.1 (`dev`: "PostgreSQL locale, migrazioni, server con ricarica, Vite")
- **Category:** maintainability (developer experience)
- **Problem:** `make dev` starts only the database. Locally, the roles are created by the test harness (with a synthetic test password), not by any dev step. So there is no documented way to run `bootstrap.sql`, set local role passwords, run `alembic upgrade head` and start `python -m menu serve` against the local cluster.
- **Scenario:** A developer wants to try `/healthz` against a real database outside pytest and has to reverse-engineer `tests/support/pg.py`.
- **Suggested fix:** In SL-01, when `dev` gains Vite, add a local-only script that does the bootstrap, sets random local passwords written to `db/dev-certs/` (already gitignored), runs the migrations, and starts uvicorn with `--reload`.
- **Verification:** `make db-reset dev` followed by `curl -s 127.0.0.1:8000/healthz` returns `{"status":"ok"}`.
- **Status:** OPEN

### CR-SL00b-012 · INFO · BACKLOG
- **Location:** `backend/migrations/versions/0001_clock_context_search.py:36` (`NOW_UTC_BODY = "select now()"`)
- **Category:** maintainability
- **Problem:** The docstring explains why `now()` is safe unqualified: `pg_catalog` is searched first, and nobody can create objects in `public`. That holds only while no caller puts a schema before an explicit `pg_catalog` in `search_path`. Writing `pg_catalog.now()` would make 0001 uniformly qualified, at the cost of updating the marker line, the semgrep exception regex and the `test_now_utc` body assertion.
- **Scenario:** No realistic exploit today: only `menu_owner` can create in `app`.
- **Suggested fix:** Optional. Qualify the call and update the three places together.
- **Verification:** `semgrep --test` fixtures and `tests/db/test_now_utc.py` stay green.
- **Status:** OPEN

### CR-SL00b-013 · INFO · BACKLOG
- **Location:** `last-modified-files.sh` (repository root, untracked)
- **Category:** maintainability
- **Problem:** A personal `watch`/`find` helper that isn't part of the slice or the plan's repository structure (§1) sits next to the slice files.
- **Scenario:** The automatic end-of-slice local commit (plan §5.7) uses `git add -A` and commits it.
- **Suggested fix:** Stage the slice files explicitly, or move the script outside the repository, or add it to a local `.git/info/exclude`.
- **Verification:** `git status` after the slice commit shows the file still untracked, or gone.
- **Status:** OPEN

## Re-check (cycle 2, 2026-10-22)
Scope: the fix diff only (`backend/tests/tools/test_ci_tiers.py`, `backend/tests/db/test_inventory_rls.py`, `backend/tests/property/test_search_norm.py`, `backend/src/menu/app/health.py`, `openapi.json`, `backend/pyproject.toml`, `.env.example`, `docs/07-plan.md` §6.2, `backend/tests/tools/test_container.py`, `backend/src/menu/seeding/guard.py`, `backend/src/menu/tenancy/engine.py`, `.semgrep/sql.yaml`, `.semgrep/sql.py`, `scripts/check_semgrep_rules.py`).

| ID | Result | Evidence |
|---|---|---|
| CR-SL00b-001 | RESOLVED | (a) `help_sections()` splits case-insensitively on the `Segnaposto` line and checks the lines after it, and `test_help_check_goes_red_when_an_activated_target_is_a_placeholder` proves the check can fail. (b) The tautology is replaced by `test_for_all_policy_without_with_check_reuses_using_as_the_check` (asserts `== []`, the real PostgreSQL behaviour) and `test_generic_isolation_catches_a_permissive_with_check` (`WITH CHECK (true)` must be caught). (c) `test_search_norm_strips_accents_and_folds_case` compares against an independent transcription of accented input; the ASCII case test is named for what it checks |
| CR-SL00b-002 | RESOLVED | `responses={503: {"model": Health, ...}}` on the route; `openapi.json` now documents `503` → `application/json`, `Health`; contract tests green |
| CR-SL00b-003 | RESOLVED | `"tests/**" = ["S101"]`; `ruff check .` → `All checks passed!` |
| CR-SL00b-004 | RESOLVED | `.env.example` lists `DATABASE_URL_APP` and `DATABASE_URL_OWNER` (value `CHANGE_ME`; the shape and `verify-full`/`sslrootcert` are described in comments), plus `SEED_TARGET` and `SEED_ALLOWED_DB_HOSTS`; the stale `DB_*` lines are gone. With the file copied as-is, startup still fails closed (a `CHANGE_ME` URL is rejected) |
| CR-SL00b-009 | RESOLVED (option A) | Plan §6.2 now states that trivy config covers only the Dockerfile, workflows are covered by zizmor and `compose.yaml` by `test_container`. `compose_port_violations()` checks non-localhost ports, `privileged`, `network_mode: host` and the Docker socket, and 6 mutation cases prove it can fail |

**Regressions from the fix diff:** none at BLOCKER level, so there are no new findings (anti-loop rule). Notes for awareness, not findings:
- `HealthProbe.database_ok` now uses a non-blocking lock. A request that arrives while a check is running gets the last result instead of queueing, which avoids queued threads. During the very first check after startup that result is the initial `False`, so a concurrent request can briefly get a 503. This is fail-closed and acceptable for a probe. The window is now measured after the check (good).
- `tenancy.init` adds `tcp_user_timeout` and keepalives (libpq options supported by the bundled libpq 17). The tenancy, healthz and concurrency suites are green.
- `seeding/guard.py` now refuses URLs whose query overrides the host (`host`, `hostaddr`, `service`). This strengthens the guard; CR-SL00b-005 (the guarded URL is the owner URL only) remains BACKLOG.
- In `.semgrep/sql.yaml`, the new rule `menu-set-config-outside-tenancy` forbids `set_config(` anywhere in `src/` except `menu.tenancy`. `docs/05-data.md` §3.1 has the caller set `app.correlation_id` with `set_config(…, true)`, so from SL-02 `tenancy` must expose that (for example a `correlation_id` argument to `family_tx`/`system_tx`). The rule fixtures pass (`3/3 ✓`, `16 casi di percorso OK`).

**Cycle 2 commands:**

| Tool | Command | Result |
|---|---|---|
| ruff / format / mypy | `ruff check .`; `ruff format --check .`; `mypy` | `All checks passed!`; `96 files already formatted`; `Success: no issues found in 94 source files` |
| pytest unit/arch/tools/contract | `pytest tests/unit tests/architecture tests/tools tests/contract -m "not container"` | `489 passed, 3 deselected` |
| pytest db / int / sec / prop | `-n 4` each | `156` / `10` / `4` / `3 passed` |
| pytest concurrency ×3 | `-n 2` three times | `1 passed` ×3 |
| container tests | `pytest tests/tools/test_container.py` (includes build) | `19 passed` |
| semgrep | `semgrep --test …/sql.yaml .semgrep/sql.py`; `check_semgrep_rules.py`; `semgrep --error --config .semgrep backend` | `3/3 ✓`; `16 casi di percorso OK`; rc 0 |

Still open, all BACKLOG (to record in `docs/STATUS.md` technical debt): CR-SL00b-005, 006, 007, 008, 010, 011, 012, 013.

## Tools run (cycle 1)
| Tool | Command | Result |
|---|---|---|
| ruff | `backend/.venv/bin/ruff check .` / `ruff format --check .` | `All checks passed!` / `89 files already formatted` |
| ruff (probe) | `ruff check tests --isolated --select S608` | `Found 8 errors.` (hidden by the per-file ignore, see CR-SL00b-003) |
| mypy | `backend/.venv/bin/mypy` (strict, `src tests scripts`) | `Success: no issues found in 87 source files` |
| bandit | `bandit -r src -c pyproject.toml` | 0 issues |
| pytest unit/arch/tools/contract | `pytest tests/unit tests/architecture tests/tools tests/contract -m "not container"` | `429 passed, 3 deselected` |
| pytest db | `pytest tests/db -n 4` (local PG17 over TLS `verify-full`) | `155 passed` |
| pytest integration / security / property | `pytest tests/integration -n 4` · `tests/security -n 4` · `tests/property -n 4` | `8 passed` · `4 passed` · `2 passed` |
| pytest concurrency ×3 | `pytest tests/concurrency -n 2` three times | `1 passed` ×3 |
| race probe | `pytest tests/db tests/integration -n 8`, 6 runs | `163 passed` ×6 (no flake reproduced) |
| bootstrap on a non-superuser (Supabase-like) | throwaway `postgres:17` (same digest), role `sbpg LOGIN CREATEROLE CREATEDB` owning the DB, `anon`/`authenticated` present, `psql -f bootstrap.sql` twice | both runs OK. Roles have the expected limits and settings, the temporary `menu_owner` membership was revoked (only the PG16+ automatic ADMIN grant remains), and `app`, `public` and the default ACLs are as designed. Container removed |
| semgrep custom rules | `semgrep --test --config .semgrep/sql.yaml .semgrep/sql.py`; same for `migrations-now`; `python3 -I scripts/check_semgrep_rules.py` | `3/3 ✓`, `1/1 ✓`, `13 casi di percorso OK` |
| semgrep on code | `semgrep --metrics=off --error --config .semgrep backend` | rc 0 |
| gitleaks | `gitleaks dir . -c .gitleaks.toml` | `no leaks found` |
| zizmor | `zizmor --offline .github/workflows` | `No findings` (6 suppressed) |
| hadolint | `hadolint Dockerfile` | OK |
| docker / trivy | `docker build`; `trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1`; `trivy config …` | build OK; image rc 0; config rc 0, but only the `Dockerfile` target was scanned (CR-SL00b-009) |
| image runtime | `docker run --entrypoint id <img> -u`; run with `sslmode=require` | `10001`; startup refused with `DATABASE_URL_APP richiede esattamente sslmode=verify-full`, without echoing the URL |
| lockfile | `uv lock --check --offline`; versions in `uv.lock` | consistent; sqlalchemy 2.1.4, alembic 1.20.0, psycopg(-binary) 3.3.6, pytest-xdist 3.8.0, hypothesis 6.169.1 (well-known packages on PyPI, as in the plan) |
| GitHub workflow | not run (no push consent) | the `backend` DB service and `container` job are UNVERIFIED on GitHub runners |

## What was done well
The DB core of the slice follows `docs/05-data.md` and ADR-0003 closely:
- **`tenancy`** sets context only with `set_config(…, true)` and binds its parameters. Pool reuse and context isolation under concurrency are tested.
- **`bootstrap.sql`** is pure SQL, idempotent (snapshot-compared), and also works as a non-superuser.
- **Migrations:** `env.py` checks the URL, `current_user`, `session_user` and the schema owner before any change. `0001` checks its prerequisites and is fully qualified apart from the clock.
- **`now_utc`** replacement is tested to keep the OID and to drive defaults.
- **Inventories** each come with "it can fail" tests on synthetic objects.
- **`/healthz`** caches its result and is serialised behind a lock, with canary tests for leaks.
- **Seed guard** is allow-list only and opens no connection.

Several SL-00a debts were also closed with regression tests: CR-SL00a-007 (body read always), 009, 010, 012 and 013.
