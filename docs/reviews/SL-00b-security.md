# SL-00b: security review

| Field | Value |
|---|---|
| Slice | SL-00b: local DB, `bootstrap.sql`, migration `0001` and `now_utc`, `tenancy`, DB inventories, container |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-22 |
| Diff base | `022cb46` (nothing committed: `git diff 022cb46` plus the untracked files read in full) |
| SRs in scope | SR-029, SR-042, SR-075 (base), SR-076 |
| THRs in scope | THR-026, THR-027, THR-043, THR-044 (base), THR-048, THR-092, THR-106, THR-133; actions A-13, A-22, A-24, A-25 |
| Verdict | **APPROVED after re-check cycle 1 (2026-10-22).** No BLOCKERs. The 3 LOW FIX-IN-SLICE findings are RESOLVED. 4 LOW BACKLOG findings remain open (to be tracked in STATUS). |

Controls stay proportionate to a low-stakes app, as the user asked. Every fix below is a few lines. Nothing asks for new infrastructure.

## 1. What was checked and how

**Files read in full:**
- database: `db/bootstrap.sql`, `backend/alembic.ini`, `backend/migrations/env.py`, `script.py.mako`, `versions/0001_clock_context_search.py`;
- backend: `backend/src/menu/tenancy/{__init__,engine}.py`, `common/context.py`, `platform/config.py`, `platform/logging.py`, `platform/http/middleware.py` (diff and body guard), `app/{factory,health}.py`, `__main__.py`, `seeding/{command,guard}.py`, `backend/scripts/export_openapi.py`;
- container and CI: `Dockerfile`, `.dockerignore`, `compose.yaml`, `scripts/dev-certs.sh`, `scripts/ci-pg-tls.sh`, `.github/workflows/ci.yml`, `Makefile`, `scripts/ci.sh`;
- rules and config: `.gitleaks.toml`, `.gitignore`, `.semgrep/*` and fixtures, `scripts/check_semgrep_rules.py`, `backend/pyproject.toml`, the `uv.lock` diff;
- tests: `tests/support/pg.py`, the security canary test, the tenancy tests and the list of every new db, integration, security, concurrency, seed and container test.

Tools run (fresh output, 2026-10-22):

| Command | Result |
|---|---|
| `make scan-secrets` (`gitleaks git` + `gitleaks dir`) | 2 commits, ~2.7 MB working tree: **no leaks found**. Without the project config, `gitleaks dir db` flags `db/dev-certs/server.key` (`private-key`), which is the expected, gitignored local key (see SEC-SL00b-007) |
| `make scan-sast` (semgrep `--test` on the custom rules + p/python, p/owasp-top-ten, p/typescript, p/react, `.semgrep`) | rc=0, rule tests green, 0 findings in `backend` |
| semgrep with p/python, p/owasp-top-ten, `.semgrep` also on `db`, `scripts`, `Dockerfile`, `compose.yaml` | 1 hit, in the rule fixture `scripts/check_semgrep_rules.py:18` (expected) |
| Hand-written probe of `menu-set-config-session-scope` (scratchpad file, not in the repo) | misses 4 out of 6 session-scope variants (SEC-SL00b-002) |
| `make scan-deps` (`pip-audit` on the exported lock, `osv-scanner` on `uv.lock`) | No known vulnerabilities found. 73 packages, no issues |
| `uv.lock` inspection of the new packages | all from `https://pypi.org/simple`, every artifact hashed, newest upload is hypothesis 6.169.1 on 2026-10-14 (more than 7 days old). `exclude-newer-span = P7D` is active |
| `hadolint Dockerfile` | clean |
| `trivy config` (all severities) | Dockerfile: 0 misconfigurations. trivy has no scanner for `compose.yaml` or workflows (INFO-6) |
| `docker build` + `trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1` (the CI gate) | rc=0. With unfixed findings: 163 OS CVEs in the Debian base (44 HIGH, 0 CRITICAL), **none with a fix available** (SEC-SL00b-005) |
| `trivy image --scanners secret` | no secrets in the image layers |
| `docker run … id` / `find / -perm /6000` in the image | uid 10001 (non-root). 11 setuid or setgid binaries present (SEC-SL00b-005) |
| `zizmor` (default / `--persona auditor`) | 0 findings / 6 informational (`anonymous-definition`) |
| Upstream checksums: trivy 0.76.0 `checksums.txt`, hadolint 2.15.1 asset digest (GitHub API) | **both match** the SHA-256 values in `ci.yml` (`e24b1c51…`, `c7187db9…`) |
| `docker buildx imagetools inspect` of the pinned `postgres:17@sha256:a63c1ea3…` | the digest exists (multi-arch OCI index) |
| `make test-db test-sec test-int` on the local PostgreSQL 17 (TLS) | 155 + 4 + 8 **passed** |
| SQLAlchemy `create_connect_args` probe with `?host=` / `?hostaddr=` / `?service=` | `?host=` silently replaces the host in the URL authority (SEC-SL00b-001) |
| `HealthProbe` simulation (probe slower than the window, 5 concurrent callers; scratchpad) | 5 serialized probes and no caching (SEC-SL00b-003) |

