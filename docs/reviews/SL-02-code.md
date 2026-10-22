# Code review · SL-02

- **Date:** 2026-10-22
- **Reviewer:** code-reviewer
- **Scope:** `git diff 1ce461c` plus untracked files (working tree, uncommitted). Migrations `0002_family.py`, `0003_security_event.py`, `0004_console_m0.py`; `menu.common.export`, `menu.family` (+ `export`), `menu.catalog` (+ `export`), `menu.console`, `menu.console_client`, `menu.audit` (`catalog`, `log`), `menu.tenancy.console_tx`, `menu.platform.logging`, `menu.__main__`; all new and modified tests under `backend/tests`; `.semgrep/sql.yaml`, `.semgrep/sql.py`, `scripts/check_semgrep_rules.py`; `.env.example`. References: plan §SL-02, §2.2, §4.4; 05-data v6 §3.2, §3.3, §4.1, §4.2, §9.3; ADR-0003/0011/0014; US-002.
- **Verdict:** APPROVED WITH FIXES (re-check, cycle 2; cycle 1 was REJECTED)
- **Cycle:** 2

## Summary
| ID | Severity | Class | Location | Problem | Status |
|---|---|---|---|---|---|
| CR-SL02-001 | HIGH → LOW (residual) | BLOCKER → FIX-IN-SLICE | `backend/src/menu/console_client/` (no `__main__.py`), plan §1 `scripts/console.sh` | The operator's console command can't be run: `python -m menu.console_client` fails, and there is no wrapper script and no entry point | OPEN (code RESOLVED; doc residual: `scripts/console.sh` still named in plan §1 and ADR-0011) |
| CR-SL02-002 | MEDIUM | FIX-IN-SLICE | `backend/src/menu/console_client/__init__.py:110-114`; `backend/tests/unit/test_console_client.py:51,116-128` | The client prints gcloud's stdout, which doesn't contain the job output (family ID, security log). The test mock hides this | ACCEPTED (deviation in plan §4.4, STATUS debt row, SL-10b) |
| CR-SL02-003 | MEDIUM | FIX-IN-SLICE | `backend/migrations/versions/0002_family.py:207-249,282-285` | `tg_person_admin_invariant` and `p_person_self` have no test, although 05-data says they were "verified in SL-02". `p_person_self` is a cross-family read path | RESOLVED |
| CR-SL02-004 | MEDIUM | FIX-IN-SLICE | `backend/tests/db/test_console_functions.py:165-305`; `0004_console_m0.py:115-145` | Error and contract cases of the console functions are untested: `console_security_events` limits and NULL inputs, SQLSTATE 22023, messages that must not echo values, own event left out of the output, row order, real IP truncation, `correlation_id` from the job | RESOLVED |
| CR-SL02-005 | LOW | FIX-IN-SLICE | `backend/tests/db/test_security_event.py:81-109`; `0003_security_event.py:63-75` | The `ip` branch of the immutability trigger is never isolated: rewriting the IP to another address, IPv6 /48 and NULL aren't tested. Assertions catch any `DatabaseError` instead of 42501 | RESOLVED |
| CR-SL02-006 | LOW | FIX-IN-SLICE | `backend/src/menu/console/__init__.py:66,74`; `0004_console_m0.py:46-51` | The bootstrap output includes the family name, against ADR-0011 ("mai … nomi") and plan §4.4 ("output solo ID ed esiti"), though AC-002.3 allows it. The name filter lets DEL, U+0085 and U+2028 through, and the SQL function accepts newlines | RESOLVED |
| CR-SL02-007 | LOW | FIX-IN-SLICE | `backend/src/menu/audit/log.py:55-87`; `backend/tests/unit/test_audit_log.py` | The write path of `security_log` isn't tested at all, and the log line is written before the transaction commits | OPEN (partial: the commit listener fires before the DBAPI COMMIT) |
| CR-SL02-008 | LOW | FIX-IN-SLICE | `backend/src/menu/console_client/__init__.py:39-42,106-113` | gcloud errors are swallowed (`capture_output`). A missing `gcloud` gives an uncaught `FileNotFoundError` traceback. The parser allows abbreviations | RESOLVED |
| CR-SL02-009 | INFO | BACKLOG | `0002_family.py:246-248` | The admin invariant doesn't fire on INSERT (an account `member` can be inserted into a family with no admin) or on a `family_id` change. This matches 05-data, so it is noted for SL-11/12 | OPEN |
| CR-SL02-010 | INFO | BACKLOG | `0003_security_event.py:84-86` | `menu_app` can insert `console.*` / `platform_operator` events, so a compromised app can forge operator events | OPEN |
| CR-SL02-011 | INFO | BACKLOG | tests (see block) | Minor test hygiene: an ineffective `PYTHONPATH` under `-I`, an assertion-free acceptance test, a tautological property, accumulating test images | OPEN |
| CR-SL02-012 | INFO | BACKLOG | `docs/STATUS.md` technical debt | SEC-SL00b-004 and the CR-SL00b items scheduled for SL-02 are not addressed in this diff | OPEN (SEC-SL00b-004 resolved; CR-SL00b items still tagged SL-02) |

