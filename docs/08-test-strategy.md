# Strategia di test: Menu Design

> Documento di proprietà del tester. Versione 2, 2026-10-19. **Stato: PROPOSTA** (in attesa del gate G4, insieme a `docs/07-plan.md`).
>
> **Novità della v2** (revisione critica G4 e decisioni dell'utente del 2026-10-19): staging separato (Supabase Free + Cloud Run `menu-staging`) per le misure ufficiali, con divieto di caricare dataset sintetici in produzione; email e password rinviate fuori da M2 (SL-33/SL-34 in backlog); orologio dei test `app.now_utc()` (D-T1 deciso, opzione b+c); inventario delle funzioni SQL ridisegnato; esecuzioni a livelli (`make ci` per slice, `make full` per milestone e pre-rilascio, `make nightly` periodico); soglie dei moduli critici 90/80; inventario degli `ExportContributor`; evidenza ancora locale (`make ci`) perché ogni push richiede il consenso dell'utente.
>
> Fonti: `docs/02-requirements.md` (v2, CHG-001 … CHG-019), `docs/03-ux.md`, `docs/04-architecture.md` (v5), ADR-0001 … ADR-0016, `docs/05-data.md` (v4, §6.3-6.4, §12), `docs/06-threat-model.md` (v2, §10.5 e §11), `docs/07-plan.md` (v1, §5.5, §6, §7, §10), `references/security-standard.md` e `references/python-standard.md` di Bottega.
>
> Come leggere il documento: le sezioni 1-5 fissano principi, strumenti e ambiente; la 6 descrive gli inventari automatici che chiudono le regole "ogni X ha un test Y"; le 7-11 i test negativi, di sicurezza, di proprietà, di concorrenza e delle migrazioni; la 12 e la 13 sono le mappe **SR → verifica** e **NFR → verifica**; la 14-16 prestazioni, accessibilità e soglie; la 17 il flusso del tester in ogni slice; la 18 dove gira ogni cosa (PR, notte, pre-rilascio); la 19 gli strumenti mancanti; la 20 incoerenze e decisioni richieste.

## 0. Sintesi

- **Piramide a 8 livelli** (sezione 2): unit, architettura, database (RLS, privilegi, migrazioni), integrazione API su PostgreSQL 17 reale, sicurezza, proprietà e concorrenza, componenti del frontend, end-to-end con accessibilità. Sopra: carico, Lighthouse e smoke su staging.
- **Nessun mock dove il comportamento da provare è l'isolamento.** Database reale (PostgreSQL 17 in container), ruoli reali (`menu_app`, `menu_owner`, `menu_console`, `menu_backup`), RLS attiva in tutti i test dell'app. Si simulano solo Google (provider OIDC finto), la posta (M2) e l'orologio.
- **Gli inventari impediscono di dimenticare**: ogni rotta ha `x-authz`, un test `cross_family`, un test negativo per ogni cella "No" della matrice, e, se traccia, un test `tracks`; ogni tabella è nell'inventario RLS; ogni funzione `SECURITY DEFINER` nell'inventario chiuso; ogni `ErrorCode` ha una chiave `it`; ogni funzione SQL dello schema `app` è eseguita da almeno un test.
- **La matrice dei permessi dei test è indipendente dal codice**: un file `authz_matrix.yaml` trascritto da `docs/02-requirements.md` ("Ruoli e permessi"), non derivato dalla tabella di `access` (altrimenti il test sarebbe una tautologia).
- **Il passato congelato (R-07, ADR-0007) ha test di proprietà con macchina a stati** (Hypothesis) contro il database reale, più casi fissi su mezzanotte e cambi d'ora.
- **Per ogni SR esiste un tipo di verifica dichiarato** (sezione 12). Gli SR che sono solo di processo (SR-052, 065, 074 …) hanno una checklist con evidenza, non un test automatico.
- **Stato dell'ambiente:** oggi in locale mancano Docker (integrato in WSL), uv, pnpm, psql e tutti gli scanner (sezione 19). Senza PostgreSQL 17 reale i test di database, integrazione, sicurezza e proprietà **non si possono eseguire**, e l'evidenza di una slice sarebbe `UNVERIFIED`. P-0 del piano resta la precondizione di SL-00a (CI e scansioni) e SL-00b (database).

## 1. Principi

1. **Il test cita il requisito.** Ogni test di un criterio porta l'ID `AC-NNN.n` nel nome o nella docstring (convenzione del piano §5.1). Un controllo automatico (sezione 17.3) elenca gli AC di una slice senza test e quelli senza esito verde.
2. **Prima rosso, poi verde, per il motivo giusto.** I test di una slice partono dalle rotte vuote del passo *contract-first*, quindi falliscono per **comportamento mancante** (501, risposta diversa dall'attesa), non per errori di configurazione (sezione 17.1).
3. **Il negativo vale quanto il positivo.** Per ogni funzione si prova l'input non valido, l'utente anonimo (401), il ruolo sbagliato (403), la risorsa di un'altra famiglia (404, mai 403, con evento), il conflitto (412/428), i limiti (413, 422, 429) e la concorrenza.
4. **Deterministico.** Nessuna dipendenza da rete esterna, orologio di sistema o ordine di esecuzione. L'ordine è mischiato apposta (`pytest-randomly`, seme stampato nel log). I test di concorrenza asseriscono **invarianti** (per esempio "esattamente una richiesta riesce"), non un ordine.
5. **Mai indebolire un test per farlo passare.** Se un test sembra sbagliato si segnala; la correzione passa dal tester.
6. **Il tester non scrive codice di produzione.** Aggiunge test, fixture, dataset (`seed.py` con il backend-developer), configurazione di test e script in `backend/tests/tools/`.
7. **Dati solo sintetici** (SR-029): email `@example.test` (RFC 2606), nomi inventati, nessun dato reale in fixture, dataset o snapshot. Un test controlla che nessuna fixture contenga indirizzi fuori da `example.test`.
8. **Proporzionato.** L'app è a basso rischio (famiglie, beta chiusa): niente test di mutazione in CI, niente confronto visivo di screenshot, niente matrice di browser a ogni PR. Si pagano solo i controlli che il threat model e i requisiti impongono.

## 2. Piramide dei test

Percorsi sotto `backend/tests/` e `web/`. Le cartelle `property/`, `concurrency/`, `contract/`, `perf/` e `tools/` sono un'aggiunta alla struttura del piano §1 (i test sono dominio del tester); `unit/`, `integration/`, `db/`, `security/`, `architecture/` restano come nel piano.

| Livello | Cosa prova | Strumento | Dove | Comando | Quando |
|---|---|---|---|---|---|
| **Unit (backend)** | Funzioni pure e servizi senza database: `email_sha256`, codec v1, validazione Pydantic, redazione dei log, `client_ip`, regole di `access` su fatti, neutralizzazione CSV, generazione dei segreti | pytest | `backend/tests/unit/` | `make test-unit` | ogni PR |
| **Architettura** | Strati e import (nessun ciclo), sessioni SQLAlchemy solo in `tenancy`, nessun `now()` nudo nelle funzioni SQL (sezione 4.4) | pytest + `ast` | `backend/tests/architecture/` | `make test-unit` | ogni PR |
| **Database** | RLS, policy, privilegi, ruoli, `CONNECTION LIMIT`, funzioni `SECURITY DEFINER`, vincoli e `CHECK`, trigger di immutabilità, funzioni SQL di presenza, migrazioni a scala | pytest + psycopg 3 su PostgreSQL 17 | `backend/tests/db/` (marker `db`) | `make test-db` | ogni PR |
| **Integrazione API** | Ogni endpoint con client HTTP in-process (FastAPI `TestClient`/httpx), dal ruolo `menu_app`, database reale, OIDC finto. Valida gli AC | pytest | `backend/tests/integration/` | `make test-int` | ogni PR |
| **Contratto** | `openapi.json` committato = generato; `x-authz` su ogni operazione; modifiche solo additive; client TypeScript generato senza differenze; copertura di `ErrorCode` e codici di validazione; fuzz dello schema | pytest, `openapi-typescript`, Schemathesis (notte) | `backend/tests/contract/`, job `web` | `make test-contract` | ogni PR (fuzz di notte) |
| **Sicurezza** | Matrice autorizzazioni, cross-family, CSRF, header, token OIDC manipolati, mass assignment, injection, limiti di frequenza, sessioni e riautenticazione, canarini nei log | pytest (marker `sec`) | `backend/tests/security/` | `make test-sec` | ogni PR |
| **Proprietà** | Passato congelato (R-07), invertibilità del codec, `search_norm`, `email_sha256` equivalente | Hypothesis (macchine a stati) | `backend/tests/property/` | `make test-prop` | PR (profilo `ci`), notte (profilo `nightly`) |
| **Concorrenza** | Quote, ultimo Amministratore, invito monouso, `If-Match` in parallelo, contatori dei limiti, corsa assegnazione/eliminazione | pytest + thread e connessioni separate | `backend/tests/concurrency/` (marker `concurrency`) | `make test-conc` | PR (ripetizioni 20), notte (200) |
| **Frontend unit e componenti** | `pasto-id`, date nel fuso della famiglia, mappa errori, coda delle scritture per unità, scadenza della cache offline, stati vuoto/caricamento/errore, comandi nascosti per ruolo | Vitest + Testing Library + happy-dom (fetch iniettato; MSW se serve intercettare altro) | `web/tests/unit/**` (SL-01: i test stanno fuori da `src/`, così lint, livelli e copertura non li includono) | `pnpm test` | ogni PR |
| **End-to-end** | Flussi reali sul container completo (SPA + API + PostgreSQL + stub OIDC), conteggio interazioni NFR-012a, XSS, offline, 360 px | Playwright | `web/tests/e2e/` | `make e2e` | ogni PR (Chromium mobile + desktop); matrice completa di notte |
| **Accessibilità** | Zero violazioni serious/critical su ogni vista e stato | `@axe-core/playwright` dentro gli e2e | `web/tests/e2e/` | `make e2e` | ogni PR |
| **Carico** | NFR-002, NFR-003, NFR-004 | Locust (gruppo di dipendenze `perf`) | `backend/tests/perf/` | `make perf` | prima di ogni rilascio, su richiesta |
| **Prestazioni client** | NFR-001 (LCP mediana di 5) | Lighthouse CI (`@lhci/cli`, `numberOfRuns=5`) | `web/tests/lighthouse/` | `make lighthouse` | notte e prima di ogni rilascio |
| **Smoke su staging** | `/healthz`, header di sicurezza, login con account di prova, piano, esportazione | pytest `-m smoke` contro URL, e script | `backend/tests/smoke/` | `make smoke URL=…` | dopo ogni deploy |
| **DAST** | OWASP ZAP baseline | `zaproxy` (container) | job `dast` | `make dast URL=…` | prima del rilascio M1 e nell'audit G6 |

Non si adottano: test di mutazione in CI (si fa un controllo a campione manuale su `access`, `history`, `tenancy` nel modo C delle slice SL-04, SL-14 e SL-28), confronto di screenshot, test su dispositivi reali (restano le verifiche manuali di NFR-008 e NFR-010).

## 3. Strumenti, versioni e dipendenze

Versioni del backend e del frontend già decise in `docs/04-architecture.md` (pytest 9.1.1, Hypothesis 6.170.1, httpx 0.28.1, ruff, mypy; Vitest 5.0.x, Playwright 1.64.x, `@axe-core/playwright` 4.14.x). **Dipendenze di test aggiuntive proposte**, da verificare sul registro all'installazione (protocollo §3.7: esistenza, nome esatto, manutenzione, licenza, CVE) e riportare nel report di SL-00a (strumenti Python), SL-00b o SL-01 (frontend). Finora **nessuna è stata verificata** (nessun accesso al registro in questa fase):

| Pacchetto | Uso | Gruppo | Slice |
|---|---|---|---|
| `pytest-cov` | copertura | `dev` | SL-00a |
| `pytest-xdist` | un database per worker, suite parallela | `dev` | SL-00b |
| `pytest-randomly` | ordine casuale con seme stampato | `dev` | SL-00a |
| `locust` | test di carico | `perf` (non installato in CI delle PR) | SL-10 |
| `schemathesis` | fuzz dello schema OpenAPI, ricerca di 500 | `nightly` | SL-06 |
| `vitest`, `@vitest/coverage-v8`, `@testing-library/react`, `@testing-library/user-event`, `msw`, `happy-dom` | test di componenti | `web` devDependencies | SL-01 |
| `@playwright/test`, `@axe-core/playwright` | e2e e accessibilità | `web` devDependencies | SL-01 |
| `@lhci/cli` | Lighthouse con mediana | `web` devDependencies (job notturno) | SL-06 |

Regole: nessun `freezegun` (l'orologio è del database, sezione 4.4), nessun `testcontainers` (il database arriva da `compose.yaml` o dal servizio `postgres:17` della CI, con immagine per digest come da SR-076), nessuna libreria di mock del database. Gli script di installazione npm restano bloccati; il download dei browser di Playwright (`playwright install`) è un comando esplicito, non uno script di installazione.

## 4. Ambiente di test

### 4.1 Database

- **PostgreSQL 17 reale** (immagine fissata per digest), avviato da `compose.yaml` in locale e come servizio nel job CI. `db/bootstrap.sql` e `alembic upgrade head` si eseguono **una volta per sessione di test** su un database *template*; `bootstrap.sql` è eseguito con psycopg (nessun comando `\` di psql, come richiede SL-00b, quindi `psql` non serve ai test).
- **Un database per worker xdist**, clonato dal template (`CREATE DATABASE … TEMPLATE`). I ruoli sono del cluster e già presenti.
- **Tre connessioni, tre ruoli.** I test dell'app usano **solo** `menu_app` (come in produzione). Un helper `owner` (`menu_owner`) serve a preparare dati e a leggere lo stato; non è mai usato dal codice dell'app (piano §5.5). `menu_console` e `menu_backup` si usano nei test di privilegi e di dump.
- **Isolamento tra test:** dopo ogni test l'helper `owner` svuota con `TRUNCATE … CASCADE` le tabelle di dati (non `alembic_version`). Una transazione di rollback non è adatta, perché `family_tx` apre transazioni proprie e i test di concorrenza usano più connessioni.
- **`track_functions = all`** nel database di test, per l'inventario "ogni funzione SQL è stata chiamata" (sezione 6.7, con somma tra i database dei worker).
- Prerequisito di esecuzione (non un test fallito): se manca `DATABASE_URL_*`, la suite si ferma con un messaggio chiaro, mai con 0 test raccolti e verde.

### 4.1b Staging (decisione dell'utente del 2026-10-19)
Staging è un secondo progetto Supabase Free e un servizio Cloud Run `menu-staging` che scala a zero, con **soli dati sintetici**. Le misure ufficiali (NFR-002, NFR-001, ZAP/DAST) e gli smoke girano su staging; le regressioni restano locali. Staging usa un client OAuth, ruoli e segreti propri (stesso progetto GCP, identità separate come da ADR-0005 rev. 5); lo stub OIDC **non** esiste su staging (un emittente configurabile su un servizio pubblico sarebbe un rischio inutile): gli smoke accedono con account Google di prova creati dall'utente; lo stub serve solo in locale e in CI. **Precondizione prima di ogni esecuzione su staging: riattivare il progetto Supabase di staging** se è in pausa (il piano Free lo mette in pausa per inattività; la riattivazione è **manuale**, dal pannello di Supabase, come da runbook di ADR-0005: non è un passo di `deploy.yml` né di `make prerelease`, perché automatizzarla richiederebbe un token Supabase dell'organizzazione che controlla anche la produzione. La pipeline e `make prerelease` si limitano ad **attendere `/healthz` = 200** e, se non arriva, si fermano con il messaggio "staging in pausa: eseguire il runbook"). Il caricamento dei dataset è protetto dalla guardia descritta in 14.1. Fino all'esistenza di staging (P-2/P-4 per il progetto Supabase) le misure ufficiali sono `UNVERIFIED`.

### 4.2 Provider OIDC finto (ASM-073)

Libreria `tests/support/fake_oidc.py`: chiavi RSA generate nel test, endpoint `discovery`, `jwks`, `authorize`, `token`. Permette di emettere token validi e **manipolati** (una claim alla volta). Nei test pytest è collegato tramite `httpx.MockTransport`; nei test e2e gira come **processo separato** nel compose di test e l'app lo usa con `APP_ENV=test`. Test fissi:
- con `APP_ENV=production` la configurazione rifiuta qualunque emittente diverso da `https://accounts.google.com` (e l'avvio fallisce);
- i token dello stub non sono accettati da un'app avviata con l'emittente Google.

### 4.3 Posta (rinviata)
Email e password sono fuori da M2 (decisione del 2026-10-19: SL-33 e SL-34 in backlog); la posta serve solo se rientrano. In quel caso: mittente finto che registra i messaggi in memoria: si verifica destinatario, assenza di testo libero di altri utenti, tetto giornaliero, mai un segreto di sessione.

### 4.4 Orologio
"Adesso" ha due fonti, e ciascuna ha un modo di simulazione:
- **Database (`now()` nelle funzioni e nei vincoli):** scadenze di sessioni, inviti, esportazioni, finestre dei limiti, "oggi" della famiglia (`app.family_today()`). I test **spostano i dati**, non l'orologio, con l'helper `owner`: per esempio `age_session(id, days=91)` riscrive `created_at` e `last_used_at`; `age_counter(key, minutes=16)` sposta `window_start`; `age_invite(id, days=8)`.
- **"Oggi" della famiglia** (congelamento, settimana corrente, KPI) e ogni altro uso di "adesso" (D-T1, deciso: opzione b+c): le funzioni, i default, le policy e le viste usano `app.now_utc()`, che in produzione restituisce `now()`. **Solo l'ambiente di test** la sostituisce con `CREATE OR REPLACE` dall'helper `owner` (`set_test_now(ts)`), quindi nel codice di produzione non c'è alcun gancio di test; le scadenze di righe si provano spostando i dati (sopra). Test obbligatorio `test_now_utc_is_now_in_production_schema`: eseguito subito dopo `alembic upgrade head`, **prima di qualunque sostituzione**, verifica che il corpo di `app.now_utc()` sia quello della migrazione e che il suo valore coincida con `now()` nella stessa transazione. `app.family_today()` (SL-02) si prova con l'orologio spostato attorno alla mezzanotte locale (Europe/Rome con i due cambi d'ora, America/New_York, Asia/Kolkata, UTC) in `tests/db/test_family_today.py`. Un secondo test verifica che, dopo ogni test che sostituisce la funzione, la fixture la ripristini (altrimenti il database del worker è scartato). Il controllo "nessun `now()` nudo" (sezione 10, punto 8) copre corpi di funzioni, **default di colonna, policy e viste**; la parte di codice SQL la applicano data-architect e tech-lead, il test la verifica sul catalogo.
- **Python:** nessuna chiamata a `datetime.now()` nel dominio (`DTZ` di ruff già lo impone); l'unico tempo applicativo è un parametro di `RequestContext` o il database.
- **Playwright:** `page.clock` per la scadenza offline di 7 giorni e il cambio di giorno.

### 4.5 Rete
Nessun test raggiunge Internet. Test e2e: tutte le richieste fuori dall'origine dell'app sono bloccate dal contesto del browser e fanno fallire il test, tranne il reindirizzamento a `accounts.google.com`, che nello stub è l'host dello stub (SR-031).

## 5. Dati di test e fixture

### 5.1 Regole
- Dati sintetici e inventati. Email `@example.test`. Nomi evidentemente finti (per esempio "Alice Alfa", "Pia Pianificatrice", "Mario Membro").
- **Costruttori** (`tests/factories.py`, eseguiti con `owner`, rapidi): `make_family`, `make_account`, `make_person(role|profile)`, `make_dish`, `make_meal`, `make_invite`, `make_session`. Non passano dall'API, quindi non dipendono dalla funzione sotto test. I flussi di fiducia (login, invito) si coprono invece con test via API.
- **Fixture di sessione** (`client_as(person)`) restituisce un client con cookie `__Host-session`, `__Host-csrf` e header `X-CSRF-Token` già validi, creando la sessione con la stessa routine del login (non un bypass).

### 5.2 Mondo di prova multi-famiglia e multi-ruolo (`world`)

| Famiglia | Persone | Scopo |
|---|---|---|
| **Alfa** | `alfa_admin`, `alfa_admin2`, `alfa_planner`, `alfa_member`, `alfa_profile` (senza account) | famiglia sotto test |
| **Beta** | `beta_admin`, `beta_planner`, `beta_member`, con piatti, pasti, inviti, esportazioni, sessioni propri | "altra famiglia" per ogni test `cross_family` |
| **Gamma** (M2) | come Alfa, con `status='pending_deletion'` | matrice "periodo di ripensamento" |
| **Solo** | un solo Amministratore | ultimo Amministratore |
| Senza famiglia | `orfano` (account senza persona), `ospite_anonimo` (nessuna sessione) | invito, codice, `not_member` |

Ogni famiglia ha **valori canarino** distinti e riconoscibili (per esempio `CANARY-ALFA-DISH-1` nel nome di un piatto, `canary-alfa@example.test`, `CANARY-ALFA-GUESTNOTE`). I test `cross_family` e i test dei log cercano questi valori nelle risposte, nei log e nelle tabelle di registro: se compaiono dove non devono, il test fallisce (SR-021, SR-047, SR-055, SR-073).

### 5.3 Dataset (`backend/scripts/seed.py`, fissato con seme `20261019`)

| Dataset | Contenuto | Uso |
|---|---|---|
| `minimal` | Famiglia Alfa e Beta del mondo di prova | sviluppo e smoke locale |
| `isolation` | 6 famiglie con tutti i ruoli, dati in ogni tabella, identificativi incrociabili | test di isolamento su dati densi e inventario dei campi personali |
| `lighthouse` | 1 famiglia, **500 piatti**, 8 persone, 3 mesi di piano (ADR-0001) | NFR-001 |
| `load` | **50 famiglie, 250 account** (NFR-004), un anno di piano, presenze, eventi, visite | NFR-002, NFR-017 (misura dello spazio), NFR-004 |

Il seed è idempotente, ricostruibile da zero e **non contiene dati reali**; un test controlla che ogni email sia `@example.test`. Che i nomi siano inventati non si verifica in automatico: vale la regola 7 dei principi e la revisione.

### 5.4 Fixture dorate
- `tests/fixtures/codec_v1/*.json`: eventi codificati dal codec v1, **committati**. Un test decodifica ciascuno e verifica il risultato atteso. Se il formato cambia, il test fallisce: il formato v1 è permanente (AC-028.5, ADR-0012).
- `tests/fixtures/schema_columns.txt`: elenco ordinato `tabella.colonna` dello schema `app`, confrontato con `information_schema`. Una colonna nuova senza aggiornamento dell'elenco fa fallire il test: obbliga a ricordare la classificazione di `docs/05-data.md` (SR-015) nella stessa slice.
- `tests/fixtures/oidc/`: nessuna chiave statica; le chiavi si generano a ogni sessione.

## 6. Inventari automatici

Un inventario è un test che confronta due insiemi calcolati e fallisce se non coincidono. Chi aggiunge una rotta, una tabella o una funzione è costretto ad aggiungere anche il test, nella stessa slice.

### 6.1 Rotte: `x-authz` e matrice
Fonte: `app.openapi()` generato dal codice. Test in `tests/contract/test_authz_inventory.py`:
- ogni operazione sotto `/api/v1` (e `/healthz`) ha `operationId` nel formato `<area>.<risorsa>.<azione>` e `x-authz` con `scope`, `roles`, `pendingDeletion` (da SL-31 obbligatorio su tutte; prima ammesso assente) e, se serve, `reauth`, `rules`, `tracks`;
- l'insieme degli `operationId` coincide con le righe di `tests/security/authz_matrix.yaml` (sezione 7.1): un'operazione senza riga nella matrice dei test, o una riga senza operazione, fa fallire;
- per ogni operazione, `x-authz.roles` e `x-authz.rules` coincidono con la matrice dei test (così un allargamento dei permessi nel codice viene visto).

### 6.2 `cross_family`
- Marker `@pytest.mark.cross_family("<operationId>")`, applicato dall'helper `assert_cross_family(op, request_builder)`.
- Fine sessione (`pytest_sessionfinish`, solo se la suite è eseguita per intero, cioè senza `-k` né `-m`): per ogni operazione con `scope: family` e un identificativo nel percorso, nel corpo o nei parametri, deve esistere almeno un test marcato. Differenza non vuota → la suite fallisce con l'elenco.
- L'helper esegue, con `beta_*` contro una risorsa di Alfa (e viceversa), e **verifica quattro cose**:
  1. risposta `404 not_found`, **mai 403**, e corpo identico (a meno di `correlation_id`) a quello di un identificativo inesistente;
  2. un evento `access.cross_family` in `security_event` (letto con `owner`), con attore e famiglia dell'attaccante, senza identificativi della vittima nei campi liberi;
  3. nessun valore canarino di Alfa nella risposta;
  4. per le scritture, lo stato di Alfa non cambia (hash delle righe di Alfa prima e dopo).
- **Variante nel corpo** (THR-021, SR-041): per ogni operazione con identificativi nel corpo (`dish_id`, `course_id`, `person_id`, `tag_id`, destinazioni di sposta/copia), un test con l'identificativo di un'altra famiglia dentro una richiesta valida della propria famiglia → `404`, evento, **nessuna scrittura parziale**.

### 6.3 `tracks`
- Marker `@pytest.mark.tracks("<operationId>")`, helper `assert_tracks(op, happy_request, failing_requests)`.
- Inventario: ogni operazione con `x-authz.tracks` non vuoto ha un test.
- L'helper verifica: (a) in caso di successo, esattamente gli eventi attesi (`unit_type`, `op`, ruolo dell'autore al momento, solo ID, valori prima/dopo, nessun valore canarino di nome o email); (b) per ogni richiesta fallita (`403`, `404`, `412`, `428`, `422`) **zero eventi** (AC-049.4) e nessuna modifica; (c) il contatore `tracked_family` aumenta di uno solo in caso di successo (SR-070).
- **Controllo inverso:** nei test di successo di ogni scrittura **senza** `tracks`, la fixture `no_unexpected_events` verifica che `change_event` non sia cresciuto.

### 6.4 RLS e privilegi (`docs/05-data.md` §6.3-6.4)
`tests/db/test_inventory_rls.py` legge `pg_class`, `pg_policy`, `pg_attribute`:
- ogni tabella di `app` con colonna `family_id` ha RLS **abilitata e forzata** e le policy `p_family` (o varianti `p_family_select`/`p_family_insert` per `change_event`), `p_owner`, `p_backup`; eccezione solo per l'elenco chiuso di §6.3 (`account`, `password_credential`, `account_token`, `auth_flow`, `signup_pending`, `session` con RLS per account, `creation_code`, `security_event`, `deletion_log`, `export_file` con `p_requester`, `job`, `periodic_task_run`, `rate_counter`, `rate_block`, `alembic_version`);
- una tabella che non è né di famiglia né nell'elenco → fallimento ("tabella non classificata");
- per ogni tabella di famiglia, test generici parametrizzati: senza contesto zero righe; con contesto A zero righe di B; `INSERT` e `UPDATE` con altro `family_id` rifiutati; `DELETE` di righe altrui = 0 righe;
- FK composite: un `dish_id`, `course_id`, `person_id` di altra famiglia in `meal_item`, `dish_like`, `attendance` ecc. è rifiutato dal database (SR-041);
- **Stato a fine SL-02** (inventari in `tests/support/inventory.py`): tabelle di famiglia `family` (RLS su `id`, `FamilyTableSpec.key_column`), `family_default_meal`, `person`, `family_bootstrap`, `course`; non di famiglia `security_event` (solo INSERT per `menu_app`, trigger d'immutabilità anche per `menu_owner`). Ogni tabella ha una voce in `tests/support/family_specs.py` e passa il test generico di isolamento su dati reali (`test_real_family_tables_isolate_families`). `menu_console`: nessun privilegio su alcuna tabella o sequenza (inventario dinamico, vale anche per le slice future).
- privilegi: `menu_console` → "permesso negato" su `SELECT` da `dish`, `meal`, `attendance`, `dish_like`, `typical_week`, `person`; `menu_app` → "permesso negato" su `UPDATE`/`DELETE` di `change_event` e `security_event`, e su `SELECT` da `security_event`; `INSERT` di `security_event` consentito; trigger d'immutabilità attivi anche per `menu_owner`;
- ruoli: esattamente `menu_owner`, `menu_app`, `menu_console`, `menu_backup` come login, nessuno con `BYPASSRLS` né superuser, `rolconnlimit` come §3.1, nessun `CREATE` su `app` e `public` per altri che `menu_owner`;
- `pg_dump --enable-row-security` con `menu_backup` contiene le righe di tutte le famiglie (THR-085);
- **riuso della connessione** (THR-027): dopo `family_tx` di A, una nuova transazione sulla stessa connessione senza contesto vede zero righe (nessun `set_config(…, false)`).

### 6.5 Funzioni `SECURITY DEFINER`
`tests/db/test_inventory_secdef.py` legge `pg_proc`: l'insieme coincide con la tabella di `docs/05-data.md` §3.3 (tabella trascritta nel test, aggiornata a ogni slice che aggiunge una funzione); ogni funzione ha `search_path=app, pg_temp`, proprietario `menu_owner`, `EXECUTE` solo al ruolo previsto e non a `PUBLIC`; le funzioni `SECURITY INVOKER` e trigger non sono eseguibili da `PUBLIC`. In SL-00b l'insieme atteso è vuoto; **da SL-02** è `console_bootstrap_family`, `console_security_events`, `console_audit_note` (`EXPECTED_SECDEF_NOW` in `tests/support/inventory.py`; EXECUTE al solo `menu_console`, tutte plpgsql, nessuna funzione di `app` eseguibile da PUBLIC). Per ogni funzione `console_*`: un test per esito (compresi gli errori), con evento `console.<comando>` e `actor_kind='platform_operator'` e **nessuna riga con email o hash** (SR-066).

### 6.6 `ErrorCode`, codici di validazione ed eventi
- `ErrorCode` del codice = tabella di ADR-0010 (trascritta nel test); ogni codice ha stato HTTP corretto.
- Frontend: ogni `ErrorCode` e ogni codice di validazione ha una chiave `error.<code>` / `validation.<code>` nel catalogo `it` (Vitest); un codice sconosciuto produce `error.generic`.
- Eventi di sicurezza: l'elenco del `CHECK` di `security_event.event_type` è confrontato con l'elenco dei tipi **osservati** durante la suite (un hook registra i `DISTINCT event_type` prima di ogni `TRUNCATE`). Un tipo previsto da SR-020 e mai prodotto da un test, a suite completa, è un avviso nel report di slice e un fallimento in `make nightly`.

### 6.7 Funzioni SQL eseguite
Obiettivo: ogni funzione dello schema `app` è eseguita da almeno un test. Poiché la suite gira su più database (uno per worker xdist) e le statistiche di PostgreSQL sono per database e raccolte in modo asincrono, il controllo è così:
1. A fine di ogni worker, una fixture di sessione chiama `pg_stat_force_next_flush()` (PostgreSQL 15+), poi legge `pg_stat_user_functions` del **proprio** database con una connessione dedicata aperta per l'occasione (non una connessione del pool dell'app) e scrive `{funzione: calls}` in un file JSON del worker (`.test-state/sqlcalls-<worker>.json`).
2. Un passo finale (`tests/tools/sql_calls_report.py`, eseguito da `make full` dopo la suite, non da un test) **somma** i file dei worker e confronta con l'elenco di `pg_proc` dello schema `app` (non trigger, che sono già coperti dai test sui vincoli). Una funzione con somma 0 è un fallimento di `make full`; in `make ci` è solo un avviso, perché una slice esegue un sottoinsieme.
3. `track_functions = all` non registra le funzioni SQL **inlinabili** (`LANGUAGE sql`, espanse nel piano della query): le loro chiamate non risultano. Regola (data-architect, `docs/05-data.md` v5): **ogni funzione `LANGUAGE sql` dello schema `app` è nell'elenco chiuso** `INLINABLE_SQL_FUNCTIONS` = `now_utc`, `current_family_id`, `current_account_id`, `search_norm`, `family_today`, `effective_meals`, `effective_attendance`, e solo quelle. Per ognuna è **obbligatorio un test di chiamata diretta** (`SELECT app.f(…)` con valore atteso), marcato `@pytest.mark.sqlfunc("<nome>")`. Il test d'inventario fallisce se: una funzione dell'elenco non ha il test; una funzione `LANGUAGE sql` di `pg_proc` non è nell'elenco; una funzione dell'elenco non è `LANGUAGE sql` o non esiste (elenco non aggiornato). Le funzioni non SQL (plpgsql) seguono il conteggio di `pg_stat_user_functions`.

### 6.8 Altri inventari
- **`ExportContributor` (OBJ-02, da SL-02):** registro in `menu.common` (`ExportContributor`, `register_export_contributor`, `export_contributors`), contributori registrati all'import di `menu.family` e `menu.catalog`. Il confronto con le tabelle reali sta in `tests/db/test_export_inventory.py` (serve il database; `make test-unit` esegue `tests/tools` senza cluster, quindi il piano `tests/tools/export_inventory` è spostato qui), la logica pura con prova di fallimento in `tests/unit/test_export_inventory_logic.py` (`tests/support/export_inventory.py`: elenco chiuso `NOT_EXPORTED` con motivo, oggi solo `family_bootstrap`, ed elenco `FORBIDDEN_EXPORT_COLUMNS`). Test di perimetro su dati reali (`family` e `self`, altra famiglia assente, nessuna colonna esclusa). Regola originale: il test confronta le tabelle di proprietà di una famiglia (tabelle con `family_id`, esclusa la lista di §6.3 e quelle dichiarate "non esportate" con motivo in un elenco chiuso del test) con i contributori registrati in `privacy` (`export_family`/`export_self`). Una tabella di famiglia senza contributore, o senza voce nell'elenco delle esclusioni, fa fallire: una funzione di esportazione non può dimenticare dati nuovi. Un test collegato verifica che ogni colonna esportata sia nel perimetro di SR-072 (nessuna email, ultima visita o sessione di altri).
- `pendingDeletion` dichiarato su tutte le rotte di scrittura (da SL-31), con test della matrice "Durante il periodo di ripensamento".
- Rotte `public`/`anonymous` (elenco chiuso: `/healthz` con `scope: public` (Q-T2 deciso), `/session`, `/auth/google/start`, `/auth/google/callback`, `/invites/resolve`): un test impedisce che una rotta nuova si dichiari `public` senza essere nell'elenco.
- `openapi.json`: nessun endpoint di modifica o cancellazione per `history` e `security_event` (AC-049.3, AC-028.6).
- Tutti i campi JSON di richiesta: modello Pydantic con `extra='forbid'` (verificato per riflessione sui modelli di `schemas.py`).

## 7. Test negativi e di autorizzazione

### 7.1 Matrice ruoli × operazioni × altra famiglia

- **File indipendente:** `backend/tests/security/authz_matrix.yaml`, scritto dal tester leggendo "Ruoli e permessi" di `docs/02-requirements.md`, non generato dal codice. Una riga per `operationId`:

  ```yaml
  catalog.dish.create:
    anonymous: 401
    admin: allow
    planner: allow
    member: {allow_if: "status in (absent, to_try)", else: 403}   # regola member_own_to_try
    other_family_member: 404
    pending_deletion: 409    # da M2
    profile: n/a
  ```
- **Generazione dei test:** un test parametrizzato per (operazione × ruolo) costruisce una richiesta valida minimale con le fixture del mondo, la esegue come quel ruolo e confronta l'esito. Le richieste valide sono fornite da una tabella `request_builders[operationId]` che il tester amplia a ogni slice.
- **Tutte le colonne della matrice**, compresi: Anonimo (401, oppure l'esito della rotta pubblica), ruolo declassato con richiesta in volo (SR-005, 403 alla richiesta successiva), persona rimossa (404 sulle risorse di famiglia e `family: null` in sessione), Membro su risorse di altri Membri (regole *Propri*), Membro assente su ospiti (*Se presente*), Gestore (non esiste rotta applicativa: sezione 6.8).
- **Celle "Sì"** sono verificate con il caso di successo; **ogni cella "No"** con almeno un test che verifica anche l'assenza di effetti (stato invariato, nessun evento di modifica, evento `access.denied`).
- **Periodo di ripensamento** (M2): per ogni scrittura con `pendingDeletion: blocked`, `409 family_pending_deletion`; per le consentite (annulla eliminazione, eliminazione dell'account, esportazione) successo.
- **Mass assignment (SR-010):** per ogni DTO di scrittura, una richiesta con campi extra (`familyId`, `role`, `createdBy`, `version`, `createdAt`, `status` per il Membro, `priority` per il Membro in M2, `id`) → `422 unknown_field` (o `403` per un permesso mancante), e lo stato non cambia. Un test per modello, generato per riflessione sui modelli di scrittura.

### 7.2 CSRF e metodo (SR-023, THR-007)
Per **ogni** operazione non sicura di `/api/v1` (elenco da OpenAPI):
1. senza `X-CSRF-Token` → `403 csrf_failed`;
2. token errato, token di un'altra sessione, token vuoto → `403 csrf_failed`;
3. `Origin` estraneo o `Sec-Fetch-Site: cross-site` con token valido → `403 csrf_failed`;
4. `Content-Type` diverso da `application/json` (`text/plain`, `multipart/form-data`, `application/x-www-form-urlencoded`) → `415` (unica eccezione: import CSV su `text/csv`);
5. nessuno di questi casi lascia effetti né eventi di modifica.

Per le rotte `anonymous` (avvio OIDC, risoluzione invito): doppio invio del cookie `__Host-csrf`, con gli stessi casi. Per i `GET`: nessuna rotta `GET` ha effetti collaterali (conteggio delle righe invariato, salvo le eccezioni dichiarate: l'impostazione del cookie CSRF in `GET /session` e il consumo di `authOutcome`). Il callback OIDC risponde sempre `302` e non accetta metodi diversi da `GET`.

### 7.3 Concorrenza ottimistica: `If-Match`, 412, 428 (ADR-0008)
Per ogni operazione con unità versionata (OpenAPI: parametro `If-Match`):
- senza `If-Match` → `428 precondition_required`, nessuna scrittura, nessun evento;
- versione superata → `412 conflict` con `params.current`, `modifiedBy`, `modifiedAt` coerenti con lo stato attuale; nessuna scrittura, nessun evento, `modifiedBy` come ID (nessun nome);
- `If-Match: "0"` su unità mai scritta → successo; su unità già scritta → `412`;
- `ETag` della risposta uguale a `version` e utilizzabile nella richiesta successiva;
- `If-Match` malformato (`abc`, `*`, `W/"3"`, numero negativo): `If-Match` valido solo se corrisponde a `^"(0|[1-9][0-9]{0,17})"$` (al massimo 18 cifre, THR-107): qualunque altro valore (`abc`, `*`, `W/"3"`, negativo, non intero, più valori, **19 cifre** `"1000000000000000000"`) → `422 validation` con `invalid_value`; il caso di 18 cifre è accettato e non produce `500`; in particolare un valore **sopra 2^31−1 ma entro 18 cifre** (per esempio `"2147483648"` e `"999999999999999999"`) non dà `500`: le colonne di versione sono `integer` e il piano lega la versione attesa come `bigint`, quindi l'esito atteso è `412 conflict` (versione superata) sulle unità esistenti e `412` anche su `0`-mai-scritta, mai un errore di overflow, verificato su un'operazione per ogni tipo di unità versionata; `If-Match` assente = `428` (SL-00a);
- richieste parallele sulla stessa versione: una riesce, le altre `412` (sezione 9);
- operazioni su più unità (`move`, `swap`, `copy`): `expectedVersions` superate → `412` con `params.units[]`, **tutto o niente**; ordine dei lock senza deadlock con operazioni incrociate (SL-20).

### 7.4 Limiti di frequenza (SR-059, SR-070, SR-003)
Un test per **ogni riga** della tabella di SR-059 e per ogni limite di SR-070 (SR-059, SR-070 e AC-001.9 → SL-03b (con la schermata S-08); le righe di registrazione, recupero e reinvio dell'email e password sono post-M2 e non si testano finché la funzione è in backlog). Per non inviare centinaia di richieste, l'helper `owner` porta il contatore a `limite − 1` (`seed_counter`), poi una richiesta passa e la successiva dà `429` con `Retry-After`; per i limiti piccoli (5, 10) si inviano le richieste vere.

| Limite | Verifica |
|---|---|
| Avvio login / callback 30 per IP / 15 min | la 31ª → `429`; IP dall'ultima voce di `X-Forwarded-For` (con `TRUSTED_PROXY_HOPS`); header falsificato non cambia IP (THR-012); salto di finestra con `age_counter` |
| Link o codici non validi 10 per IP / 15 min; codici errati 5 per account (M2) | `429`; il link valido non conta |
| Login fallito, registrazione, recupero, reinvio, import, esportazioni (M1/M2) | un test per riga; esportazioni: 3 per account e 3 per famiglia al giorno |
| API autenticata 300/min per sessione, di cui 60 scritture | le richieste oltre → `429`; una seconda sessione ha contatori propri |
| 60 scritture/min **per account**, sommando le sessioni (SR-070) | due sessioni dello stesso account sommano |
| 5.000 scritture tracciate/giorno per famiglia, giorno locale nel fuso della famiglia | contatore a 4.999; la 5.000ª riesce, la successiva `429` + evento `rate_limit.exceeded`; il giorno seguente (`age_counter`) riparte; due fusi diversi cambiano la finestra |
| Massimo 20 sessioni per account | il 21º login revoca la meno recente |
| Contatori persistenti | riavvio simulato (nuova app sullo stesso database): i contatori restano; due istanze condividono lo stesso upsert |
| Fail closed | se l'upsert dei limiti fallisce (database in errore simulato), la richiesta è negata, non permessa |

Ogni `429` ha `Retry-After`, corpo `problem+json` generico e nessuna informazione sull'identità limitata (SR-004).

### 7.5 Sessione e riautenticazione (SR-005, SR-037, SR-039, SR-068)
- Attributi del cookie: `__Host-`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, nessun `Domain`.
- Nel database c'è solo l'hash SHA-256 del token (nessuna colonna contiene il token in chiaro; il test legge tutte le colonne `bytea`/`text` di `session` e cerca il token appena emesso).
- Scadenza mobile 30 giorni (31 giorni di inattività → rifiutata, `age_session`), assoluta 90 giorni (ultimo uso recente ma creata 91 giorni fa → rifiutata). Rinnovo di `last_used_at` al massimo ogni ora.
- Rigenerazione al login: con cookie preesistente, la vecchia sessione è cancellata; il token non è mai in URL, né in storage JS (e2e).
- Logout invalida sul server (riuso del vecchio cookie → 401). Rimozione dalla famiglia: la richiesta successiva dà 404 sulle risorse (SR-005). Cambio password (M2) e eliminazione account: sessioni invalidate.
- Revoca globale (SL-24): tutte le sessioni invalide alla richiesta successiva.
- **Riautenticazione (M2, SL-28):** per ogni operazione con `reauth: true`: senza riautenticazione → `403 reauth_required`; riautenticazione a 9 minuti → permessa, a 11 minuti → `403`; riautenticazione con **un `sub` diverso** (stesso telefono, altro account Google) → esito `reauth_wrong_account`, `auth_time` non aggiornato, evento `reauth.mismatch`, e l'operazione resta bloccata (THR-008); `auth_time` precedente all'avvio del flusso oltre la tolleranza di 60 s o nel futuro → rifiutato; il flusso `reauth` è legato a `auth_flow.session_id` (altra sessione → rifiutato).
- Le sessioni di altri non si leggono né si revocano: `GET/DELETE /me/sessions/{id}` con ID altrui → `404` (RLS per account, AC-047.3).

### 7.6 Validazione e limiti (SR-060, SR-024)
- Corpo 65 KB → `413`; profondità JSON 11 → `422`; `Content-Type` sbagliato → `415`.
- Per ogni campo di testo: lunghezza al limite (accettata) e al limite + 1 (`string_too_long`), stringa vuota, solo spazi, Unicode (accenti, emoji, combinanti), caratteri di controllo e ritorni a capo (neutralizzati nei log), `NUL`.
- URL delle fonti: accettati `http` e `https`; rifiutati `javascript:`, `data:`, `file:`, `ftp:`, URL senza schema, con credenziali; output con `rel="noopener noreferrer"` (e2e).
- Paginazione `limit` 101 → `422`; `cursor` manomesso o di altra famiglia → `422`/`404` senza fuoriuscita di dati.
- Intervallo del piano 63 giorni → `422 range_too_large`; `from > to` → `range_order`; data non valida → `date_invalid`.
- Quote per famiglia con richieste concorrenti (sezione 9).
- **Iniezione SQL (THR-025):** nei campi di ricerca e filtri, i payload `' OR 1=1 --`, `%`, `_`, `\`, `'; SELECT set_config('app.family_id', …`, `";`, nome di piatto contenente apici: la risposta è corretta e **nessuna riga di un'altra famiglia** compare; un test sul codice cerca in `src/` l'uso di `text()` con f-string o `format` (regola semgrep, in aggiunta all'unit test).

## 8. Test di proprietà: il passato congelato (R-07, ADR-0007, ADR-0009)

Libreria Hypothesis, database reale, profili: `ci-small` (20 esempi, in `make ci`), `ci` (50 esempi, `derandomize=True`, `deadline=None`, in `make full`) e `nightly` (500 esempi, seme casuale stampato; ogni controesempio trovato si trasforma in un `@example` fisso e committato). Ogni esempio parte da un database svuotato (helper `owner`).

### 8.1 Macchina a stati del passato congelato
`RuleBasedStateMachine` con un **modello di riferimento** in Python (dizionari delle presenze e dei pasti per giorno), indipendente dall'implementazione SQL. Regole (operazioni casuali):
- cambiare i pasti di default della famiglia;
- cambiare la settimana tipo di una persona (aggiunta e rimozione di assenze);
- far entrare una persona (data di ingresso = oggi o prima);
- far uscire o rimuovere una persona;
- creare o eliminare un profilo;
- **avanzare il giorno** (di 1 o più giorni, anche attraverso mezzanotte e cambi d'ora);
- cambiare il fuso della famiglia (anche vicino alla mezzanotte);
- aggiungere, togliere e rimettere un pasto in un giorno non passato;
- correzione esplicita di una presenza o di un pasto in un giorno passato (unica modifica ammessa al passato);
- eccezione dell'utente su un pasto futuro;
- chiamata spontanea di `ensure_frozen` (idempotenza).

**Invarianti** (controllati dopo ogni passo):
1. per ogni giorno `d < oggi` già osservato, `effective_meals(d)` e `effective_attendance(d)` sono **uguali** a quelli osservati la prima volta in cui `d` è diventato passato, salvo le correzioni esplicite del modello;
2. per i giorni futuri, le presenze coincidono con il modello (settimana tipo + eccezioni + ingresso);
3. all'uscita di una persona: settimana tipo ed eccezioni future cancellate, presenze passate conservate come "ex membro" senza nome;
4. rimettere un pasto tolto azzera contenuto, ospiti ed eccezioni **dei giorni non congelati** (ADR-0009);
5. una persona entrata oggi conta in tutti i pasti di oggi (ASM-058) e in nessun pasto di ieri;
6. `ensure_frozen` chiamata due volte non cambia nulla (idempotenza).

Casi fissi di accompagnamento (non casuali, sempre eseguiti): lunedì 00:00 nel fuso Europe/Rome; sabato 28 marzo → domenica 29 marzo 2026 (inizio dell'ora legale) e 24 → 25 ottobre 2026 (fine); cambio di fuso Europe/Rome → America/New_York a ridosso della mezzanotte; famiglia creata a mezzanotte; fuso con mezzora di scarto (Asia/Kolkata).

Questo test è scritto **prima** dell'implementazione in SL-09 (parte pasti) e completato in SL-14 (parte presenze). Si esegue anche con `app.now_utc()` sostituita (sezione 4.4).

### 8.2 Altre proprietà
- **Codec v1** (ADR-0012): per ogni coppia (prima, dopo) generata, `decode(encode(prima, dopo))` restituisce i valori; lo stato di un'unità in un istante passato si ricostruisce dai valori "prima" e "dopo"; i valori vuoti, Unicode e le liste sono supportati; l'evento resta sotto la dimensione compatta attesa (NFR-017, soglia in byte da `docs/05-data.md` §14 dopo SL-10).
- **`search_norm`:** idempotente; "Crème" e "creme" coincidono; per ogni stringa generata la ricerca trova il piatto con quel nome.
- **`email_sha256`:** lo stesso risultato dallo script della console e dal servizio per maiuscole, spazi, caratteri non ASCII (I-03, SL-02).
- **Settimana ISO nel fuso:** `weekly_visit` e "settimana corrente" nel fuso della famiglia, per fusi e giorni generati.

## 9. Concorrenza

Tutte le prove usano connessioni indipendenti, un `threading.Barrier` che fa partire le richieste insieme, e asseriscono invarianti. Ripetute 3 volte in `make ci` e 200 volte in `make full` e `make nightly` (`-m concurrency`).

| Scenario | Slice | Invariante |
|---|---|---|
| Quota di 2.000 piatti: famiglia con 1.999 piatti (preparata con `owner`) e due `POST /dishes` insieme | SL-04 | esattamente un `201`, un `409 quota_exceeded`; mai più di 2.000 |
| Altre quote con lock (persone, inviti in sospeso 20, inviti al giorno 20, "Altro pasto" 5 al giorno) | SL-11, SL-16, SL-40 | mai oltre il limite |
| Due `PUT` con lo stesso `If-Match` | SL-04, SL-06b, SL-15, SL-19 | uno `200`, uno `412`; nessuna perdita silenziosa; un solo evento |
| Scritture su unità diverse dello stesso pasto (contenuto, ospiti, presenza) | SL-15, SL-19 | entrambe riescono; versioni indipendenti |
| Eliminazione di un piatto e assegnazione in corsa | SL-08 | `409 dish_already_planned`; mai pasto con piatto inesistente (FK `NO ACTION`) |
| Due Amministratori che si declassano/escono insieme | SL-13 | almeno un Amministratore; il secondo `409 last_admin` |
| Declassamento di un Pianificatore con la sua richiesta in volo | SL-13 | la richiesta in volo termina prima o dà `403`; nessuna scrittura dopo il declassamento |
| Due accettazioni dello stesso invito | SL-12 | una sola persona creata, l'altra risposta generica `invite_invalid` |
| Invito revocato mentre si fa login | SL-12 | risposta generica, nessun dato |
| Stesso account che accetta due inviti di famiglie diverse | SL-12 | `ux_person_account_single_family` lo impedisce |
| `move`/`swap` incrociati A→B e B→A | SL-20 | nessun deadlock (ordine dei lock per chiave), tutto o niente |
| Contatori dei limiti con N richieste simultanee | SL-03b, SL-05 | il conteggio finale è esattamente N |
| Due worker sovrapposti | SL-10 | compiti idempotenti, advisory lock, nessun doppio effetto |
| Due `signup/accept` con lo stesso cookie | SL-12 | un solo account/persona |

Quando una prova non è affidabile al 100%, non si rende "più lenta" con `sleep`: si cambia la sincronizzazione (barriera, advisory lock di test) o si segnala come instabile e si corregge. Un test instabile non resta mai sulla linea principale: va riparato o rimosso con una nota nel report.

## 10. Migrazioni

Test in `backend/tests/db/test_migrations.py` (marker `db`, `slow`), eseguiti così: in `make ci` solo il ciclo della revisione nuova (`upgrade → downgrade -1 → upgrade`) più `downgrade base` ↔ `upgrade head`; la scala di **ogni** revisione in `make full`:
1. **Una sola testa** (`alembic heads`), rev-id a quattro cifre, catena lineare.
2. **A scala per ogni revisione** (`docs/05-data.md` §12): `upgrade` → `downgrade -1` → `upgrade`, poi `downgrade base` e `upgrade head`. Dopo ogni passo si eseguono gli **inventari** (RLS, policy, privilegi, `SECURITY DEFINER`, funzioni): un `downgrade` che lascia una policy, un grant o una funzione fa fallire.
3. **Schema identico dopo il ciclo:** il dump dello schema (`pg_dump --schema-only`) dopo `upgrade head` è uguale a quello dopo `upgrade head → downgrade base → upgrade head`.
4. **Dati attraverso la migrazione:** si porta il database alla revisione N−1, si inseriscono dati con le fixture, si fa `upgrade` a N e si verifica che i dati ci siano e che le nuove colonne abbiano i valori di default previsti. I `downgrade` marcati `LOSSY` sono nell'elenco dei test e il test verifica che la docstring lo dichiari.
5. **Compatibilità espansione/contrazione:** pre-rilascio (non a ogni PR), la suite di integrazione della release precedente (checkout in un worktree) gira contro lo schema nuovo: ogni migrazione deve restare compatibile con il codice precedente (`menu-migrate` precede il deploy).
6. **Lock e timeout:** `env.py` imposta `lock_timeout` 5 s e `statement_timeout` 60 s; rifiuto dell'esecuzione se il ruolo non è `menu_owner` (test).
7. **`db/bootstrap.sql`:** eseguibile due volte senza errori (idempotente), senza comandi `\`, senza password nel file, con revoche verso `anon` e `authenticated` solo se i ruoli esistono (si prova sia senza questi ruoli sia creandoli prima, per simulare Supabase). La migrazione `0001` fallisce con un messaggio chiaro se un prerequisito manca (si prova togliendone uno alla volta).
8. **Nessun `now()` nudo** (D-T1): il test legge dal catalogo (`pg_get_functiondef`, `pg_get_expr` dei default, `pg_policy`, `pg_get_viewdef`, `CHECK`, trigger) e fallisce se trova una delle espressioni vietate `now()`, `CURRENT_TIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIME`, `LOCALTIMESTAMP`, `LOCALTIME`, `transaction_timestamp()`, `statement_timestamp()`, `clock_timestamp()`, `timeofday()` (confronto senza distinzione tra maiuscole e minuscole, anche come `DEFAULT`). **Un'unica eccezione:** il corpo di `app.now_utc()`. Nessuna eccezione per `created_at` o altri default. Il test `test_now_utc_is_now_in_production_schema` (4.4) gira subito dopo `upgrade head`.

## 11. Test di sicurezza mappati sulle minacce alte e critiche

Minacce con rischio inerente Alto o Critico (plan §10.4) e relativa verifica. `Auto` = test automatico nella suite; `Pipeline` = controllo bloccante in CI; `Processo` = checklist con evidenza, non automatizzabile.

| THR | Minaccia | Verifica | Tipo | Slice |
|---|---|---|---|---|
| THR-001 | Token ID falsificato o manipolato | Stub OIDC: un test per claim: firma con altra chiave, `alg=none`, `alg=HS256` con chiave pubblica come segreto, `iss`, `aud`, `exp`, `nonce` ripetuto o assente, `email_verified=false`, `kid` sconosciuto (refresh JWKS una sola volta), `state` di altro flusso, cookie `auth_flow` assente o scaduto | Auto (`sec`) | SL-03a |
| THR-004 | Account Google della vittima compromesso | Fuori dal prodotto. Si provano le mitigazioni: scadenze 30/90, lista sessioni e revoca, revoca globale, riautenticazione per operazioni critiche | Auto + Processo | SL-03a, SL-25, SL-28 |
| THR-005 | Furto del token di sessione | Attributi del cookie, solo hash nel database, nessun token in storage/URL/log (e2e e canarino), CSP con Trusted Types (header), nessun `innerHTML` (ESLint e semgrep) | Auto + Pipeline | SL-01, SL-03a |
| THR-008 | Riautenticazione con altro account | Sezione 7.5: `sub` diverso, `auth_time` fuori tolleranza, flusso legato a sessione, esito `reauth_wrong_account` | Auto | SL-28 |
| THR-012 | `X-Forwarded-For` falsificato | `client_ip` con `TRUSTED_PROXY_HOPS`: ultima voce attendibile; cento richieste con IP diversi nell'header contano su un solo IP reale; evento di sicurezza con IP reale. Verifica reale in staging (V-3, smoke) | Auto + Processo | SL-00a, SL-03a |
| THR-020 | IDOR/BOLA su tutte le rotte | Inventario `cross_family` (6.2) + RLS generico (6.4) | Auto | SL-02 …, ogni slice |
| THR-021 | Riferimenti nel corpo verso altre famiglie | Variante nel corpo (6.2) + FK composite (6.4) | Auto | SL-04, SL-06, SL-20 |
| THR-023 | Escalation verticale | Matrice (7.1): ogni operazione da Amministratore provata come Pianificatore e Membro; ruolo riletto a ogni richiesta (declassamento) | Auto | SL-04, SL-09, SL-11, SL-13, SL-17 |
| THR-025 | SQL injection | Sezione 7.6 + regole semgrep proprie + `bandit` + ruoli: anche se un'iniezione riuscisse, `menu_app` non legge `security_event` (6.4) | Auto + Pipeline | SL-00a, SL-04 |
| THR-030 | Link di invito trapelato | Monouso, scadenza 7 giorni, revoca, segreto solo come hash, `GET` che non consuma, anteprima di chat che non consuma, ruolo massimo Pianificatore, nome della famiglia solo dopo il login, `Referrer-Policy: no-referrer`, frammento `#` non inviato al server (e2e intercetta le richieste), evento di ingresso visibile agli Amministratori con email (SR-073) | Auto | SL-11, SL-12, SL-13 |
| THR-040 | Credenziali dei ruoli + endpoint DB pubblico (ADR-0016) | Rischio accettato. Si provano i controlli compensativi: `sslmode=verify-full` obbligatorio all'avvio, `CONNECTION LIMIT`, nessun `BYPASSRLS`, privilegi minimi, allarmi di attività fuori finestra (SL-26). Restrizioni di rete, password, MFA: verifiche sul progetto reale | Auto + Processo | SL-00b, SL-26 |
| THR-042 | Forza bruta sulle password dei ruoli | Processo: lunghezza ≥ 32 caratteri generate da `role-secret.sh` (test sullo script: lunghezza e alfabeto); ban del fornitore da verificare (P-4) | Auto (script) + Processo | SL-00b |
| THR-046 | Esaurimento della quota di 500 MB | Limite 5.000 scritture/giorno, esportazioni ≤ 20 MB, allarme al 70% (`db_size()` con soglia di prova), misura sul dataset `load` | Auto + Perf | SL-05, SL-10, SL-27 |
| THR-050 | Recupero dell'Amministratore | Quattro esiti con evento; `not_eligible` identico per email inesistente, senza famiglia, hash ambiguo; nessuna riga contiene email o hash; email in argomento rifiutata; sessioni del promosso invalidate; avviso alla famiglia 30 giorni. Rischio residuo R-11 accettato | Auto | SL-24 |
| THR-052 | PC del Gestore compromesso | Processo (P-5). Automatico: `console_client` non stampa né salva email, argomenti del job solo hash esadecimali e `request_ref` valido, output solo ID ed esiti | Auto (script) + Processo | SL-02 |
| THR-070 | XSS memorizzato | E2E: payload (`<img src=x onerror=…>`, `"><script>`, `javascript:`, SVG, entità) in nome piatto, note, voce libera, nome pasto, nota ospiti, portata, tag, nome famiglia, nome visualizzato di Google: mostrati come testo, nessun dialogo/evento, nessuna violazione CSP; l'informativa Markdown senza HTML grezzo; ESLint/semgrep contro `dangerouslySetInnerHTML` | Auto (e2e) + Pipeline | SL-01, SL-04, SL-07 |
| THR-090 | Dipendenze compromesse | `pip-audit`, `osv-scanner`, `pnpm audit`, cooldown 7 giorni, script npm bloccati; test di configurazione su `pyproject.toml`, `.npmrc` | Pipeline + Auto (config) | SL-00a, SL-01 |
| THR-091 | GitHub Actions e deploy | `zizmor`, azioni fissate a SHA, `permissions` minimi, nessun `pull_request_target`; test che legge i workflow e verifica gli stessi punti | Pipeline + Auto (config) | SL-00a |
| THR-093 | Segreti nel repository | `gitleaks detect` su tutta la storia + hook; test che `.env*` sia ignorato e `.env.example` contenga solo segnaposto | Pipeline + Auto (config) | SL-00a |
| THR-094 | Configurazione cloud errata | Processo (checklist del devops in `docs/09-release.md`); smoke su staging: job non invocabili da anonimo, nessun bucket pubblico, ruolo del servizio minimo | Processo + Smoke | SL-10, rilascio |
| THR-122 | (post-M2, backlog) Credential stuffing/pre-hijacking con password | Argon2id con parametri minimi, hash fittizio per email inesistente (si verifica che la funzione di hash sia invocata nei due casi, non il tempo), risposta unica, ritardo progressivo, nessuna unione automatica, controllo k-anonimato (la richiesta al servizio finto contiene solo i primi 5 caratteri dell'hash) | Auto | backlog (ex SL-33/SL-34) |

Altre prove richieste dal threat model §10.5, non nell'elenco precedente (rischio medio o basso): invito attraverso OIDC senza storage (THR-033), riuso della connessione senza contesto (THR-027, 6.4), inventario `SECURITY DEFINER` e grant (THR-044, 6.5), download dopo il declassamento e perimetro delle esportazioni (THR-060, THR-063), nessun `last_visit_at` di altri nelle risposte (THR-112, 12/SR-014), limiti per account e per famiglia (THR-100, 7.4), service worker e callback OIDC (THR-073, e2e: il callback e `/api/` non sono mai serviti dalla cache), funzioni di recupero (THR-050).

### Header di sicurezza (SR-023, SR-046)
Un test per ogni **classe di risposta**: `200` autenticata, `200` pubblica, `401`, `403`, `404`, `413`, `415`, `422`, `429`, `500` simulato, file statici, `index.html`, `sw.js`. Header attesi: `Content-Security-Policy` (default-src 'self'; `connect-src 'self'`; `frame-ancestors 'none'`; Trusted Types; nessun `unsafe-inline` né `unsafe-eval`), `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security`, nessun `Server`/`X-Powered-By` che riveli versioni. `Cache-Control: no-store` su ogni risposta autenticata; `no-cache` su `sw.js` e `index.html`; asset con hash `immutable`. CORS: un'origine estranea non riceve `Access-Control-Allow-Origin`; richiesta di preflight non consentita da altre origini. Il test confronta con una tabella dichiarata nel test, non con il valore letto dal codice.

## 12. SR → tipo di verifica

Legenda dei tipi: **U** unit; **DB** test di database; **I** integrazione API; **SEC** suite di sicurezza; **E2E** end-to-end; **PBT** test di proprietà; **CONC** concorrenza; **ARCH** test di architettura; **CFG** test di configurazione/file; **CI** controllo bloccante di pipeline; **PERF** carico; **PROC** processo con checklist (evidenza = documento o verifica registrata in `docs/09-release.md`).

| SR | Verifica | Tipo | Come |
|---|---|---|---|
| SR-001 | Code + PKCE S256, solo scope `openid email profile`, legame al `sub` con `email_verified` | I, SEC | Redirect di avvio contiene `code_challenge_method=S256` e gli scope esatti; `email_verified=false` rifiutato; stesso `sub` con email cambiata = stesso account |
| SR-002 (post-M2) | Argon2id (o bcrypt ≥ 12), lunghezza 12-128 | U, I, SEC | Parametri dell'hash; 11 e 129 caratteri rifiutati, 12 e 128 accettati; nessuna regola di composizione; nessuna password in chiaro in DB/log |
| SR-003 | Limiti di frequenza su login, registrazione, inviti, codici, import, esportazioni, API | SEC | Sezione 7.4 |
| SR-004 | Nessuna enumerazione di account, email, inviti, codici | SEC | Per login, registrazione, recupero, invito, codice: stesso stato, corpo e intestazioni per esistente/inesistente (confronto strutturale); funzione di hash invocata anche per l'inesistente; confronto statistico dei tempi solo di notte, con tolleranza ampia |
| SR-005 | Cookie e sessione | SEC, I | Sezione 7.5 |
| SR-006 (post-M2) | Email non verificata senza accesso; link monouso 24 h / 1 h | I | Token riusato, scaduto (`age_token`), di altro tipo; accesso ai dati prima della verifica = 401/403 |
| SR-007 | Segreto ≥ 128 bit, solo hash, monouso, scadenza, revoca | U, DB, I | Lunghezza e CSPRNG (`secrets`); nessuna colonna contiene il segreto (scansione delle tabelle per il segreto appena emesso); scadenza a 7 e 30 giorni; `GET` non consuma |
| SR-008 | Negato per default, a livello di oggetto, famiglia dalla membership | SEC, DB | Inventario `cross_family` (6.2); RLS (6.4); parametri `family_id` nel client ignorati o rifiutati |
| SR-009 | Matrice centralizzata, test negativo per ogni cella "No", inventario | SEC, CI | Sezioni 6.1, 7.1 |
| SR-010 | Campi scrivibili espliciti, nessun mass assignment | SEC, ARCH | Sezione 7.1 (mass assignment); `extra='forbid'` per riflessione |
| SR-011 | "Almeno un Amministratore" atomico | CONC, I | Sezione 9 |
| SR-012 | Il Gestore non legge i contenuti | DB, U, ARCH | `menu_console` senza `SELECT` (6.4); nessuna rotta applicativa del Gestore; output dei comandi senza contenuti |
| SR-013 | Età: solo il fatto e la data; < 14 blocca senza consumare | I, DB | Nessuna colonna di data di nascita (scansione dei nomi in `schema_columns.txt`); blocco, invito ancora valido, nessun dato salvato |
| SR-014 | Minimizzazione dei dati dell'account; ultima visita solo per sé | DB, SEC | Le colonne di `account` coincidono con l'elenco ammesso; scansione ricorsiva di tutte le risposte per ruoli diversi: nessuna chiave `lastVisitAt` né valore canarino di altri (THR-112) |
| SR-015 | Classificazione dei dati | DB, PROC | Istantanea `schema_columns.txt` (obbliga all'aggiornamento); la classificazione è in `docs/05-data.md` (data-architect) |
| SR-016 | Esportazioni: solo richiedente, 24 h, formule neutralizzate | I, U, SEC | Download di un altro account → `404`; dopo 24 h (`age_export`) → `404` e file cancellato; celle che iniziano con `=`, `+`, `-`, `@`, tabulazione, ritorno a capo |
| SR-017 | Eliminazione dell'account | I, DB | Dopo l'eliminazione, scansione di tutte le colonne di testo e `bytea` di tutte le tabelle per nome ed email canarino: zero righe (SR-047); sessioni invalide. Backup entro 30 giorni: PROC |
| SR-018 | Eliminazione della famiglia | I | Dopo la scadenza (`age_family`), zero righe di quella famiglia in tutte le tabelle |
| SR-019 | Conservazione | I | Per ogni compito periodico: dati scaduti rimossi, dati recenti conservati, idempotenza, registro 12 mesi, inviti/job 30 giorni |
| SR-020 | Catalogo degli eventi di sicurezza | I, DB | Per ogni evento, almeno un test che lo produce (6.6); campi obbligatori; nessun evento con contenuti |
| SR-021 | Nessun segreto o contenuto nei log e nei registri; ritorni a capo | U, I, SEC | Test del processore di redazione; test canarino: eseguiti i flussi principali con valori canarino (token, segreti, email, nomi, note), nessuno compare nei log catturati (`caplog`, stdout) né in `security_event`/`change_event` |
| SR-022 | Cronologia immutabile e privata | DB, I | `UPDATE/DELETE` negati a `menu_app`; nessun endpoint di modifica; altra famiglia → `404` |
| SR-023 | TLS/HSTS, header, CSRF, CORS | SEC, PROC | Sezione 11 (header), 7.2 (CSRF); TLS e certificato della piattaforma: smoke su staging e checklist |
| SR-024 | Validazione, URL `http/https`, codifica in output | I, E2E | Sezioni 7.6 e THR-070 |
| SR-025 | Import CSV | U, I, PERF | UTF-8, 1 MB, 1.000 righe, riga per riga, nessuna formula interpretata, limite 5/ora, quota atomica; NFR-003 |
| SR-026 | Cache offline legata all'account e svuotata | E2E, U | Con service worker attivo: logout, `401`, rimozione dalla famiglia, eliminazione, cambio di account sullo stesso dispositivo → IndexedDB e cache vuote; nessun dato di un altro account |
| SR-027 | Residenza UE | CFG, PROC | Il file di deploy/configurazione contiene solo regioni UE (test su `deploy.yml`); DPA e regioni: P-4, P-10 |
| SR-028 | Cifratura a riposo, backup cifrato | I, PROC | Il backup prodotto da `Dockerfile.backup` inizia con l'intestazione `age`; nessun dump in chiaro su disco; cifratura del provider: P-4 |
| SR-029 | Solo dati sintetici | CFG, CI | Test sulle fixture e sui seed (email `@example.test`); `gitleaks` |
| SR-030 | Informativa breve | E2E, I, PROC | Mostrata all'ingresso (S-17, SL-16), resa senza HTML; la build di rilascio M1 fallisce se `privacy-v1.md` è `draft` (test sul controllo del deploy); testo: P-8 |
| SR-031 | Nessuno strumento di terzi | E2E, CI | Nessuna richiesta fuori origine (4.5); `connect-src 'self'`; ricerca di domini noti di analitica nel bundle |
| SR-032 | Avviso sui dati sanitari | E2E | Testo presente accanto a note piatto e nota ospiti |
| SR-033 | Validazione del token ID, bootstrap | SEC | THR-001; il bootstrap si lega all'email fino al primo login, poi al `sub`; scade dopo 7 giorni (`age_bootstrap`) |
| SR-034 (post-M2) | Nessuna unione automatica; registrazione con email esistente | I | Stessa risposta di una nuova, email informativa al titolare |
| SR-035 (post-M2) | Registrazione solo dentro un invito o un codice; non verificati cancellati dopo 7 giorni | I | Registrazione senza flusso → rifiutata; job di pulizia; limiti 254 e 128 |
| SR-036 (post-M2) | Robustezza del login con password | U, I | Controllo compromesse (servizio finto, solo prefisso a 5 caratteri), hash fittizio, ritardo progressivo con `age_counter`, email dopo reimpostazione |
| SR-037 | Sessione opaca ≥ 128 bit, hash, scadenze | U, SEC | Lunghezza del token, solo hash nel DB, 30/90 giorni (7.5) |
| SR-038 | Le mie sessioni | I, SEC | Elenco, revoca, effetto dalla richiesta successiva, sessioni altrui `404` |
| SR-039 | Riautenticazione entro 10 minuti | SEC | Per ogni operazione elencata (7.5) |
| SR-040 | Sicurezza del Gestore | DB, U, PROC | Ruolo `menu_console` senza lettura, evento per ogni comando; MFA e credenziali: P-5 |
| SR-041 | Identificativi del corpo della famiglia, stessa transazione | SEC, DB, CONC | Variante nel corpo (6.2), FK composite, nessuna scrittura parziale |
| SR-042 | Un solo livello di accesso ai dati, RLS, ID non sequenziali | ARCH, DB, CI | Test architettura (sessioni solo in `tenancy`), semgrep, inventario RLS; ID UUID v4 (formato) |
| SR-043 | Inviti e codici: `GET` non consuma, `POST` autenticata con CSRF, consumo atomico | I, CONC, SEC | Sezioni 9 e 11 (THR-030) |
| SR-044 | Mai `admin` da un invito | I, DB | `role=admin` → `422`; `INSERT` diretto con `owner` rifiutato dal `CHECK` |
| SR-045 | Collegamento profilo-account solo dopo conferma | I | Prima della conferma l'account non vede lo storico; dopo, sì; revoca del precedente |
| SR-046 | `no-store`, service worker `no-cache` | SEC, E2E | Header (sezione 11); cache del service worker non contiene `/api/` |
| SR-047 | Cronologia e registro solo con ID | DB, I | Canarini; scansione delle tabelle dopo una cancellazione (SR-017) |
| SR-048 | Registro delle cancellazioni e riapplicazione | I | Ripristino di un dump in un database nuovo, `maint replay-deletions`, idempotente, fusione con duplicati; l'account cancellato dopo il backup non esiste dopo il replay. Prova reale trimestrale: P-13 |
| SR-049 | Login senza famiglia non crea account | I, DB | Nessuna riga in `account`; `signup_pending` sparisce entro 24 h (`age_signup`) |
| SR-050 | Cancellazione per inattività | n/a | Fuori dall'MVP (backlog SL-91): test alla creazione della slice |
| SR-051 | Log 30 giorni, IP troncato dopo 90 giorni | I, CFG, PROC | Compito di troncamento con `age_event`; nessun IP completo nel log strutturato; bucket: P-7 |
| SR-052 | Registro dei trattamenti e DPA | PROC | Checklist di rilascio M1 (P-10) |
| SR-053 | Procedura di violazione e revoca globale | I, PROC | Comando `sessions revoke-all` (SL-24); procedura e simulazione: P-12, P-15 |
| SR-054 | Diritti degli interessati | I, PROC | Rettifica del proprio nome; contatto privacy: P-8 |
| SR-055 | Presenze, settimana tipo, ospiti mai in log, statistiche solo aggregate | SEC, DB | Canarini nelle note e nei conteggi; `console_stats_global` non accetta famiglia, non legge presenze o gusti, soglia `< 5` nascosta |
| SR-056 | Presa visione dell'informativa e nuova conferma | I, E2E | `privacyReviewRequired` blocca i dati fino alla conferma; versione e data registrate |
| SR-057 | Registro in sola aggiunta | DB | `UPDATE/DELETE/SELECT` negati a `menu_app`, trigger di immutabilità |
| SR-058 | Allarmi entro 15 minuti | U, PROC | Ogni soglia produce il log strutturato atteso (simulazione); metrica e notifica: prova su staging (devops, `docs/09-release.md`) |
| SR-059 | Valori dei limiti (SL-03b, e le slice che aggiungono le righe) | SEC | Sezione 7.4, un test per riga e per il riavvio |
| SR-060 | Limiti di richiesta e quote | SEC, CONC | Sezioni 7.6 e 9 |
| SR-061 (post-M2) | Email e dominio | I, PROC | Mittente finto; SPF/DKIM/DMARC: verifica DNS di rilascio (P-14) |
| SR-062 | Budget e degrado | CFG, PROC | `max-instances` e timeout nel file di deploy; budget: P-2 |
| SR-063 | Limiti su inviti e codici | CONC, I | Sezione 9 |
| SR-064 | Dichiarazione genitoriale | I, DB | Profilo senza dichiarazione rifiutato; `CHECK`; data e autore registrati |
| SR-065 | DPIA | PROC | Firma prima di M1 (P-9) |
| SR-066 | Recupero dell'Amministratore | DB, U, I | THR-050 |
| SR-067 | Esportazione da console | I, U | Perimetro del richiedente, output con ID e stato, payload con `family_id` estraneo ignorato |
| SR-068 | Riautenticazione sulla stessa identità | SEC | THR-008 |
| SR-069 | Respinta (CHG-009) | n/a | Nessun test |
| SR-070 | Limiti per account e famiglia, 20 sessioni (SL-03b) | SEC, I | Sezione 7.4 |
| SR-071 | Scadenza della cache offline a 7 giorni | E2E | `page.clock` avanti di 8 giorni: dati non mostrati e cancellati |
| SR-072 | Perimetro e ciclo di vita delle esportazioni | I, SEC | Download `family` solo se ancora Amministratore; declassamento o uscita cancella i file; nessuna email, ultima visita o sessione di altri nei file |
| SR-073 | Email visibile solo agli Amministratori | SEC | Scansione ricorsiva delle risposte per Pianificatore e Membro (chiavi e valori): nessuna email; solo per persone entrate con invito |
| SR-074 | MFA e igiene degli accessi del Gestore | PROC | Checklist P-5 |
| SR-075 | Hardening del database | DB, CFG, PROC | `rolconnlimit`, no `BYPASSRLS`, `verify-full` obbligatorio, revoche; impostazioni di Supabase: P-4, P-11 |
| SR-076 | Catena di fornitura | CI, CFG | Gitleaks, semgrep, trivy, osv-scanner, pip-audit, pnpm audit, zizmor, hadolint; test di configurazione su `exclude-newer`, `minimumReleaseAge`, `onlyBuiltDependencies`, digest delle immagini, SHA delle azioni |

## 13. NFR → verifica

| NFR | Verifica | Dove/quando |
|---|---|---|
| NFR-001 LCP ≤ 2,0 s | Lighthouse CI, `numberOfRuns=5`, profilo mobile predefinito (4G lenta simulata, CPU 4x), mediana, asserzione `largest-contentful-paint ≤ 2000` su piano, archivio, scheda, selettore. Dataset `lighthouse`. Budget bundle iniziale ≤ 150 KB gzip a ogni PR | notte e pre-rilascio; budget ogni PR |
| NFR-002 p95 ≤ 500/800 ms | Locust, 25 utenti, dataset `load`, 10 minuti, misura lato server | pre-rilascio (sezione 14) |
| NFR-003 import 1.000 righe | Anteprima ≤ 10 s, import ≤ 30 s | test `perf`, SL-44 |
| NFR-004 50 famiglie, 250 account | Stesso test di NFR-002 sul dataset `load`; quote | pre-rilascio |
| NFR-005, NFR-007 | `/healthz`: `200 {"status":"ok"}` con database raggiungibile, `503 {"status":"unavailable"}` con database fermo, `Cache-Control: no-store`, nessun dettaglio dell'errore nel corpo; esito tenuto in memoria per circa 5 s: raffiche di richieste entro la finestra eseguono un solo `SELECT 1` (contatore delle istruzioni), dopo la finestra l'esito si aggiorna (tempo simulato nella cache, THR-106; SL-00a/SL-00b); errore 5xx forzato su staging e allarme entro 15 minuti | integrazione; processo P-7 |
| NFR-006 | Dump → ripristino in database nuovo → replay delle cancellazioni (SL-27); prova reale trimestrale | integrazione; P-13 |
| NFR-008 | axe su tutte le viste e stati (sezione 15) + verifica manuale | ogni PR; pre-rilascio |
| NFR-009 | Chromium mobile 360 px a ogni PR (nessuno scorrimento orizzontale: `scrollWidth ≤ innerWidth`); matrice Chrome, Firefox, Edge, WebKit (Safari iOS emulato) di notte; ultime 2 versioni stabili; Safari iOS reale: manuale | PR; notte; pre-rilascio |
| NFR-010 | Controllo di installabilità di Chrome (CDP `Page.getInstallabilityErrors`, manifest valido, service worker); Safari iOS "Aggiungi a Home": manuale | e2e SL-43; pre-rilascio M2 |
| NFR-011 | `lingui extract` senza differenze, `compile --strict`, `no-unlocalized-strings`; test Intl nel fuso della famiglia; test di copertura delle chiavi | ogni PR |
| NFR-012a | E2E con helper `countInteractions()` (tocchi/selezioni, digitazione esclusa): assegnare un piatto ≤ 3 | SL-06b |
| NFR-012b | Test di usabilità con il Pianificatore: manuale | P-12 |
| NFR-013 | E2E per ogni vista: stato vuoto con messaggio e azione, caricamento (risposta ritardata), errore con "Riprova" (risposta `500`) | ogni slice con viste |
| NFR-014 | Test di configurazione: nessuna variabile o import specifico di un provider fuori dal modulo di configurazione | CFG |
| NFR-015 | Inventario `x-authz` e `openapi.json` | ogni PR |
| NFR-016 | Regioni nel deploy (CFG), verifiche P-4 e P-7 | CFG; processo |
| NFR-017 | Misura reale dello spazio con `load` (SL-10, SL-27), valori in `docs/05-data.md` §14; allarme al 70% con soglia di prova | SL-10, SL-27 |

## 14. Prestazioni, carico e Lighthouse

### 14.1 Carico (NFR-002, NFR-004)
- **Strumento:** Locust, gruppo di dipendenze `perf`, uno scenario scritto in Python (come lo stack) e riusabile. Alternativa k6 (un binario in più, nessun vantaggio per 25 utenti): scartata.
- **Scenario:** 25 utenti concorrenti su famiglie del dataset `load`, ciascuno col proprio account e con CSRF; durata 10 minuti dopo 1 minuto di riscaldamento. Miscela indicativa: 85% letture (piano della settimana, ricerca nell'archivio, scheda piatto, pasto, cronologia), 15% scritture (contenuto del pasto con `If-Match`, presenza, ospiti, gusto). Le scritture sono su famiglie diverse da quelle delle letture di verifica per non generare `412` voluti.
- **Misura:** p95 *lato server* dai log delle richieste (`httpRequest.latency` su Cloud Run in staging, istogramma dei tempi dell'app in locale), perché NFR-002 parla di tempo di risposta del server; il tempo lato client si riporta come informazione. Soglie: letture ≤ 500 ms, scritture ≤ 800 ms, errori 5xx = 0, `429` inattesi = 0 (i limiti di SR-059 non devono scattare con il traffico normale di 25 utenti: 300/min per sessione).
- **Dove (D-T2 deciso):** il valore ufficiale si misura **solo su staging**: un secondo progetto Supabase Free e un servizio Cloud Run `menu-staging` che scala a zero, con dati esclusivamente sintetici. Le regressioni relative girano in locale contro il container con PostgreSQL 17. La misura su staging consuma quote gratuite e connessioni (SR-062, `CONNECTION LIMIT`): si lancia in una finestra concordata, si interrompe se gli errori superano l'1%, si riportano le metriche del fornitore. Il servizio staging ha un proprio ruolo di database e propri segreti, mai quelli di produzione.
- **Regola dei dataset (vincolante):** i dataset sintetici `load` e `lighthouse` (e `isolation`) **non vanno mai caricati in produzione**. `seed.py` ha una guardia: è una **allow-list, non una deny-list**: parte solo se `APP_ENV` vale esattamente `dev` o `staging`; qualunque altro valore, assente o vuoto (`production`, `prod`, `test`, `Production`) è rifiutato, e il test è parametrizzato su questi valori. In più l'host del database deve essere nell'allow-list di sviluppo/staging (`SEED_ALLOWED_DB_HOSTS`) e `SEED_TARGET` deve valere esplicitamente `local` o `staging`; la guardia ha test (con `APP_ENV=production` esce con codice ≠ 0 senza connettersi, e lo stesso con l'host del database di produzione) e una regola `.semgrep/` che vieta di aggirarla. **Caricamento dei dataset nei test (`APP_ENV=test`):** le fixture (`isolation`, `minimal`) chiamano direttamente la **libreria di caricamento** (`menu.seeding.datasets`, funzioni `load_isolation(conn)` ecc.) sul database di test con l'helper `owner`; il comando `seed`, con la guardia, è un punto d'ingresso separato che i test **non usano mai**. Test: `python -m menu seed --dataset isolation` con `APP_ENV=test` esce con codice ≠ 0 senza connettersi, e un test d'architettura verifica che nessun file sotto `tests/` importi il modulo del comando. `seed.py` è ora scritto da backend-developer e tester insieme (SL-10a); la guardia è un requisito di accettazione.
- **Avvio a freddo** riportato a parte (non nel p95 dei 10 minuti).

### 14.2 Regressioni di prestazione in `make ci` (senza carico)
- **Conteggio delle istruzioni SQL** per richiesta con un contatore di eventi SQLAlchemy: `GET /plan` con 62 giorni sul dataset `isolation` esegue un numero costante di istruzioni (nessun N+1) e al massimo un limite dichiarato nel test.
- **Dimensione della risposta** di `GET /plan` 62 giorni con presenze entro il limite dichiarato (NFR-002, Q2 di `docs/05-data.md` §8).
- **Piano di esecuzione:** per le query principali (`GET /dishes` con ricerca e ordinamento, `effective_meals`, `effective_attendance`, cronologia) un test `EXPLAIN` sul dataset `load` verifica l'uso degli indici `(family_id, …)` (nessun `Seq Scan` sulle tabelle grandi), senza asserire i tempi.

### 14.3 Lighthouse (NFR-001, CHG-018)
- `@lhci/cli` con `numberOfRuns=5` e asserzione sulla **mediana** del LCP ≤ 2.000 ms, per piano, archivio, scheda del piatto e selettore, profilo mobile predefinito (rete 4G lenta simulata, CPU rallentata 4x) con il dataset `lighthouse` (500 piatti, 8 persone).
- Chrome headless con la stessa versione di Chromium di Playwright. Login tramite lo stub OIDC e cookie impostati prima del test.
- **Notturno e prima di ogni rilascio; mai sulle PR** (ADR-0001, OBJ-08). Il risultato notturno **non blocca** le PR: genera un allarme (CHG-018). Il risultato pre-rilascio è il valore ufficiale, misurato **su staging** (dopo il caricamento del dataset `lighthouse` con la guardia di 14.1), perché la rete reale conta.
- Parte dalla slice SL-06a (prima vista principale), con il dataset di SL-10a. Prima di SL-10a si usa il dataset `minimal` ingrandito, solo per tendenza.

### 14.4 Altri NFR misurabili
NFR-003: `perf` con CSV da 1.000 righe. NFR-005/007: smoke periodico dopo ogni deploy; il controllo di disponibilità reale è del fornitore (P-7).

## 15. Accessibilità (NFR-008, WCAG 2.2 AA)

- **Automatica:** `@axe-core/playwright` in ogni test e2e di vista, con i tag `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`. Fallisce se ci sono violazioni **serious** o **critical**; `moderate` e `minor` vanno nel report come avvisi. Funzione comune `expectNoSeriousA11y(page)` in `web/tests/e2e/support`.
- **Dove:** per ogni vista (S-01 … S-20 e banner B-01 … B-03) negli stati vuoto, caricamento, errore e normale; con finestre aperte (conflitto D-01, selettore, conferme, avviso del passato); a 360 px e a 1280 px; con `prefers-reduced-motion`.
- **Controlli programmatici in più** (axe non li copre): ordine del focus dopo l'apertura e la chiusura di dialoghi (il focus torna all'elemento che li ha aperti), operabilità con sola tastiera dei flussi US-008, US-021, US-024 (Tab, Invio, Spazio, Esc), nome accessibile di ogni controllo, lingua `it` nel documento, bersagli di tocco ≥ 24 px (WCAG 2.2 2.5.8), zoom 200% senza perdita di contenuto.
- **Manuale (non automatizzabile, a cura dell'utente):** VoiceOver su iOS e TalkBack su Android sui flussi US-008, US-021, US-024 (NFR-008, P-12) prima del rilascio M1. Il tester prepara la checklist e la registra in `docs/09-release.md`. Axe rileva circa un terzo dei problemi di accessibilità: l'esito verde non sostituisce la verifica manuale.

## 16. Soglie e qualità dei test

### 16.1 Soglie (bloccanti in CI)

| Misura | Soglia | Note |
|---|---|---|
| Copertura dei requisiti | **100% degli AC di ogni slice** con almeno un test che li cita e passa | Controllo di 17.3; regola di DoD |
| Backend, copertura di riga (`pytest-cov`, unit+integrazione+sicurezza) | ≥ 85% globale, branch ≥ 75% | Pavimento, non obiettivo |
| Moduli critici (`access`, `tenancy`, `identity`, `ratelimit`, `history`, `audit`, `console`, `privacy`, `platform/http`) | riga ≥ 90%, branch ≥ 80% | Si aggiungono man mano che le slice li creano |
| Funzioni SQL dello schema `app` | 100% eseguite da almeno un test (somma dei worker; elenco chiuso delle inlinabili con chiamata diretta) | 6.7, in `make full` |
| Frontend (`@vitest/coverage-v8`) | riga ≥ 80%, branch ≥ 70%; `src/lib` e `src/api/errors.ts` ≥ 95% | |
| E2E | ogni vista con stati vuoto/caricamento/errore (NFR-013) e un controllo axe | Checklist per vista nel report di slice |
| Inventari | `cross_family`, `tracks`, RLS, `SECURITY DEFINER`, authz, `ErrorCode`, funzioni SQL | zero differenze |
| Test saltati/atteso-fallire | zero senza motivo scritto; `xfail_strict = true`; `--strict-markers` | Un `skip` richiede un motivo e un riferimento a un debito tecnico in `docs/STATUS.md` |
| Bundle iniziale | ≤ 150 KB gzip | NFR-001 |
| Test instabili | zero sulla linea principale | Se un test fallisce una volta su 20 ripetizioni si ripara |

La copertura di riga è un pavimento per accorgersi dei buchi, non una prova di qualità: la qualità la dicono AC, inventari e prove negative. Le soglie si rivedono a G6 e non si abbassano senza una nota in `docs/STATUS.md`.

### 16.2 Qualità dei test (controllo del modo C)
Per ogni slice, il tester controlla che:
- non ci siano test che passano sempre: asserzioni presenti e specifiche (nessun `assert True`, nessun `except: pass`, nessun test senza `assert`/`expect`); regole `PT` di ruff e `no-conditional-expect` di ESLint; una verifica a campione "rompo il codice, il test deve diventare rosso" sui moduli critici;
- i mock non nascondano il comportamento sotto test: nel backend si mocka solo Google, posta e tempo; mai il database, mai `access`, mai `tenancy`; nel frontend MSW risponde con i tipi del client generato e un test controlla che le risposte simulate rispettino lo schema OpenAPI;
- nessun test salti senza motivo;
- i test non dipendano dall'ordine (l'ordine casuale lo scopre) né dall'orologio o dalla rete;
- gli identificativi di test e fixture non siano dati reali.

## 17. Flusso del tester in ogni slice

### 17.1 Modo B: test prima dell'implementazione ("rosso per il motivo giusto")
1. Il backend-developer consegna il passo *contract-first* (modelli, rotte vuote che rispondono `501`, `openapi.json`). Senza contratto, il tester risponde `BLOCKED` con le domande.
2. Il tester scrive: un test per ogni `AC-NNN.n`; i negativi (401, 403, 404 cross-family, 412, 428, 413/415/422, 429, concorrenza); i test di sicurezza dei THR/SR della slice; le righe di `authz_matrix.yaml` e `request_builders`; aggiorna `tests/ac_map.yaml` (slice → AC).
3. Esegue la suite **intera** e riporta: numero di test raccolti e falliti, elenco dei fallimenti raggruppati per causa.
4. **Criterio "rosso giusto":** i fallimenti devono essere asserzioni su comportamenti mancanti (`501`, `404` dove si attende `200`, tabella assente per una migrazione ancora da scrivere). Non sono accettabili: errori di importazione, database non raggiungibile, fixture rotta, `fixture not found`. Il segnale di salute è un test `test_environment_sanity` nella stessa esecuzione, che deve passare e dimostra che database, ruoli, stub OIDC e fixture funzionano.
5. Nessun codice di produzione.

### 17.2 Modo C: verifica dopo l'implementazione
1. Esegue la **suite intera**, ruff, `ruff format --check`, mypy `--strict`, `pnpm lint`, `tsc`, `vitest`, e2e, inventari; allega l'output.
2. Produce la tabella **AC → test → esito** (17.3).
3. Controlla la qualità dei test (16.2) e le soglie (16.1).
4. **Prova a rompere il sistema** (esplorazione mirata): confini dei campi, Unicode, date a cavallo di mezzanotte e di cambi d'ora, doppio invio, doppio clic, richieste ripetute, ordine degli eventi, rete lenta (e2e), sessione scaduta a metà operazione, ruoli cambiati in corsa, risposta `500` nel mezzo di una scrittura (nessun evento, nessuna scrittura parziale). Ogni bug trovato diventa un test che lo riproduce e una segnalazione `TST-SLNN-NNN` nel report.
5. Segnala sul report di slice quali verifiche sono **UNVERIFIED** perché lo strumento manca (sezione 19).

### 17.3 Tracciabilità AC → test → esito
- `tests/ac_map.yaml`: per slice, l'elenco degli AC (da `docs/07-plan.md` §7 e §10.1), mantenuto dal tester.
- `backend/tests/tools/ac_report.py`: cerca gli ID nei nomi e nelle docstring dei test Python, nei `describe/it` di Vitest e nei titoli di Playwright; unisce i risultati dei report JUnit (`pytest --junitxml`, Vitest `--reporter=junit`, Playwright `--reporter=junit`); stampa la tabella `AC | test | esito` ed esce con errore se un AC non ha test o non ha un esito verde. Un AC che si completa in un'altra slice è marcato nella mappa come tale, con il perimetro verificato in ciascuna. Esempio (OBJ-09): **AC-001.1** è verificato in SL-03a per il reindirizzamento a `/piano` e per la sessione (cookie, `GET /session`); la parte end-to-end sul piano completo si chiude in SL-06a (`ac_map`: `AC-001.1: {SL-03a: "redirect /piano + sessione", SL-06a: "e2e con il piano"}`). L'AC conta come coperto solo quando tutte le parti sono verdi, e il report di SL-03a lo dichiara "parziale".
- Un test che cita un AC inesistente fa fallire il controllo (refusi).

## 18. Cosa gira dove

### 18.1 Livelli di esecuzione (OBJ-06)

Finché non gira una CI remota (ogni push richiede il consenso dell'utente; le evidenze restano quelle del `make ci` locale, e i minuti gratuiti di GitHub Actions sono limitati) i comandi sono quelli del Makefile e si eseguono a mano o dall'agente. Il lavoro si divide in tre livelli.

| Livello | Comando | Quando | Contenuto | Durata obiettivo |
|---|---|---|---|---|
| **Per slice** | `make ci` | a ogni slice (modi B e C) e a ogni PR | Lint, format, mypy, bandit; **unit, architettura, db, integrazione, sicurezza, contratto**; e2e **della slice** (Chromium mobile 360 px e desktop) con axe e regressione dei flussi principali; **concorrenza ×3**; proprietà con profilo ridotto (`ci-small`: 20 esempi); migrazioni: **solo la nuova revisione** (`upgrade → downgrade -1 → upgrade`) più `downgrade base` ↔ `upgrade head`; inventari; copertura e soglie; `openapi.json` senza differenze; frontend (eslint, prettier, tsc, vitest, lingui, client generato, build, budget bundle); scansioni installate (gitleaks, semgrep, pip-audit/osv-scanner/pnpm audit, trivy, hadolint, zizmor) | ≤ 15 minuti |
| **Per milestone e pre-rilascio** | `make full` | fine di M0, M1, M2 e prima di ogni rilascio | **Tutto**: scala completa delle migrazioni (ogni revisione), proprietà `ci` (50 esempi) e `nightly` (500), concorrenza ×200, matrice completa dei browser, Schemathesis, inventari globali (eventi di sicurezza mai prodotti, 6.6; funzioni SQL mai eseguite, 6.7), confronto statistico dei tempi (SR-004), scansioni complete. `make full` è **solo locale**: i controlli su staging e la checklist di 18.3 appartengono unicamente a `make prerelease`, quindi la chiusura di M1 (`make full` locale verde) non aspetta mai passi dell'utente | lungo, accettato |
| **Periodico** | `make nightly` | **passo obbligatorio del modo C almeno ogni 5 slice** e a ogni milestone, finché non gira una CI remota; dopo, solo nei giorni con commit | Lighthouse (mediana di 5) sul dataset `lighthouse` locale (tendenza, allarme, non blocca), matrice completa dei browser, proprietà `nightly`, concorrenza ×200, Schemathesis, scansioni con database aggiornati (nuove CVE su dipendenze invariate), inventari globali | lungo |

**Livelli attivati (`CI_TIERS`, piano v3 §6.1).** `scripts/ci.sh` costruisce `make ci` da un elenco esplicito `CI_TIERS` che ogni slice estende quando introduce un livello, e l'output di `make ci` dichiara quali livelli ha eseguito. Un target segnaposto fallisce con messaggio esplicito solo se chiamato direttamente; non è mai incluso in `make ci` finché la sua slice non lo attiva. Sequenza (confini decisi dal piano): **SL-00a** `lint`, `unit` (con architettura), `contract`, `scan`; **SL-00b** `db` con `integration`, `security`, `property` (`ci-small`), `concurrency` ×3 e migrazioni, più `container`; **SL-01** `web` ed `e2e` (con axe). I livelli di test sicurezza/integrazione/proprietà/concorrenza esistono quindi da SL-00b: le suite sono quasi vuote all'inizio e si riempiono slice dopo slice (non c'è un'attivazione successiva con SL-03a o SL-09). Il test `tests/tools/test_ci_tiers.py` confronta `CI_TIERS` con la tabella delle slice di `docs/STATUS.md` (ogni livello di una slice DONE è attivo, nessuno prima della sua slice). Un riepilogo di `make ci` che non elenca i livelli eseguiti non è accettato come evidenza di slice. **M2 inizia solo a M1 chiusa**: SL-27 dipende da tutte le altre slice di M1 e da SL-10b; il `make full` di M1 verde è la condizione di chiusura. Lo staging si distribuisce su richiesta e obbligatoriamente prima di ogni rilascio (piano §6.3, scelta B), non a ogni push.

Con il remoto: `ci.yml` esegue `make ci` su PR e push su `main`; `nightly.yml` esegue `make nightly` condizionato a commit nelle ultime 24 ore (salta nei giorni senza commit per risparmiare minuti). I test `slow` (scala completa, proprietà estese) restano fuori dalla PR. Esecuzione parallela con `pytest-xdist`.

### 18.2 Contenuto della notte (`make nightly`)
Vedi la riga "Periodico" sopra. Il risultato Lighthouse notturno non blocca nulla (CHG-018). Le scansioni di dipendenze e immagini non sono un sostituto di quelle bloccanti di `make ci`.

### 18.3 Pre-rilascio (modo D, prima di G7; per ogni milestone)
`make full` più `make prerelease URL=<staging>` (che attende `/healthz` = 200 e si ferma con messaggio chiaro se staging è in pausa; poi smoke, Lighthouse, carico e ZAP contro **staging**, mai contro produzione) e una checklist registrata in `docs/09-release.md`:

| Controllo | M0 | M1 | M2 |
|---|---|---|---|
| Suite completa di PR + notte (verde, con evidenza) | sì | sì | sì |
| Regressione e2e dei flussi principali (login, archivio, piano, assegnazione, correzione del passato) | sì | + inviti, presenze, ospiti, cronologia, esportazione, recupero | + riautenticazione, eliminazioni, password, offline |
| Smoke su **staging** (`/healthz` 200 con corpo atteso, **test degli header di sicurezza** di §11 sulle classi di risposta raggiungibili senza dati (`200` pubblica, `401`, `404`, statici, `index.html`, `sw.js`), login con account di prova, `X-Forwarded-For` V-3, job non invocabili da anonimo) | sì | sì | sì |
| Lighthouse (mediana di 5) su **staging**, dataset `lighthouse` caricato con la guardia di `seed.py` | sì | sì | sì |
| Carico NFR-002/NFR-004 su **staging** (dataset `load`, con la guardia) | misura di base | sì (con presenze) | sì |
| Compatibilità con il codice precedente (10.5) | – | sì | sì |
| ZAP baseline contro **staging** | – | **sì** (piano §6) | sì |
| Prova di ripristino e replay delle cancellazioni (NFR-006) | primo backup | sì | sì |
| Verifica manuale accessibilità (VoiceOver, TalkBack) | – | **sì** (US-008, US-021, US-024) | sì |
| Test di usabilità NFR-012b (utente) | – | sì | – |
| Installabilità PWA e Safari iOS | – | – | sì |
| Controlli di processo (P-x del piano §8.3) con evidenza | P-1 … P-7 | P-8 … P-12 | P-14, P-15 |
| Build fallita se l'informativa è `draft` | – | sì | sì |

### 18.4 Manuale
Accessibilità con lettori di schermo, usabilità (NFR-012b), Safari iOS, ripristino reale trimestrale, checklist di processo. Il tester prepara script e checklist; l'utente o il devops eseguono e registrano l'esito.

### 18.5 Prova manuale della shell
`make run-web` builda la SPA (con il controllo del budget) e la serve con FastAPI su `http://127.0.0.1:8000/` (porta con `WEB_PORT=...`). Usa un database fittizio, come la configurazione Playwright: serve a vedere shell, navigazione e i18n, non le route che leggono dati. Non fa parte di nessun livello di `make ci`.

## 19. Strumenti mancanti in locale (verificato il 2026-10-19)

| Strumento | Serve a | Stato | Effetto sulle evidenze | Rimedio |
|---|---|---|---|---|
| **Docker** | PostgreSQL 17 per tutti i test di database/integrazione/sicurezza/proprietà; e2e; trivy image; ZAP | Il binario appare nel `PATH` ma punta a Docker Desktop su Windows, e `docker version` risponde che l'integrazione WSL non è attiva | **Bloccante**: senza PostgreSQL 17 reale non si eseguono i livelli DB, integrazione, sicurezza, proprietà, concorrenza, migrazioni, e2e. Evidenza di slice = `UNVERIFIED` | Attivare l'integrazione WSL di Docker Desktop (P-0). In alternativa, PostgreSQL 17 nativo in WSL (richiede `sudo`) con `unaccent` e `pg_trgm`; non si accettano sostituti (SQLite, mock) per i test di RLS |
| **uv** | Ambiente Python, lockfile, `pytest` | Mancante (Python 3.14.4 presente) | Nessun test Python eseguibile con l'ambiente previsto; un `venv` temporaneo non produce evidenza di slice | `pipx install uv` o script ufficiale (P-0) |
| **pnpm** | Vitest, Playwright, Lighthouse | Mancante (Node 24.18 presente) | Nessun test del frontend | `corepack enable` (P-0) |
| **Browser di Playwright** | e2e e axe | Da scaricare dopo `pnpm install`; le dipendenze di sistema possono richiedere `sudo` (`playwright install --with-deps`) | e2e non eseguibili | Passo di P-0 |
| **psql** | Controlli manuali del DB | Mancante | Nessuno per la suite (usa psycopg); utile per il debug | `sudo apt install postgresql-client-17` |
| gitleaks, semgrep, trivy, osv-scanner, pip-audit, bandit, zizmor, hadolint | Job di sicurezza della pipeline | Mancanti | I controlli di pipeline restano `UNVERIFIED` in locale: nessuna affermazione "scansione pulita" | Installazione come in `docs/STATUS.md` e `docs/06-threat-model.md` §11 |
| Locust, Lighthouse, ZAP | Carico, LCP, DAST | Non installati (arrivano con le slice) | Rilevanti dal rilascio M0 | Gruppo `perf`; `@lhci/cli`; immagine ZAP (richiede Docker) |

Regola: finché uno strumento manca, il report della slice indica **cosa non è stato eseguito e perché** e lo stato è `UNVERIFIED`, non "verde". Non si fa passare per evidenza l'esecuzione di un sottoinsieme.

## 20. Incoerenze, domande e decisioni

### 20.1 Incoerenze trovate nei documenti di altri ruoli (da correggere dai proprietari)

| ID | Documento | Problema | Proposta | Proprietario | Prima di |
|---|---|---|---|---|---|
| I-T1 | `docs/07-plan.md` §5.5 (orologio) | "Oggi" si simula con un parametro letto da `app.family_today()` "solo quando la configurazione è `test`": nel codice SQL di produzione resta un gancio di test, e `menu_app` può già eseguire `set_config`, quindi la condizione non è una vera barriera. | Funzione `app.now_utc()` (restituisce `now()`), usata ovunque al posto di `now()`; solo i test la sostituiscono con `CREATE OR REPLACE` via `menu_owner`. Nessun gancio in produzione. **Deciso (D-T1).** Il piano §5.5 va aggiornato. | tech-lead, data-architect | SL-02 (prima funzione con tempo) |
| I-T2 | `docs/07-plan.md` §6, riga `nightly` | Lighthouse parte da SL-06a, ADR-0001 dice "dalla prima slice con UI" (SL-01/SL-03). | Accettabile: S-01 e S-08 non sono viste principali. Segnare nel piano che SL-01 ha solo il budget del bundle. | tech-lead | – |
| I-T3 | `docs/07-plan.md` §6 / §5.5 e `docs/06-threat-model.md` §11 | Il piano indica ZAP baseline "prima del rilascio M1" e `dast` come passo di rilascio; il threat model lo chiede anche "nell'audit (G6)". ZAP richiede Docker e uno staging. | Aggiungere nel piano il DAST anche per G6; staging disponibile solo dopo P-4/P-2. | tech-lead, devops | rilascio M1 |
| I-T4 | `docs/07-plan.md` §4.1 | Il contratto non dice cosa succede con `If-Match` malformato (`abc`, `*`, `W/"3"`, negativo). | **Deciso (Q-T1):** `422 invalid_value`; il piano §4.1 va completato. | tech-lead | SL-04 |
| I-T5 | `docs/02-requirements.md` SR-059 vs SR-070 e `docs/07-plan.md` SL-03/SL-05 | Due limiti simili con ambiti diversi: "300/min per sessione, di cui 60 scritture" (SR-059) e "60 scritture/min per account" (SR-070). Sono compatibili, ma SL-03 realizza il primo e SL-05 il secondo: tra le due slice un account con più sessioni può superare 60 scritture/min in totale. | Nessuna correzione; i test coprono entrambi (7.4). Solo una nota. | tech-lead | – |
| I-T6 | `docs/07-plan.md` §1 | Il Makefile prevede solo `dev, test, lint, ci, openapi, seed`. | Aggiungere `test-unit`, `test-db`, `test-int`, `test-sec`, `test-prop`, `test-conc`, `test-contract`, `e2e`, `lighthouse`, `perf`, `smoke`, `nightly`, `prerelease`, `dast` (sezioni 2 e 18). `make test` = unit + db + int + sec + prop (profilo ci) + conc + contract. | tech-lead, devops | SL-00 |
| I-T7 | `docs/04-architecture.md` §Stack ("Test del frontend: decide il tester") | Scelta ora fatta: Vitest, Testing Library, MSW, Playwright, axe, Lighthouse CI, più Locust per il carico. | Aggiornare la riga dopo G4. | architect | – |

### 20.2 Domande e decisioni risolte (G4)

| ID | Esito |
|---|---|
| Q-T1 | **Deciso:** `If-Match` malformato o `*` → `422 validation` (`invalid_value`); assente → `428`. Test in 7.3. |
| Q-T2 | **Deciso:** `/healthz` è `scope: public` nell'elenco chiuso delle rotte pubbliche (6.8). |
| Q-T3 | **Deciso:** i finding del tester usano `TST-SLNN-NNN`. |
| D-T1 | **Deciso (b)+(c):** `app.now_utc()` sostituibile solo nei test via `menu_owner`, scadenze con spostamento dei dati, test dopo `upgrade head` che `now_utc() = now()` (4.4). Chiude I-T1 lato test; la parte SQL (default, policy, viste) spetta a data-architect e tech-lead. |
| D-T2 | **Deciso:** misure ufficiali su staging (secondo Supabase Free + Cloud Run `menu-staging`, solo dati sintetici); regressioni locali; guardia di `seed.py` contro i dataset sintetici in produzione (14.1). |
| Evidenza | Resta il `make ci` locale: il repository remoto esiste ma ogni push richiede il consenso dell'utente. |

### 20.3 Allineamento al piano v2 (2026-10-20)
- Suddivisioni adottate: SL-00a (CI e scansioni) e SL-00b (database, migrazione `0001` con `now_utc`, scansione del container); SL-03a (OIDC, sessioni, CSRF) e SL-03b (SR-059, SR-070, S-08, AC-001.9); SL-23a (coda, job, perimetro) e SL-23b (download, cancellazione). S-13 (settimana tipo) è in SL-15 e S-17 (informativa) in SL-16. SL-33 e SL-34 sono post-M2.
- Email e password rinviate: SR-002, 006, 034, 035, 036, 061 e THR-122 sono marcati "post-M2" e non entrano in nessuna esecuzione.

## 21. Tracciabilità

- **Requisiti:** NFR-001 … NFR-017 (sezione 13), SR-001 … SR-076 (sezione 12), AC di ogni slice (sezione 17.3, `tests/ac_map.yaml`), FR/US coperti attraverso gli AC.
- **Piano:** §5.5 (vincoli di test), §6 (pipeline), §7 (slice), §10 (matrice). Le slice che introducono ciascun inventario sono SL-00a (authz, header, redazione dei log, rotte pubbliche), SL-00b (RLS, `SECURITY DEFINER`, `now_utc`, `/healthz`), SL-02 (prima RLS reale, funzioni console), SL-05 (`tracks`), SL-09 e SL-14 (proprietà R-07), SL-10a (dataset e misura dello spazio) e SL-10b (test di staging, WIF ed environment), SL-31 (`pendingDeletion`).
- **Threat model:** THR alti e critici (sezione 11), §10.5 (prove richieste), §11 (pipeline).
- **ADR:** ADR-0003 (RLS e ruoli), ADR-0004 (sessioni), ADR-0006 (limiti), ADR-0007 e ADR-0009 (passato congelato), ADR-0008 (`If-Match`), ADR-0010 (`ErrorCode`), ADR-0011 (console), ADR-0012 (codec), ADR-0013 (worker), ADR-0016 (rischio accettato).
