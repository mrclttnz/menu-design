# Menu Design: unico punto di verità per lint, test, scansioni e CI (piano §6.1).
# I target senza contenuto falliscono con un messaggio esplicito (mai "verdi a vuoto").
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV      ?= uv
BACKEND := backend
RUN     := cd $(BACKEND) && $(UV) run --frozen
WEB     := web
# pnpm viene da corepack alla versione fissata in web/package.json (`packageManager`).
# Cooldown e script d'installazione sono in web/pnpm-workspace.yaml (SR-076).
PNPM    := cd $(WEB) && pnpm

# Strumenti di scansione installati fuori dal lockfile (SR-076): versione fissata
# e cooldown di 7 giorni anche sulle dipendenze transitive. Stesse versioni in CI.
SEMGREP_VERSION := 1.180.0
ZIZMOR_VERSION  := 1.30.1
TOOL_COOLDOWN   := 7 days

# Segnaposto: $(call todo,<slice>,<target>)
define todo
	@echo "ERRORE: 'make $(2)' non è ancora disponibile: disponibile da $(1)." >&2; exit 2
endef

# --- database locale (compose.yaml, SL-00b) -------------------------------------
# Porta host configurabile (un altro servizio puo' occupare 5432). I test leggono MENU_TEST_PG_*:
# se MENU_TEST_PG_ADMIN_PASSWORD e' gia' impostata (CI: servizio postgres) il cluster e'
# esterno e non viene avviato; altrimenti `make dev` avvia compose.yaml con certificati usa e getta.
MENU_PG_HOST_PORT ?= 5432
CERTS_DIR := $(CURDIR)/db/dev-certs
PG_WORKERS ?= 4
CONC_WORKERS ?= 2
CONC_REPEAT ?= 3
ENSURE_DB := $(if $(MENU_TEST_PG_ADMIN_PASSWORD),,dev)
IMAGE_TAG ?= menu-design:local
define PG_ENV
export MENU_PG_HOST_PORT="$(MENU_PG_HOST_PORT)"; \
export MENU_TEST_PG_HOST="$${MENU_TEST_PG_HOST:-localhost}"; \
export MENU_TEST_PG_PORT="$${MENU_TEST_PG_PORT:-$(MENU_PG_HOST_PORT)}"; \
export MENU_TEST_PG_CA="$${MENU_TEST_PG_CA:-$(CERTS_DIR)/ca.crt}"; \
if [ -z "$${MENU_TEST_PG_ADMIN_PASSWORD:-}" ]; then \
  [ -r "$(CERTS_DIR)/admin-password" ] || { echo "ERRORE: manca $(CERTS_DIR)/admin-password: eseguire 'make dev'" >&2; exit 2; }; \
  MENU_TEST_PG_ADMIN_PASSWORD="$$(cat "$(CERTS_DIR)/admin-password")"; export MENU_TEST_PG_ADMIN_PASSWORD; \
fi
endef

.PHONY: help sync dev db-up db-down db-reset dev-certs tier-db tier-container tier-web web-install web-build run-web lint lint-py lint-web test test-web test-unit test-db test-int test-sec test-prop \
        test-conc test-contract e2e lighthouse perf smoke dast scan scan-secrets scan-sast \
        scan-deps scan-workflows scan-web scan-container scan-rules tools-semgrep tools-zizmor ci nightly full prerelease openapi seed

help:
	@echo "Target attivi: sync dev db-up db-down db-reset lint test test-unit test-contract"
	@echo "        test-db test-int test-sec test-prop test-conc scan scan-container ci"
	@echo "        lint-web test-web web-build run-web scan-web tier-web e2e"
	@echo "        (db e container sono livelli di 'make ci' da SL-00b; 'make dev' avvia PostgreSQL 17 con TLS;"
	@echo "         web ed e2e da SL-01: pnpm da corepack, Chromium via 'pnpm exec playwright install chromium')"
	@echo "Segnaposto ('disponibile da SL-xx', falliscono se chiamati):"
	@echo "        lighthouse perf smoke dast nightly full prerelease seed"