## Findings

### CR-SL02-001 · HIGH · BLOCKER
- **Location:** `backend/src/menu/console_client/__init__.py:93` (`main` has no caller); there is no `backend/src/menu/console_client/__main__.py`, no `scripts/console.sh` (plan §1 file tree, line 175) and no `[project.scripts]` entry.
- **Category:** correctness
- **Problem:** ADR-0011 says the operator's command is `scripts/console.sh` or `uv run python -m menu.console_client`. Neither works, so the operator can't run the command of AC-002.1 ("quando eseguo il comando di bootstrap con il nome della famiglia e quella email"). The only command that runs is the job, and it takes the hash, not the email.
- **Scenario:** `backend/.venv/bin/python -I -m menu.console_client --help` → `No module named menu.console_client.__main__; 'menu.console_client' is a package and cannot be directly executed`, rc=1. All client tests import `main` directly, so none of them notices.
- **Suggested fix:** add `backend/src/menu/console_client/__main__.py` with `import sys; from menu.console_client import main; sys.exit(main())`, and either add `scripts/console.sh` (`cd backend && exec uv run --frozen python -m menu.console_client "$@"`) or update plan §1 and ADR-0011 to name the single entry point.
- **Verification:** a test that runs `[sys.executable, "-I", "-m", "menu.console_client", "--help"]` as a subprocess and expects rc 0 and usage text, plus a second run with no arguments that expects rc 2 and a generic message. If the wrapper is added, `bash -n scripts/console.sh`.
- **Status:** OPEN. Code RESOLVED in cycle 2; the documentation half of the fix is still due, see the re-check section.

### CR-SL02-002 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/src/menu/console_client/__init__.py:110-114`; `backend/tests/unit/test_console_client.py:51` (`Recorder` returns `"{FAMILY_ID} Famiglia Alfa"` as the gcloud stdout) and `:116-128`.
- **Category:** correctness / tests (a mock hides a bug)
- **Problem:** `gcloud run jobs execute … --wait` reports the execution status, not the container's stdout. The job's output goes to Cloud Logging. ADR-0011 requires that the script "mostra a terminale l'esito letto dai log del job". The client prints `done.stdout`, so with the real gcloud the operator never sees the family ID or the `security-log` rows. The unit test passes only because the fake runner returns the job output as if gcloud printed it.
- **Scenario:** the operator runs `family bootstrap --name "Rossi"` → the job succeeds → the terminal shows gcloud's "Execution … has successfully completed" (or nothing on stdout) and no family ID. `security-log --since …` likewise prints no events.
- **Suggested fix:** take the execution name from gcloud's output (`--format=value(metadata.name)`, or the `--async` + `describe` pattern), then read that execution's logs. For example, use `gcloud logging read 'resource.type="cloud_run_job" AND labels."run.googleapis.com/execution_name"="<name>"' --format=value(textPayload)`, or the equivalent `gcloud beta run jobs executions logs read`; TO VERIFY the exact command against the gcloud version pinned for SL-10b. Pass every call through the injected `runner`. If the real wiring has to wait for SL-10b, which deploys the job, write that down explicitly as a deviation in plan §4.4 and change the fake runner so it doesn't pretend gcloud returns the job's stdout.
- **Verification:** the unit test's fake runner returns realistic gcloud output for `execute` and the job lines only for the log-read call. Assert that the client prints the family ID and that the log-read call contains only the execution name, with no hash and no email.
- **Status:** ACCEPTED (user decision 2026-10-22: deviation recorded in plan §4.4, debt row in `docs/STATUS.md`, target SL-10b).

### CR-SL02-003 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/migrations/versions/0002_family.py:207-249` (`tg_person_admin_invariant`), `:282-285` (`p_person_self`); `docs/05-data.md:593` ("Verificato in SL-02: il passaggio di consegne … va a buon fine, degradare l'unico Amministratore fallisce al commit").
- **Category:** tests
- **Problem:** `grep -rn "admin_invariant\|p_person_self" backend/tests` finds nothing. The deferred trigger, which is the database defense for FR-011/SR-011, and the `p_person_self` policy have no automated test. `p_person_self` is the one policy that grants rows regardless of `app.current_family_id()`. The generic isolation test (`support/inventory.py:465`) sets only `app.family_id`, so `p_person_self` never takes part in it. Together with the ASM-050 index, the policy is what keeps a `menu_app` session with account context X out of other families' `person` rows (SR-042).
- **Scenario:** a later migration widens `p_person_self` (for example, it drops `account_id =` or adds `OR true` while debugging), or the trigger is dropped or loses `DEFERRABLE`. Every test stays green. My throwaway-database probe confirms the current behavior: demoting the only admin as `menu_app` gives `CheckViolation: the family must keep at least one active admin`. That evidence isn't in the suite.
- **Suggested fix:** add to `tests/db/test_family_schema.py`, or a new `test_person_policies.py`:
  1. Promote a second person, then demote the first, in one transaction → commit succeeds.
  2. Demote the only admin → `CheckViolation` at commit, with constraint name `tg_person_admin_invariant`.
  3. Delete the only admin while an account member stays → violation.
  4. A tombstone-only family and a family with no persons → no violation.
  5. Deleting the family cascades without violation (already covered indirectly; make it explicit).
  6. `menu_app` with only `app.account_id = X` (no family) sees exactly X's active person and no other row, from either family.
  7. With `app.family_id = A` and `app.account_id` set to an account of B, the session sees A's persons plus only the one row for that account, never other B rows.
