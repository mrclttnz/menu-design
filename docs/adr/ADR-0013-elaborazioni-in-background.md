# ADR-0013: Elaborazioni in background con coda in PostgreSQL e worker eseguito a intervalli

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-19
  - revisione 2: backend Python;
  - revisione 3: perimetro delle esportazioni e rilevazione degli accessi, dal threat model;
  - revisione 4: OBJ-07 e OBJ-08 (worker con `menu_app`, rilevazione semplificata, niente riconciliazione).
- **Decisori:** architect. Revisione di devops.
- **Requisiti collegati:** FR-016, FR-063, FR-065, SR-016, SR-017, SR-018, SR-019, SR-035, SR-048, SR-049, SR-050, SR-051, SR-057, SR-059, SR-062, NFR-014

## Contesto
Servono elaborazioni fuori dalle richieste:
- esportazioni (FR-065) e loro cancellazione dopo 24 ore;
- congelamento notturno (ADR-0007);
- cancellazione definitiva delle famiglie (M2);
- pulizie (flussi OIDC, sessioni, inviti, codici, contatori dei limiti, account non verificati);
- conservazione del registro di sicurezza e troncamento degli IP;
- controllo dello spazio del database;
- gestione dell'inattività (apertura al pubblico).

Sulle piattaforme serverless (ADR-0005) la CPU non è garantita tra una richiesta e l'altra e le istanze si fermano. Il worker gira quindi come job schedulato che termina.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Affidabilità (i compiti avvengono, una sola volta) | 5 |
| Semplicità | 4 |
| Costo | 4 |
| Portabilità | 3 |

## Opzioni considerate
| Criterio | A: tabella `job` + `worker --once` schedulato (codice proprio) | B: procrastinate 3.10 con `run_worker(wait=False)` | C: Celery o RQ | D: APScheduler nel processo web |
|---|---|---|---|---|
| Affidabilità (5) | 4 | 5 | 5 | 1 |
| Semplicità (4) | 4 | 3 | 2 | 5 |
| Costo (4) | 5 | 5 | 2 | 5 |
| Portabilità (3) | 5 | 4 | 4 | 4 |
| **Totale pesato** | **71** | **69** | **53** | **57** |

- **B, procrastinate 3.10.0** (2026-09-23, MIT):
  - coda su PostgreSQL matura, con tentativi e lock;
  - il parametro `wait=False` fa terminare il worker quando la coda è vuota, quindi è compatibile con un job schedulato;
  - ma porta un proprio schema e le proprie migrazioni, da integrare con Alembic e con i privilegi per ruolo (ADR-0003);
  - i compiti periodici scaduti da più di `max_delay` (10 minuti per default) vengono saltati, quindi andrebbe configurato con attenzione;
  - è l'alternativa più vicina.
- **C:** richiede un broker (Redis o RabbitMQ) sempre attivo.
- **D:** non affidabile con lo scale-to-zero e con più istanze.

## Decisione
**Opzione A.** Il codice è piccolo e trasparente rispetto a ruoli e RLS. procrastinate resta il ripiego se la coda cresce in complessità.

- **Coda:**
  - tabella `job` con `id`, `type`, `payload` (solo ID), `run_after`, `status`, `attempts`, `locked_until` e `last_error` (codice, non contenuti);
  - prelievo con `SELECT … FOR UPDATE SKIP LOCKED`;
  - massimo 5 tentativi con backoff, poi `failed` più un log d'errore, che fa scattare l'allarme di NFR-007.
- **Worker:**
  - comando `python -m menu worker --once --max-seconds 240`, stessa immagine del servizio;
  - avviato ogni 10 minuti dallo scheduler della piattaforma (ADR-0005);
  - elabora i job scaduti e i compiti periodici dovuti, poi termina;
  - due esecuzioni sovrapposte sono innocue grazie a `SKIP LOCKED` e a un advisory lock (`pg_try_advisory_xact_lock`) per ogni compito periodico.