## 2. Findings

### SEC-SL00b-001 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/seeding/guard.py:18-24` (`_database_host`) and `:43`
- **Category:** security (CWE-20 improper input validation; CWE-183 permissive allow-list)
- **Problem:** the seed guard takes the database host from the URL authority with `urlsplit(...).hostname`. libpq, through SQLAlchemy's psycopg dialect, also accepts a `host` query parameter, and that parameter **overrides** the authority. The allow-list therefore checks a host that is not the one the connection will use.
- **Scenario (verified with SQLAlchemy 2.1.4):** `DATABASE_URL_OWNER=postgresql+psycopg://menu_owner:…@localhost:5432/menu?sslmode=verify-full&host=<production pooler>` with `APP_ENV=dev`, `SEED_TARGET=local` and `SEED_ALLOWED_DB_HOSTS=localhost`. The guard sees `localhost` and allows the seed. `create_connect_args` returns `{'host': '<production pooler>', …}`. Today the impact is nil, because `seed` does not connect yet (the dataset library arrives in SL-10a). Once it connects, the second of the three THR-133 layers can be bypassed by a misconfigured URL, for example one copied from a runbook. `hostaddr` is less of a problem, since verify-full checks the certificate against `host`. `service` does not override an explicit host.
- **Suggested fix:** in `_database_host`, refuse any URL whose query string contains `host`, `hostaddr` or `service` (`parse_qsl` is enough, no new dependency): `SeedNotAllowed("the URL must not override the host in its parameters")`. Alternative: compute the host with the same parser the connection uses (`sqlalchemy.engine.make_url(...).query`).
- **Verification:** in `tests/unit/test_seed_guard.py`, check that `…@localhost/menu?host=db.example.com`, `?hostaddr=203.0.113.9` and `?service=prod` are all refused, with the password absent from the message.
- **Status:** RESOLVED (re-check cycle 1, see section 6)

### SEC-SL00b-002 · LOW · FIX-IN-SLICE
- **Location:** `.semgrep/sql.yaml:36` (`menu-set-config-session-scope`). The same regex is in `backend/tests/db/test_tenancy.py` (`test_tenancy_sources_never_set_session_scoped_context`).
- **Category:** security (CWE-1023 incomplete comparison; static control of THR-027 / SR-042)
- **Problem:** `set_config\s*\([^)]*,\s*false\s*\)` stops at the first `)`. A `set_config` call with a nested parenthesis, which is exactly the shape `tenancy` uses (`cast(:family as text)`), is never matched. Equivalent spellings of "false" are not matched either. Neither are `SET SESSION AUTHORIZATION` and `RESET ROLE`.
- **Scenario (verified):** a file in `backend/src/menu/orders/` with these strings was scanned with the project rule:
  - `set_config('app.family_id', cast(:family as text), false)`: **not flagged**;
  - `set_config('app.family_id', :f, 'off')`: **not flagged**;
  - `pg_catalog.set_config('app.family_id', :f, (false))`: **not flagged**;
  - `SET SESSION AUTHORIZATION menu_owner`: **not flagged**;
  - only the plain `…, :f, false)` and `set app.family_id = …` are flagged.

  A future module could copy the tenancy pattern with `false`, and the family context would then survive on a pooled connection (THR-027). The runtime test `test_rls_applies_through_tenancy_and_is_not_leaked_by_connection_reuse` covers only `tenancy` itself.