sync:
	cd $(BACKEND) && $(UV) sync --frozen

# --- database locale -----------------------------------------------------------
dev-certs:
	./scripts/dev-certs.sh

db-up dev: dev-certs
	MENU_PG_HOST_PORT="$(MENU_PG_HOST_PORT)" docker compose up -d --wait postgres
	@echo "PostgreSQL 17 pronto su 127.0.0.1:$(MENU_PG_HOST_PORT) (TLS; CA: db/dev-certs/ca.crt)."

db-down:
	docker compose down

# Cancella il volume dei dati locali (solo sviluppo, dati sintetici).
db-reset:
	docker compose down --volumes

# --- lint -----------------------------------------------------------------
lint: lint-py lint-web

lint-py: sync
	cd $(BACKEND) && $(UV) lock --check
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) bandit -q -c pyproject.toml -r src

# Installazione dal solo lockfile (SR-076): `--frozen-lockfile` fallisce se non coincide.
web-install:
	$(PNPM) install --frozen-lockfile

lint-web: web-install
	$(PNPM) run lint
	$(PNPM) run format:check
	$(PNPM) run typecheck
	$(PNPM) run i18n:check
	$(PNPM) run i18n:compile

# Compila la SPA in web/dist e verifica il budget del bundle (NFR-001).
web-build: web-install
	$(PNPM) run build
	$(PNPM) run budget

# Prova manuale della shell: builda la SPA e la serve con FastAPI su http://127.0.0.1:$(WEB_PORT)/.
# Database fittizio (la shell non lo tocca, come in playwright.config.ts): le route con dati falliscono.
WEB_PORT ?= 8000
DUMMY_DB_URL = postgresql+psycopg://menu_app:$(DUMMY_DB_PW)@localhost:1/menu?sslmode=verify-full&sslrootcert=/nonexistent/ca.crt
DUMMY_DB_PW  = dummy-run-web-never-connected
DUMMY_PEPPER = dummy-run-web-pepper-0123456789abcdef0123456789
run-web: web-build sync
	cd $(BACKEND) && APP_ENV=test TRUSTED_PROXY_HOPS=0 SESSION_PEPPER="$(DUMMY_PEPPER)" WEB_DIST_DIR="$(CURDIR)/$(WEB)/dist" \
	  APP_BASE_URL="http://127.0.0.1:$(WEB_PORT)" \
	  DATABASE_URL_APP='$(DUMMY_DB_URL)' \
	  $(UV) run --frozen python -m menu serve --host 127.0.0.1 --port $(WEB_PORT)

# --- test -----------------------------------------------------------------
test: test-unit test-web tier-db test-contract

# Livello `web` di `make ci`.
tier-web: lint-web test-web web-build

test-web: web-install
	$(PNPM) run test
	$(PNPM) run api:check

# Livello `db` di `make ci` (piano §6.1): db, integrazione, sicurezza, proprieta', concorrenza.
tier-db: test-db test-int test-sec test-prop test-conc

# I test `container` (build reale dell'immagine) girano nel livello `container`.
test-unit: sync
	$(RUN) pytest tests/unit tests/architecture tests/tools -m "not container" --cov=menu --cov-report=term-missing:skip-covered

test-contract: sync
	$(RUN) pytest tests/contract

test-db: sync $(ENSURE_DB)
	$(PG_ENV); $(RUN) pytest tests/db -n $(PG_WORKERS)
test-int: sync $(ENSURE_DB)
	$(PG_ENV); $(RUN) pytest tests/integration -n $(PG_WORKERS)
test-sec: sync $(ENSURE_DB)
	$(PG_ENV); $(RUN) pytest tests/security -n $(PG_WORKERS)
