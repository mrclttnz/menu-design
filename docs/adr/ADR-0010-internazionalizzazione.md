# ADR-0010: Internazionalizzazione nel frontend con Lingui e ID espliciti, server che restituisce solo codici

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-19. Precisazione G4 dello stesso giorno: `If-Match` malformato (Q-T1), `/healthz` fuori contratto (Q-T2) e nuovo codice `dish_not_planned`. Precisazione del 2026-10-20 (piano v3 §11.3): esito `already_in_family`, `units[]` nel `412` su più unità, nuovo codice `course_in_use`.
  - revisione 2: backend Python;
  - revisione 3: enumerazione `ErrorCode` completa;
  - revisione 4: `reauth_wrong_account`;
  - revisione 5: questo ADR è la **fonte unica** di codici e parametri (OBJ-06), con gli esiti di autenticazione (OBJ-04) e il limite di "Altro pasto" attivi.
- **Decisori:** architect. Revisione della UX.
- **Requisiti collegati:** NFR-011, FR-055, FR-068, SR-021, SR-030, SR-061, ASM-025, Q-014, visione ("i18n fin da M0")

## Contesto
In M0 l'interfaccia è solo in italiano, ma:
- il 100% dei testi deve stare in file di risorse per lingua;
- la CI deve fallire se trova testo dell'interfaccia nel codice;
- date, ore e numeri vanno formattati per lingua, locale e fuso della famiglia;
- aggiungere una lingua deve richiedere solo nuovi file;
- i contenuti degli utenti non si traducono.

La visione chiede "nessun testo italiano scritto direttamente nel codice", quindi i messaggi usano **ID espliciti**. Con il backend in Python (ADR-0002), tutti i testi dell'interfaccia stanno nel frontend.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Controllo automatico in CI dei testi nel codice | 5 |
| Supporto ICU (plurali, selezioni, formattazione) | 4 |
| Esperienza di sviluppo | 4 |
| Maturità | 4 |
| Peso sul bundle (NFR-001) | 3 |

## Opzioni considerate (libreria del frontend)
| Criterio | A: Lingui 6 + `eslint-plugin-lingui` | B: react-i18next 17 + `eslint-plugin-i18next` | C: FormatJS (react-intl 12) + `eslint-plugin-formatjs` |
|---|---|---|---|
| Controllo in CI (5) | 5 | 4 | 4 |
| ICU (4) | 5 | 3 | 5 |
| Esperienza (4) | 4 | 4 | 3 |
| Maturità (4) | 4 | 5 | 5 |
| Bundle (3) | 5 | 3 | 3 |
| **Totale pesato** | **92** | **77** | **81** |

Versioni verificate il 2026-10-18: `@lingui/core` e `@lingui/react` 6.10.0, `eslint-plugin-lingui` 0.16.0, react-i18next 17.1.0, react-intl 12.1.4, `eslint-plugin-formatjs` 8.1.1.

## Decisione
**Opzione A** per il frontend. Il server non produce testi per l'interfaccia.

### Frontend
- **Cataloghi:** `web/src/locales/<lingua>/messages.po` in formato ICU, con ID semantici (`plan.empty.title`) e regola `lingui/require-explicit-id`. Il testo italiano sta solo nel catalogo `it`.
- **Controlli in CI (bloccanti):**
  - ESLint con `lingui/no-unlocalized-strings` sul codice della UI (JSX e attributi `aria-label`, `title`, `alt`, `placeholder`), con eccezioni solo per valori tecnici;
  - `lingui extract` senza differenze rispetto al catalogo committato;
  - `lingui compile --strict`.
- **Lingue:** ricavate dalle cartelle dei cataloghi al momento della build. Aggiungerne una non richiede modifiche al codice. Nell'MVP la lingua è `it` con il locale `it-IT`.
- **Contenuti lunghi** (informativa e sintesi delle condizioni, FR-068): file per lingua e versione (`content/it/privacy-v1.md`), resi senza HTML grezzo.
- **Formattazione:** solo con `Intl` e ICU, con locale e `timeZone` della famiglia (ADR-0009).

### Messaggi d'errore dell'API (come si localizzano)
- **Formato:** il server risponde con RFC 9457 `application/problem+json` e campi stabili, non testi:
  - `code`: enumerazione `ErrorCode` del backend, esposta in OpenAPI (vedi la tabella "Enumerazione `ErrorCode`" qui sotto);
  - `params`: valori da interpolare, per esempio `retryAfterSeconds`, `deletionDate`, `modifiedBy` (ID), `modifiedAt`;
  - per `validation`, un elenco `errors[]` con `field` (percorso JSON), `code` e `params`. Il gestore di `RequestValidationError` di FastAPI traduce gli errori Pydantic (`type` e `ctx`, per esempio `string_too_long` con `max_length`) nei nostri codici stabili, così un aggiornamento di Pydantic non cambia il contratto.