- **Suggested fix (simplest and robust):** forbid **any** `set_config(` and any `SET`/`RESET` of `role`, `session authorization`, `search_path` or `app.` under `backend/src/` **outside** `backend/src/menu/tenancy/`, using a path rule like `menu-sqlalchemy-session-outside-tenancy`. Inside `tenancy`, keep a regex that tolerates one level of nesting, for example `set_config\s*\((?:[^()]|\([^()]*\))*,\s*\(?\s*(?:false|'(?:f|false|off|no|0)')`. Apply the same change to the static test.
- **Verification:** add the 4 strings above to `.semgrep/sql.py` as `ruleid:`, and a `tenancy/` versus non-`tenancy/` path case to `scripts/check_semgrep_rules.py`.
- **Status:** RESOLVED (re-check cycle 1, see section 6)

### SEC-SL00b-003 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/app/health.py:36-47` (`HealthProbe.database_ok`); `backend/src/menu/tenancy/engine.py:42-45` (no bound on a query over a dead connection)
- **Category:** security (CWE-400 uncontrolled resource consumption; CWE-833); THR-106, A-24
- **Problem:** two small defects remove the protection A-24 asks for when the database is slow, which is exactly when it matters:
  1. `_measured_at` gets the time taken **before** the probe (`now = self._clock()` at line 37, stored at line 46). If a probe takes longer than the 5 s window, the cached result is already stale when it is stored, so every caller probes again.
  2. Every caller waits on `self._lock` inside a sync route, which means inside a thread of the AnyIO threadpool (40 threads by default, shared with every other sync route).

  A probe can last more than 5 s in two cases: `pool_timeout` 3 s plus `connect_timeout` 3 s, or a `SELECT 1` on a pooled connection whose peer vanished without RST. psycopg has no client-side timeout, and TCP retransmission can take minutes.
- **Scenario (verified, scaled timing in the scratchpad):** probe 0.6 s with a 0.5 s window (the same ratio as 6 s against 5 s). 5 concurrent callers produced **5 serialized probes**, and the last caller waited 3.0 s. Under real conditions, an anonymous flood of `GET /healthz` during a database slowdown queues threads behind the lock. It exhausts the threadpool and stalls every other sync route. It also turns the "one `SELECT 1` every 5 s" promise into one per request. Impact: availability only, while the database is already degraded.
- **Suggested fix (about 8 lines):**
  ```python
  def database_ok(self) -> bool:
      if not self._lock.acquire(blocking=False):
          return self._ok                      # probe in flight: last known result
      try:
          if self._measured_at is not None and 0 <= self._clock() - self._measured_at < WINDOW_SECONDS:
              return self._ok
          ... ping ...
          self._measured_at = self._clock()    # time AFTER the probe
          return self._ok
      finally:
          self._lock.release()
  ```
  Optionally (cheap, and it also protects real routes), bound queries on dead peers with `connect_args={"tcp_user_timeout": 5000, "keepalives_idle": 30, …}` in `tenancy.init`.
- **Verification:** in `tests/integration/test_healthz_db.py` (or as a unit test with a fake `ping`), check that with a probe slower than the window and N concurrent callers, `ping` is called once and the other callers return immediately.
- **Status:** RESOLVED (re-check cycle 1, see section 6)

