# Menu Design

Applicazione web (PWA) per pianificare i pasti di casa in famiglia: piatti con gusti e ricette, piano dei pasti condiviso, presenze. Repository privato, in sviluppo per slice verticali (fase P5 Build).

Lo stato aggiornato (gate, slice completate, debito tecnico) è in [`docs/STATUS.md`](docs/STATUS.md).

## Stato

Completate: SL-00a (scheletro, CI), SL-00b (database locale, migrazione 0001, tenancy, container), SL-01 (shell web, i18n, client generato). Per ora non c'è ancora nessuna funzione utente (login, piatti, piano): la shell mostra navigazione e testi localizzati.

## Stack

- **Backend**: Python 3.14, FastAPI, SQLAlchemy (sincrono), Alembic, PostgreSQL 17 (TLS obbligatorio).
- **Frontend**: React 19, React Router, TanStack Query, React Aria Components, Lingui, Vite, TypeScript.
- **Test**: pytest e Hypothesis (backend), Vitest (web), Playwright e axe (e2e e accessibilità).
- **Esecuzione prevista**: Cloud Run con Supabase Free (ADR-0005).

In produzione l'app è un solo servizio: FastAPI serve anche la SPA compilata (`web/dist`).

## Prerequisiti

| Strumento | Note |
|---|---|
| [uv](https://docs.astral.sh/uv/) | gestisce l'ambiente Python; non installare pacchetti fuori da un virtualenv |
| Node ≥ 24 e pnpm | pnpm arriva da corepack, versione fissata in `web/package.json` |
| Docker con Compose | solo per il database locale |
| gitleaks, semgrep, trivy, osv-scanner | solo per `make scan` e `make ci` (versioni in `Makefile` e `docs/08-test-strategy.md` §19) |

## Provare l'applicazione

```bash
make run-web        # http://127.0.0.1:8000/
make run-web WEB_PORT=8080
```

Builda la SPA (con controllo del budget del bundle) e la serve con FastAPI. Usa un database fittizio: la shell non lo tocca, ma le route che leggono dati falliscono. Non c'è un server di sviluppo Vite: dopo ogni modifica al frontend rilancia il comando.

### Con il database locale

```bash
make dev            # PostgreSQL 17 con TLS (compose.yaml); certificati e password in db/dev-certs/
make db-down        # ferma il database
make db-reset       # ferma e cancella il volume dei dati locali
```

La porta host è `5432`; per cambiarla usa `MENU_PG_HOST_PORT=...`. Per avviare il server contro questo database copia `.env.example` in `.env` e compila `DATABASE_URL_APP` (e `DATABASE_URL_OWNER` per le migrazioni) con `sslmode=verify-full` e `sslrootcert=db/dev-certs/ca.crt`. Non mettere mai valori reali in `.env.example`.

Per l'accesso con Google (da SL-03a) servono anche `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `APP_BASE_URL` (origine pubblica, senza percorso; l'URI di reindirizzamento da registrare nel client OAuth è `APP_BASE_URL/api/v1/auth/google/callback`); `OIDC_ISSUER` vale Google e in `staging` e `production` non può essere altro. In `dev` e `test` le prime due sono facoltative (i test usano un provider finto). `make e2e` usa lo stesso cluster di `make test-db`.

Per avviare il backend a mano:

```bash
cd backend
uv run --frozen python -m menu serve --host 127.0.0.1 --port 8000
```

`WEB_DIST_DIR` indica la cartella della SPA (`web/dist`); se è vuota il server espone solo le API.

## Comandi principali

`make help` elenca i target. Il `Makefile` è l'unico punto di verità: la CI esegue gli stessi comandi.

| Comando | Cosa fa |
|---|---|
| `make sync` | installa le dipendenze Python dal lockfile |
| `make lint` | ruff, mypy, bandit; eslint, prettier, tsc, controlli i18n |
| `make test` | unit backend, unit web, test database, contratto |
| `make test-web` | Vitest con copertura e controllo del client generato |
| `make web-build` | compila la SPA in `web/dist` |
| `make e2e` | Playwright su Chromium (360 px e desktop) con axe |
| `make scan` | segreti, SAST, dipendenze, workflow, pnpm audit |
| `make openapi` | riesporta `openapi.json` (da cui si genera il client web) |
| `make ci` | tutti i livelli abilitati, come la pipeline |

Per vedere gli e2e nel browser: `cd web && pnpm exec playwright test --headed` (la prima volta: `pnpm exec playwright install chromium`).

## Struttura

| Percorso | Contenuto |
|---|---|
| `backend/` | pacchetto `menu` (FastAPI), migrazioni Alembic, test |
| `web/` | SPA React/Vite, cataloghi i18n, test unit ed e2e |
| `db/` | bootstrap SQL e certificati di sviluppo (generati, non versionati) |
| `scripts/` | CI, certificati di sviluppo, controlli delle regole |
| `docs/` | visione, requisiti, UX, architettura, ADR, dati, minacce, piano, strategia di test, revisioni |
| `openapi.json` | contratto API, sorgente del client TypeScript |

## Documentazione

Ordine di lettura consigliato: [visione](docs/01-vision.md), [requisiti](docs/02-requirements.md), [UX](docs/03-ux.md), [architettura](docs/04-architecture.md) e [ADR](docs/adr/), [dati](docs/05-data.md), [modello delle minacce](docs/06-threat-model.md), [piano](docs/07-plan.md), [strategia di test](docs/08-test-strategy.md).

## Sicurezza

Le scansioni (segreti, SAST, dipendenze, container) sono bloccanti in CI. Prima del primo push va eseguito gitleaks sull'intera storia. Il push verso `origin` avviene a ogni punto significativo (fine slice, fine fase o gate) senza ulteriore consenso, come autorizzato dal proprietario.
