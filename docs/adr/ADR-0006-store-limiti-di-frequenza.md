# ADR-0006: Contatori dei limiti di frequenza in PostgreSQL

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-18 (revisione 2: backend Python, ADR-0002). Revisione 3 del 2026-10-19: IP del client su Cloud Run e limiti di SR-070, dal threat model. Revisione 4: un solo upsert per richiesta e pulizia senza funzioni privilegiate (OBJ-07). Revisione 5 del 2026-10-19: ritardo progressivo rinviato con il login con password (CHG-020).
- **Decisori:** architect. Revisione del security-engineer.
- **Requisiti collegati:** SR-003, SR-036, SR-058, SR-059, SR-060, SR-062

## Contesto
SR-059 fissa i limiti e chiede contatori **condivisi tra le istanze e persistenti al riavvio**. Le istanze serverless nascono e muoiono, e possono essere due. Il carico atteso è minimo.

Situazione delle librerie Python, verificata il 2026-10-18:
- `limits` 5.8.0 (MIT) supporta Redis, Memcached, MongoDB e la memoria, **non PostgreSQL**;
- `slowapi` si basa su `limits`, quindi ha gli stessi backend.

Non esiste una libreria Python consolidata con store PostgreSQL. La libreria `rate-limiter-flexible` della revisione 1 era per Node.js.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Aderenza a SR-059 (condivisi e persistenti) | 5 |
| Pochi pezzi in movimento | 5 |
| Sicurezza e residenza UE | 4 |
| Costo | 3 |
| Prestazioni | 3 |

## Opzioni considerate
| Criterio | A: contatori in PostgreSQL (modulo proprio) | B: `limits` + Redis gestito UE | C: memoria del processo | D: WAF del provider |
|---|---|---|---|---|
| SR-059 (5) | 5 | 5 | 1 | 3 |
| Pochi pezzi (5) | 5 | 3 | 5 | 2 |
| Sicurezza e UE (4) | 5 | 3 | 4 | 4 |
| Costo (3) | 5 | 4 | 5 | 1 |
| Prestazioni (3) | 3 | 5 | 5 | 5 |
| **Totale pesato** | **94** | **79** | **76** | **59** |

- **A:**
  - nessun servizio in più, contatori atomici nel database già presente;
  - il codice proprio è piccolo (circa 100 righe) e non è crittografia né autenticazione;
  - costa una scrittura per ogni richiesta limitata.
- **B:** un fornitore in più con dati (IP) e un segreto in più, per un carico che PostgreSQL regge senza sforzo.
- **C:** viola SR-059.
- **D:** a pagamento, legato al provider, non conosce identità e sessione.

## Decisione
**Opzione A**, modulo `ratelimit`:
- **Tabella `rate_counter (key bytea, window_start timestamptz, count int, PRIMARY KEY (key, window_start))`**, creata da Alembic.
- **Algoritmo:**
  - finestra fissa con stima della finestra scorrevole: si pesa il conteggio della finestra precedente, come nell'algoritmo "sliding window counter";
  - incremento atomico in **una sola istruzione per richiesta** (OBJ-07): tutte le regole che si applicano alla richiesta (per sessione, per account, per famiglia, per IP) si aggiornano con un'unica `INSERT … VALUES (…), (…), … ON CONFLICT (key, window_start) DO UPDATE SET count = rate_counter.count + 1 RETURNING key, count`, in una transazione `system_tx()` breve e separata da quella di dominio. Il codice confronta i conteggi restituiti con i limiti di ciascuna regola.
- **Ritardo progressivo** — *[rinviato, CHG-020: vale solo per il login con password, spostato nel backlog dopo M2; era M2]*. Nell'MVP non si realizza e la tabella `rate_block` non si crea. Testo di riferimento: tabella `rate_block (key, blocked_until, strikes)`. Il blocco cresce esponenzialmente fino a 15 minuti, mai in modo permanente (SR-036).
- **Chiavi:** HMAC-SHA-256, con un segreto lato server (pepper), di IP, email normalizzata, ID di sessione, account o famiglia. Nessun identificativo in chiaro (minimizzazione).
- **Regole:** una tabella dichiarativa in codice, una regola per riga di SR-059. Più regole si combinano (per esempio per identità e per IP).
- **Applicazione:** dipendenze FastAPI per regola, applicate alle rotte. Il limite generale dell'API autenticata (300 richieste al minuto per sessione, di cui al massimo 60 scritture) è un middleware.
- **Risposta:** `429` con `Retry-After` e `problem+json` `code=rate_limited`, più l'evento di sicurezza `rate_limit.exceeded` (SR-020, SR-058).
- **Fail closed:** se il database non risponde, la richiesta riceve `503`.
- **Pulizia:** il worker (ruolo `menu_app`) cancella ogni ora con SQL normale in `system_tx()` le finestre scadute e i blocchi terminati (ADR-0013). Non serve nessuna funzione privilegiata.
- **IP del client (A-04, THR-012):**
  - una sola funzione (`platform.http.client_ip`) usata da rate limit, registro di sicurezza e sessioni;
  - su Cloud Run prende **l'ultima voce** di `X-Forwarded-For`, cioè quella aggiunta dal Google Front End. Le voci precedenti le controlla il client e si ignorano;
  - uvicorn non riscrive l'indirizzo (`--proxy-headers` disattivato), per evitare due regole diverse;
  - la regola è in configurazione (`TRUSTED_PROXY_HOPS=1`), così un cambio di piattaforma non tocca il codice;
  - **verifica di devops (V-3 del threat model):** in staging, una richiesta con `X-Forwarded-For` falsificato deve registrare l'IP reale. L'esito si annota in `docs/09-release.md` prima di M0.
- **Limiti aggiuntivi di SR-070 (A-06, THR-013, THR-100)**, accettati dall'utente:
  - al massimo **60 scritture al minuto per account**, sommando tutte le sue sessioni (chiave = account), in aggiunta alle 60 per sessione di SR-059;
  - al massimo **5.000 scritture tracciate al giorno per famiglia** (chiave = famiglia, finestra giornaliera nel fuso della famiglia). Al superamento: `429` con `rate_limited` e allarme al Gestore (SR-058);
  - il massimo di 20 sessioni per account è in ADR-0004 (revisione 2).
- **Test:** un test per ogni riga di SR-059, un test di concorrenza (N richieste parallele non superano il limite), un test di riavvio con i contatori conservati.

## Conseguenze
- Positive: nessuna infrastruttura in più, stesso comportamento in locale e in produzione.
- Negative e costi:
  - codice proprio da mantenere e testare;
  - circa 1-3 ms e una scrittura per ogni richiesta limitata.
- Azioni successive: il data-architect include le tabelle. Il security-engineer rivede l'algoritmo.

## Quando rivedere
Se il carico supera qualche centinaio di richieste al secondo: `limits` con Redis.