### SEC-SL00b-004 · LOW · BACKLOG (scheduled: SL-02, next DB-heavy slice)
- **Location:** `backend/tests/support/pg.py:38` (`TEST_ROLE_PASSWORD`), `:70-81` (`cluster()`), `:144-155` (`set_role_passwords`)
- **Category:** security (CWE-798 hard-coded credential, test harness reachable to a real cluster)
- **Problem:** the test harness connects as the cluster administrator to **any** host given in `MENU_TEST_PG_HOST`. It then runs `ALTER ROLE menu_owner|menu_app|menu_console|menu_backup PASSWORD 'synthetic-test-cluster-only'`, a value published in the repository, and creates and drops databases.
- **Scenario:** a developer points the test variables at the staging Supabase project (for example "to try the suite on the real thing") with the `postgres` password. The staging role passwords become a public value, and the staging pooler is reachable from the Internet (THR-132). The data is synthetic, but the THR-132 assumption ("role passwords generated separately") is silently broken. In production the `postgres` password sits in the password manager, so this is unlikely.
- **Suggested fix:** in `cluster()`, refuse a host that is not loopback (`localhost`, `127.0.0.1`, `::1`) with `pytest.exit(...)`. A remote host should need an explicit, documented opt-in such as `MENU_TEST_PG_ALLOW_REMOTE=1`, which CI never sets.
- **Verification:** a unit test on `cluster()` with `MENU_TEST_PG_HOST=db.example.com` → exit.
- **Status:** OPEN

### SEC-SL00b-005 · LOW · BACKLOG (scheduled: SL-10b, before the first deploy; one line, can be done now)
- **Location:** `Dockerfile:27-33` (final stage)
- **Category:** security (CWE-250 execution with unnecessary privileges, defense in depth); THR-092
- **Problem:** the runtime image keeps 11 setuid or setgid binaries from the Debian base: `su`, `mount`, `umount`, `passwd`, `chsh`, `chfn`, `gpasswd`, `newgrp`, `chage`, `expiry`, `unix_chkpwd`. trivy reports 44 HIGH OS CVEs with no fix available, including util-linux CVE-2026-76642 (`mount` helper) and local privilege escalations. The CI gate (`--ignore-unfixed`) correctly passes them.
- **Scenario:** an attacker with code execution as uid 10001 (through some future application bug) uses a setuid binary to become root inside the container. The impact is limited by the Cloud Run sandbox and a read-only filesystem.
- **Suggested fix:** in the final stage, add `find / -xdev -perm /6000 -type f -exec chmod a-s {} +` to the existing `RUN`. At deploy time (SL-10b), run with a read-only filesystem and no extra capabilities.
- **Verification:** `tests/tools/test_container.py`: `find / -xdev -perm /6000 -type f` in the image prints nothing.
- **Status:** OPEN

### SEC-SL00b-006 · LOW · BACKLOG (scheduled: SL-01, with the uvicorn/correlation notes of CR-SL00a)
- **Location:** `backend/src/menu/platform/logging.py:70-83` (`configure_logging`)
- **Category:** security (CWE-532 sensitive information in logs, defense in depth); SR-021
- **Problem:** the redaction pipeline covers structlog only. The standard-library `logging` loggers are not routed through it: `sqlalchemy.pool`/`sqlalchemy.engine`, `uvicorn.error`, `alembic`. They print through Python's last-resort handler or uvicorn's handler, with full exception text. Two real paths reach them:
  - SQLAlchemy's pool logs "Exception during reset or similar" with `exc_info`;
  - uvicorn logs "Exception in ASGI application" when an exception is raised **after** the response has started. `EnvelopeMiddleware` re-raises in that case, and the full psycopg message is printed, including any server `DETAIL: Key (…)=(…)`.

  Neither path is reachable with this slice's routes (no streaming, no data tables), so this is not a current leak. The canary test passes.