test-prop: sync $(ENSURE_DB)
	$(PG_ENV); $(RUN) pytest tests/property -n $(PG_WORKERS)
# Pochi worker: menu_app ha CONNECTION LIMIT 20 per tutto il cluster; ripetuto CONC_REPEAT volte.
test-conc: sync $(ENSURE_DB)
	$(PG_ENV); for i in $$(seq 1 $(CONC_REPEAT)); do \
	  echo "--- concorrenza: ripetizione $$i/$(CONC_REPEAT)"; \
	  ( $(RUN) pytest tests/concurrency -n $(CONC_WORKERS) ) || exit 1; done

# Playwright avvia da solo lo stack di backend/tests/support/e2e_stack.py: database di prova sul
# cluster di test (come `make test-db`: serve `make dev`, o MENU_TEST_PG_* in CI), provider OIDC
# finto e il server FastAPI che serve web/dist (E2E_BASE_URL: server gia' avviato).
# Chromium: `cd web && pnpm exec playwright install chromium` (in CI con --with-deps).
e2e: web-install $(ENSURE_DB)
	$(PNPM) run build
	$(PG_ENV); $(PNPM) run test:e2e
lighthouse:
	$(call todo,SL-06a,lighthouse)
perf:
	$(call todo,SL-10a,perf)
smoke:
	$(call todo,SL-10b,smoke)
dast:
	$(call todo,SL-10b,dast)
openapi: sync
	$(RUN) python scripts/export_openapi.py
seed:
	$(call todo,SL-10a,seed)

# --- scansioni (SR-076) ----------------------------------------------------
# Attive in SL-00a: segreti, SAST, dipendenze Python, workflow; da SL-01 anche pnpm audit.
# scan-web (pnpm audit) da SL-01. scan-container (hadolint, trivy) e' il livello `container`.
scan: scan-secrets scan-sast scan-deps scan-workflows scan-web

scan-secrets:
	gitleaks git . --config .gitleaks.toml --redact --no-banner
	gitleaks dir . --config .gitleaks.toml --redact --no-banner

# ECCEZIONE STRETTA al cooldown, solo certifi (stessa decisione utente del lock backend):
# GHSA-6q48-6c7w-9gw2 (CRITICAL) colpisce certifi 2026.7.22; la fix 2026.10.19 e' piu'
# recente di 7 giorni. Da rimuovere entro ~2026-10-27, insieme all'eccezione in pyproject.toml.
TOOL_CERTIFI_EXCEPTION := certifi=2026-10-21T00:00:00Z

tools-semgrep:
	$(UV) tool install --force --exclude-newer "$(TOOL_COOLDOWN)" --exclude-newer-package "$(TOOL_CERTIFI_EXCEPTION)" "semgrep==$(SEMGREP_VERSION)"

tools-zizmor:
	$(UV) tool install --force --exclude-newer "$(TOOL_COOLDOWN)" "zizmor==$(ZIZMOR_VERSION)"

# Regole custom: `semgrep --test` verifica i pattern (fixture in .semgrep/) ma ignora i
# filtri `paths`; check_semgrep_rules.py li verifica con una scansione reale.
scan-rules:
	semgrep --test --metrics=off --config .semgrep/sql.yaml .semgrep/sql.py
	semgrep --test --metrics=off --config .semgrep/frontend.yaml .semgrep/frontend.tsx
	semgrep --test --metrics=off --config .semgrep/migrations-now.yaml .semgrep/migrations-now.py
	python3 -I scripts/check_semgrep_rules.py

scan-sast: scan-rules
	semgrep scan --metrics=off --error --quiet \
	  --config p/python --config p/owasp-top-ten --config p/typescript --config p/react \
	  --config .semgrep backend web

