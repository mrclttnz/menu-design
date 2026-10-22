# ADR-0011: Console del Gestore come job Cloud Run avviato dal PC, con ruolo di database limitato a funzioni dedicate

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-19, revisione 4
  - revisione 2: CLI Python;
  - revisione 3: esecuzione come job cloud, dal threat model;
  - revisione 4: obiezioni della revisione critica OBJ-01, OBJ-02 e OBJ-06, con le decisioni dell'utente del 2026-10-19. Il principio guida dell'utente è "non stiamo parlando di un sistema che gestisce cose critiche, facciamoci meno paranoie".
- **Decisori:** utente, architect. Revisione del security-engineer.
- **Requisiti collegati:** FR-005, FR-007, FR-064, FR-065, SR-012, SR-020, SR-021, SR-040, SR-053, SR-055, SR-057, SR-058, SR-063, SR-066, SR-067, SR-074, ASM-045, ASM-057
- **ADR collegati:** ADR-0003 (ruoli), ADR-0005 (job), ADR-0015 (ripristino), ADR-0016 (endpoint e restrizioni di rete)

## Contesto
Il Gestore agisce solo da console, senza interfaccia di amministrazione e senza leggere i contenuti delle famiglie (SR-012, SR-040). Il segreto di un codice di creazione deve arrivare al Gestore senza finire nei log (SR-021). Il PC del Gestore non deve conservare credenziali del database (SR-074). Con le restrizioni di rete (ADR-0016) il PC, che ha un IP variabile, non potrebbe collegarsi al database.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Minimo privilegio (SR-040, SR-066, SR-067, SR-074) | 5 |
| Nessun segreto o dato personale in chiaro nei log | 4 |
| Tracciabilità | 4 |
| Semplicità | 4 |
| Compatibilità con le restrizioni di rete del database | 3 |
| Portabilità | 2 |

## Opzioni considerate
| Criterio | A: CLI locale connessa al database | B: job Cloud Run `menu-console` avviato dal PC | C: endpoint HTTP di amministrazione protetti da IAM | D: SQL manuale dalla console del provider |
|---|---|---|---|---|
| Minimo privilegio (5) | 4 | 5 | 3 | 1 |
| Niente segreti nei log (4) | 5 | 5 | 4 | 4 |
| Tracciabilità (4) | 4 | 5 | 4 | 2 |
| Semplicità (4) | 4 | 3 | 2 | 5 |
| Restrizioni di rete (3) | 1 | 5 | 5 | 4 |
| Portabilità (2) | 5 | 3 | 3 | 4 |
| **Totale pesato** | **85** | **98** | **76** | **69** |

## Decisione
**Opzione B.**

### Esecuzione
- **Job:** Cloud Run Job `menu-console` in europe-west3, stessa immagine del backend, comando `python -m menu console <comando> …`.
- **Script locale** (`uv run python -m menu.console_client`; nessuno script wrapper; la lettura dei log del job arriva in SL-10b, vedi piano §4.4), che:
  - **chiede le email solo con un prompt interattivo** (`getpass`, senza eco), mai come argomento della riga di comando, così non finiscono nella cronologia della shell;
  - **calcola in locale** gli hash:
    - per le email, con la normalizzazione esatta descritta in "Hash dell'email" qui sotto;
    - per i codici di creazione, lo SHA-256 del segreto;
  - valida `request_ref` con l'espressione regolare qui sotto prima di inviarlo;
  - esegue `gcloud run jobs execute menu-console --region=europe-west3 --wait --args=<comando>,…`;
  - mostra a terminale l'esito letto dai log del job.
- **Argomenti del job** (OBJ-02): **mai un'email in chiaro**. Solo:
  - hash SHA-256 delle email;
  - identificativi;
  - `request_ref`;
  - hash dei codici.
  - L'hash di un'email è uno pseudonimo, non un'anonimizzazione: chi conosce l'email può ricalcolarlo. È accettabile, perché lo vedono solo l'account del Gestore e i log del progetto.
- **Identità:**
  - l'account Google del Gestore (MFA resistente al phishing, SR-074) ha soltanto il permesso di eseguire **quel** job e leggerne i log;
  - il job gira con un account di servizio dedicato, con `secretAccessor` sul solo segreto `menu-console-db-url`.
