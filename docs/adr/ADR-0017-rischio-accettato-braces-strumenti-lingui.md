# ADR-0017: Accettazione del rischio: `braces` vulnerabile negli strumenti di sviluppo di Lingui

- **Stato:** RISK ACCEPTANCE (decisione dell'utente, 2026-10-22).
- **Data:** 2026-10-22.
- **Decisori:** utente (Gestore), architect. Revisione del security-engineer.
- **Requisiti collegati:** SR-076 (scansioni bloccanti in CI), NFR-011 (controlli i18n di Lingui, ADR-0010).
- **Minacce:** THR-090.
- **Scadenza dell'accettazione:** **2026-11-21**. Dopo quella data l'eccezione smette di valere da sola e le scansioni tornano a fallire.

## Contesto
`make scan-web` (`pnpm audit`) e osv-scanner segnalano **GHSA-vfj7-8cjw-p6xm**: `braces` <= 3.0.3, gravità HIGH (CVSS 8.7), esaurimento dello stack con pattern glob annidati in profondità.
- Non esiste una versione corretta di `braces`.
- `micromatch` 4.0.8, l'ultima, richiede ancora `braces` ^3.0.3.
- `@lingui/cli` 6.10.0, l'ultima, dipende ancora da `micromatch`.

Il pacchetto arriva **solo come dipendenza di sviluppo**:
- `micromatch` ← `@lingui/cli` (e `@lingui/vite-plugin` attraverso la CLI);
- `micromatch` ← `eslint-plugin-lingui`.

Non entra mai nel bundle della SPA servito agli utenti.

Alternative:
- **(a)** Sostituire gli strumenti di Lingui. Respinta: cambio grande, ADR-0010 è accettato, si perdono i controlli di NFR-011 (estrazione, cataloghi completi, regole ESLint).
- **(b)** Override di pnpm verso una versione corretta. Impossibile, perché non esiste. Uno shim locale al posto del pacchetto violerebbe la regola "solo pacchetti dal registro, con hash nel lockfile" (THR-090).
- **(c)** Lasciare la scansione rossa. Respinta: blocca la slice e abitua a ignorare le scansioni.

## Rischio
- **Minaccia:** un pattern glob costruito apposta manda in crash il processo Node che lo espande (negazione del servizio).
- **Esposizione:**
  - i pattern elaborati sono quelli del repository (configurazione di Lingui ed ESLint), non controllati da un attaccante;
  - gli strumenti girano sul PC di sviluppo e in CI, mai in produzione;
  - in CI i job `web`, `e2e` e `deps` girano su runner ospitati da GitHub, con `permissions: contents: read`, `persist-credentials: false` e nessun segreto (verificato su `.github/workflows/ci.yml` il 2026-10-22).
- **Impatto:** basso. Nel caso peggiore fallisce una build o un comando locale.
- **Probabilità:** molto bassa. Servirebbe una modifica malevola ai pattern del repository, che è già una compromissione più grave.
- **Rischio residuo:** basso.

## Controlli
1. **Eccezione limitata al solo ID GHSA-vfj7-8cjw-p6xm**, in `make scan-web` e nella configurazione di osv-scanner. Nessuna esclusione per pacchetto o per gravità: ogni altra vulnerabilità, anche in `braces` o `micromatch`, continua a bloccare.
2. **Scadenza automatica il 2026-11-21:** dopo quella data l'eccezione non vale più e le scansioni tornano a fallire, senza bisogno di ricordarsene.
3. **Registrata nel debito tecnico** di `docs/STATUS.md`, con la scadenza.
4. Stesso schema dell'eccezione al cooldown per certifi (GHSA-6q48-6c7w-9gw2): stretta, motivata, con data di rimozione.

## Eventi che riaprono la decisione
- Una versione corretta di `braces` o di `micromatch`: si aggiorna (rispettando il cooldown di SR-076) e si toglie l'eccezione.
- Un rilascio di Lingui (CLI, plugin Vite o plugin ESLint) che abbandona `micromatch`: si aggiorna e si toglie l'eccezione.
- `braces` che compare in una dipendenza di runtime o nel bundle della SPA.
- Un aggiornamento dell'avviso che cambia gravità o vettore (per esempio input remoto).
- In ogni caso, la scadenza del 2026-11-21: si rinnova solo con una nuova decisione dell'utente.

## Conseguenze
- Il devops aggiunge l'eccezione con scadenza in `make scan-web` e nella configurazione di osv-scanner, e la voce in `docs/STATUS.md`.
- Il security-engineer verifica nell'audit che l'eccezione copra il solo ID e che la scadenza funzioni.