- **Verification:** `pytest tests/db -k "admin_invariant or person_self"`. Each test must fail if the policy predicate is replaced with `true` or the trigger is dropped (show this once as red evidence).
- **Status:** RESOLVED (cycle 2).

### CR-SL02-004 · MEDIUM · FIX-IN-SLICE
- **Location:** `backend/tests/db/test_console_functions.py:165-184` (`pytest.raises(psycopg.DatabaseError)`), `:244-256` (`suppress(psycopg.DatabaseError)`), `:270-283` (`sorted(types)`), `:295-305` (`!= "203.0.113.77"`); `backend/migrations/versions/0004_console_m0.py:115-145`; `backend/tests/integration/test_console_job.py:73-101`.
- **Category:** tests
- **Problem:** 05-data §3.3 and test strategy 08 §6.5 ask for "un test pytest per funzione, compresi i casi d'errore". Several cases are missing or weak:
  - **`console_security_events` errors:** `p_since IS NULL` and `p_limit` 0, 1001 or NULL have no test (`grep "1001\|p_limit" tests` → nothing).
  - **Error contract:** nothing asserts SQLSTATE 22023 (`InvalidParameterValue`), or that the error message doesn't contain the value it received. The tests accept any `DatabaseError`, and `suppress` doesn't even prove that an error was raised.
  - **Own event:** the `console.security_log` event, written after the read, is never checked for being absent from its own output, and its `details` (`since`, `limit`) are never checked.
  - **Order:** the "in order" test sorts the result before comparing, so ordering by `(occurred_at, id)` is never verified.
  - **IP truncation:** the test only checks `!= full IP`. Returning NULL would pass, and IPv6 /48 is not exercised.
  - **Correlation ID:** no test checks that the job (`console_tx`) actually fills `security_event.correlation_id`.
- **Scenario:** examples of regressions the suite wouldn't catch:
  - `console_security_events` returns `NULL` for the IP;
  - it orders by `id DESC`;
  - it accepts `p_limit = 100000`, so the console can dump the whole log;
  - an error message ends up quoting the family name, which then lands in the job logs;
  - `console_tx` stops setting `app.correlation_id`.
- **Suggested fix:**
  1. Parametrize `(None, 10)`, `(t, 0)`, `(t, 1001)`, `(t, None)` → `pytest.raises(psycopg.errors.InvalidParameterValue)`, and assert that no `console.security_log` event exists afterwards.
  2. Replace the broad `DatabaseError` and `suppress` with `InvalidParameterValue`, and assert that `str(exc)` contains neither the name nor the hex value.
  3. Assert the exact list in order, with equal timestamps broken by `id`.
  4. Assert `host(ip) == '203.0.113.0'` and an IPv6 case such as `2001:db8:1234:5678::1` → `2001:db8:1234::`.
  5. Assert that the `console.security_log` row has `details == {"since": …, "limit": …}` and does not appear in its own result.
  6. In the integration bootstrap test, assert that `correlation_id IS NOT NULL` on the event.
- **Verification:** `pytest tests/db/test_console_functions.py tests/integration/test_console_job.py`. Each new assertion is shown red by temporarily breaking the function in a scratch database.
- **Status:** RESOLVED (cycle 2).

### CR-SL02-005 · LOW · FIX-IN-SLICE
- **Location:** `backend/tests/db/test_security_event.py:81-99` (the parameter `"ip = '198.51.100.1', outcome = 'failure'"`), `:102-109`; `backend/migrations/versions/0003_security_event.py:63-75`.
- **Category:** tests
- **Problem:** the only "bad IP" case changes `outcome` as well, so it is rejected by the first check (`to_jsonb(new) - 'ip'`), and the second branch ("only truncation or NULL") never runs. IPv6 /48 truncation and clearing to NULL, both allowed, are not tested. The rejections are asserted as `DatabaseError`, while 05-data §4.1 specifies `insufficient_privilege` (42501). In a probe, the truncation branch also accepts `203.0.113.0/16` (same host text, different mask): that is harmless for privacy, but it shows the check compares only `host()`.
- **Scenario:** a refactor that turns the second `raise` into `return new` lets `menu_owner` (or the future `maint_security_log_retention`) rewrite an event's IP to any address, and the suite stays green.
- **Suggested fix:** add `ip`-only updates. `'198.51.100.1'` → `InsufficientPrivilege`. `'203.0.113.0'`, `NULL`, and an IPv6 address to its /48 → accepted. Optionally require `masklen(new.ip) in (32, 24)` for IPv4 and `(128, 48)` for IPv6 in the trigger. Use `psycopg.errors.InsufficientPrivilege` in the parametrized test.
- **Verification:** `pytest tests/db/test_security_event.py`. Show red by temporarily replacing the final `raise` with `return new`.
- **Status:** RESOLVED (cycle 2).

