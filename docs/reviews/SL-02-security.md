# SL-02: security review

| Field | Value |
|---|---|
| Slice | SL-02: console bootstrap, security log, first RLS check |
| Reviewer | security-engineer (mode B) |
| Date | 2026-10-22 |
| Diff base | `1ce461c` (nothing committed: `git diff 1ce461c` plus the untracked files from `git status`) |
| SRs in scope | SR-012, SR-020, SR-033 (bootstrap part), SR-040, SR-042, SR-057 |
| THRs in scope | THR-003, THR-020, THR-026, THR-044, THR-051, THR-053, THR-111 |
| ADRs checked | ADR-0003, ADR-0011, ADR-0014, ADR-0016 |
| Verdict | **APPROVED.** No BLOCKERs and no FIX-IN-SLICE findings. 2 LOW BACKLOG findings and 8 INFO notes. The narrowed semgrep rule has no real gap: the only statements it now lets through are function-level, and the SECURITY DEFINER inventory test catches the dangerous ones. |

The controls are proportionate to a low-stakes app, as the user asked. Neither LOW finding needs action in this slice.

## 1. What was checked and how

**Files read in full:**
- migrations `0002_family.py`, `0003_security_event.py`, `0004_console_m0.py`;
- `menu/console/__init__.py` (job), `menu/console_client/__init__.py` (local script), `menu/__main__.py`, `menu/tenancy/engine.py` (`console_tx`), `menu/audit/{catalog,log}.py`, `menu/common/{export,email}.py`, `menu/family/export.py`, `menu/catalog/export.py`, the `platform/logging.py` diff, `.env.example`;
- `.semgrep/sql.yaml` and `.semgrep/sql.py` (diff), `scripts/check_semgrep_rules.py` (diff);
- tests: the diffs of `test_inventory_rls.py`, `test_inventory_secdef.py`, `support/inventory.py` (including `secdef_problems` and `app_functions`), plus the list of tests in `test_console_privileges.py`, `test_security_event.py`, `test_console_client.py` and `test_console_job.py`;
- docs: 05-data §3.2, §3.3, §9.3, the ADR-0014 note, the ADR-0011 command table, and the THRs in scope in 06-threat-model.

**Tools run (fresh output, 2026-10-22):**

| Command | Result |
|---|---|
| `gitleaks dir .` and `gitleaks git .` (`.gitleaks.toml`, `--redact`) | **no leaks found** (working tree ~4.8 MB, history 6 commits ~2.3 MB) |
| `make scan-rules` (semgrep `--test` on the 3 custom rule files + `check_semgrep_rules.py`) | all tests passed; "regole custom: 23 casi di percorso OK" |
| `semgrep scan --error --config p/python --config p/owasp-top-ten --config .semgrep backend` | rc=0, 0 findings |
| `make scan-deps` (pip-audit on the exported lock + osv-scanner on `uv.lock` and `pnpm-lock.yaml`) | No issues found (only the already-accepted GHSA-vfj7-8cjw-p6xm filtered, ADR-0017). **No new dependencies** in this slice (`pyproject.toml`, `uv.lock` and `package.json` unchanged) |
| `make test-db test-int test-prop` | **332 + 25 + 7 passed** |
| `pytest tests/unit/test_console_client.py tests/unit/test_audit_log.py tests/unit/test_export_inventory_logic.py` | 43 passed |
| Probe against a throwaway local database (`sec_probe_sl02`, created from the head template, then dropped), via `SET ROLE` | see below |
| semgrep probe file in the scratchpad (9 edge cases for `menu-set-config-session-scope`) | see §3 |

