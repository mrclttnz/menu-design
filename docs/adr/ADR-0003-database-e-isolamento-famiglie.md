# ADR-0003: PostgreSQL unico con isolamento delle famiglie su due livelli (filtro centralizzato e Row-Level Security)

- **Stato:** ACCEPTED (decisione dell'utente, 2026-10-18: PostgreSQL su Supabase, RLS come seconda linea di difesa)
- **Data:** 2026-10-19, revisione 5, consolidata. Storia:
  - revisione 2: backend Python;
  - revisione 3: proposte del data-architect accettate;
  - revisione 4: azioni A-10 e A-13 del threat model;
  - revisione 5: obiezione OBJ-07 della revisione critica, accettata dall'utente il 2026-10-19:
    - quattro ruoli di login;
    - niente `menu_maint`;
    - `SECURITY DEFINER` solo dove è inevitabile;
    - RLS su `session` ma non su `account`;
  - revisione 6 (2026-10-20): tabella delle funzioni allineata a `docs/05-data.md` v5 §3.3 (I-P5).
- **Decisori:** utente, architect. Revisione del data-architect e del security-engineer.
- **Requisiti collegati:** SR-008, SR-009, SR-011, SR-012, SR-040, SR-041, SR-042, SR-055, SR-057, SR-060, NFR-002, NFR-004, FR-030, FR-032
- **ADR collegati:** ADR-0011 (console), ADR-0013 (worker), ADR-0014 (Supabase), ADR-0015 (backup), ADR-0016 (endpoint esposto)

## Contesto
Il prodotto è multi-tenant fin dal primo giorno, con dati di minori e dati che rivelano quando una casa è vuota (SR-055). SR-042 chiede un unico livello di accesso ai dati, con la RLS valutata come difesa aggiuntiva. Il modello è relazionale e richiede vincoli, transazioni e lock (FR-011, SR-060, SR-063).

L'utente chiede la soluzione più semplice che rispetti gli obblighi reali: "non stiamo parlando di un sistema che gestisce cose critiche".

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Sicurezza (impatto di un singolo errore) | 5 |
| Semplicità di sviluppo | 4 |
| Operabilità (migrazioni, backup) | 4 |
| Verificabilità automatica dell'isolamento | 3 |
| Prestazioni | 3 |
| Portabilità | 3 |
| Competenze | 3 |

## Opzioni considerate
| Criterio | A: solo filtro applicativo centralizzato | B: filtro centralizzato + RLS + FK composite | C: uno schema (o database) per famiglia |
|---|---|---|---|
| Sicurezza (5) | 3 | 5 | 4 |
| Semplicità (4) | 5 | 4 | 2 |
| Operabilità (4) | 5 | 4 | 1 |
| Verificabilità (3) | 3 | 5 | 4 |
| Prestazioni (3) | 5 | 4 | 4 |
| Portabilità (3) | 5 | 5 | 4 |
| Competenze (3) | 5 | 5 | 4 |
| **Totale pesato** | **109** | **114** | **80** |

## Decisione
**Opzione B.** Il dettaglio dello schema è in `docs/05-data.md`.

### Motore
- PostgreSQL 17 su Supabase (ADR-0014), con la stessa major in sviluppo;
- estensioni `unaccent` e `pg_trgm` nello schema `extensions`, sempre richiamate con lo schema qualificato;
- `gen_random_uuid()` per UUID v4.

### Tabelle di famiglia e RLS
- Ogni tabella di famiglia ha `family_id uuid NOT NULL`, `UNIQUE (family_id, id)`, FK composite verso le tabelle referenziate (SR-041) e indici con `family_id` in testa.
- `ENABLE` e `FORCE ROW LEVEL SECURITY`, con tre policy esplicite:
  - `p_family` per `menu_app`: `USING` e `WITH CHECK` su `family_id = app.current_family_id()`. Senza contesto non restituisce righe (fail closed);
  - `p_owner` per `menu_owner`, `USING (true)`;
  - `p_backup` per `menu_backup`, `FOR SELECT USING (true)`.
- Un controllo in CI fallisce se una tabella con `family_id` non ha RLS forzata e le tre policy.
- **Eccezioni:**
  - `change_event` ha solo `SELECT` e `INSERT` (ADR-0012);
  - `person` ha in più `p_person_self` (`account_id = app.current_account_id()`) per risolvere la membership della sessione;
  - `invite` e `family_bootstrap` sono tabelle di famiglia. La ricerca prima dell'appartenenza passa da funzioni di risoluzione strette (sotto);
  - `export_file` ha RLS per richiedente (`p_requester`, `requester_account_id = app.current_account_id()`).
- **RLS su `session`** (A-10, ridotta in OBJ-07):
  - `session` è leggibile e modificabile da `menu_app` solo per l'account del contesto;
  - la risoluzione della sessione a ogni richiesta passa da `app.session_resolve(p_token_hash) → (session_id, account_id)`;
  - **`account` resta senza RLS**: è accessibile solo dal modulo `identity` tramite `system_tx()`. Il costo di un'altra coppia di policy e funzioni non è giustificato a questa scala.

### Accesso ai dati
- `family_tx(ctx)`, nel modulo `tenancy`, è l'unico modo di toccare dati di famiglia:
  - imposta `app.family_id`, `app.account_id` e `app.role` con `set_config(…, true)`;
  - i repository aggiungono comunque `WHERE family_id = :f`.
- `family_id` viene solo dalla membership della sessione (SR-008).
- `system_tx()` serve le tabelle non di famiglia: account, flussi OIDC, codici, limiti di frequenza, job, registri, nei moduli `identity`, `ratelimit`, `jobs`, `audit` e `privacy`. L'elenco chiuso è in `docs/05-data.md` §6.3 e fa parte del test di inventario.
- Un test che analizza gli import impedisce di creare sessioni SQLAlchemy fuori da `tenancy`.

### Connessione
- Pooler Supavisor in modalità transazione;
- psycopg con `prepare_threshold=None`;
- solo `set_config(…, true)`, nessun `SET` di sessione;
- **TLS obbligatorio (A-13):** l'avvio di qualunque processo (servizio, worker, job) fallisce se un URL del database non ha `sslmode=verify-full` con il certificato della CA configurato.

### Ruoli di login: quattro (OBJ-07)
| Ruolo | Uso | Privilegi |
|---|---|---|
| `menu_owner` | Migrazioni Alembic e `maint replay-deletions` (job di migrazione, ADR-0015) | Proprietario dello schema `app`, `NOBYPASSRLS`, policy `p_owner`. Mai usato dal servizio. |
| `menu_app` | Servizio web **e worker** | DML con RLS sulle tabelle di famiglia. Sulle tabelle non di famiglia, i privilegi della matrice di `docs/05-data.md` §3.2: le pulizie che **non** attraversano famiglie né tabelle di sola aggiunta sono SQL normale in `system_tx()`, per esempio flussi OIDC scaduti, contatori dei limiti, job terminati, account non verificati (M2). Solo `INSERT` e `SELECT` su `change_event`. **Solo `INSERT`** su `security_event` e `deletion_log`. `EXECUTE` sulle funzioni di risoluzione e di manutenzione. Nessun `BYPASSRLS`, nessun DDL. |
| `menu_console` | Job della console (ADR-0011) | Solo `EXECUTE` sulle funzioni `console_*` e `SELECT` su `console_stats_global`. `CONNECTION LIMIT 2`. |
| `menu_backup` | Job di backup (ADR-0015) | `NOBYPASSRLS`, `SELECT` su tutto tramite `p_backup`, `pg_dump --enable-row-security`. `CONNECTION LIMIT 2`. |

- Ogni ruolo ha `statement_timeout` e una password casuale generata e conservata come descritto in ADR-0016 (controllo 1).
- `REVOKE CREATE ON SCHEMA public, app FROM PUBLIC`.

### Funzioni `SECURITY DEFINER`: solo dove è inevitabile
Si usano **solo** quando un'operazione deve attraversare le famiglie, o toccare una tabella di sola aggiunta, oppure quando il chiamante non ha privilegi sulle tabelle (console).
- Regole comuni:
  - proprietario `menu_owner`, `SET search_path = app, pg_temp`;
  - `EXECUTE` revocato a `PUBLIC` e concesso al solo ruolo previsto;
  - parametri solo identificativi, hash o enumerati;
  - restituiscono solo ID o esiti;
  - un test per funzione;
  - un test d'inventario confronta funzioni e grant con l'elenco atteso.
- Insieme previsto: 18 funzioni fino a M1, 21 con M2. **L'elenco autorevole, con firme e milestone, è `docs/05-data.md` §3.3**, che prevale in caso di differenza (allineamento I-P5 del 2026-10-20):

  | Gruppo | Funzioni | Ruolo |
  |---|---|---|
  | Risoluzione prima del contesto | `session_resolve`, `invite_resolve`, `bootstrap_resolve` (per `email_sha256`) | `menu_app` |
  | Operazione dell'app che la RLS per richiedente impedirebbe | `purge_family_exports` (SR-072, cambio di ruolo o uscita) | `menu_app` (servizio) |
  | Manutenzione che attraversa le famiglie o tocca tabelle di sola aggiunta | `maint_families_needing_freeze`, `maint_purge_family_notices`, `maint_security_log_retention`, `maint_purge_deletion_log`, `maint_db_size`; M2: `maint_purge_due_families` | `menu_app` (worker) |
  | Console | `console_bootstrap_family`, `console_recover_admin`, `console_enqueue_export`, `console_export_status`, `console_security_events`, `console_revoke_all_sessions`, `console_audit_note`; M2: funzioni dei codici | `menu_console` |
  | Ripristino | `maint_apply_deletion` | solo `menu_owner` |

- **Non sono `SECURITY DEFINER`** (SQL normale del worker con `menu_app`):
  - pulizia di sessioni ed esportazioni scadute, grazie alle policy `p_session_expired` e `p_export_expired`. Le funzioni `maint_purge_sessions` e `maint_purge_exports` non esistono;
  - pulizia di inviti e bootstrap nel passaggio notturno per famiglia con `family_tx`, e dei codici di M2 in `system_tx`. La funzione `maint_purge_invites_codes` non esiste;
  - controllo delle finestre orarie dei ruoli privilegiati (`maint_role_activity`): query su `pg_stat_activity`, dove `usename` e `backend_start` sono visibili a ogni ruolo.

### Supabase
- Data API disattivata, schema `app` non esposto;
- privilegi di default revocati ad `anon` e `authenticated`;
- nessun uso di Supabase Auth, Storage o SDK (ADR-0014).

### Test obbligatori (pytest su PostgreSQL 17 reale)
- `menu_app` senza contesto legge zero righe di famiglia;
- con il contesto A legge zero righe di B;
- un `INSERT` o `UPDATE` con un altro `family_id` viene rifiutato;
- le FK composite rifiutano i riferimenti incrociati;
- `session` di un altro account non è visibile;
- `menu_app` riceve "permesso negato" su `SELECT` da `security_event`, e su `UPDATE` e `DELETE` di `change_event` e `security_event`;
- `menu_console` riceve "permesso negato" sulle tabelle di famiglia;
- un dump con `menu_backup` contiene le righe di tutte le famiglie;
- l'avvio fallisce con un URL senza `verify-full`;
- inventario delle funzioni `SECURITY DEFINER` e dei grant.

## Conseguenze
- Positive: una fuga di dati tra famiglie richiede due errori indipendenti. Meno ruoli e meno funzioni privilegiate rispetto alla revisione 4.
- Negative e costi:
  - il worker usa lo stesso ruolo del servizio, quindi una credenziale di `menu_app` rubata vale anche per la manutenzione. L'impatto non cambia, perché `menu_app` legge già tutti i dati di famiglia una volta impostato il contesto (ADR-0016, controllo 4);
  - le policy vanno mantenute in ogni migrazione.
- Azioni successive: il data-architect allinea `docs/05-data.md` (ruoli, matrice, funzioni). Il security-engineer aggiorna il threat model.

## Quando rivedere
Se una funzionalità futura richiede letture tra famiglie (condivisione pubblica, ASM-010): viste pubbliche dedicate con policy esplicite, mai `BYPASSRLS` nel servizio web.
