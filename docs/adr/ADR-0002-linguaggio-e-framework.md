# ADR-0002: Backend in Python (FastAPI, SQLAlchemy, Alembic) e frontend in TypeScript (React)

- **Stato:** ACCEPTED (decisione dell'utente, 2026-10-18: opzione B)
- **Data:** 2026-10-18 (revisione 2). Revisione 3 del 2026-10-19: argon2-cffi e Pwned Passwords fuori dall'MVP (CHG-020).
- **Decisori:** utente, architect
- **Requisiti collegati:** NFR-002, NFR-008, NFR-011, NFR-014, NFR-015, SR-009, SR-010, SR-024, SR-042, vincolo "sviluppatore singolo, poche dipendenze consolidate"

## Contesto
L'utente conosce Python, TypeScript e JavaScript, SQL e PostgreSQL. Il frontend è comunque TypeScript (ADR-0001). Per il backend servono:
- generazione di OpenAPI dagli schemi;
- validazione rigorosa con liste esplicite di campi;
- una libreria OIDC matura;
- migrazioni reversibili;
- transazioni con `set_config` per la RLS (ADR-0003).

La prima versione di questo ADR raccomandava TypeScript su tutto lo stack (138 contro 137). L'utente ha scelto Python per il backend.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Aderenza ai requisiti (OpenAPI, validazione, i18n, RLS) | 5 |
| Sicurezza (maturità delle librerie di auth e validazione) | 5 |
| Semplicità per uno sviluppatore singolo | 5 |
| Competenze dell'utente | 4 |
| Maturità ed ecosistema | 4 |
| Operabilità | 3 |
| Costo totale | 2 |
| Lock-in | 2 |

## Opzioni considerate
| Criterio | A: TypeScript (Fastify + Kysely + React) | B: Python (FastAPI + SQLAlchemy/Alembic) + React | C: meta-framework TS (Next.js / SvelteKit) |
|---|---|---|---|
| Requisiti (5) | 5 | 5 | 3 |
| Sicurezza (5) | 4 | 5 | 4 |
| Semplicità (5) | 5 | 3 | 4 |
| Competenze (4) | 5 | 5 | 4 |
| Maturità (4) | 4 | 5 | 4 |
| Operabilità (3) | 4 | 4 | 3 |
| Costo (2) | 5 | 5 | 5 |
| Lock-in (2) | 5 | 5 | 3 |
| **Totale pesato** | **138** | **137** | **112** |

### Opzione B (scelta)
- Pro:
  - OpenAPI 3.1 nativa in FastAPI, generata dai modelli Pydantic;
  - SQLAlchemy e Alembic molto maturi, con migrazioni `upgrade` e `downgrade`;
  - Authlib solido, e argon2-cffi disponibile se il login con password verrà ripreso (CHG-020);
  - ottimo supporto ai test di proprietà (Hypothesis), utili per ADR-0007.
- Contro:
  - due linguaggi e due catene di dipendenze da scansionare (`pip-audit` e `pnpm audit`, `osv-scanner` per entrambe);
  - gli schemi non sono condivisi con il client: il contratto è il file `openapi.json`, da cui si generano i tipi TypeScript.
- Rischi:
  - `httpx` è stabile alla 0.28.1 (dicembre 2024), con la 1.0 in sviluppo attivo (1.0.dev6, agosto 2026). È usato solo per le chiamate HTTP in uscita e si può sostituire con `requests`;
  - `psycopg` ha licenza LGPL-3.0. È compatibile con l'uso come libreria non modificata in un servizio non distribuito.

## Decisione
**Opzione B.**

### Backend
| Ruolo | Scelta | Versione (PyPI, verificata il 2026-10-18) | Licenza |
|---|---|---|---|
| Runtime | CPython 3.14 (bugfix fino al 2030). La 3.15 è uscita il 2026-10-09: da adottare quando le dipendenze la supportano. | 3.14.x | PSF |
| Framework HTTP | FastAPI | 0.146.0 (2026-10-18) | MIT |
| Server ASGI | uvicorn | 0.54.0 (2026-09-25) | BSD-3-Clause |
| Modelli e validazione | Pydantic v2 | 2.14.1 (2026-10-11) | MIT |
| Configurazione | pydantic-settings | 2.16.0 (2026-10-14) | MIT |
| Accesso ai dati | SQLAlchemy 2.1, Core per le query e ORM leggero dove utile | 2.1.5 (2026-10-16) | MIT |
| Migrazioni | Alembic, con `upgrade` e `downgrade` obbligatori | 1.20.0 (2026-09-11) | MIT |
| Driver PostgreSQL | psycopg 3 | 3.3.6 (2026-09-18) | LGPL-3.0 |
| Log strutturati | structlog | 26.1.0 (2026-06-06) | MIT o Apache-2.0 |
| HTTP in uscita (OIDC; ~~Pwned Passwords~~ *rinviato, CHG-020*) | httpx | 0.28.1 (2024-12-06) | BSD-3-Clause |
| OIDC (~~e password~~ *rinviato, CHG-020*) | Vedi ADR-0004 (Authlib 1.9.1, joserfc 1.7.5). argon2-cffi 25.1.0 **non entra nell'MVP**: si aggiunge solo se il login con password (FR-002) viene ripreso dal backlog | | |
| CLI della console | `argparse` della libreria standard | | |

### Scelte di stile
- **Sincrono:**
  - rotte FastAPI `def`, eseguite nel thread pool, con SQLAlchemy sincrono e psycopg;
  - è più semplice da ragionare (transazioni, `set_config`, lock) ed è sufficiente per 25 utenti concorrenti (NFR-002);
  - si passa all'asincrono solo se le misure lo richiedono.
- **Modelli Pydantic:**
  - le richieste usano `ConfigDict(extra='forbid')`, così un campo sconosciuto produce `422` (SR-010);
  - modelli di scrittura distinti per ruolo dove servono (per esempio la creazione di un piatto da parte di un Membro non ha il campo `status`);
  - `response_model` esplicito: nessun campo interno nelle risposte.
- **OpenAPI:**
  - generata da FastAPI (3.1);
  - un tipo di rotta personalizzato (`AuthzRoute`) **impedisce l'avvio** dell'app se una rotta non dichiara `authz`, ed espone la dichiarazione come `x-authz` nella specifica (SR-042);
  - `openapi.json` è esportato da uno script e committato. Un controllo in CI fallisce se differisce da quello generato.
- **Middleware propri, piccoli e testati:**
  - limite del corpo (64 KB, 1 MB per l'import);
  - controllo della profondità JSON (≤ 10) prima del parsing;
  - header di sicurezza (CSP, HSTS, `nosniff`, `Referrer-Policy`, `frame-ancestors`);
  - `Cache-Control: no-store` sulle risposte autenticate;
  - ID di correlazione.
  - Le librerie terze per queste funzioni sono poco mantenute o superflue.
- **Strumenti:**

  | Strumento | Versione |
  |---|---|
  | uv (dipendenze e `uv.lock` committato) | 0.13.1 |
  | ruff (lint e formattazione) | 0.17.1 |
  | mypy, in modalità `strict` | 2.4.0 |
  | pytest | 9.1.1 |
  | Hypothesis | 6.170.1 |
  | bandit | 1.9.4 |
  | pip-audit | 2.10.1 |

### Frontend (invariato)
- React 19, React Router 8, TanStack Query 5, React Aria Components, Vite 8, `vite-plugin-pwa`, Lingui 6 (ADR-0010).
- Client tipizzato generato da `openapi.json` con `openapi-typescript` e `openapi-fetch`.
- La validazione nei moduli è un aiuto all'utente, scritta a mano con i limiti della specifica. L'autorità resta il server.
- Package manager pnpm.

### Immagine
- `python:3.14-slim`, multi-stage, utente non root, file system di sola lettura.
- L'immagine di backup contiene il client `pg_dump` della stessa major del server (ADR-0015).

## Conseguenze
- Positive: OpenAPI e validazione di prima classe, migrazioni robuste, librerie di sicurezza mature.
- Negative e costi:
  - due toolchain;
  - il contratto passa da un artefatto generato, quindi serve il controllo in CI di `openapi.json` e dei tipi generati;
  - l'avvio a freddo di Python (2-4 s stimati) è più lento di Node, mitigato dai controlli ogni 5 minuti.
- Azioni successive:
  - il tech-lead imposta il monorepo (`backend/` con uv, `web/` con pnpm, `openapi.json` alla radice) e la CI con entrambe le toolchain;
  - il security-engineer verifica CVE e licenze all'installazione.

## Quando rivedere
- Se `httpx` resta senza rilasci stabili mentre emergono CVE: passare a `requests`.
- Se il carico misurato richiede I/O asincrono.