- **Campi testuali:** `title` e `detail` restano in inglese tecnico e generico. Servono agli sviluppatori e ai log, **non vengono mai mostrati** all'utente e non contengono dati (SR-021).
- **Frontend:**
  - mappa `code` → ID di catalogo (`error.conflict`, `validation.string_too_long`) e interpola `params` con ICU;
  - un `code` sconosciuto produce il messaggio generico `error.generic`;
  - un test verifica che ogni valore dell'enumerazione `ErrorCode` di OpenAPI abbia un ID nel catalogo `it`.
- **Enumerazione `ErrorCode`: fonte unica di verità (OBJ-06).**
  - Questa tabella è l'unico elenco autorevole di codici, stati HTTP e parametri. `docs/03-ux.md`, `docs/05-data.md` e gli altri ADR la citano senza duplicarla. In caso di differenza vale questa tabella.
  - Nel codice c'è una sola enumerazione Python `ErrorCode`, esportata in OpenAPI, e un test verifica che coincida con questa tabella.
  - Le chiavi di catalogo seguono `docs/03-ux.md` §7.3; per i codici nuovi le definisce la UX.

  | `code` | HTTP | `params` | Uso |
  |---|---|---|---|
  | `validation` | 422 | `errors[]` (`field`, `code`, `params`) | Schema, lunghezze, formati, campi sconosciuti (SR-010). Anche `If-Match` malformato, debole, `*` o con più di 18 cifre (regex `^"(0|[1-9][0-9]{0,17})"$`, THR-107): `field: "If-Match"`, `code: "invalid_value"` (ADR-0008, Q-T1). Per gli header, `field` è il nome dell'header. |
  | `not_found` | 404 | — | Risorsa inesistente o di un'altra famiglia (SR-008) |
  | `forbidden` | 403 | — | Permesso mancante |
  | `unauthenticated` | 401 | — | Sessione assente o scaduta (chiave `error.sessionExpired`) |
  | `reauth_required` | 403 | — | SR-039 |
  | **`reauth_wrong_account`** | 403 | `expectedEmailMasked` (per esempio `m***@gmail.com`) | Riautenticazione completata con un account Google diverso da quello della sessione (SR-068, ADR-0004 rev. 2). Il parametro è l'email **dell'account della sessione**, mascherata dal server: primo carattere della parte locale, `***` e dominio. Non contiene mai dati dell'account usato per sbaglio. |
  | `csrf_failed` | 403 | — | Token CSRF o `Origin` non validi |
  | `conflict` | 412 | Unità singola: `current`, `modifiedBy`, `modifiedAt`. Più unità (sposta, scambia, copia): `units[]`, un elemento per unità in conflitto con `key` (la stessa chiave di `expectedVersions`), `reason` (`version_changed` o `choice_required`), `current`, `modifiedBy`, `modifiedAt` | Versione cambiata (ADR-0008) |
  | `precondition_required` | 428 | — | Manca `If-Match` |
  | `rate_limited` | 429 | `retryAfterSeconds` | SR-059 |
  | `payload_too_large` | 413 | `maxBytes` | SR-060 |
  | `family_pending_deletion` | 409 | `deletionDate` | Periodo di ripensamento (FR-016) |
  | `invite_invalid` | 404 | — | Invito non valido, scaduto, usato o revocato: risposta unica (SR-007) |
  | `code_invalid` | 404 | — | Codice di creazione non valido (M2, S-18, SR-007) |
  | **`age_declaration_blocked`** | 422 | — | Dichiarata un'età inferiore a 14 anni: l'invito resta valido (SR-013) |
  | **`already_in_family`** | 409 | — | L'account appartiene già a una famiglia (ASM-050) |
  | **`last_admin`** | 409 | — | Operazione che lascerebbe la famiglia senza Amministratori (FR-011, SR-011) |
  | **`dish_already_planned`** | 409 | — | Eliminazione definitiva di un piatto già pianificato: si può solo archiviare (FR-029) |
  | **`dish_not_planned`** | 409 | — | Archiviazione di un piatto mai pianificato, vietata dal `CHECK` su `dish.archived_at`: si può solo eliminare (SL-08, AC-007.7). Chiave UX `error.dish_not_planned` (`docs/03-ux.md` §7) |
  | **`course_in_use`** | 409 | `usageCount` | Eliminazione di una portata personalizzata usata da almeno un piatto o un pasto (FR-037, AC-033.3, SL-41). Chiave UX da definire (ux-designer) |
  | **`quota_exceeded`** | 409 | `quota` (`dishes`, `people`, `courses`, `tags`, `pending_invites`, `daily_invites`, `other_meals_per_day`), `limit` | Quote di ASM-034, SR-060, SR-063 e limite di 5 "Altro pasto" **attivi** per giorno (ADR-0009) |
  | **`range_too_large`** | 422 | `maxDays` (62) | Intervallo del piano oltre il limite (SR-060) |
  | **`course_not_allowed`** | 422 | — | Portata non tra quelle del piatto (FR-037, AC-008.6) |
  | **`person_before_join`** | 422 | `joinedOn` | Presenza su un pasto precedente all'ingresso della persona (ASM-058, AC-021.8) |
  | `unsupported_media_type` | 415 | — | Metodo non sicuro senza `Content-Type: application/json` (ADR-0004) |
  | `internal` | 500 | — | Errore imprevisto (`error.generic`) |

  **Esiti di autenticazione** (OBJ-04). Arrivano alla SPA **una sola volta** nel campo `authOutcome: {code, params}` di `GET /api/v1/session`, dopo il `302` del callback, mai in un URL (ADR-0004 rev. 3):

  | `code` | `params` | Uso |
  |---|---|---|
  | `auth_cancelled` | — | Consenso annullato su Google (AC-001.6) |
  | `auth_failed` | — | Token non valido o errore del provider (AC-001.7, messaggio generico) |
  | `not_member` | — | Login riuscito ma nessuna famiglia, invito o codice (AC-001.5, SR-049) |
  | `invite_invalid` | — | Invito diventato non valido durante il login |
  | `already_in_family` | — | Il callback di un invito trova un account che appartiene già a una famiglia (ASM-050, AC-013.4). Si crea la normale sessione dell'account nella sua famiglia e l'invito non viene consumato. Il nome della famiglia dell'invito non viene mai rivelato (THR-034). Ha lo stesso significato dell'errore `409 already_in_family` della tabella sopra |
  | `reauth_wrong_account` | `expectedEmailMasked` | Come nella tabella sopra |
  | `age_declaration_blocked` | — | Come nella tabella sopra, se avviene nel passo successivo al login |

  - `GET /healthz` è fuori da questo contratto: risponde solo `{"status":"ok"}` oppure `503` (vedi `docs/04-architecture.md`).
  - I conflitti di versione usano `412` (ADR-0008). Le violazioni di regole di stato usano `409`. Gli input non accettabili usano `422`.
  - Nuovi codici si aggiungono all'enumerazione con il messaggio nel catalogo `it`. Il test di copertura lo impone.