- **Suggested fix:** in `configure_logging`, attach a `structlog.stdlib.ProcessorFormatter` (with the same `redact` processor) to the root handler, and let `uvicorn.error` and `sqlalchemy` propagate to it. Alternatively, keep those loggers at `ERROR` and replace `exc_info` with `describe_exception`. Add a canary for "exception after response start" when the first streaming response appears.
- **Verification:** extend `tests/security/test_error_logging_canaries.py` with a route that raises after `http.response.start`. The canary must not appear in stdout or stderr.
- **Status:** OPEN

### SEC-SL00b-007 · LOW · BACKLOG (any time; two lines)
- **Location:** `.gitleaks.toml:12` (allowlist `db/dev-certs/`)
- **Category:** security (CWE-1391 / secrets-scanning coverage)
- **Problem:** the allowlist is needed for `gitleaks dir` (the gitignored local key is in the working tree), but it applies to `gitleaks git` too. If a file under `db/dev-certs/` is ever force-added (`git add -f`), neither the history scan nor the pre-commit hook will flag it. The material is throwaway: a localhost-only dev CA (whose key is deleted) and the local `postgres` password. So the real impact is small, but the control has a blind spot.
- **Suggested fix:** keep the allowlist, and add to `scan-secrets` (or `tests/tools`) the check `test -z "$(git ls-files db/dev-certs)"`. Alternatively, pass a separate `--config` with the allowlist only to `gitleaks dir`.
- **Verification:** `git add -f db/dev-certs/server.key` in a scratch clone → `make scan-secrets` fails.
- **Status:** OPEN

## 3. Checks that passed (by area)

- **`bootstrap.sql` (SR-075 base, THR-040/044):**
  - the roles are created with `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS`, **no password and no verifier**, and the `CONNECTION LIMIT` values of 05-data §3.1;
  - per-role timeouts are set;
  - `REVOKE CREATE` on `public` (including from its owner) and on `app`, and `REVOKE ALL ON SCHEMA app FROM PUBLIC`;
  - the `anon`/`authenticated` revocations run only when those roles exist;
  - `ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC` is global (correct, since the PUBLIC function default is global);
  - the temporary `menu_owner` membership for Supabase's non-superuser `postgres` is revoked at the end;
  - all dynamic SQL uses `format('%I')`;
  - there are no psql meta-commands;
  - `0001` refuses to run if a role exists with privileged attributes.
- **`0001` and D1 (inlinable functions without `SET search_path`):** **accepted.** Everything in the bodies is schema-qualified (`pg_catalog.current_setting`, `pg_catalog.uuid`, `pg_catalog.lower`, `extensions.unaccent` with an explicit `regdictionary`). The only unqualified call is `now()`, and it cannot be hijacked:
  - no role other than `menu_owner` can `CREATE` in `public` or `app`;
  - functions are never looked up in `pg_temp`;
  - `pg_catalog` is searched first unless the caller lists it explicitly, and only the caller's own privileges are at stake for `SECURITY INVOKER`;
  - the SECURITY DEFINER functions of 0008 will pin `app, pg_temp`.

  Further, `EXECUTE` is revoked from PUBLIC and granted to `menu_app` only, and the tests prove that `menu_app` cannot replace or shadow `now_utc` (including via `pg_temp`). This holds as long as the "no CREATE on `public`/`app`" inventory test stays green (INFO-4 adds `extensions`).
- **`env.py` (THR-043, THR-048):**
  - the URL comes only from `DATABASE_URL_OWNER`;
  - the user must be `menu_owner`;
  - exactly `sslmode=verify-full` is required (a duplicate key becomes a tuple and is refused);
  - after connecting, it checks that `current_user` and `session_user` are `menu_owner` and that `app` is owned by `menu_owner`;
  - offline `--sql` mode is refused;
  - `hide_parameters=True`;
  - no error message echoes the URL.