- **Rete:** il job esce dalla piattaforma (con l'IP statico, se attivato, ADR-0016). Il PC non si collega mai al database di produzione.
- **Codici di creazione:** lo script genera il segreto (256 bit da `secrets`), passa al job solo l'hash e stampa il segreto una sola volta a terminale. Il segreto non entra mai nel cloud.
- **Output del job** (log UE, 30 giorni): solo identificativi, codici di esito e ID di correlazione. Mai email, nomi o contenuti. `security-log` restituisce gli IP troncati.
- **Verifica di devops (OBJ-02):**
  - accertare che cosa conservano le esecuzioni dei job Cloud Run (argomenti visibili nei dettagli dell'esecuzione) e gli audit log, e per quanto tempo;
  - impostare la conservazione delle esecuzioni al minimo utile;
  - annotare l'esito in `docs/09-release.md`;
  - gli argomenti contengono comunque solo hash e codici.

### Hash dell'email (I-03 del threat model v2)
- **Una sola funzione Python**, `menu.common.email_sha256(email: str) -> bytes`, usata sia dallo script locale sia dal servizio:
  `hashlib.sha256(email.strip().lower().encode("utf-8")).digest()`;
  - `strip()` toglie gli spazi bianchi iniziali e finali;
  - `lower()` porta in minuscolo;
  - codifica UTF-8;
  - SHA-256.
- **Negli argomenti del job:** l'hash viaggia come esadecimale **minuscolo** di 64 caratteri, validato con `^[0-9a-f]{64}$`. La funzione SQL lo riceve come `bytea` (`decode(p, 'hex')`).
- **Lato database non si normalizza nulla:**
  - il servizio scrive `account.email_sha256` con la stessa funzione Python, alla creazione dell'account e a ogni login in cui l'email verificata cambia;
  - `console_bootstrap_family` salva l'hash ricevuto in `family_bootstrap.email_sha256`;
  - le funzioni confrontano solo valori `bytea` (`account.email_sha256 = p_email_sha256`).
  - Così l'hash è identico per costruzione, senza differenze tra `lower()` e `btrim()` di PostgreSQL e quelli di Python.
- Nessun hash con chiave (HMAC): l'utente preferisce la semplicità. L'hash resta uno pseudonimo.
- Un test confronta la funzione dello script con quella del servizio su un insieme di email di esempio (maiuscole, spazi, caratteri non ASCII).

### ID di correlazione
Le funzioni `console_*` non hanno un parametro di correlazione. Il job imposta `set_config('app.correlation_id', …, true)` nella transazione, come in `docs/05-data.md`, e le funzioni lo leggono per gli eventi di sicurezza.

### Privilegi
`menu_console` (uno dei 4 ruoli di login, ADR-0003) non ha privilegi su tabelle di famiglia. Ha:
- `EXECUTE` sulle sole funzioni `console_*` (`SECURITY DEFINER`, proprietario `menu_owner`, `search_path` fisso, `EXECUTE` revocato a `PUBLIC`);
- `SELECT` sulla vista `console_stats_global`;
- `CONNECTION LIMIT 2`.

### Formato di `request_ref`
- Espressione regolare stretta `^[A-Z]{2,5}-[0-9]{8}-[0-9]{1,3}$`, per esempio `REC-20261019-1` o `EXP-20261102-3`;
- validata dallo script e dalla funzione;
- non contiene dati personali;
- il Gestore annota nel runbook la corrispondenza tra codice e richiesta ricevuta.

### Recupero dell'Amministratore (decisione dell'utente, OBJ-01): `console_recover_admin`
Lo scopo è **aggiungere un Amministratore** quando una famiglia non ne ha uno raggiungibile, o chiede aiuto.
- **Procedura:**
  1. il membro scrive al contatto privacy **dall'email del proprio account**;
  2. il Gestore controlla il mittente ed esegue `admin recover --request-ref <ref>`. Lo script **chiede l'email con un prompt interattivo**, senza eco nel terminale;
  3. lo script invia al job solo l'hash calcolato con `menu.common.email_sha256` e `request_ref`.
- **Funzione:** `console_recover_admin(p_email_sha256 bytea, p_request_ref text) → text`, in un'unica transazione:
  1. valida `request_ref`;
  2. trova l'account con `account.email_sha256 = p_email_sha256` (vedi "Hash dell'email");
  3. **ricava la famiglia dall'unica persona attiva dell'account** (ASM-050: una sola famiglia per account nell'MVP). Il Gestore non indica la famiglia;
  4. se la persona è già `admin`, l'esito è `already_admin`, senza modifiche;
  5. altrimenti imposta `role='admin'` e invalida le sessioni dell'account (SR-066);
  6. scrive l'evento di modifica (`actor_kind='platform_operator'`, `unit_type='membership'`, `op='role_change'`);
  7. crea l'avviso per tutta la famiglia in `family_notice` (`kind='admin_recovered'`, `subject_person_id`, scadenza a 30 giorni). L'app mostra "{nome} è diventato Amministratore tramite il supporto" (chiave `notice.adminRecovered`, nome risolto in lettura);
  8. scrive l'evento di sicurezza `console.admin_recover`, con allarme al Gestore (SR-058).
- **Ogni esito** (`promoted`, `not_eligible`, `already_admin`, `invalid_request_ref`) produce un evento di sicurezza `console.admin_recover` con `outcome`, `request_ref`, `correlation_id` e, se noti, gli ID dell'account e della famiglia (I-01 del threat model v2). **Mai l'email né il suo hash.** Per gli esiti negativi l'evento si scrive in una transazione separata, così resta anche se la promozione non avviene.
- **Nessuna** soglia di inattività, nessun controllo "Amministratore utilizzabile", nessun limite per famiglia. Il controllo umano è la verifica del mittente; la trasparenza è l'avviso a tutta la famiglia e la cronologia.
- **Esiti:** `promoted`, `not_eligible` (account inesistente o senza famiglia attiva: un esito unico che non rivela altro), `already_admin`, `invalid_request_ref`.
- Il nome `console_recover_admin` è **l'unico** usato in tutti i documenti. Sostituisce `console_promote_admin`.

### Avvisi alla famiglia (OBJ-06)
- **Lettura:** `GET /api/v1/session` restituisce `notices[]`, cioè gli avvisi attivi della famiglia non ancora chiusi da questo account (`id`, `kind`, `subjectPersonId`, `createdAt`).
- **Chiusura:** `POST /api/v1/notices/{id}/dismiss` chiude l'avviso **per l'account corrente**. La chiusura si salva sul server (tabella di famiglia del data-architect), quindi vale su tutti i dispositivi. Risposta `204`, idempotente.
- Un avviso scade comunque dopo 30 giorni.

### Comandi
| Comando | Funzione | Mx | Argomenti del job | Cosa restituisce |
|---|---|---|---|---|
| `family bootstrap --name` (email chiesta con il prompt) | `console_bootstrap_family(p_name, p_email_sha256)` | M0 | nome della famiglia, hash dell'email | ID della famiglia. Il bootstrap conserva **solo `email_sha256`**. Al primo login il server confronta l'hash dell'email verificata di Google (ADR-0004). |
| `codes issue` / `list` / `revoke <id>` | `console_issue_code(p_code_hash)` e affini | M2 | hash del codice, ID | ID e stati. Limite di 20 codici attivi (SR-063). |
| `admin recover --request-ref` (email chiesta con il prompt) | `console_recover_admin` | M1 | hash dell'email, `request_ref` | Esito, vedi sopra. |
| `export enqueue --scope self\|family --request-ref` (email chiesta con il prompt) / `export status <job>` | `console_enqueue_export(p_email_sha256, p_scope, p_request_ref)`, `console_export_status` | M1 | hash dell'email, ambito, `request_ref` | `job_id`, oppure l'esito unico `not_eligible`. Il worker ricontrolla il perimetro (ADR-0013). |
| `stats` | vista `console_stats_global` | M1 | nessuno | Conteggi globali (sotto 5 mostrati come `<5`). |
| `security-log --since` | `console_security_events` | M0 | istante | Eventi con IP troncati. |
| `sessions revoke-all --reason` | `console_revoke_all_sessions` | M1 | motivo codificato | Numero di sessioni revocate (SR-053). |
| `audit note --ref` | `console_audit_note` | M0 | `request_ref` | Annota un accesso diretto al database (ASM-045). |

### Test (pytest)
- un test per ogni funzione e per ogni esito;
- l'esito per "account inesistente" e per "account senza famiglia attiva" deve essere identico;
- creazione dell'avviso e sua chiusura per account;
- "permesso negato" di `menu_console` sulle tabelle di famiglia;
- l'output e gli argomenti del job non contengono email in chiaro.

## Conseguenze
- Positive:
  - nessuna credenziale del database e nessun dato personale in chiaro passano per il PC o per gli argomenti del job;
  - compatibile con le restrizioni di rete;
  - recupero semplice e trasparente per la famiglia.
- Negative e costi:
  - qualche secondo di avvio per ogni comando;
  - chi controlla l'email di un membro può ottenere il ruolo di Amministratore tramite il Gestore. Rischio R-11, accettato dall'utente e mitigato dalla verifica del mittente e dall'avviso a tutta la famiglia.
- Azioni successive:
  - **product-analyst:** aggiornare FR-064, SR-066 e ASM-057 secondo questa procedura;
  - **data-architect:** firme delle funzioni con `p_email_sha256`, `account.email_sha256` (scritto dal servizio), `family_bootstrap.email_sha256` al posto dell'email, `family_notice` con la chiusura per account;
  - **ux-designer:** banner degli avvisi;
  - **devops:** job, IAM, script locale, verifica della conservazione delle esecuzioni.

## Quando rivedere
All'apertura al pubblico, se servono più operatori o un'interfaccia di amministrazione.