**Database probe results** (local PostgreSQL 17 only):
- `menu_console`: `SELECT` on `family` and `security_event` → permission denied; `INSERT` into `security_event` → denied; `app.family_today()` and `app.now_utc()` → permission denied. It can create a TEMP table (INFO-4).
- `console_bootstrap_family`: name of 61 characters, 1-byte hash → `invalid_parameter_value`, generic message with no echo of the input. A name with a newline is **accepted** by the function (INFO-3; the job rejects it before calling).
- `console_audit_note`: a ref with a trailing `\n` → rejected (the `!~` regex is anchored and `collate "C"`). A non-UUID `app.correlation_id` → cast error, transaction rolled back.
- `console_security_events`: `p_limit` 1001 → rejected; the output IP is masked.
- Events written: `console.family_bootstrap` with no `details`; `console.audit_note` with only `request_ref`; `console.security_log` with only `since`/`limit`. **No email or hash in any event.**
- Immutability trigger (run as owner): `10.1.2.3 → 10.1.2.0` and `2001:db8:1:2::5 → 2001:db8:1::` allowed; `→ 10.1.0.0`, `→ 9.9.9.0`, `details` changed, `outcome` changed together with `ip=null` → all rejected; `ip = null` allowed. `10.1.2.0 → 10.1.2.0/8` (masklen only) allowed (INFO-7).
- `menu_app`: `UPDATE`, `DELETE`, `TRUNCATE`, `SELECT` on `security_event` → denied; `console_audit_note` → denied. With no family context: 0 rows from `family`, `family_bootstrap`, `person`; `INSERT INTO family` → RLS violation.

## 2. Checks against THRs, SRs and the standard

| Item | Result |
|---|---|
| THR-020, THR-026, SR-042: RLS on the 5 new tables | ENABLE + FORCE, `p_family` with matching `USING`/`WITH CHECK`, `p_owner`, `p_backup` (SELECT only). `family` filters on `id`, the others on `family_id`, and a test asserts the column. A generic isolation test runs on the real tables (without context 0 rows, A cannot see/update/delete B, INSERT for B refused). `p_person_self` is SELECT only and returns only the caller's own row. Composite FKs `(family_id, …)` prevent cross-family references. **Met.** |
| THR-044, SR-040: SECURITY DEFINER | Exactly 3 functions, owner `menu_owner`, `search_path=app, pg_temp` (checked as an exact `proconfig` element), plpgsql, no dynamic SQL, every relation qualified with `app.` and every built-in with `pg_catalog.`, EXECUTE revoked from PUBLIC and granted to `menu_console` only (test for each role). Trigger and INVOKER functions are also closed to PUBLIC (test). **Met.** |
| THR-051, SR-012: `menu_console` | No privileges on any table or sequence (test + probe). The functions return no family content: bootstrap returns only the ID, the security log returns IDs, enums and the masked IP. `CONNECTION LIMIT 2`, `statement_timeout 30s`. **Met.** |
| THR-053, SR-012: console arguments and output | The email is read only with `getpass`, validated, hashed in Python by `menu.common.email_sha256`, and never put in argv, stdout, stderr or messages (argparse `error()` is overridden in both parsers so input values are not echoed; the job prints only the exception type name). The job validates the hash with `[0-9a-f]{64}` before it touches the DB, and the DB checks 32 bytes again. `request_ref` is constrained in 3 places. `subprocess.run` gets an argument list with no shell. A comma in the name is refused, and every `--args` value starts with a fixed word, so gcloud's `^X^` delimiter escape cannot be injected. `DATABASE_URL_CONSOLE` must have `sslmode=verify-full`. **Met.** |
| THR-003, SR-033 (bootstrap part) | 168-hour expiry fixed by a CHECK, single-use and hash removal on redemption enforced by CHECKs, no alias normalization (only `strip().lower()`). Redemption itself arrives with SL-03a. **Met for this slice.** |
| THR-111, SR-057, SR-020: security log | `menu_app` has INSERT only (no SELECT, so no `RETURNING`). `menu_console` reads only through the function. The trigger rejects every UPDATE, owner included, except clearing `ip` or truncating it to /24 or /48 of its *own* old value. Server UTC time by default. The structured log copy has `ip_prefix` only, never the full IP or the account ID. **Met.** Note: the owner can still DELETE, TRUNCATE or disable the trigger. That is by design (12-month retention, migration identity, ADR-0016). |
| Export contributors, SR-072 | Explicit column allow-lists (no `account_id`, `family_bootstrap` excluded). `person` queries carry the explicit `family_id = app.current_family_id()` filter that `p_person_self` requires. `family`, `family_default_meal` and `course` have only `p_family` for `menu_app`, so RLS alone is correct there. **Met.** |
| Standard §3 injection, §6 secrets, §9 logging | All queries are bound `text()` with parameters. No secrets (gitleaks clean; `.env.example` has placeholders only). No PII in logs. |