- **Startup `verify-full` (A-13):** `check_database_url` requires exactly one `sslmode` equal to `verify-full` in every `APP_ENV`. `PGSSLMODE` cannot weaken it (it is tested), since an explicit parameter wins. The URL is a `SecretStr` with `hide_input_in_errors=True`. Tests and CI use `verify-full` against a real TLS 1.3 server with a throwaway CA, and a foreign CA is refused.
- **Tenancy (THR-026/027, SR-042):**
  - context is set only with `set_config(…, true)` and bound parameters;
  - `family_tx` refuses a context without a family;
  - `engine.begin()` rolls back on error, and the tests prove that the context does not survive commit, rollback or connection reuse;
  - `prepare_threshold=None` keeps it compatible with the pooler in transaction mode;
  - `hide_parameters=True`, plus the `handle_error` hook that sets `params=None`;
  - `describe_exception` logs only exception types and file:line:function, never messages;
  - the canary test proves this for SQL parameters, server-echoed values and Pydantic input (SEC-SL00a-006 **resolved**).
- **`/healthz` (THR-106):** the body is only `{"status": …}` with `no-store`, it runs on the existing pool as `menu_app`, the window cache works when the probe is fast, and the log carries only the exception type. Apart from SEC-SL00b-003, it matches A-24.
- **Seed guard (A-22, THR-133):**
  - allow-list `APP_ENV ∈ {dev, staging}`, plus an explicit `SEED_TARGET` and a host allow-list;
  - the guard runs before any connection;
  - messages never contain the URL;
  - tests do not import the command;
  - only SEC-SL00b-001 remains.
- **Container (THR-092):**
  - multi-stage build, bases pinned by digest;
  - the runtime venv is owned by root and read-only to uid 10001;
  - pip is removed and there is no bytecode at runtime;
  - the build context is minimal (no `db/`, tests, `.env*`, keys);
  - `access_log=False`, `proxy_headers=False`, `server_header=False`;
  - the image starts with no secrets and refuses to start without `APP_ENV`.
- **Local and CI database:**
  - compose binds to `127.0.0.1` only, and the admin password comes from a docker secret file generated with `openssl rand`;
  - the dev CA key is deleted after signing, and the server key has mode 0600 and is copied with owner `postgres`;
  - `db/dev-certs/` is gitignored and excluded from the build context.
- **CI workflow (SR-076, THR-091):**
  - actions are pinned to the same verified SHAs as SL-00a;
  - `permissions: contents: read`, `persist-credentials: false`, no `pull_request_target` (and the grep for it is now stricter);
  - the new tool downloads (hadolint, trivy) are **checksum-verified, and the values match upstream**;
  - the postgres service is pinned by digest and bound to `127.0.0.1`.
- **New dependencies (SR-076, protocol §3.7):**

  | Package | Version | Registry / maintenance | License | CVEs (pip-audit, osv) | Cooldown |
  |---|---|---|---|---|---|
  | sqlalchemy | 2.1.4 | PyPI, sqlalchemy org, active | MIT | none | 2026-10-07 ✓ |
  | alembic | 1.20.0 | PyPI, sqlalchemy org, active | MIT | none | 2026-09-11 ✓ |
  | psycopg / psycopg-binary | 3.3.6 | PyPI, psycopg org, active | LGPL-3.0 (dynamic use: compatible) | none | 2026-09-18 ✓ |
  | pytest-xdist (dev) | 3.8.0 | PyPI, pytest-dev, active | MIT | none | 2025-07-01 ✓ |
  | hypothesis (dev) | 6.169.1 | PyPI, HypothesisWorks, active | MPL-2.0 | none | 2026-10-14 ✓ |
  | transitive: mako 1.4.3, markupsafe 3.0.4, execnet 2.1.2, tzdata 2026.5, sortedcontainers 2.4.0 | | PyPI | MIT / BSD / Apache | none | ✓ |

  Names are exact (no look-alikes), every artifact is hashed in `uv.lock`, and the source is `pypi.org/simple`.