scan-deps: sync
	req="$$(mktemp)"; trap 'rm -f "$$req"' EXIT; \
	cd $(BACKEND) && $(UV) export --frozen --no-emit-project --format requirements-txt \
	  -o "$$req" >/dev/null && \
	$(UV) run --frozen pip-audit -r "$$req" --no-deps --disable-pip --progress-spinner off
	osv-scanner scan source --lockfile $(BACKEND)/uv.lock --config osv-scanner.toml --lockfile $(WEB)/pnpm-lock.yaml

scan-workflows:
	zizmor --no-progress .github/workflows

# Include le devDependencies (nessun --prod) e fallisce se il registro non risponde.
# ECCEZIONE STRETTA e DATATA, solo questo GHSA (decisione utente 2026-10-22): braces <=3.0.3
# (HIGH, solo dev via micromatch <- @lingui/cli, eslint-plugin-lingui; nessuna versione corretta).
# `pnpm audit --ignore` non e' usabile: scrive l'esenzione in pnpm-workspace.yaml, senza scadenza.
# Qui il report JSON e' filtrato per quell'unico ID, solo prima di WEB_AUDIT_EXCEPTION_UNTIL (UTC);
# dopo, o se il report manca o e' illeggibile (registro irraggiungibile), l'audit fallisce.
# (pnpm esce con codice != 0 se trova vulnerabilita': il verdetto e' solo quello del filtro.)
# Tenere allineata con osv-scanner.toml.
WEB_AUDIT_EXCEPTION_GHSA  := GHSA-vfj7-8cjw-p6xm
WEB_AUDIT_EXCEPTION_UNTIL := 2026-11-21

define WEB_AUDIT_VERDICT
const fs = require("fs");
const until = process.env.EXC_UNTIL, id = process.env.EXC_GHSA;
const active = new Date().toISOString().slice(0, 10) < until;
let r;
try { r = JSON.parse(fs.readFileSync(0, "utf8")); } catch { console.error("audit: report illeggibile"); process.exit(1); }
if (!r || typeof r.advisories !== "object" || !r.metadata) { console.error("audit: report incompleto"); process.exit(1); }
const bad = Object.values(r.advisories).filter((a) => ["high", "critical"].includes(a.severity)
  && !(active && a.github_advisory_id === id));
for (const a of bad) console.error("audit: " + a.severity + " " + a.github_advisory_id + " " + a.module_name + " " + a.vulnerable_versions);
if (!active) console.error("audit: eccezione " + id + " scaduta il " + until);
process.exit(bad.length ? 1 : 0);
endef
export WEB_AUDIT_VERDICT

scan-web: web-install
	f="$$(mktemp)"; trap 'rm -f "$$f"' EXIT; \
	$(PNPM) audit --audit-level high --json > "$$f" || audit_rc=$$?; \
	EXC_GHSA="$(WEB_AUDIT_EXCEPTION_GHSA)" EXC_UNTIL="$(WEB_AUDIT_EXCEPTION_UNTIL)" \
	  node -e "$$WEB_AUDIT_VERDICT" < "$$f"

# Livello `container`: hadolint, build, trivy (immagine: HIGH e CRITICAL con correzione;
# configurazione: Dockerfile, compose.yaml e workflow).
scan-container: tier-container
tier-container:
	hadolint Dockerfile
	docker build -t $(IMAGE_TAG) -f Dockerfile .
	trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed --no-progress --skip-version-check $(IMAGE_TAG)
	trivy config --exit-code 1 --severity HIGH,CRITICAL --skip-version-check --skip-dirs .venv,backend/.venv,backend/tests .
	$(RUN) pytest tests/tools/test_container.py tests/tools/test_container_web.py -m container

# --- livelli -----------------------------------------------------------------
ci:
	./scripts/ci.sh

nightly:
	$(call todo,SL-06a (nightly.yml da SL-10b),nightly)
full:
	$(call todo,la chiusura di M0 (richiede i livelli di SL-00b),full)
prerelease:
	$(call todo,SL-10b,prerelease)