### CR-SL02-006 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/console/__init__.py:66` (control-character filter `ord(c) < 32`), `:74` (`f"{family_id} {name}\n"`); `backend/migrations/versions/0004_console_m0.py:46-51`; `backend/tests/integration/test_console_job.py:87`.
- **Category:** design / security (CWE-117, minor)
- **Problem:** the documents disagree. ADR-0011 says "Output del job … solo identificativi, codici di esito e ID di correlazione. Mai email, nomi o contenuti", and plan §4.4 says "output solo ID ed esiti". AC-002.3 allows "identificativo e nome della famiglia". The code follows the AC and prints the name, so it lands in Cloud Logging for 30 days. The family name is user-chosen and often a surname. Separately:
  - The job's filter rejects only C0 controls. DEL (`\x7f`), NEL (`\x85`), U+2028 and U+2029 pass, and some log viewers treat them as line breaks.
  - `console_bootstrap_family` itself accepts a name with `\n`. A probe on a scratch DB returned a UUID for `'Rossi\nFAKE LOG'`, so the database layer has no defense in depth if another caller appears.
- **Scenario:** `--name "Rossi
{\"severity\":\"ERROR\"…}"` is accepted by both the client (`ord < 32` check) and the job, and is echoed into the job log.
- **Suggested fix:**
  - Pick one rule and align the documents. The simplest is to print only the family ID, which satisfies AC-002.3 and the ADR; then update the integration test at `:87`. Otherwise, record the deviation in ADR-0011 and plan §4.4.
  - In both client and job, reject `unicodedata.category(c).startswith("C")` and the separators U+2028 and U+2029.
  - Optionally add `p_family_name !~ '[[:cntrl:]]'` to the SQL function.
- **Verification:** unit or integration tests with `\x7f`, `
` and `\n` in the name → rc 2 and nothing created. Assert that the output matches `^[0-9a-f-]{36}\n$` (if only the ID is printed).
- **Status:** RESOLVED (cycle 2; user decision: the job prints the family ID only).

### CR-SL02-007 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/audit/log.py:55-87`; `backend/tests/unit/test_audit_log.py:1-28`.
- **Category:** tests / correctness
- **Problem:**
  - `security_log` is the app's only write path into the security log (SR-020, SR-057). Its tests cover only the catalog check and `ip_prefix`. Nothing tests that the INSERT succeeds as `menu_app` (the casts to `inet`, `varchar` and `jsonb`, and the `details` JSON), or that the structured log line has `ip_prefix` and never the full `ip`. That second point depends on `platform.logging.ALLOWED_FIELDS`, which was extended in this diff.
  - With an external `tx`, the log line is written before the caller commits. If the transaction rolls back, stdout reports an event that the database doesn't have, and log-based alarms (SR-058) would count it.