**Done well:** the IP-truncation exception compares the whole row minus `ip` through `to_jsonb`, so a future column cannot slip through it. The secdef inventory matches `proconfig` by exact element, not by substring. The job and the client both refuse to echo argparse messages.

## 3. The narrowed semgrep rule `menu-set-config-session-scope`

The change adds `(?<!definer )` before `\b(?:SET|RESET)`. I ran semgrep with `.semgrep/sql.yaml` on a scratch file with 9 cases:

| Case | Flagged | Assessment |
|---|---|---|
| `create function … security definer set search_path = app, pg_temp` | no | intended exemption |
| `… security definer set search_path = app, pg_temp as $$ begin set search_path = public; end $$` | **yes** | a SET in the body is still caught |
| `SECURITY DEFINER` + newline + `SET search_path …` | yes | false positive, safe direction |
| `alter function app.f() reset all` (no `definer`) | yes | caught |
| `x = 'definer ' ; set role postgres` | yes | the lookbehind needs `definer` immediately followed by one space, then SET |
| `alter function app.f() security definer reset all` | no | function-level, not session-level. It removes the `search_path` pin, so **`secdef_problems` fails** (`proconfig` empty) |
| `alter function … security definer set search_path = public, pg_temp` | no | function-level. **`secdef_problems` fails** (the exact element `search_path=app, pg_temp` is missing) |
| `create function … security definer set app.family_id = 'x'` | no | function-scoped and restored on exit. It has no effect on the owner (policy `p_owner` is `true`) |
| `"select 1; -- definer \nSET search_path = public"` (escaped `\n` inside a Python string) | **no** | not caused by the lookbehind: see SEC-SL02-002 |

**Conclusion:** the user-approved exemption opens no real gap. Only statements of the form `definer SET|RESET …` escape the rule. In valid SQL, those are function attributes, not session statements. The dangerous variants (unpinning or weakening `search_path` on a definer function) are caught by the DB inventory test in CI (`tests/db/test_inventory_secdef.py`). Options: add the two `alter function … security definer` cases to `.semgrep/sql.py` as `ok:` fixtures with a comment that the inventory covers them, to document this boundary (INFO-1).

## 4. Findings

### SEC-SL02-001 · LOW · BACKLOG
- **Location:** `backend/migrations/versions/0002_family.py:270` (`_rls`: `grant select, insert, update, delete … to menu_app`, applied to `app.family` too)
- **Category:** security (CWE-269, improper privilege management; least privilege)
- **Problem:** `menu_app` can `DELETE FROM app.family` for the family in context. 05-data §3.3 has the definitive deletion done only by `maint_purge_due_families()` (SECURITY DEFINER, M2) and `maint_apply_deletion` (owner), so the app role never needs this privilege. The privilege follows the generic "family tables" row of the §3.2 matrix, so it complies with the approved design. This is defense in depth only.
- **Scenario:** a future route bug, or a broken FR-016 implementation, runs `DELETE FROM app.family` in an Admin's context. The family and all its tables cascade away immediately, skipping the 7-day cooling-off (SR-018). The impact is limited to the caller's own family, and recovery is from backup.
- **Suggested fix:** in the migration that adds `maint_purge_due_families` (SL-31), `revoke delete on app.family from menu_app` and amend the 05-data §3.2 matrix ("`family`: no DELETE, purge only through `maint_purge_due_families`"). The `test_family_schema` cascade test can run as owner.
- **Verification:** `has_table_privilege('menu_app','app.family','DELETE')` is false in `test_console_privileges.py` / the privilege matrix test.
- **Status:** OPEN (BACKLOG, data-architect, SL-31)