- **Compiti periodici:**
  - registro nel codice con nome, frequenza e funzione;
  - tabella `periodic_task_run` con l'ultima esecuzione;
  - un compito in ritardo viene eseguito alla prima occasione, non saltato;
  - ogni compito è idempotente.

  | Compito | Frequenza |
  |---|---|
  | Congelamento delle famiglie con `frozen_through` < ieri | Ogni esecuzione |
  | Esportazioni scadute (24 ore) | Ogni esecuzione |
  | Flussi OIDC e stati temporanei (SR-049) | Ogni ora |
  | Contatori dei limiti | Ogni ora |
  | Sessioni scadute | Ogni giorno |
  | Inviti e codici scaduti o usati da più di 30 giorni | Ogni giorno |
  | Troncamento degli IP oltre 90 giorni e registro oltre 12 mesi | Ogni giorno |
  | Spazio del database (metrica nei log, allarme al 70%) | Ogni giorno |
  | Cancellazione definitiva delle famiglie | Ogni ora (M2) |
  | Account non verificati da più di 7 giorni | Ogni giorno (M2) |
  | Inattività di 24 mesi | Ogni giorno (apertura al pubblico) |

- **Privilegi:**
  - il worker usa **solo `menu_app`** (OBJ-07: il ruolo `menu_maint` non esiste più, ADR-0003);
  - i compiti per famiglia usano `family_tx`;
  - le pulizie di tabelle non di famiglia senza vincoli di sola aggiunta (flussi OIDC, contatori dei limiti, job terminati, account non verificati) sono SQL normale in `system_tx()`;
  - solo le operazioni che attraversano le famiglie o toccano tabelle di sola aggiunta passano dalle funzioni `maint_*` `SECURITY DEFINER` elencate in ADR-0003, eseguibili da `menu_app`.
- **Esportazioni:**
  - JSON più CSV compresso in ZIP, generato con la libreria standard (`json`, `csv`, `zipfile`), con neutralizzazione delle formule;
  - salvato nella tabella `export_file` con scadenza a 24 ore;
  - il perimetro del richiedente si ricontrolla all'esecuzione (SR-067).
- **Perimetro delle esportazioni (A-09, A-17, SR-072; THR-060, THR-063, THR-064, THR-112):**
  - **il worker ricava la famiglia dalla membership attuale del richiedente** e ignora qualunque `family_id` nel payload del job. Il payload contiene solo `requester_account_id`, `scope` e `request_ref`;
  - per `scope='family'` il job si esegue solo se il richiedente è **ancora Amministratore**. Altrimenti termina con `last_error_code='not_admin'` (AC-044.4);
  - **il download** di un file `family` ricontrolla che il richiedente sia ancora Amministratore di quella famiglia. Altrimenti risponde `404`. Da M2 richiede la riautenticazione (SR-039);
  - i file `family` di un account **si cancellano** quando perde il ruolo di Amministratore, esce o viene rimosso. La cancellazione avviene nella stessa transazione del cambio di ruolo o dell'uscita;
  - **contenuto dell'esportazione `family`:** i contenuti della famiglia e i nomi visualizzati. **Non** contiene email, ultima visita, ordinamento preferito, sessioni o IP degli altri account;
  - **contenuto dell'esportazione `self`:** i dati del proprio account e le righe della propria persona;
  - test per ciascuna regola.
- **Rilevazione degli accessi al database (SR-075, ADR-0016 controllo 9):**
  - compito periodico `maint_role_activity` a ogni esecuzione, cioè ogni 10 minuti. **Non è una funzione `SECURITY DEFINER`**: è SQL normale di `menu_app` su `pg_stat_activity` (`usename`, `backend_start`, visibili a ogni ruolo; `docs/05-data.md` §3.4, allineamento del 2026-10-20);
  - controlla **solo le finestre orarie** dei ruoli `menu_owner` (deploy), `menu_backup` (backup notturno) e `menu_console` (comandi). Se uno risulta connesso fuori dalla sua finestra, scrive un evento nei log e fa scattare l'allarme (OBJ-08);
  - nessun conteggio per indirizzo né altre analisi;
  - è subordinato alla verifica V-4.
- **Cancellazioni:** registro nel database più l'evento `deletion.executed` instradato fuori dal database. Nessuna riconciliazione giornaliera (OBJ-08): dopo un ripristino la fusione tra i due registri è un passo del runbook (ADR-0015).
- **Portabilità:** lo stesso comando si può avviare da qualunque cron.

## Conseguenze
- Positive: nessun processo sempre acceso, nessun servizio in più, costo vicino a zero.
- Negative e costi:
  - latenza fino a 10 minuti per le esportazioni (accettabile);
  - un avvio a freddo di Python a ogni esecuzione (pochi secondi);
  - codice della coda da testare.
- Azioni successive: il devops configura scheduler e allarmi sui job falliti. Il data-architect definisce le tabelle.

## Quando rivedere
Se servono latenze sotto il minuto o molti tipi di job: procrastinate con un worker sempre attivo.