- **Semgrep rules (SEC-SL00a-007):** **resolved** for `text()`, `literal_column()` and `exec_driver_sql()` (only plain literals, including through module aliases) and for async engines and sessions outside `tenancy`. The `now_utc` body exception is anchored to one marked line, and the catalog test enforces "exactly once". The remaining gap is SEC-SL00b-002.
- **SL-00a backlog closed in this slice:**
  - SEC-SL00a-006: resolved;
  - SEC-SL00a-007: resolved, except SEC-SL00b-002;
  - INFO-14: resolved (the tool cooldown exception is limited to the certifi variable on semgrep, with mutation tests);
  - CR-SL00a-007: the body guard is now fail-closed.

## 4. INFO (no action required in this cycle)

1. **Literal CI password** (`ci.yml:49,58`, `ci-throwaway-pg-admin`) and **test role password** (`tests/support/pg.py:38`): these are not secrets under SS §6. They protect an ephemeral cluster with no data, on the job VM, bound to `127.0.0.1`, and they are never reused. Accepted as is. Never reuse either value anywhere else.
2. **psycopg-binary** ships its own libpq and OpenSSL inside the wheel. Their CVEs are not visible to pip-audit, osv-scanner or trivy's OS scan. Update psycopg-binary promptly when psycopg announces a libpq or OpenSSL refresh (the Dependabot item SEC-SL00a-009 covers the mechanism).
3. **Supabase `service_role`** (BYPASSRLS) is not in the bootstrap revocation list. It gets nothing on `app` by default: the default privileges of `postgres` are scoped to `public`, and the `app` objects belong to `menu_owner`. For symmetry, it could be added to the `anon`/`authenticated` loop. Verify on the real project at P-4.
4. **`extensions` schema:** add an inventory assertion that no `menu_*` role has `CREATE` on it. This keeps the D1 reasoning true on Supabase.
5. **`.env.example`** still lists `DB_HOST`/`DB_APP_PASSWORD`… instead of `DATABASE_URL_APP` (with a `sslmode=verify-full&sslrootcert=…` placeholder) and `DATABASE_URL_OWNER`. This is a documentation mismatch only, and startup rejects a bad URL anyway.
6. **`trivy config`** detects only the Dockerfile. It has no scanner for `compose.yaml` or GitHub workflows, so the plan text in §6.2 ("trivy config on compose and workflow") overstates it. Workflows are covered by zizmor, and compose is checked by `tests/tools/test_container.py`. Correct the plan wording.
7. **Pinned base digests are older than the current tags** (`postgres:17` and `python:3.14-slim` have moved on). That is expected with digest pinning, and no HIGH or CRITICAL CVE with a fix is pending. A refresh cadence comes with SEC-SL00a-009.
8. **`last-modified-files.sh`** (repo root, untracked) is a personal helper. Keep it out of the slice commit, or add it to `.git/info/exclude`.
9. **Connection budget:** `menu_app` has `CONNECTION LIMIT 20` and the pool is 5 + 5 overflow per instance. With `max-instances=2` plus the worker, the budget is exactly at the limit. The devops should size it in SL-10b.

## 5. Status per finding

| ID | Severity | Class | Status |
|---|---|---|---|
| SEC-SL00b-001 | LOW | FIX-IN-SLICE | RESOLVED (cycle 1) |
| SEC-SL00b-002 | LOW | FIX-IN-SLICE | RESOLVED (cycle 1) |
| SEC-SL00b-003 | LOW | FIX-IN-SLICE | RESOLVED (cycle 1) |
| SEC-SL00b-004 | LOW | BACKLOG (SL-02) | OPEN |
| SEC-SL00b-005 | LOW | BACKLOG (SL-10b) | OPEN |
| SEC-SL00b-006 | LOW | BACKLOG (SL-01) | OPEN |
| SEC-SL00b-007 | LOW | BACKLOG | OPEN |

THR verification state after this slice:
- **verified by tests:** THR-026 (inventory machinery, empty set), THR-027, THR-043, THR-044 (base: empty SECURITY DEFINER inventory, grants, CREATE), THR-048, THR-092, THR-106 (apart from SEC-SL00b-003);
- THR-133 verified as well after cycle 1 (SEC-SL00b-001 resolved), and THR-106 without reservations (SEC-SL00b-003 resolved).

