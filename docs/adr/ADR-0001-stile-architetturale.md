# ADR-0001: Monolite modulare con SPA PWA e API REST/OpenAPI sulla stessa origine

- **Stato:** ACCEPTED (2026-10-19, gate G3, confermato dopo il secondo giro della revisione critica (nessun blocco))
- **Data:** 2026-10-18 (revisione 2: contratto OpenAPI generato da FastAPI). Revisione 3 del 2026-10-19: service worker, CSP e scadenza offline dal threat model. Revisione 4: Lighthouse di notte e prima del rilascio, budget del bundle per PR (OBJ-08).
- **Decisori:** utente (da confermare al gate G3), architect
- **Requisiti collegati:** NFR-001, NFR-002, NFR-010, NFR-014, NFR-015, FR-054, SR-026, SR-031, SR-037, SR-046, vincoli della visione ("non precludere un'API per app native", sviluppatore singolo)

## Contesto
NFR-015 impone che tutte le operazioni della UI passino da un'interfaccia server documentata con OpenAPI e versionata, riutilizzabile da future app native. Il prodotto è una web app mobile-first, installabile come PWA, con consultazione offline in sola lettura (FR-054, M2). La sviluppa una sola persona nel tempo libero, con al massimo circa 50 famiglie nell'anno uno. Bisogna decidere:
- lo stile di deployment (monolite o servizi);
- la forma del client (SPA, pagine rese dal server, framework full-stack);
- lo stile dell'API.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Aderenza ai requisiti (OpenAPI per tutte le operazioni, PWA, offline) | 5 |
| Sicurezza (superficie, CSRF e CORS, gestione del token) | 5 |
| Semplicità per uno sviluppatore singolo | 5 |
| Riutilizzo per app native | 4 |
| Prestazioni percepite su mobile (NFR-001) | 3 |
| Portabilità (NFR-014) | 3 |

## Opzioni considerate
| Criterio | A: monolite modulare, SPA + API REST stessa origine | B: pagine rese dal server (MPA/HTMX) più un'API separata | C: framework full-stack (Next.js, SvelteKit) con server function | D: servizi separati (API, auth, worker) |
|---|---|---|---|---|
| Requisiti (5) | 5 | 3 | 3 | 5 |
| Sicurezza (5) | 4 | 4 | 4 | 3 |
| Semplicità (5) | 4 | 3 | 4 | 1 |
| Riutilizzo nativo (4) | 5 | 3 | 2 | 5 |
| Prestazioni mobile (3) | 3 | 5 | 4 | 3 |
| Portabilità (3) | 5 | 5 | 3 | 3 |
| **Totale pesato** | **109** | **92** | **84** | **83** |

### Opzione A: monolite modulare, SPA React più API REST `/api/v1` sulla stessa origine
- Pro:
  - la UI usa la stessa API delle future app native, quindi NFR-015 è soddisfatto per costruzione;
  - un solo deploy;
  - la stessa origine elimina CORS e permette il cookie `__Host-` senza `Domain`;
  - la PWA offline è naturale.
- Contro:
  - una SPA deve scaricare JavaScript prima di mostrare dati, quindi l'LCP su 4G lenta è più a rischio (R-03).
- Rischi: ingrossamento del bundle. Mitigato con un budget in CI.

### Opzione B: pagine rese dal server più API separata
- Pro: ottimo LCP, poco JavaScript.
- Contro:
  - due interfacce da mantenere (pagine e API), quindi la UI non "passa dall'API" come chiede NFR-015, oppure lo fa con un doppio salto;
  - l'offline PWA è più laborioso.

### Opzione C: framework full-stack con server function
- Pro: SSR e buon LCP, un solo progetto.
- Contro:
  - le server function e le azioni sono RPC del framework, non un'API OpenAPI riutilizzabile;
  - servirebbe comunque un'API REST parallela;
  - lock-in sul framework e spesso sulla piattaforma di hosting preferita.

### Opzione D: servizi separati
- Contro: complessità operativa non giustificata da nessun requisito.

### Stile dell'API (sotto-decisione)
- **REST JSON più OpenAPI 3.1** (scelta): standard, generata da FastAPI dai modelli Pydantic (ADR-0002), consumabile da client nativi, caching e precondizioni HTTP (`ETag` e `If-Match`) utili per FR-044.
- GraphQL, scartato: introspezione, limiti di complessità e autorizzazione per campo sono un costo in più senza beneficio a questa scala.
- tRPC, scartato: non produce un contratto OpenAPI nativo e lega i client a TypeScript.