### SEC-SL02-002 · LOW · BACKLOG
- **Location:** `.semgrep/sql.yaml:36` (`\b(?:SET|RESET)` branch of `menu-set-config-session-scope`)
- **Category:** security (CWE-1023, incomplete comparison; detection gap in a SAST rule)
- **Problem:** in `generic` mode semgrep matches the raw source text. When SET follows an escaped newline or tab inside a Python string literal (`"…;\nSET search_path = public"`), the character before `S` is the `n` of `\n`, so `\b` does not match and the rule stays silent. This was already true before this slice. The new lookbehind does not cause it.
- **Scenario:** a developer writes `conn.exec_driver_sql("select 1;\nSET search_path = public")` in a non-tenancy module. Session state then leaks through the pool (THR-025/027), and the custom rule does not flag it. The other controls stay in place (no `set_config` outside tenancy, `menu_app` cannot create objects in `app`/`public`, review). That is why this is LOW.
- **Suggested fix:** replace `\b(?:SET|RESET)` with `(?:(?<=\\[nrt])|\b)(?:SET|RESET)`, keeping the `(?<!definer )` lookbehind in front. Add `# ruleid:` fixtures with `\nSET search_path` and `\tRESET ALL` in `.semgrep/sql.py`.
- **Verification:** `make scan-rules` green with the new fixtures.
- **Status:** OPEN (BACKLOG, devops/backend, any slice, e.g. SL-03a)

## 5. INFO notes (no action required)

- **INFO-1 · semgrep exemption boundary.** Covered in §3. Optionally document the `alter function … security definer reset all` / `set search_path = public` cases as fixtures and point to `secdef_problems`.
- **INFO-2 · `tg_person_admin_invariant` is SECURITY INVOKER under RLS.** As `menu_app`, its lookups only see the family in context. If a transaction ever ran with no family context, or a different one, at commit, the check would see no `family` row and pass silently. Today `family_tx` sets the context once per transaction and `set_config` is banned outside tenancy, and the trigger is documented as secondary to the application lock (FR-011). When SL-13 adds last-admin flows, keep the test "last admin removed in context → `check_violation`".
- **INFO-3 · Control characters in the family name.** `console_bootstrap_family` (and the `ck_family_name` CHECK) accept a newline. Only the job rejects control characters, and only the operator can call the function. Output is escaped by React, and the name is never logged. Optional: add `p_family_name !~ '[[:cntrl:]]'` to the function and later to the CHECK, together with app-side validation (SL-09).
- **INFO-4 · TEMP on the database.** `menu_console` (like every role, via the PUBLIC default) can create temporary tables. This is not exploitable here: `pg_temp` is last in the definer `search_path`, every relation is `app.`-qualified, and functions and operators are never resolved from `pg_temp`. Optional hardening in `db/bootstrap.sql`: `REVOKE TEMPORARY ON DATABASE … FROM PUBLIC` (check Supabase compatibility at P-4).
- **INFO-5 · App can log `console.*` event types.** `EVENT_TYPES` includes the three console types, so `audit.security_log` would let app code write a fake `console.family_bootstrap` with `actor_kind='platform_operator'`. That needs compromised app code, which can insert raw rows anyway (THR-111, accepted Low). Optional: have `security_log` refuse the `console.` prefix.
- **INFO-6 · Data in Cloud Run execution args and logs.** The family name and the email SHA-256 go into the job's `--args`, and the name goes into stdout. This follows the approved ADR-0011 and THR-053: an email hash is a pseudonym, not anonymization. The devops check I-05 (retention of job args and audit logs, `docs/09-release.md`) is still open. Not security, **TO VERIFY by the code reviewer:** `gcloud run jobs execute --wait` reports the execution status but, as far as I know, does not stream the container's stdout. If so, the `security-log` and `bootstrap` output reaches only Cloud Logging, not the operator's terminal, as `console_client` assumes.
- **INFO-7 · Masklen-only update.** The trigger allows `10.1.2.0 → 10.1.2.0/8` on an already-truncated address: same host, different netmask. This is harmless (no new or forged information), and `console_security_events` normalises the masklen on output.
- **INFO-8 · Failed console calls leave no event.** Invalid arguments roll back the whole transaction, event included (documented in `0004`). The job also validates first, and its non-zero exit code stays in the Cloud Run execution history. This is acceptable for SR-020 in M0. Revisit if alarms on failed console commands are wanted (SL-26).

**Carried-over debt:** SEC-SL00b-004 (test harness sets the published role password on any `MENU_TEST_PG_HOST`; refuse non-loopback hosts without an opt-in) was scheduled for SL-02. It is **not addressed** in this diff (`backend/tests/support/pg.py:144`). It is still LOW: reschedule it (for example SL-03a) or close it in this slice with a two-line guard.