- **Enumerazioni di dominio:** i valori sono codici, per esempio tipi di pasto (`breakfast`, `lunch`, `snack`, `dinner`, `other`) e portate di base (`first`, `second` …), tradotti nel client. Le portate personalizzate, i tag, i nomi dei piatti e le note sono contenuti degli utenti e non si traducono (ASM-025).
- **Controllo in CI sul backend:** un test verifica che ogni risposta d'errore usi un `ErrorCode` dichiarato. ruff e una revisione vietano stringhe libere destinate all'utente nelle risposte.

### Email (*[rinviato, CHG-020]* ~~M2~~: dal primo flusso email; nell'MVP l'app non invia email)
Le email sono generate dal server Python con cataloghi gettext `.po` per lingua (`backend/locales/<lingua>/`) e modelli fissi che contengono solo ID di messaggio. Lo strumento di compilazione (per esempio Babel) si sceglie con l'ADR del provider email, prima di M2.

## Conseguenze
- Positive:
  - NFR-011 verificato meccanicamente da M0;
  - un'unica fonte dei testi dell'interfaccia;
  - le future app native ricevono gli stessi codici e li localizzano con i propri cataloghi.
- Negative e costi:
  - mantenere la mappa da `code` a messaggio;
  - gli ID espliciti richiedono disciplina nel nominarli.
- Azioni successive:
  - il tech-lead configura ESLint, gli script e il test di copertura degli `ErrorCode`;
  - la UX fornisce i testi.

## Quando rivedere
All'arrivo della seconda lingua: preferenza per account, `Accept-Language`, piattaforma di traduzione.
