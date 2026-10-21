# Menu Design: unico punto di verità per lint, test, scansioni e CI (piano §6.1).
# I target senza contenuto falliscono con un messaggio esplicito (mai "verdi a vuoto").
SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

UV      ?= uv
BACKEND := backend
RUN     := cd $(BACKEND) && $(UV) run --frozen

# Strumenti di scansione installati fuori dal lockfile (SR-076): versione fissata
# e cooldown di 7 giorni anche sulle dipendenze transitive. Stesse versioni in CI.
SEMGREP_VERSION := 1.180.0
ZIZMOR_VERSION  := 1.30.1
TOOL_COOLDOWN   := 7 days

# Segnaposto: $(call todo,<slice>,<target>)
define todo
	@echo "ERRORE: 'make $(2)' non è ancora disponibile: disponibile da $(1)." >&2; exit 2
endef

.PHONY: help sync dev lint lint-py lint-web test test-unit test-db test-int test-sec test-prop \
        test-conc test-contract e2e lighthouse perf smoke dast scan scan-secrets scan-sast \
        scan-deps scan-workflows scan-web scan-container scan-rules tools-semgrep tools-zizmor ci nightly full prerelease openapi seed

help:
	@echo "Target: sync dev lint test test-unit test-contract scan ci (attivi)"
	@echo "        test-db test-int test-sec test-prop test-conc e2e lighthouse perf smoke dast"
	@echo "        nightly full prerelease openapi seed (segnaposto: 'disponibile da SL-xx')"

sync:
	cd $(BACKEND) && $(UV) sync --frozen

dev:
	$(call todo,SL-00b,dev)

# --- lint -----------------------------------------------------------------
lint: lint-py

lint-py: sync
	cd $(BACKEND) && $(UV) lock --check
	$(RUN) ruff check .
	$(RUN) ruff format --check .
	$(RUN) mypy
	$(RUN) bandit -q -c pyproject.toml -r src

lint-web:
	$(call todo,SL-01,lint-web)

# --- test -----------------------------------------------------------------
test: test-unit test-db test-int test-sec test-prop test-conc test-contract

test-unit: sync
	$(RUN) pytest tests/unit tests/architecture tests/tools --cov=menu --cov-report=term-missing:skip-covered

test-contract: sync
	$(RUN) pytest tests/contract

test-db:
	$(call todo,SL-00b,test-db)
test-int:
	$(call todo,SL-00b,test-int)
test-sec:
	$(call todo,SL-00b,test-sec)
test-prop:
	$(call todo,SL-00b,test-prop)
test-conc:
	$(call todo,SL-00b,test-conc)

e2e:
	$(call todo,SL-01,e2e)
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
# Attive in SL-00a: segreti, SAST, dipendenze Python, workflow.
# scan-web (pnpm audit) da SL-01; scan-container (hadolint, trivy) da SL-00b.
scan: scan-secrets scan-sast scan-deps scan-workflows

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
	  --config .semgrep backend $$( [ -d web ] && echo web )

scan-deps: sync
	cd $(BACKEND) && $(UV) export --frozen --no-emit-project --format requirements-txt \
	  -o .pip-audit-requirements.txt >/dev/null; \
	$(UV) run --frozen pip-audit -r .pip-audit-requirements.txt --no-deps --disable-pip \
	  --progress-spinner off; rc=$$?; rm -f .pip-audit-requirements.txt; exit $$rc
	osv-scanner scan source --lockfile $(BACKEND)/uv.lock

scan-workflows:
	zizmor --no-progress .github/workflows

scan-web:
	$(call todo,SL-01,scan-web)
scan-container:
	$(call todo,SL-00b,scan-container)

# --- livelli -----------------------------------------------------------------
ci:
	./scripts/ci.sh

nightly:
	$(call todo,SL-06a (nightly.yml da SL-10b),nightly)
full:
	$(call todo,la chiusura di M0 (richiede i livelli di SL-00b),full)
prerelease:
	$(call todo,SL-10b,prerelease)
