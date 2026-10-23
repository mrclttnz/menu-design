# ADR-0004: Autenticazione con libreria OIDC (Authlib) e sessioni opache lato server

- **Stato:** ACCEPTED (decisione dell'utente, 2026-10-18: opzione A. Le opzioni B, C e D sono respinte.)
- **Data:** 2026-10-18 (opzioni rivalutate per Python, ADR-0002). Revisione 2 del 2026-10-19: integrazioni dal threat model, in fondo. Revisione 3 del 2026-10-19: avvio del login come `POST` ed esito del callback lato server (OBJ-04), bootstrap con `email_sha256`. Revisione 4 del 2026-10-19 (CHG-020, decisione dell'utente al gate G4): **login con email e password rinviato al backlog dopo M2**. Il testo originale resta qui sotto, marcato *[rinviato, CHG-020]*, come riferimento per quando verrà ripreso. Revisione 5 del 2026-10-23 (SL-03a, CR-SL03a-004): token CSRF di sessione **derivato** con HMAC dal token di sessione invece che casuale e indipendente.
- **Decisori:** utente, architect. Revisione del security-engineer.
- **Requisiti collegati:** FR-001, FR-002, FR-003, FR-004, FR-007, FR-069, SR-001…SR-007, SR-033…SR-039, SR-043, SR-049, SR-059

## Contesto
I requisiti di identità sono molto specifici:
- Google OIDC da M0, con account legato a (provider, `sub`) ed `email_verified` obbligatorio;
- bootstrap legato all'email fino al primo login, con scadenza di 7 giorni;
- nessun account persistente senza invito o codice (SR-049);
- *[rinviato, CHG-020: backlog dopo M2]* email e password ~~da M2~~, solo dentro i flussi di invito o codice, senza unione automatica tra metodi. Nell'MVP (M0-M2) l'unico metodo di accesso è Google;
- sessione opaca salvata come hash, cookie `__Host-`, scadenza mobile di 30 giorni e assoluta di 90;
- elenco e revoca delle sessioni;
- riautenticazione entro 10 minuti con `prompt=login`, `max_age` e `auth_time`.

Lo standard di sicurezza chiede di non scrivere da zero l'autenticazione.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Aderenza ai requisiti specifici (SR-033…SR-039, SR-049) | 5 |
| Sicurezza (pratiche consolidate, manutenzione attiva) | 5 |
| Semplicità e manutenzione | 4 |
| Dati nell'UE e numero di fornitori | 4 |
| Lock-in | 3 |
| Costo | 2 |

## Opzioni considerate (Python)
| Criterio | A: Authlib + joserfc + sessioni proprie + argon2-cffi | B: fastapi-users (+ httpx-oauth) | C: provider gestito (Auth0, Zitadel Cloud) | D: Supabase Auth |
|---|---|---|---|---|
| Requisiti (5) | 5 | 3 | 3 | 2 |
| Sicurezza (5) | 4 | 3 | 5 | 4 |
| Semplicità (4) | 4 | 3 | 3 | 4 |
| UE e fornitori (4) | 5 | 5 | 3 | 4 |
| Lock-in (3) | 5 | 4 | 2 | 2 |
| Costo (2) | 5 | 5 | 4 | 5 |
| **Totale pesato** | **106** | **84** | **78** | **78** |

### Opzione A: Authlib più sessioni lato server proprie
Versioni verificate il 2026-10-18:

| Pacchetto | Versione | Data | Licenza | Uso |
|---|---|---|---|---|
| Authlib | 1.9.1 | 2026-10-14 | BSD-3-Clause | Client OAuth 2.0 e OIDC, PKCE |
| joserfc | 1.7.5 | 2026-08-29 | BSD-3-Clause | JWS, JWK, JWT. Stesso autore di Authlib, successore di `authlib.jose` |
| argon2-cffi | 25.1.0 | 2025-06-03 | MIT | Argon2id. *[rinviato, CHG-020]* Non entra nell'MVP: si aggiunge solo se FR-002 viene realizzato, ricontrollando versione e manutenzione |
| httpx | 0.28.1 | 2024-12-06 | BSD-3-Clause | Trasporto HTTP |

- Pro:
  - protocollo OIDC e validazione del token ID delegati a librerie mature e attive;
  - Google resta l'identity provider (MFA delegata a Google, FR-059);
  - le sessioni opache in tabella sono un pattern semplice, verificabile riga per riga contro SR-037;
  - nessun fornitore in più.
- Contro: sessioni, CSRF e (solo se FR-002 verrà ripreso, CHG-020) il flusso password sono codice nostro, da testare e rivedere.
- Rischi: *[rinviato, CHG-020]* argon2-cffi non ha rilasci da giugno 2025. È una libreria stabile con un perimetro piccolo, e le verifiche di CVE restano obbligatorie.

### Opzione B: fastapi-users 15.0.5
- Pro: registrazione, login, OAuth e verifica email già pronti.
- Contro:
  - **il progetto è dichiaratamente in modalità manutenzione** (solo correzioni di sicurezza, nessuna nuova funzionalità);
  - il modello di registrazione aperta e le strategie di token vanno piegati ai requisiti (invito o codice, bootstrap email → `sub`, SR-049, hash del token, `auth_time`).

### Opzione C: provider gestito
- Pro: password, MFA e protezioni dagli abusi già fatte.
- Contro:
  - un fornitore in più con dati di account di minori;
  - la registrazione chiusa va spostata in hook proprietari;
  - modello a JWT diverso dalla sessione richiesta;
  - lock-in.

### Opzione D: Supabase Auth
- Contro: token nello storage del browser per default (in conflitto con SR-037), semantica delle sessioni diversa, legame a Supabase (NFR-014).

## Decisione
**Opzione A**, Authlib più joserfc, con sessioni e CSRF propri. argon2-cffi solo se il login con password verrà ripreso (CHG-020).

- **OIDC Google (M0):**
  - client OAuth 2.0 di Authlib (`authlib.integrations.httpx_client.OAuth2Client`) con PKCE S256 (`code_challenge_method='S256'`, `code_verifier` generato con `secrets`), `state` e `nonce` monouso;
  - lo stato del flusso **non** usa la `SessionMiddleware` di Starlette: sta in una tabella `auth_flow` con TTL di 10 minuti, referenziata dal cookie `__Host-auth_flow` (`SameSite=Lax`);
  - validazione del token ID con joserfc: algoritmo fisso RS256, JWKS di Google in cache, `iss`, `aud`, `exp`, `nonce`, `email_verified === true` e, per la riautenticazione, `auth_time`;
  - chiave dell'account `(provider='google', sub)`;
  - la libreria esatta per la validazione delle claim (joserfc oppure gli helper OIDC di Authlib) si fissa in implementazione. I test di SR-033 (token manipolati) sono obbligatori in entrambi i casi.
- **Bootstrap (FR-007):**
  - il record conserva solo `email_sha256` (ADR-0011) e la scadenza a 7 giorni;
  - al primo login, il server calcola l'hash dell'email verificata di Google con `menu.common.email_sha256` (normalizzazione unica, ADR-0011) e lo cerca con `app.bootstrap_resolve`;
  - il servizio mantiene anche `account.email_sha256`, usato dalla console;
  - se lo trova, una sola transazione crea l'account e la membership da Amministratore e consuma il bootstrap;
  - da quel momento conta solo il `sub`.
- **Sessione:**
  - token di 256 bit da `secrets.token_bytes(32)`, salvato come SHA-256 nella tabella `session`;
  - campi `created_at`, `last_used_at`, `auth_time`, dispositivo approssimato e IP troncato;
  - cookie `__Host-session` con `Path=/`, `Secure`, `HttpOnly`, `SameSite=Lax` e `Max-Age` di 30 giorni rinnovato;
  - validità: `now - last_used_at ≤ 30 giorni` e `now - created_at ≤ 90 giorni`;
  - `last_used_at` si aggiorna al massimo una volta ogni ora;
  - nuova sessione a ogni login;
  - cancellazione al logout, al cambio password (solo con FR-002, rinviato), all'eliminazione dell'account e su revoca;
  - comando console di revoca globale (SR-053).
  - La risoluzione della sessione è una dipendenza FastAPI che costruisce il `RequestContext` a ogni richiesta e rilegge la membership (SR-005).
- **CSRF:**
  - ~~token casuale per sessione~~ token per sessione **derivato dal token di sessione** (Revisione 5), salvato come hash nella riga della sessione, restituito da `GET /api/v1/session` e inviato nell'header `X-CSRF-Token` su ogni richiesta non sicura;
  - confronto con `hmac.compare_digest`;
  - in più si verificano `Origin` (o `Sec-Fetch-Site: same-origin`) contro l'origine dell'app;
  - nessun CORS.
  - È codice nostro di poche righe, perché per FastAPI non esiste una libreria CSRF consolidata e mantenuta. Va coperto da test negativi.
- **Riautenticazione (SR-039, M2):**
  - stesso flusso con `purpose=reauth`, `prompt=login` e `max_age=0`;
  - si verifica `auth_time` e si aggiorna `session.auth_time`;
  - le rotte con `reauth: true` in `authz` richiedono `now - auth_time ≤ 10 min`, altrimenti rispondono `reauth_required`.
- **Email e password — *[rinviato, CHG-020: backlog dopo M2; era M2]*.** Nell'MVP non si realizza, non si aggiungono le dipendenze e l'app non invia email. Il testo resta come riferimento:
  - argon2-cffi (`PasswordHasher`, Argon2id, parametri ≥ raccomandazione OWASP: m=19 MiB, t=2, p=1);
  - lunghezza tra 12 e 128 caratteri controllata prima dell'hash;
  - controllo con l'API range di Pwned Passwords (k-anonimato) tramite httpx;
  - hash fittizio per le email inesistenti;
  - ritardo progressivo (ADR-0006);
  - token di verifica e di recupero salvati come hash, monouso.
  - Provider email: ADR da scrivere ~~prima di M2~~ prima del primo flusso email (FR-002 ripreso o SR-050 all'apertura al pubblico).
- **App native (futuro):** la stessa tabella `session` potrà emettere token opachi inviati in `Authorization: Bearer` (ADR futuro).

## Revisione 2: integrazioni dal threat model (2026-10-19)
Applica le azioni A-01, A-02, A-03 e A-05 di `docs/06-threat-model.md` §10.1 e le proposte SR-068, SR-070 (parte sessioni) e SR-073, accettate dall'utente il 2026-10-18. Prevalgono sulle parti corrispondenti sopra.

1. **Riautenticazione legata alla stessa identità (SR-068, A-01, THR-008, THR-009), da subito:**
   - il flusso `purpose='reauth'` è legato in `auth_flow.session_id` alla sessione che lo avvia;
   - al callback la riautenticazione vale solo se il token ID ha la **stessa coppia (provider, `sub`)** dell'account della sessione, e un `auth_time` presente e non precedente all'avvio del flusso (tolleranza di 60 s);
   - altrimenti `session.auth_time` non cambia, nessuna sessione nuova viene creata, e si registra l'evento di sicurezza `reauth.mismatch`;
   - il client riceve `reauth_wrong_account` con la sola email mascherata dell'account della sessione (ADR-0010). Nessun dato dell'altro account Google viene restituito né salvato;
   - *[rinviato, CHG-020]* per email e password ~~(M2)~~ si verificherà la password dello stesso account.
2. **Invito attraverso il login Google (A-02, THR-033):**
   1. la pagina dell'invito legge il segreto dal frammento `#` e lo invia con una `POST /api/v1/invites/resolve`, protetta come al punto 4;
   2. il server lo risolve con `app.invite_resolve` (ADR-0003) e, se valido, crea un `auth_flow` con `purpose='invite'` e il solo `invite_id`;
   3. il segreto non viene salvato lato server né nel browser (niente storage, niente URL di ritorno). Il client lo cancella dalla barra degli indirizzi con `history.replaceState` appena letto;
   4. dopo il login, il callback trasferisce `invite_id` in `signup_pending` (passo età e informativa);
   5. l'accettazione finale ricontrolla l'invito in `family_tx` con l'`UPDATE` condizionato;
   6. un invito diventato non valido nel frattempo produce la risposta generica `invite_invalid`.
3. **URL di ritorno (A-03, THR-010):** `return_to` si salva in `auth_flow` all'avvio del flusso. Si accettano solo percorsi relativi di un'allow-list (`/piano…`, `/piatti…`, `/altro…`, `/invito…`), mai URL assoluti, `//` o `\`. Altrimenti si torna a `/piano`.
4. **CSRF per le richieste anonime e tipo del contenuto (A-05, THR-007):**
   - le `POST` senza sessione (risoluzione dell'invito, avvio del login; registrazione e recupero solo se FR-002 e FR-003 verranno ripresi, CHG-020) richiedono il controllo di `Origin` (o `Sec-Fetch-Site: same-origin`) più un token **double submit** in un cookie `__Host-csrf` (casuale, `SameSite=Strict`) ripetuto nell'header `X-CSRF-Token`;
   - tutte le richieste con metodi non sicuri devono avere `Content-Type: application/json`, altrimenti rispondono `415`. Questo impedisce i form cross-site;
   - per le richieste autenticate resta il token legato alla sessione.
5. **Massimo 20 sessioni attive per account (SR-070):** a un login oltre il limite si revoca la sessione con `last_used_at` meno recente. Si registra l'evento `session.evicted`.
6. **Identità verificabile di chi entra con un invito (SR-073):**
   - nell'elenco delle persone e nell'evento di ingresso visibile agli Amministratori compaiono il nome visualizzato **e l'email verificata** dell'account entrato;
   - l'email è restituita solo alle persone con ruolo Amministratore della stessa famiglia, mai a Pianificatori o Membri;
   - è un nuovo trattamento visibile in famiglia: il product-analyst aggiorna l'informativa e SR-014.

## Revisione 3: avvio del login ed esito del callback (OBJ-04, 2026-10-19)
Prevale sulle parti corrispondenti sopra.

1. **Token CSRF anonimo:**
   - `GET /api/v1/session` senza sessione valida risponde `200` con `{"authenticated": false, "notices": []}`;
   - se manca, imposta il cookie `__Host-csrf` (casuale, `SameSite=Strict`, `Secure`, `Path=/`, **non** `HttpOnly`, perché la SPA deve leggerlo e ripeterlo nell'header);
   - la SPA chiama sempre `GET /api/v1/session` all'avvio, quindi il cookie c'è prima di qualunque `POST` anonima.
2. **Avvio del login come `POST` JSON anonima:**
   - `POST /api/v1/auth/google/start` con corpo `{"purpose": "login"|"reauth"|"invite", "returnTo": "/piano"}` e header `X-CSRF-Token`;
   - il server verifica `Origin`, il token CSRF e il rate limit, crea `auth_flow` (con `return_to` dall'allow-list e, per `invite`, l'`invite_id` già risolto in sessione di flusso), imposta `__Host-auth_flow` e risponde `200 {"redirectUrl": "https://accounts.google.com/…"}`;
   - la SPA esegue `window.location.assign(redirectUrl)`;
   - per `reauth` serve la sessione e il CSRF legato alla sessione.
   - Nessuna `GET` avvia flussi o modifica stato.
3. **Esito del callback, salvato sul server e letto dalla SPA:**
   - il callback (`GET /api/v1/auth/google/callback`) termina sempre con un `302` verso `return_to` (o `/piano`), **senza parametri d'esito nell'URL**;
   - l'esito si salva sul server nella riga `auth_flow` del flusso: `outcome_code` e `outcome_params` come JSON. La riga non si cancella subito: si marca come consumata e ha un TTL di 5 minuti;
   - la successiva `GET /api/v1/session` legge l'esito tramite il cookie `__Host-auth_flow`, lo restituisce **una sola volta** come `authOutcome: {code, params}`, cancella la riga e il cookie;
   - esempi di esito:
     - `reauth_wrong_account` con `expectedEmailMasked` (ADR-0010);
     - `invite_invalid`;
     - "serve un invito" (`not_member`);
     - consenso annullato (`auth_cancelled`);
   - **l'email mascherata non compare mai in un URL**, né nei log di accesso;
   - un esito positivo non ha `authOutcome`: la sessione è semplicemente attiva.
4. Il diagramma del flusso 1 di `docs/04-architecture.md` (v5) riflette questa sequenza.

## Revisione 5: token CSRF di sessione derivato (SL-03a, CR-SL03a-004, 2026-10-23)
Prevale sul punto "CSRF" della Decisione per le richieste **autenticate**. Il double submit anonimo (Revisione 2, punto 4, e Revisione 3, punto 1) non cambia.

1. **Derivazione:**
   - token CSRF = `base64url(HMAC-SHA256(chiave = token di sessione, messaggio = "menu-design/csrf/v1"))`, senza padding (`menu.identity.tokens.csrf_token_for`);
   - alla creazione della sessione si salva `session.csrf_token_hash = SHA-256(token CSRF)`. Né il token di sessione né il token CSRF si conservano in chiaro;
   - `GET /api/v1/session` ricalcola il token dal cookie `__Host-session` ricevuto e lo restituisce;
   - la verifica delle richieste non sicure confronta `SHA-256(X-CSRF-Token)` con `session.csrf_token_hash` usando `hmac.compare_digest`. La colonna resta come difesa in profondità: un token derivato con un'altra chiave o un altro contesto non passa.
2. **Motivo:**
   - `GET /api/v1/session` deve restituire **lo stesso** token a ogni chiamata (la SPA lo richiede all'avvio e a ogni ricarica, anche in più schede), ma nel database stanno solo hash (SR-037). Un token casuale salvato solo come hash non si può restituire una seconda volta; salvarlo in chiaro, o cifrato, aggiungerebbe un segreto conservato e una chiave da gestire;
   - la derivazione è deterministica, non richiede stato in più né una chiave del server.
3. **Esposizione:** nessuna in più rispetto al token casuale.
   - Il token CSRF si ottiene solo con il token di sessione, e chi ha il cookie di sessione è già autenticato: può comunque chiamare `GET /api/v1/session` e leggere il token. Il CSRF protegge da richieste cross-site che *usano* il cookie senza poterlo leggere, e questo resta vero (cookie `HttpOnly`, nessun CORS, controllo di `Origin`);
   - dal token CSRF (o dal suo hash) non si ricava il token di sessione: HMAC-SHA256 con chiave di 256 bit non è invertibile;
   - il contesto con versione (`/v1`) separa questo uso da eventuali derivazioni future dallo stesso token.
4. **Conseguenze:**
   - il token CSRF vive e muore con la sessione: cambia a ogni login (nuova sessione) e sparisce con logout o revoca;
   - **non si può ruotare il token CSRF senza ruotare la sessione.** SL-25 (elenco e revoca delle sessioni) e i lavori futuri non devono presumere un token CSRF indipendente. Se servirà ruotarlo, si ruota la sessione (nuovo token e nuova riga). Cambiare il contesto (`/v2`) non basta da solo: gli hash salvati non corrispondono più, e quindi equivale a invalidare tutte le sessioni. Un token CSRF ruotabile da solo richiederebbe di conservarlo in modo recuperabile, con una nuova revisione di questo ADR.

## Conseguenze
- Positive: ogni requisito è implementabile e testabile. Nessun fornitore in più. Nessun token nel JavaScript.
- Negative e costi:
  - sessioni e CSRF (e la password, se ripresa) sono codice nostro, con revisione obbligatoria del security-engineer;
  - una query di sessione per ogni richiesta.
- Azioni successive:
  - il security-engineer modella le minacce su OIDC, bootstrap, sessioni e CSRF;
  - il tester scrive i test di SR-033 e SR-037.

## Quando rivedere
- *[rinviato, CHG-020]* ~~Prima di M2~~ Quando il login con email e password viene ripreso dal backlog: confronto di nuovo tra flusso proprio e alternative, se risulta troppo costoso da rendere sicuro.
- All'arrivo delle app native o del login Apple.
- Se Authlib o joserfc smettono di ricevere manutenzione.