- **Scenario:** a typo in `_INSERT` (for example `cast(:ip as inet)` given an invalid string) surfaces only at the first caller in SL-03a. A later change that logs `ip=event.ip` is dropped silently only because `ip` isn't in the allow-list; there is no test pinning that behavior.
- **Suggested fix:** add a DB test that calls `security_log(SecurityEvent(...ip="203.0.113.77", details_json='{"k":"v"}'))` through `menu.tenancy` as `menu_app` and checks the row as owner. Add a capture of the structured output (`capsys` with `configure_logging()`) asserting `ip_prefix == "203.0.113.0/24"` and that `203.0.113.77` is absent. Document, or change, the ordering: either emit the log line after commit (the caller's responsibility, stated in the docstring) or accept and note it.
- **Verification:** `pytest tests/db -k security_log` and `pytest tests/unit/test_audit_log.py`.
- **Status:** OPEN. Partially fixed in cycle 2, see the re-check section.

### CR-SL02-008 · LOW · FIX-IN-SLICE
- **Location:** `backend/src/menu/console_client/__init__.py:39-42` (`_Parser` without `allow_abbrev=False`), `:106-113`.
- **Category:** maintainability / correctness
- **Problem:**
  - `capture_output=True` hides gcloud's stderr: "not authenticated", "job not found" and region errors all become "il job menu-console è fallito". If gcloud needs a reauth prompt, the prompt is captured and the command appears to hang.
  - If `gcloud` isn't installed, `runner` raises `FileNotFoundError`, which is not caught, and Python prints a traceback that includes the full command list with the email hash.
  - The client parser allows abbreviated options (`--na`); the job parser explicitly forbids them.
- **Scenario:** the operator runs the client on a machine without gcloud → traceback on the terminal with `--args=family,bootstrap,--name,…,--email-sha256,<hex>`.
- **Suggested fix:** catch `OSError` around `runner` → fixed message and `EXIT_JOB_FAILED`. Pass gcloud's stderr through on failure: it doesn't contain the email, only the hash already visible in the execution metadata. Alternatively, don't capture stderr. Add `allow_abbrev=False` to the client `_Parser`. This can be done together with CR-SL02-002.
- **Verification:** unit tests: a runner raising `FileNotFoundError` → rc 1 and no `Traceback` in stderr; `--na Rossi` → rc 2.
- **Status:** RESOLVED (cycle 2).

### CR-SL02-009 · INFO · BACKLOG
- **Location:** `backend/migrations/versions/0002_family.py:246-248`.
- **Category:** design
- **Problem:** the constraint trigger is `AFTER UPDATE OR DELETE` and checks only `old.family_id`, exactly as 05-data §4.2 specifies. A probe confirmed that `menu_app` can INSERT an account person with `role='member'` into a family that has no admin, and commit. This is consistent with the spec, since the primary mechanism is the application lock, but SL-11/12 (invite acceptance) will be the first INSERT path for account persons.
- **Scenario:** a bug in invite acceptance for a family whose bootstrap was never redeemed leaves a family with members and no admin, and the database doesn't object.
- **Suggested fix:** data-architect to decide in SL-11/12 whether to add `INSERT` (and `UPDATE OF family_id`, checking `new.family_id`) to the trigger.
- **Verification:** a test in SL-12.
- **Status:** OPEN

### CR-SL02-010 · INFO · BACKLOG
- **Location:** `backend/migrations/versions/0003_security_event.py:84-86`.
- **Category:** security (CWE-345, defense in depth)
- **Problem:** `menu_app` has INSERT on all columns, so a compromised app can write rows that look like console commands. A probe inserted `console.family_bootstrap` with `actor_kind='platform_operator'` as `menu_app`, and it was accepted. Append-only protects existing rows, not the authenticity of new ones.
- **Scenario:** after an app compromise, an attacker inserts fake `console.audit_note` events to muddy the forensic timeline.
- **Suggested fix:** under the user's "proportionate security" principle this is acceptable. If wanted later, a `BEFORE INSERT` trigger can reject `actor_kind='platform_operator'` or `event_type LIKE 'console.%'` when `current_user = 'menu_app'`. The security-engineer should decide.
- **Verification:** n/a.
- **Status:** OPEN

### CR-SL02-011 · INFO · BACKLOG
- **Location:** `backend/tests/integration/test_console_job.py:47,191`; `backend/tests/db/test_family_schema.py:193-203`; `backend/tests/property/test_email_sha256.py:345-349`; `backend/tests/tools/test_container.py:181`.
- **Category:** tests
- **Problem:** minor hygiene issues:
  - `PYTHONPATH` is set, but `python -I` ignores it; the test works only because the venv has `menu` installed.
  - `test_tombstone_person_has_no_name_and_no_account` has no assertion. It is a valid "accepted" test, but its name promises more than it checks.
  - `test_different_normalized_emails_have_different_hashes` checks SHA-256 collision resistance and can't fail meaningfully.
  - Container tests leave many `menu-design-test:*` and `menu-design-web-test:*` images behind; this predates SL-02.
- **Suggested fix:** drop `PYTHONPATH` or the `-I` flag. Rename the tombstone test (`…_is_accepted`) or read the row back. Drop the collision property. Remove test images in a fixture finalizer.
- **Verification:** n/a.
- **Status:** OPEN

### CR-SL02-012 · INFO · BACKLOG
- **Location:** `docs/STATUS.md`, technical debt table.
- **Category:** maintainability
- **Problem:** several items are scheduled for SL-02 but don't appear in this diff:
  - SEC-SL00b-004: the test harness should refuse non-loopback `MENU_TEST_PG_HOST`; `support/pg.py` is unchanged.
  - Part of CR-SL00b-005..008: the harness race on `menu_owner` connection limit 3, and no `pool_pre_ping`.
- **Suggested fix:** the orchestrator either includes them in the SL-02 fix cycle or moves them to a named slice.
- **Verification:** n/a.
- **Status:** OPEN (BACKLOG). SEC-SL00b-004 resolved in cycle 2; the CR-SL00b items are still tagged SL-02 in STATUS.

## Tools run
| Tool | Command | Result |
|---|---|---|
| pytest (unit, architecture, tools) | `backend/.venv/bin/pytest tests/unit tests/architecture tests/tools -m "not container"` | 733 passed, 7 deselected, 0 skipped |
| pytest (7 deselected) | `--collect-only -m container`, then `pytest tests/tools/test_container.py tests/tools/test_container_web.py -m container` | The 7 deselected tests are the container tests from SL-00b/SL-01 (the `container` tier builds the image); none are from SL-02. Run here: 7 passed |
| pytest (db, integration, security, property) | `pytest tests/db tests/integration tests/security tests/property -n 4` (local PG 17 TLS) | 368 passed, 0 skipped, 0 xfail |
| pytest (concurrency, contract) | `pytest tests/concurrency tests/contract -n 2` | 14 passed |
| ruff | `ruff check .`, `ruff format --check .` | All checks passed; 124 files already formatted |
| mypy | `mypy` | Success: no issues found in 119 source files |
| bandit | `bandit -q -c pyproject.toml -r src` | rc 0 |
| semgrep rule tests | `semgrep --test --config .semgrep/sql.yaml .semgrep/sql.py` (1.180.0) | 4/4 passed |
| semgrep path cases | `python3 -I scripts/check_semgrep_rules.py` | 23 path cases OK |
| semgrep custom scan | `semgrep scan --error --config .semgrep backend` | rc 0, no findings |
| entry point | `python -I -m menu.console_client --help` | `No module named menu.console_client.__main__`, rc 1 (CR-SL02-001) |
| DB probe (scratch DB cloned from the head template, dropped afterwards) | script in the session scratchpad | demoting the only admin → CheckViolation; INSERT member into a family with no admin → accepted; IP update `/24` accepted, other address → 42501, `203.0.113.0/16` accepted; `console_bootstrap_family` accepts `'Rossi\nFAKE LOG'`; `menu_app` → EXECUTE on `console_*` denied; `menu_app` can insert a `console.*` event; `menu_console` → SELECT on `family` and EXECUTE on `family_today` denied |

The diff of `.semgrep/sql.yaml` is correct. The lookbehind `(?<!definer )` exempts only the function attribute `security definer set search_path` written on one line. The new fixtures cover SET search_path, SET ROLE, RESET ALL and `set_config(..., false)`, which are still flagged, and the definer attribute next to a real session SET, which is still flagged. The other formattings (attribute on a new line, `SET` before `SECURITY DEFINER`) are false positives, which fails safe. Note: no line-by-line review found empty-bodied tests or unjustified `skip`/`xfail` markers. The weak assertions are listed in CR-SL02-004, 005 and 011.

## What was done well
The migrations follow 05-data closely and are well commented: composite FKs, forced RLS with `WITH CHECK`, `SECURITY DEFINER` functions with a fixed `search_path`, no dynamic SQL and PUBLIC revoked, intervals in hours to avoid DST errors, and a reversible base↔head ladder. The export inventory is designed to be able to fail and proves it with synthetic data. The job never echoes its arguments and reports errors only by type name.

## Re-check · cycle 2
- **Date:** 2026-10-22
- **Scope:** only the open findings CR-SL02-001..008 and the diff of the fix: `git diff 1ce461c` plus untracked files. Files read in full for the fix: `menu/console_client/__init__.py` and `__main__.py`, `menu/console/__init__.py`, `menu/audit/log.py`, `menu/tenancy/engine.py`, migrations `0003` and `0004`, `tests/support/pg.py`, `tests/db/test_console_functions.py`, `test_person_policies.py`, `test_security_event.py`, `test_security_log_write.py`, `tests/unit/test_console_client.py`, `tests/integration/test_console_job.py`; plan §1 and §4.4, ADR-0011, `docs/STATUS.md`.
- **Anti-loop rule:** no new findings were opened. The fix introduced no BLOCKER regression. The two points still due are residuals of findings that were already open (CR-SL02-001 and CR-SL02-007).
- **Re-check verdict:** **APPROVED WITH FIXES**. Two small FIX-IN-SLICE residuals remain. Both need only a targeted check, not a new full review.

### Outcome per finding
| ID | Outcome | Evidence |
|---|---|---|
| CR-SL02-001 | Code RESOLVED; doc residual OPEN (LOW, FIX-IN-SLICE) | `console_client/__main__.py` exists. `test_the_operator_command_is_runnable_as_a_module` runs `python -I -m menu.console_client` as a subprocess: `--help` gives rc 0 and usage text; no arguments gives rc 2 and no traceback. The doc residual is described below |
| CR-SL02-002 | ACCEPTED (user decision) | The deviation is recorded in plan §4.4, line 558 ("Deviazione SL-02 …, lettura automatica dei log in SL-10b"). STATUS has a debt row (MEDIUM, SL-10b). The fake runner now returns realistic gcloud status text. The client prints a fixed "read the Cloud Run job logs" message and no longer prints gcloud's stdout as if it were the job's result. `test_ac_002_3_client_output_points_to_the_job_logs_without_the_email` checks that the family ID inside gcloud's stdout is **not** printed |
| CR-SL02-003 | RESOLVED | `tests/db/test_person_policies.py` covers all of these. For the trigger: handover, deferred check, demoting / tombstoning / deleting the only admin (`CheckViolation` with `diag.constraint_name == "tg_person_admin_invariant"`), the owner also bound, per-family scope, tombstone-only and profile-only families, family cascade. For `p_person_self`: account context only; no context; unknown account; family A + account of B (exact set, `b2` excluded); read-only; no INSERT into another family. The assertions are exact set equalities, so a `true` predicate or a dropped trigger would turn them red |
| CR-SL02-004 | RESOLVED | All six points are covered. `p_since` NULL and `p_limit` 0, -1, 1001, 100000 and NULL raise `InvalidParameterValue` with `sqlstate == "22023"`, leave no event, and the message doesn't echo the value. Bootstrap and audit-note errors are now `InvalidParameterValue` with a check that values aren't echoed, and the `suppress` is gone. Order is checked on the unsorted result, with rows inserted out of order and a timestamp tie. The command's own event is checked for `details == {since, limit}` and for being absent from its own output. IP truncation is exact for IPv4 /24 and IPv6 /48, and NULL stays NULL. `correlation_id` comes from `console_tx` for all three functions, and does not carry over to the next transaction |
| CR-SL02-005 | RESOLVED | `ip`-only updates are now isolated. Different address, different /24, different host in the same /24, v4↔v6, IPv6 rewrite, and NULL→address are all refused with `InsufficientPrivilege`. Truncation to /24 and /48, clearing to NULL, and no change are all accepted. The broad parametrized test now expects `InsufficientPrivilege`. The optional `masklen` check was not added, which is fine (it was optional) |
| CR-SL02-006 | RESOLVED | The job prints only `f"{family_id}\n"`. The integration test asserts `re.fullmatch(r"[0-9a-f-]{36}\n", stdout)`. Client and job both reject `unicodedata.category(c).startswith("C")` and U+2028/U+2029. The client has tests for `\x7f`, `\x85`, U+2028 and U+2029: rc 2 and no gcloud call. Migration 0004 adds `p_family_name ~ '[\x01-\x1f\x7f\u0080-\u009f\u2028\u2029]'`. A scratch-database probe (cloned from the head template, then dropped) shows `\n`, `\t`, DEL, NEL and U+2028 are rejected, while `Rossi Bianchi` and `Zoë-Àlfa` are accepted. Minor, non-gating: format characters such as U+200B and U+202E still pass at the SQL layer, though the job rejects them; the SQL filter and the job's filter have no DB or integration test of their own. Adding `"Rossi\nX"` to the parametrized invalid-argument test in `test_console_functions.py` would pin the SQL filter |
| CR-SL02-007 | PARTIAL, OPEN (LOW, FIX-IN-SLICE) | The write path is now well covered by `tests/db/test_security_log_write.py`: a real INSERT as `menu_app` with all casts; NULL fields; external `tx`; only `ip_prefix` in the log (IPv4 and IPv6), never the full IP and never `details`; a failed INSERT logs nothing; a rolled-back external `tx` logs nothing. The residual is described below |
| CR-SL02-008 | RESOLVED | `OSError` around `runner` gives a fixed message and rc 1, with no traceback and no hash in the output (tested). On failure, gcloud's stderr (the last 2000 characters) is passed through (tested with "active account"). `allow_abbrev=False` is set (`--na` gives rc 2, tested) |

### Residual 1: CR-SL02-001, documentation (LOW · FIX-IN-SLICE)
- **Location:** `docs/07-plan.md:175` (file tree: `│   └── console.sh   # wrapper di menu.console_client`); `docs/adr/ADR-0011-console-del-gestore.md:41` ("**Script locale** (`scripts/console.sh` o `uv run python -m menu.console_client`)").
- **Problem:** `scripts/console.sh` doesn't exist (`ls scripts` shows `check_semgrep_rules.py ci-pg-tls.sh ci.sh dev-certs.sh`). The cycle-1 suggested fix asked for one of two things: add the wrapper, or update plan §1 and ADR-0011 so they name the single entry point. Neither was done. The plan tree is what later slices treat as the layout contract, and an operator who follows the ADR looks for a script that isn't there.
- **Decision:** a doc fix is required. It costs two lines and needs no code: the module entry point already works and is tested.
- **Suggested fix:** in plan §1, remove the `console.sh` line, or mark it "(SL-10b, optional)". In ADR-0011:41, write only `uv run python -m menu.console_client` (run from `backend/`), or add "(wrapper `scripts/console.sh` from SL-10b)". Optionally, ADR-0011 could also point to the plan §4.4 deviation next to "mostra a terminale l'esito letto dai log del job".
- **Verification:** `grep -rn "console.sh" docs | grep -v docs/reviews` returns either nothing or only mentions marked as future.

### Residual 2: CR-SL02-007, log line before the COMMIT (LOW · FIX-IN-SLICE)
- **Location:** `backend/src/menu/audit/log.py:85-87` (`sa_event.listen(tx, "commit", emit, once=True)`), together with the docstring at `:56` ("la riga di log esce solo dopo il commit").
- **Problem:** SQLAlchemy's `ConnectionEvents.commit` fires **before** the DBAPI COMMIT. In 2.1.4, `Connection._commit_impl` calls `self.dispatch.commit(self)` and then `dialect.do_commit(...)` (`sqlalchemy/engine/base.py:1150-1165`). If the COMMIT itself fails, the line has already been written: a deferred constraint, a serialization failure, or a dropped connection. The new tests only exercise the success path and an exception raised inside the `with` block. In that second case there is no commit at all, so the listener never fires.
- **Scenario:** a sqlite probe in the scratchpad patches `do_commit` to raise. The commit raises `RuntimeError`, yet the listener has already logged `emitted`. In this codebase the realistic case is `tg_person_admin_invariant`, which is `DEFERRABLE INITIALLY DEFERRED` and fails only at COMMIT. A role change or member removal in SL-11/12 that writes `security_log(..., tx)` in the same `family_tx` and demotes the last admin gets a `CheckViolation` at commit. Stdout still carries a "success" `security_event` line that the database doesn't have, and the SR-058 log-based alarms count it. A second, harmless probe confirmed that the listener doesn't leak to later transactions after a rollback.
- **Suggested fix:** either of these is fine under the proportionate-security principle:
  - (a) Run the callback after a real commit. The tenancy context managers (`family_tx`, `system_tx`, `console_tx`) run `conn.info.pop("after_commit", [])` callbacks after `with engine.begin()` has exited without an exception, and `security_log` appends `emit` to `tx.info.setdefault("after_commit", [])` instead of registering an event listener.
  - (b) Keep the listener, but correct the docstring and add a note in `log.py`: "emitted just before COMMIT; if the COMMIT fails the line remains". Record it as accepted in the slice report.
- **Verification:** for (a), a DB test inside `family_tx` as `menu_app` that demotes the only admin and calls `security_log(..., tx)`. Assert `CheckViolation` on exit from the `with` block, zero `security_event` rows, and no `security_event` line in `capfd` output. For (b), only the docstring and comment change.

### Other areas of the fix diff (regression check)
- **`audit.security_log` commit listener:** no leak across transactions, `once=True`, the own-`system_tx` path emits after its block. The only issue is residual 2 above.
- **Migration 0004 name filter:** the Python string `'[\\x01-…]'` becomes the SQL ARE escapes `\x01…\u2029` (with `standard_conforming_strings` on). It behaves as intended (see the probe above), and the `downgrade` is unchanged.
- **`console_client/__main__.py`:** minimal and correct; `sys.exit(main())` passes the rc through. Stdlib + `menu.common` only.
- **`tests/support/pg.py` guard:** refuses non-loopback hosts unless `MENU_TEST_PG_ALLOW_REMOTE=1`. CI uses `MENU_TEST_PG_HOST: localhost` (`.github/workflows/ci.yml:50`), so CI is unaffected. Nit: the comment mentions CI needing the opt-in, which is not currently true. The guard itself has no test (it's harness code, acceptable).
- **`test_console_functions.py` `_call` helper:** the three literal SQL calls through `exec_driver_sql` are equivalent to the former dict of strings and contain no `%` that would need escaping. The correlation and no-leak tests stay meaningful. Semgrep custom scan rc 0, rule tests 4/4. Nit: the docstring of `test_correlation_id_does_not_leak_to_the_next_transaction` says "same connection", which the pool doesn't guarantee, but the property holds either way.
- **STATUS:** SEC-SL00b-004 removed as fixed. The row `CR-SL00b-005..008, 010..013` is still tagged "SL-02 / SL-10a / P-4" (CR-SL02-012, BACKLOG: the orchestrator should retag it to the slice that will take it).

### Tools run (cycle 2)
| Tool | Command | Result |
|---|---|---|
| pytest (unit, architecture, tools) | `pytest tests/unit tests/architecture tests/tools -m "not container"` | 740 passed, 7 deselected (container tier, unchanged from cycle 1) |
| pytest (db, integration, security, property) | `pytest tests/db tests/integration tests/security tests/property -n 4 -p no:randomly` with the `MENU_TEST_PG_*` env from the Makefile | 432 passed, 0 skipped. Note: without `MENU_TEST_PG_ADMIN_PASSWORD` the session exits on purpose (harness message), and under xdist this shows as an INTERNALERROR, not a test failure |
| ruff | `ruff check .`, `ruff format --check .` | All checks passed; 127 files formatted |
| mypy | `mypy` | Success, 122 source files |
| bandit | `bandit -q -c pyproject.toml -r src` | rc 0 |
| semgrep | `--test` on `.semgrep/sql.yaml`; `scan --error --config .semgrep backend`; `scripts/check_semgrep_rules.py` | 4/4; rc 0; 23 path cases OK |
| DB probe | scratch DB `create database … template menu_tpl_head_…`, `console_bootstrap_family` with 10 names, then `drop database` | control characters and line separators rejected; Cf characters and normal names accepted |
| SQLAlchemy probe | sqlite scripts in the session scratchpad (`probe_commit.py`, `probe_leak.py`) | the `commit` listener fires before a failing `do_commit`; no leak after a rollback |

The fix cycle was careful: every finding got targeted tests with exact assertions (SQLSTATE, constraint name, unsorted order, exact truncated IP), and the user's decisions are recorded where the next slices will find them.