## 6. Re-check, cycle 1 (2026-10-22)

Scope: only SEC-SL00b-001, 002 and 003, plus regressions introduced by the fix diff (contract, anti-loop rule). I re-ran the original probes against the fixed code (scratchpad scripts, nothing written to the repo).

| Finding | Fix reviewed | Probe and evidence | Result |
|---|---|---|---|
| SEC-SL00b-001 | `seeding/guard.py`: any `host`, `hostaddr` or `service` key in the query string is refused. Keys are compared after `parse_qsl` decoding and lower-casing | With an allow-list of `localhost`, `&host=prod…`, `&hostaddr=…`, `&service=prod`, `&h%6Fst=prod…` (percent-encoded) and `&HOST=x` are **all refused**, with no URL in the message. `;host=…` is allowed, but SQLAlchemy does not treat it as a parameter either (effective host `localhost`). The guard and the connection parser agree | **RESOLVED** |
| SEC-SL00b-002 | `.semgrep/sql.yaml`: nested-parenthesis regex, `'off'/'f'/'no'/'0'`, `(false)`, `SET/RESET … AUTHORIZATION/ROLE/ALL`. New `menu-set-config-outside-tenancy` rule: no `set_config(` anywhere in `backend/src` except `tenancy`. `tests/support/sqlscan.py` and `tests/architecture/test_tenancy_session_scope.py` apply the same checks | Outside `tenancy`, all 8 original variants are flagged, including the formerly missed `cast(... as text), false`, `'off'`, `(false)`, `SESSION AUTHORIZATION` and `reset role`. A correct `…, true` call is flagged too, by the new path rule, as intended. Inside `tenancy`: `cast(...), false`, `coalesce(cast(...), ''), 'f'` and `SET ROLE` are flagged. **The real `tenancy/engine.py` gives 0 hits** (no false positive). `make scan-rules`: all rule tests green, 16 path cases OK | **RESOLVED** |
| SEC-SL00b-003 | `app/health.py`: `acquire(blocking=False)` (callers that find a probe in flight get the last result), and the window timestamp is taken **after** the probe. `tenancy/engine.py`: `tcp_user_timeout=10000`, `keepalives`(30/10/3) | Same scaled simulation as before (0.6 s probe, 0.5 s window, 5 concurrent callers): **1 probe** (was 5). 4 callers returned in 0.0 s, the prober in 0.6 s. A call 0.2 s after the probe ended used the cache. `make test-db` 156 passed, `make test-int` 10 passed (the new psycopg connection parameters are accepted by libpq) | **RESOLVED** |

Regressions checked:
- **503 right after startup:** while the very first probe is running, concurrent callers get `_ok=False` → `503 {"status":"unavailable"}`. This lasts for one `SELECT 1` (milliseconds with a healthy DB). It is fail-closed and the 503 body is unchanged. Startup and liveness probes retry, so this is **acceptable, no finding** (INFO).
- **Residual static-rule gaps:** inside `tenancy` only, a non-literal third argument (`0::boolean`, a bound `:local`) is not flagged. Outside `tenancy`, any `set_config(` is forbidden, so this cannot recur elsewhere. Inside `tenancy`, the runtime tests (`test_context_does_not_survive_the_transaction`, `test_rls_applies_through_tenancy_and_is_not_leaked_by_connection_reuse`) catch it. INFO, no action.
- **Keepalives and `tcp_user_timeout`:** bounding queries on a dead peer to about 10 s also applies to real routes. That is desirable, and it does not affect queries that are merely slow: those remain bounded by `statement_timeout` 5 s.
- **Suites:** architecture, seed and healthz unit tests: 125 passed. No new BLOCKER was introduced by the fix.

Verdict: **APPROVED.** SEC-SL00b-004..007 (LOW, BACKLOG) go to the technical-debt table in `docs/STATUS.md`.
