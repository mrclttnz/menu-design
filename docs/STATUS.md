# Project status: Menu Design

| Field | Value |
|---|---|
| Created | 2026-10-17 |
| Current phase | P5 Build |
| Last update | 2026-10-22 |
| Automatic commit at end of slice | yes (local only; every push needs the user's explicit consent) |
| Remote | https://github.com/mrclttnz/menu-design (private, created by the user 2026-10-19); run gitleaks on full history before the first push |
| Git | repository initialized 2026-10-17, branch main, local commits only |
| User profile | Experienced developer; knows Python, TypeScript/JavaScript, SQL/PostgreSQL |
| Missing tools (P-0, block SL-00a) | Docker WSL integration, uv, pnpm, psql; gitleaks (`go install github.com/gitleaks/gitleaks/v8@latest` or release binary), semgrep (`pipx install semgrep`), trivy (`sudo apt install trivy` via Aqua repo, or release binary), osv-scanner (`go install github.com/google/osv-scanner/v2/cmd/osv-scanner@latest`) |

## Gates
| Gate | Outcome | Date | Notes / conditions |
|---|---|---|---|
| G1 Vision | APPROVED | 2026-10-17 | docs/01-vision.md rev. 3. Open for P2: Q-009 (attendance details), Q-010 (concurrent edits), Q-012 (teen as Planner), Q-014 (user-content translation, default no), Q-001 partial. ASM-015 (Italian age threshold 14) to verify before writing SRs. |
| G2 Requirements | APPROVED | 2026-10-18 | docs/02-requirements.md v2: 69 FR, 16 NFR, 67 SR, 49 US. Preconditions of M1: short privacy notice (Q-017), risk assessment in threat model (SR-065). Non-blocking Q: Q-014, Q-021 (before public launch). Design must decide via ADR: frozen past mechanism, tenant isolation (RLS), optimistic concurrency; threat model must check SR-039, SR-066 (recovery), SR-067 (console export). |
| G3 Design | APPROVED | 2026-10-19 | 03-ux, 04-architecture v5, ADR-0001..0016 (0016 = risk acceptance), 05-data v4, 06-threat-model v2. ASM-067..070 confirmed. Accepted residual risks: R-02/THR-040 (DB endpoint), R-11/THR-050 (simple Admin recovery), THR-030 (invite link), THR-072 (offline cache 7 days), THR-028, THR-083. DDL unverified until first slice. |
| G4 Plan | APPROVED | 2026-10-20 | docs/07-plan.md v3 (48 MVP slices: M0 15, M1 18, M2 15; all S/M), docs/08-test-strategy.md v2. Critic: 3 rounds, 0 open objections. User decisions: private remote, push only with consent (D-1); email/password deferred after M2, CHG-020 (D-2), returns when first needed, Q-031 (a); staging = second Supabase Free + Cloud Run menu-staging, same GCP project, no uptime check, manual reactivation (ADR-0005 rev. 5). Backlog: SL-33/34 (after M2), SL-90/91 (public launch). |
| G5 Slices | see slice table | | |
| G6 Verification and audit | – | | |
| G7 Release | – | | |

## Slices
| ID | Goal | Status (TODO / IN PROGRESS / DONE) | Git base | Code review | Security review | Date |
|---|---|---|---|---|---|---|
| SL-00a | Repo, backend skeleton, CI with lint, tests, blocking scans | DONE | 44a5a03 | docs/reviews/SL-00a-code.md (APPROVED, 6 fixed) | docs/reviews/SL-00a-security.md (0 open BLOCKER, 5 fixed) | 2026-10-21 |
| SL-00b | Local DB, migration 0001, tenancy, DB inventories, container | DONE | 022cb46 | docs/reviews/SL-00b-code.md (APPROVED, 5 fixed) | docs/reviews/SL-00b-security.md (APPROVED, 3 fixed) | 2026-10-22 |
| SL-01 | Web shell, i18n, generated client | DONE | 08d6432 | docs/reviews/SL-01-code.md (APPROVED, 5 fixed) | docs/reviews/SL-01-security.md (APPROVED, 0 open; 2 LOW fixed voluntarily) | 2026-10-22 |
| SL-02 | Console bootstrap, security log, first RLS check | TODO | | | | |
| SL-03a | Google login, sessions, CSRF, logout | TODO | | | | |
| SL-03b | Rate limits, session cap | TODO | | | | |
| SL-04 | Dish archive | TODO | | | | |
| SL-05 | Change events, dish status | TODO | | | | |
| SL-06a | Week view, meals of the day | TODO | | | | |
| SL-06b | Assign dishes to meals | TODO | | | | |
| SL-07 | Free text, special meals, last cooked, past corrections | TODO | | | | |
| SL-08 | Archive, restore, delete dishes | TODO | | | | |
| SL-09 | Family settings, timezone, meal freeze | TODO | | | | |
| SL-10a | Worker, retention, backup, seed datasets, storage measure | TODO | | | | |
| SL-10b | Staging, deploy pipeline, M0 release | TODO | | | | |
| SL-11 | Invite links | TODO | | | | |
| SL-12 | Accept or decline invite | TODO | | | | |
| SL-13 | People, roles, last admin, leave | TODO | | | | |
| SL-14 | Typical week, frozen past attendance | TODO | | | | |
| SL-15 | Absences, guests, covers | TODO | | | | |
| SL-16 | Profiles, display name, privacy notice | TODO | | | | |
| SL-17 | Tastes, Member dish proposals | TODO | | | | |
| SL-18 | Member view, visits, modified by | TODO | | | | |
| SL-19 | Edit conflicts | TODO | | | | |
| SL-20 | Move and swap | TODO | | | | |
| SL-21 | Copy day or week | TODO | | | | |
| SL-22 | History | TODO | | | | |
| SL-23a | Exports: queue, job, scope | TODO | | | | |
| SL-23b | Exports: download, purge on role loss | TODO | | | | |
| SL-24 | Admin recovery, notices, revoke-all | TODO | | | | |
| SL-25 | My sessions | TODO | | | | |
| SL-26 | Security alarms, role activity, stats | TODO | | | | |
| SL-27 | M1 retention, deletion replay (closes M1) | TODO | | | | |
| SL-28 | Reauth bound to the same identity | TODO | | | | |
| SL-29 | Nominate or revoke admins | TODO | | | | |
| SL-30 | Delete my account | TODO | | | | |
| SL-31 | Delete family with cooling-off | TODO | | | | |
| SL-32 | Creation codes, new family | TODO | | | | |
| SL-35 | Link a profile to an account | TODO | | | | |
| SL-36 | Tags, prep-time filter, least-recently-cooked sort | TODO | | | | |
| SL-37 | Priority and preferred sort | TODO | | | | |
| SL-38 | Promotion proposal | TODO | | | | |
| SL-39 | Doesn't like warning | TODO | | | | |
| SL-40 | Several named Altro pasto | TODO | | | | |
| SL-41 | Custom courses | TODO | | | | |
| SL-42 | Similar dish names | TODO | | | | |
| SL-43 | Offline PWA | TODO | | | | |
| SL-44 | CSV import (Could) | TODO | | | | |

## Blockers and pending decisions
- Before M1: privacy notice written by the user (Q-017); sign DPIA v1 (06-threat-model §8.6); accept Google Cloud and Supabase DPAs; devops checks V-1..V-7 (Supabase network restrictions → static IP or residual risk in DPIA), Cloud Run X-Forwarded-For and job execution retention
- Before the M0 release (plan P-2): Google Cloud billing account with budget (Cloud Run needs it for M0)
- Before the first slice (plan P-0): enable Docker WSL integration; install uv, pnpm, psql, gitleaks, semgrep, trivy, osv-scanner

## Decisions during build
- 2026-10-22 · SL-01: TypeScript pinned to 5.9.x (openapi-typescript 7.13 crashes on TS 7.0.2; deviation from architecture TS 7.0.x, revisit when the generator supports TS 7); static JS/CSS compressed by the app so the 150 KiB gzip budget holds in delivery; pnpm cooldown and build-script allow-list in `web/pnpm-workspace.yaml`, not `.npmrc` (plan §1 and §5.6 to be corrected).

## Technical debt
| Finding ID / source | Description | Severity | Scheduled in |
|---|---|---|---|
| SEC-SL00a-008, CR-SL00a-011 | certifi cooldown exception (backend `pyproject.toml` `exclude-newer-package` and Makefile `TOOL_CERTIFI_EXCEPTION`, user decision 2026-10-20, GHSA-6q48-6c7w-9gw2): remove both lines and re-run `uv lock` | LOW | **by 2026-10-27** |
| GHSA-vfj7-8cjw-p6xm (SL-01) | `braces` <=3.0.3 (HIGH, stack exhaustion on nested glob patterns, no patched version), dev-only via micromatch <- @lingui/cli / eslint-plugin-lingui; dated exception limited to this GHSA in `make scan-web` and the osv-scanner config, user decision 2026-10-22 (risk-acceptance ADR): remove the exception and re-run the scans when braces/micromatch is patched or Lingui drops micromatch | HIGH (accepted, dev-only) | **by 2026-11-21** |
| SEC-SL00a-005 | `TRUSTED_PROXY_HOPS` defaults to 0: on Cloud Run per-IP limits become global; remove the default | LOW | SL-03b |
| SEC-SL00a-006 | Hide SQL parameters in logged errors (`hide_parameters=True`) and add DB/Pydantic error canary test | LOW | SL-00b |
| SEC-SL00a-007 | Semgrep `text()` rule: allow only literals; add `literal_column`, `exec_driver_sql`, async session variants; fixtures for `SET ROLE`/`search_path`/`SESSION` | LOW | SL-00b |
| SEC-SL00a-009 | Dependabot with 7-day cooldown; zizmor online checks | LOW | SL-10b or earlier |
| SEC-SL00a INFO-14 | Tool-install cooldown test accepts exceptions for any package; restrict to the certifi variable | INFO | SL-00b |
| CR-SL00a-007..013 | Body-size guard fail-open branch (not exploitable on HTTP/1.1), untested platform branches, dead code in `scan-deps`, pre-commit `uv run` without `--frozen`, `make help` wording, uvicorn access-log/correlation_id notes (details in code review report) | LOW | SL-00b / SL-01 |
| SEC-SL00b-004 | Test harness sets a published role password on any `MENU_TEST_PG_HOST`: refuse non-loopback hosts without explicit opt-in | LOW | SL-02 |
| SEC-SL00b-005 | Image keeps 11 setuid/setgid binaries (add `chmod a-s`); 44 unfixed HIGH OS CVEs reported by trivy | LOW | SL-10b |
| CR-SL01-006..014 | Blank page if the lazy language catalog fails to load (main.tsx has no catch); API client not typed against generated `paths` (before SL-03a); e2e runs against local uvicorn, not container + PostgreSQL + OIDC stub (plan §6.1/6.2 deviation, to record); static server reads and gzips synchronously per request, If-Modified-Since and in-root symlink branches untested; frame-ancestors e2e treats timeout as blocked; `i18n-check.mjs` rewrites the committed catalog on failure; `packageManager` pnpm pin integrity (security confirmed pinned by hash); uvicorn startup errors reduced to logger name (runbook note); non-scalar branch of `_neutralise` (logging.py:66) untested | LOW/INFO | SL-03a / SL-10b |
| SL-01 notes | THR-074: `Referrer-Policy: no-referrer` on `/invito` in SL-11; ADR-0017 braces advisory is upstream HIGH, contextual LOW (dev-only); Playwright on this WSL host needs `sudo pnpm exec playwright install-deps chromium` (libnspr4, libnss3, libasound2; workaround via LD_LIBRARY_PATH in scratchpad) | INFO | SL-11 / before first push |
| SEC-SL00b-007 | gitleaks allowlist of `db/dev-certs/` hides force-added files: add `git ls-files db/dev-certs` empty check | LOW | SL-00b follow-up / SL-10b |
| CR-SL00b-005..008, 010..013 | Seed guard checks only the `DATABASE_URL_OWNER` host (tie to the URL used, SL-10a); harness race on `menu_owner` connection limit 3; no `pool_pre_ping` (500 on first request after pooler restart); Hypothesis examples hard-coded (no ci/nightly profile); Supabase `service_role` CREATE on `public` and `extensions` (verify at P-4, add to bootstrap revoke list); `make dev` starts only the DB; unqualified `now()` in `now_utc` body (accepted, D1); keep `last-modified-files.sh` out of commits | LOW/INFO | SL-02 / SL-10a / P-4 |
| SL-00b notes | From SL-02 `tenancy` must offer a way to set `app.correlation_id` (semgrep bans `set_config(` outside tenancy); 0008+ SECURITY DEFINER needs `SET search_path` (semgrep rule exception); 05-data §3.1/§11.1 and ADR-0014 to align (backup default SELECT, CREATE revoked from `public` owner, Supabase ADMIN-only membership, non-inlinable search_path trade-off); 08 §6.7 INLINABLE list split allowed (7) / expected now (4); CI workflow (postgres TLS service, container job) not yet run on GitHub (no push consent) | INFO | before first push |
| SL-00a note | docs/07-plan.md and 08-test-strategy mention semgrep 1.181.0 / zizmor 1.31.1; Makefile pins 1.180.0 / 1.30.1; docs-only CI path filter (plan §6.3) not yet implemented | INFO | before first push |

## Log
- 2026-10-17 · orchestrator · discovery interview (P1) · –
- 2026-10-17 · product-analyst · created product vision · docs/01-vision.md
- 2026-10-17 · critic · vision review: 1 BLOCKER, 6 IMPORTANT, 2 MINOR (OBJ-01..09) · none
- 2026-10-17 · product-analyst · vision rev. 2: user decisions OBJ-01..09, milestones M0-M2, KPI-1..8 · docs/01-vision.md
- 2026-10-17 · product-analyst · vision rev. 3: final gate decisions (M0 Google-only, age self-declaration, operator via script, i18n readiness) · docs/01-vision.md
- 2026-10-17 · orchestrator · gate G1 approved by the user; phase → P2 Requirements · docs/STATUS.md
- 2026-10-17 · setup · git init, .gitignore, docs/adr and docs/reviews, user profile and security tools recorded · .gitignore, docs/STATUS.md
- 2026-10-18 · security-engineer · requirements security review: proposed SR-033..SR-063, decisions SD-1..SD-7, weaknesses of SR-001..SR-032 in report · docs/02-requirements.md
- 2026-10-18 · orchestrator · requirements elicitation (P2) · –
- 2026-10-18 · product-analyst · requirements v1: FR-001..059, NFR-001..016, SR-001..032, US-001..041 · docs/02-requirements.md
- 2026-10-18 · critic · requirements review: 2 BLOCKER, 6 IMPORTANT, 2 MINOR · none
- 2026-10-18 · product-analyst · requirements v2: user decisions OBJ-01..10, integrated SR-033..063 + SD-1..7, FR-060..069, SR-064..067, US-042..049 · docs/02-requirements.md
- 2026-10-18 · orchestrator · gate G2 approved by the user; phase → P3 Design · docs/STATUS.md
- 2026-10-18 · product-analyst · G2 confirmations applied (ASM confirmed, Q-022 closed, Q-021 deferred); vision rev. 4 aligned to approved requirements · docs/02-requirements.md, docs/01-vision.md
- 2026-10-18 · architect · architecture v1-v3, ADR-0001..0016; user decisions: Python backend, Supabase Free Frankfurt, RLS, daily backups, Cloud Run europe-west3, Authlib + own sessions; ADR-0016 risk acceptance (exposed DB endpoint) · docs/04-architecture.md, docs/adr/
- 2026-10-18 · ux-designer · UX v1 + update with user decisions (sort, priority, multiple named "Altro pasto", server last visit) · docs/03-ux.md
- 2026-10-18 · data-architect · data model v1-v2 (RLS, roles, frozen past, compact change_event, slot for "Altro pasto", storage estimate) · docs/05-data.md
- 2026-10-18 · product-analyst · post-G2 changes CHG-001..007 (FR-070..072, NFR-017, FR-062b last visit), Q-023..Q-030 closed, ASM-063..066 confirmed, ASM-067..070 proposed for G3 · docs/02-requirements.md
- 2026-10-18 · architect · architecture v3: data-architect proposals accepted, compact events, meal_slot for multiple "Altro pasto", full ErrorCode table, Supabase checks for devops · docs/04-architecture.md, docs/adr/
- 2026-10-18 · security-engineer · threat model v1 (91 THR, DPIA-lite SR-065, ADR-0016 control review, SR-068..076 proposed) · docs/06-threat-model.md
- 2026-10-19 · data-architect · data model v3: threat-model actions, simple Admin recovery (console_recover_admin, family_notice), invite across login, connection limits, export rules · docs/05-data.md
- 2026-10-19 · ux-designer · UX update: recovery notice B-03, Admin-visible emails, offline expiry, reauth wrong account · docs/03-ux.md
- 2026-10-19 · product-analyst · threat-model SRs integrated (CHG-008..015: SR-068, 070-076 accepted, SR-069 rejected → simple Admin recovery, DPIA v1 from M1, THR-030 accepted); vision rev. 5 · docs/02-requirements.md, docs/01-vision.md
- 2026-10-19 · architect · architecture v4: threat-model actions A-01..A-19, simple recovery, console as cloud job, ADR-0016 rev. 2, reauth_wrong_account · docs/04-architecture.md, docs/adr/
- 2026-10-19 · critic · G3 joint review: 1 BLOCKER (recovery contract), 8 IMPORTANT, 1 MINOR · none
- 2026-10-19 · ux-designer · UX aligned to ADR-0010 codes, notices endpoints, 5 active "Altro pasto" · docs/03-ux.md
- 2026-10-19 · product-analyst · CHG-016..018: simplified Admin recovery, 5 active "Altro pasto" with reuse, Lighthouse nightly; vision rev. 6 · docs/02-requirements.md, docs/01-vision.md
- 2026-10-19 · security-engineer · threat model v2: simplified recovery (R-11 accepted), DPIA v1 §8 updated, §15 review · docs/06-threat-model.md
- 2026-10-19 · data-architect · data model v4: G3 objections, console_recover_admin, email SHA-256, meal_slot + reuse, 4 roles, RLS on session · docs/05-data.md
- 2026-10-19 · architect · G3 objections OBJ-01..08/10 resolved, ADR-0001 and 0006..0013 ACCEPTED, architecture v5 · docs/04-architecture.md, docs/adr/
- 2026-10-19 · critic · G3 round 2: no BLOCKER, 4 IMPORTANT text fixes · none
- 2026-10-19 · architect, data-architect, product-analyst (CHG-019), security-engineer, ux-designer · round-2 consistency fixes (email hash in Python, prompt for email, meal reuse resets, NFR-017 mapped) · docs/
- 2026-10-19 · orchestrator · gate G3 approved by the user; ASM-067..070 confirmed; phase → P4 Plan · docs/STATUS.md
- 2026-10-19 · tech-lead · development plan v1: monorepo and module layers, API contracts, conventions, CI, 45 slices SL-00..SL-44 (M0 11, M1 17, M2 17, sizes S/M), migration sequence, traceability US/SR/NFR/THR, user preconditions P-0..P-15, decisions D-1, D-2 · docs/07-plan.md
- 2026-10-19 · tester · test strategy v1 (pyramid, inventories, SR/NFR → verification, CI/nightly/pre-release, missing local tools; D-T1, Q-T1..3, I-T1..7) · docs/08-test-strategy.md
- 2026-10-19 · critic · G4 review of plan and test strategy: 1 BLOCKER (slices effectively L: SL-00, SL-03, SL-23), 5 IMPORTANT, 4 MINOR (OBJ-01..10); opinions on D-1, D-2, D-T1, D-T2, Q-T1, Q-T2 · none
- 2026-10-19 · architect · G4 user decisions: staging env (2nd Supabase Free + Cloud Run menu-staging, separate WIF/secrets/OAuth client, synthetic data only, Supabase pause, V-8) and private GitHub repo in ADR-0005 rev. 5; Q-T1 (malformed If-Match → 422 invalid_value) in ADR-0008/0010; Q-T2 (/healthz contract); CHG-020 applied (password login, email provider, Pwned Passwords, argon2-cffi, progressive delay marked deferred); ErrorCode dish_not_planned (409); architecture v6 · docs/04-architecture.md, docs/adr/ADR-0002-linguaggio-e-framework.md, docs/adr/ADR-0004-autenticazione-e-sessioni.md, docs/adr/ADR-0005-hosting-backup-monitoraggio.md, docs/adr/ADR-0006-store-limiti-di-frequenza.md, docs/adr/ADR-0008-concorrenza-ottimistica.md, docs/adr/ADR-0010-internazionalizzazione.md, docs/STATUS.md
- 2026-10-19 · product-analyst · CHG-020: email/password login (FR-002, FR-003, US-029) deferred to post-M2 backlog per user decision at G4; SR-002/006/034/035/036 follow FR-002, SR-061 moves to first email flow, Google-related SRs kept; new Q-031; vision rev. 7 (ASM-024) · docs/02-requirements.md, docs/01-vision.md
- 2026-10-20 · product-analyst · NFR-017 clarified (plan v3 I-P3): storage measured in SL-10a and repeated in SL-27; requirement unchanged · docs/02-requirements.md
- 2026-10-20 · product-analyst · Q-031 closed (user, option a): email/password resumes at first tester without Google, decided before public launch at the latest · docs/02-requirements.md
- 2026-10-19 · ux-designer · CHG-020: J13 and "Continua con email e password" marked deferred (post-M2), WCAG 3.3.8 password note not applicable to MVP, AC-013.1 checked against S-12, stale PROPOSTA header updated, microcopy for validation.invalid_value / unknown_field / dish_archived (plan §11.3) · docs/03-ux.md
- 2026-10-19 · ux-designer · added UX key error.dish_not_planned (409, archive of a never-planned dish; plan §11.3, due before SL-08) · docs/03-ux.md
- 2026-10-20 · ux-designer · UX copy for architect contracts: error.course_in_use, multi-unit conflict reasons (version_changed, choice_required), already_in_family copy confirmed and extended · docs/03-ux.md
- 2026-10-19 · tester · test strategy v2: staging + seeding guard, now_utc test, SQL-function inventory redesign, run tiers (ci/full/nightly), critical modules 90/80, ExportContributor inventory, email/password post-M2 · docs/08-test-strategy.md
- 2026-10-19 · security-engineer · threat model v3 (G4): CHG-020 (THR-121/122 not applicable in MVP, TB-9 inactive, DPIA without email provider, §12 mapping 18 High in MVP), staging review (TB-10 proposed, THR-130..134), /healthz THR-106, If-Match THR-107 (bigint overflow → 500), actions A-20..A-25, no new SRs, PROPOSTA header removed · docs/06-threat-model.md
- 2026-10-20 · architect · threat model v3 follow-ups: A-20 (email provider and TB-9 marked deferred, TB-10 staging added), THR-107 (If-Match regex max 18 digits), WIF bindings also check ref == refs/heads/main and both GitHub environments allow only main, seed guard as allow-list (APP_ENV dev|staging) · docs/04-architecture.md, docs/adr/ADR-0005-hosting-backup-monitoraggio.md, docs/adr/ADR-0008-concorrenza-ottimistica.md, docs/adr/ADR-0010-internazionalizzazione.md, docs/STATUS.md
- 2026-10-20 · architect · ADR-0003 rev. 6: function table aligned to 05-data v5 §3.3 (I-P5: removed maint_purge_sessions/exports/invites_codes, maint_role_activity as plain SQL on pg_stat_activity, added maint_purge_family_notices, maint_db_size, purge_family_exports); same fix in ADR-0013, ADR-0016, 04-architecture; APP_ENV adds `test`; ADR-0005 staging Supabase reactivation stays manual (no org-wide Supabase token in CI); checked 08-test-strategy §4.1b · docs/adr/ADR-0003-database-e-isolamento-famiglie.md, docs/adr/ADR-0013-elaborazioni-in-background.md, docs/adr/ADR-0016-rischio-accettato-endpoint-database.md, docs/adr/ADR-0005-hosting-backup-monitoraggio.md, docs/04-architecture.md, docs/STATUS.md
- 2026-10-20 · architect · plan v3 items: I-P13 (staging on demand via workflow_dispatch and before each release; production only after a successful staging run of the same digest), §11.3 contract (authOutcome already_in_family, params.units[] with key/reason/current/modifiedBy/modifiedAt in multi-unit 412, ErrorCode course_in_use 409 {usageCount}) · docs/adr/ADR-0005-hosting-backup-monitoraggio.md, docs/04-architecture.md, docs/adr/ADR-0008-concorrenza-ottimistica.md, docs/adr/ADR-0010-internazionalizzazione.md, docs/STATUS.md
- 2026-10-20 · tech-lead · development plan v2: G4 objections OBJ-01/02/04/06..10 (SL-00a/b, SL-03a/b, SL-23a/b, now_utc, ExportContributor DoD, tiered make ci/nightly/full), D-1 (private repo, push by consent, Actions budget), D-2/CHG-020 (SL-33/34 to post-M2 backlog, M2 15 slices), staging per ADR-0005 rev. 5 in SL-10 and P-16, healthz and If-Match contract, UX keys, threat model v3 A-22..A-25 and WIF ref check; 46 MVP slices (M0 13, M1 18, M2 15), all S/M · docs/07-plan.md
- 2026-10-20 · data-architect · data model v5 (G4): CHG-020 deferrals (password_credential, account_token, rate_block, account.status, UQ lower(email) → §4.3; auth_provider google only), app.now_utc() everywhere incl. defaults with single exception + LANGUAGE sql list (D-T1), default-meal change converts future inherit meals with content/guests to added (I-P1), maint_ prefix + ADR-0003 mismatch reported (I-P5), I-P2/P6/P7/P8 fixes, seed allow-list dev|staging and no synthetic data in migrations, dish_not_planned mapping · docs/05-data.md
- 2026-10-20 · tester · test strategy aligned to plan v2 (SL-00a/b, SL-03a/b, SL-23a/b, S-13→SL-15, S-17→SL-16, SL-33/34 post-M2); added 19-digit If-Match, seed APP_ENV allow-list, /healthz body+cache, staging header smoke, Supabase staging reactivation precondition · docs/08-test-strategy.md
- 2026-10-20 · tester · test strategy: closed INLINABLE_SQL_FUNCTIONS list, now()-forbidden expression set (only now_utc body), seed allow-list dev/staging, dataset loader library for tests, If-Match above 2^31-1 test · docs/08-test-strategy.md
- 2026-10-20 · critic · G4 round 2: OBJ-01 resolved for SL-00/03/23; new 1 BLOCKER (SL-10 effectively L after staging), 4 IMPORTANT (M2→M1 dependencies, make ci red in SL-00a/b, Supabase auto-reactivation token, contract-first rule scope and §11.2 status) · none
- 2026-10-20 · tester · test strategy: Supabase staging reactivation is manual (ADR-0005), SL-10a/b references, enabled-tiers mechanism for make ci · docs/08-test-strategy.md
- 2026-10-20 · tech-lead · development plan v3: critic round 2 OBJ-11..15 (SL-10a/b, SL-27 = M1 closed, CI_TIERS in ci.sh with test, no auto Supabase reactivation and staging on demand per Actions budget, status columns and ancestor blocking rule, I-P1/2/5..9/12 closed), tiers aligned to 08 §18.1, now_utc body exception, SL-06 split into 06a/06b, 05-data v5 follow-ups (maint_* names, rate_block deferred, bigint version binding, menu.seeding.datasets); 48 MVP slices (M0 15, M1 18, M2 15), all S/M · docs/07-plan.md
- 2026-10-20 · tester · test strategy aligned to plan v3 (SL-06a/b, CI_TIERS and test_ci_tiers, db/security/integration tiers from SL-00b, staging on demand) · docs/08-test-strategy.md
- 2026-10-20 · critic · G4 round 3 (final check plan v3): OBJ-11..15 resolved; SL-06a/b, SL-10a/b believable S/M; G4 checklist passes; 0 BLOCKER, 2 IMPORTANT (OBJ-16 staging inside `make full` vs §8.3; OBJ-17 blocking rule for slices without an API, I-P3/I-P13 open) · none
- 2026-10-20 · tester · test strategy §18.1: make full is local only; staging checks and 18.3 checklist only in make prerelease · docs/08-test-strategy.md
- 2026-10-20 · tech-lead · development plan v3 final touch-ups: OBJ-16 (make full local only, staging checks only in make prerelease), OBJ-17 (blocking rule for slices without API), closed I-P3, I-P13 and §11.3 items (already_in_family auth outcome, params.units[] with reason, course_in_use); no open items left · docs/07-plan.md
- 2026-10-20 · orchestrator · gate G4 approved by the user; Q-031 (a); staging defaults kept; slice table filled (48 TODO); phase → P5 Build · docs/STATUS.md
- 2026-10-21 · orchestrator, devops, tester, backend-developer, code-reviewer, security-engineer · SL-00a built: repo scaffold, FastAPI skeleton (/healthz, headers, limits, If-Match, AuthzRoute, redaction), CI with blocking scans; 312 tests; reviews: 0 BLOCKER, 11 FIX-IN-SLICE fixed in 2 cycles (incl. SEC-010); certifi cooldown exception approved by the user · docs/reviews/SL-00a-code.md, docs/reviews/SL-00a-security.md
- 2026-10-22 · orchestrator, tester, data-architect, devops, backend-developer, code-reviewer, security-engineer · SL-00b built: PostgreSQL 17 TLS (compose, dev-certs), bootstrap.sql, Alembic env + 0001, tenancy, healthz DB probe, seed guard, Dockerfile, db/container CI tiers; 663 tests; reviews: 0 BLOCKER, 7 FIX-IN-SLICE fixed in 1 cycle; plan §6.2 amended (trivy config covers Dockerfile only) · docs/reviews/SL-00b-code.md, docs/reviews/SL-00b-security.md
- 2026-10-22 · tester · SL-01 mode B (tests before code): backend static-serving, INFO-10/12, web tooling/CI/container tests; web unit/component, Playwright e2e + axe + budget specs; all red for missing implementation · backend/tests/unit/test_static_files.py, backend/tests/unit/test_static_mount_and_body_guard_gaps.py, backend/tests/tools/test_web_shell.py, backend/tests/tools/test_container_web.py, backend/tests/tools/test_ci_tiers.py, backend/tests/support/assets.py, web/tests/, web/playwright.config.ts, docs/08-test-strategy.md
- 2026-10-22 · orchestrator, frontend-developer, backend-developer, tester, code-reviewer, security-engineer, ux-designer · SL-01 built: web shell (Vite/React/Lingui), generated client, static serving with CSP + Trusted Types, stdlib log redaction, `web`/`e2e` CI tiers; 690 backend + 413 web unit + 116 e2e tests; reviews: 0 BLOCKER, 5 FIX-IN-SLICE fixed in 1 cycle, SEC-SL01-001/002 applied · docs/reviews/SL-01-code.md, docs/reviews/SL-01-security.md