## Decisione
Opzione A.
- **Un'unica immagine container** con tre comandi:
  - `serve`: API e file statici della SPA;
  - `worker --once`: elaborazioni in background (ADR-0013);
  - `console`: comandi del Gestore (ADR-0011).
- **Moduli backend:** `identity`, `access`, `tenancy`, `family`, `catalog`, `planning`, `attendance`, `history`, `privacy`, `audit`, `ratelimit`, `jobs`. Confini espliciti: un modulo non legge le tabelle di un altro.
- **API:** REST JSON sotto `/api/v1`, con OpenAPI 3.1 generata da FastAPI e Pydantic e committata (`openapi.json`). Il client TypeScript è generato da quel file (`openapi-typescript`, `openapi-fetch`). Errori RFC 9457. Estensione `x-authz` per operazione (SR-042).
- **PWA:**
  - service worker generato da `vite-plugin-pwa`, che precarica solo l'app shell (HTML, JS, CSS, icone);
  - le risposte API sono `no-store` e **non** sono messe in cache dal service worker;
  - da M2 l'app salva l'ultimo piano caricato in IndexedDB, sotto una chiave che contiene l'ID dell'account, con l'istante di aggiornamento ("dati aggiornati al …");
  - offline: sola lettura, comandi disabilitati;
  - la cache si svuota al logout, a ogni `401`, quando il server dice che l'account non appartiene più alla famiglia o che la famiglia è eliminata, e quando l'ID dell'account della sessione è diverso da quello della cache (SR-026, SR-046);
  - `sw.js` è servito con `no-cache`;
  - il token non è mai accessibile al JavaScript (cookie `HttpOnly`).
- **Prestazioni (NFR-001):**
  - bundle iniziale ≤ 150 KB gzip, verificato in CI;
  - code splitting per rotta, font di sistema;
  - budget del bundle verificato **a ogni PR**;
  - Lighthouse (mediana di 5 esecuzioni, NFR-001) su un dataset sintetico di 500 piatti e 8 persone, **di notte e prima di ogni rilascio**, non a ogni PR (OBJ-08), a partire dalla prima slice con UI.

## Integrazioni dal threat model (2026-10-19)
1. **Service worker (A-12, THR-070):**
   - `navigateFallbackDenylist` per `/api/`, così le navigazioni verso l'API non ricevono mai l'app shell;
   - **nessun runtime caching** delle risposte `/api/` nel service worker. Solo il precache dell'app shell;
   - i dati offline li gestisce solo il codice dell'app in IndexedDB.
2. **CSP (A-12, THR-073):** oltre a `default-src 'self'`, `script-src 'self'` e `frame-ancestors 'none'`:
   - `object-src 'none'`;
   - `base-uri 'none'`;
   - `form-action 'self'`;
   - `require-trusted-types-for 'script'`, con una policy Trusted Types di default che rifiuta i sink HTML. React non usa `innerHTML` (SR-024).
   - Header impostati dal middleware di sicurezza (ADR-0002) e verificati da un test.
3. **Scadenza della cache offline (A-19, SR-071; decisione dell'utente: solo la scadenza, contenuto invariato):**
   - i dati offline più vecchi di **7 giorni** (dall'istante "dati aggiornati al …") non si mostrano e si cancellano all'apertura dell'app;
   - il contenuto resta quello di ASM-043, compresi presenti, assenti e ospiti dell'ultimo piano caricato;
   - restano invariati gli svuotamenti di SR-026 e SR-046.

## Conseguenze
- Positive: un solo contratto per web e nativo, un solo deploy, una superficie piccola, nessun CORS.
- Negative e costi: rischio sull'LCP (R-03). Il primo caricamento richiede JavaScript.
- Azioni successive:
  - il tech-lead definisce la struttura del monorepo (`backend/` in Python, `web/` in TypeScript, `openapi.json` come contratto, ADR-0002);
  - il tester inserisce il budget del bundle nella pipeline delle PR, e Lighthouse in quella notturna e prima di ogni rilascio.

## Quando rivedere
- Se la mediana dell'LCP misurata nella prima slice con UI supera 2,0 s nonostante il budget: valutare il prerender dell'app shell o un framework con SSR che **consumi** la stessa API.
- All'avvio delle app native: verificare il trasporto del token (header `Authorization` invece del cookie, ADR-0004).
