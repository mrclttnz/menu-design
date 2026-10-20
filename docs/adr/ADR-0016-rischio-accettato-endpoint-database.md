# ADR-0016: Accettazione del rischio: endpoint del database raggiungibile da Internet durante la beta chiusa

- **Stato:** RISK ACCEPTANCE (decisione dell'utente, 2026-10-18: opzione (a)). Revisione 2 del 2026-10-19, decisa dall'utente:
  - controlli 4 e 9 corretti;
  - hardening di SR-075 da M0;
  - verifica delle restrizioni di rete prima di M1.
- **Data:** 2026-10-18, revisione 2 del 2026-10-19 (dal threat model, `docs/06-threat-model.md` §7 e azione A-11). Revisione 3 del 2026-10-19: OBJ-03, OBJ-07 e OBJ-08 della revisione critica (password, quattro ruoli, rilevazione semplificata).
- **Decisori:** utente (Gestore, titolare del trattamento), architect. Revisione del security-engineer.
- **Requisiti collegati:** SR-012, SR-027, SR-028, SR-040, SR-042, SR-065, SR-074 e SR-075 (proposte), security standard §12 ("i database non sono mai esposti a Internet")
- **Minacce:** THR-040, THR-041, THR-042, THR-043. Rischio R-02 di `docs/04-architecture.md`.
- **Scadenza dell'accettazione:**
  - riconferma **prima di M1**, dopo la verifica delle restrizioni di rete (sotto);
  - in ogni caso **prima dell'apertura al pubblico**, nella DPIA (SR-065).

## Contesto
Con Supabase Free (ADR-0014) e Cloud Run con IP di uscita variabili (ADR-0005), l'endpoint PostgreSQL (pooler Supavisor) è raggiungibile da Internet, protetto solo da TLS e credenziali. Lo standard di sicurezza (§12) chiede che i database non siano esposti a Internet. La regola non è [MUST], ma la deroga va resa esplicita.

Alternative:
- **(b)** IP di uscita statico per Cloud Run (Direct VPC egress più Cloud NAT più IP riservato, circa 5 €/mese da verificare) con le restrizioni di rete di Supabase. Diventa il **piano per M1**, se le restrizioni sono disponibili sul piano Free (sotto);
- **(c)** VPS con database su `localhost`, non compatibile con Supabase.

## Rischio
- **Minaccia:**
  - attacchi alle credenziali: forza bruta, credential stuffing, credenziali sottratte da una macchina, un repository o una pipeline;
  - vulnerabilità del pooler o di PostgreSQL sfruttabili da remoto.
- **Impatto:** alto. Dati di tutte le famiglie, compresi minori e presenze in casa.
- **Probabilità con i controlli:** bassa.
- **Rischio residuo:** medio (valutazione del threat model).

## Controlli compensativi (obbligatori)
1. **Password (OBJ-03):**
   - password casuali di 32 byte, diverse per ognuno dei quattro ruoli (`menu_owner`, `menu_app`, `menu_console`, `menu_backup`);
   - sono generate in Cloud Shell con `scripts/role-secret.sh` e scritte **direttamente** nel Secret Manager. Nel database arriva solo il verificatore SCRAM, incollato nell'editor SQL (ADR-0015);
   - la password di `postgres` (e quella del progetto temporaneo di ripristino) è casuale e resta **solo offline** nel gestore di password del Gestore. Si usa solo dalla dashboard di Supabase;
   - `db/bootstrap.sql` si esegue una volta dall'editor SQL di Supabase;
   - mai password nel repository, in CI, nei log, in file sul PC o nella cronologia della shell.
2. **TLS:**
   - `sslmode=verify-full` con la CA di Supabase;
   - "Enforce SSL on incoming connections" attivo sul progetto;
   - l'applicazione **rifiuta di avviarsi** se un URL del database non ha `sslmode=verify-full` (A-13, ADR-0003).
3. **Minimo privilegio** (ADR-0003, ADR-0011):
   - nessun ruolo con `BYPASSRLS`;
   - quattro ruoli di login (OBJ-07): `menu_owner`, `menu_app`, `menu_console`, `menu_backup`;
   - `CONNECTION LIMIT` per ruolo (`menu_console` 2, `menu_backup` 2);
   - `statement_timeout` per ruolo;
   - ogni servizio o job ha un account di servizio con `secretAccessor` sul solo segreto che gli serve.
4. **RLS e FK composite (riformulato).**
   - **Proteggono dai difetti dell'applicazione** (THR-020): una query o una rotta sbagliata non espone altre famiglie.
   - **Non proteggono dal furto della credenziale di `menu_app`:** chi si connette con quel ruolo imposta da sé `app.family_id` e `app.account_id` con `set_config` e può leggere tutte le famiglie una alla volta. Lo stesso vale per `menu_backup`, che legge tutto per scopo.
   - Contro il furto valgono i controlli 1, 3, 9, 10 e le restrizioni di rete (piano per M1).
   - La RLS su `session` (A-10, ADR-0003 revisione 5) alza un poco il costo per l'attaccante, ma non chiude il punto.
5. **Ban automatici di Supabase** sui tentativi di autenticazione falliti, attivi. Soglia e durata da verificare (V-2).
   - Una password errata in un deploy farebbe bannare l'IP di uscita del servizio, quindi la rotazione si fa in due passi (controllo 8).
6. **Superficie HTTPS di Supabase chiusa:**
   - Data API (PostgREST) disattivata;
   - registrazioni di Supabase Auth disattivate;
   - nessun bucket Storage;
   - nessuna chiave `anon` o `service_role` usata né distribuita;
   - verifica con una richiesta REST che deve fallire.
7. **MFA resistente al phishing** (passkey o chiave di sicurezza) su Supabase, Google Cloud, GitHub, registrar e DNS. Il PC del Gestore non contiene credenziali del database: la console gira come job cloud (ADR-0011, SR-074).
8. **Rotazione delle password dei ruoli:**
   - documentata in `docs/09-release.md`, in **due passi senza fermo**, con `scripts/role-secret.sh` (nuova versione del segreto e verificatore SCRAM), poi deploy;
   - si esegue a ogni sospetto, a un cambio o una perdita del PC, all'uscita di un collaboratore, a un allarme di gitleaks, e comunque almeno ogni 12 mesi.
9. **Rilevazione automatica degli accessi anomali (riformulato).**
   - La revisione mensile dei log di connessione **non è attuabile** sul piano Free, che conserva i log del database per 1 giorno e non ha i log drain.
   - Al suo posto (SR-075, semplificato con OBJ-08): controllo `maint_role_activity` eseguito dal worker ogni 10 minuti (ADR-0013), come SQL normale su `pg_stat_activity` e non come funzione privilegiata.
     - Controlla **solo le finestre orarie** di `menu_owner` (deploy), `menu_backup` (backup notturno) e `menu_console` (comandi).
     - Allarme al Gestore (SR-058) se uno di questi ruoli risulta connesso fuori dalla sua finestra.
   - La fattibilità dei privilegi (`pg_read_all_stats` o equivalente su Supabase) è **da verificare** (V-4). Se non è fattibile: estrazione giornaliera dei log tramite la Management API di Supabase verso Cloud Logging, con un token conservato come segreto potente. Se nemmeno questa è accettabile: Supabase Pro, con log di 7 giorni.
10. **Hardening di SR-075 da M0:**
    - "Enforce SSL" (controllo 2);
    - `CONNECTION LIMIT` (controllo 3);
    - password di `postgres` gestita (controllo 1);
    - Supabase Auth e Storage chiusi (controllo 6);
    - rilevazione (controllo 9);
    - `REVOKE CREATE ON SCHEMA public, app FROM PUBLIC`.

## Piano per M1: restrizioni di rete
Prima che entrino dati di altre famiglie (M1), il devops verifica se le **network restrictions** di Supabase sono disponibili sul piano Free (V-1). La documentazione dice che valgono per connessioni dirette e pooler, ma non chiarisce il piano.
- **Se disponibili** (decisione dell'utente):
  - si attiva un IP di uscita statico per Cloud Run (servizio e tutti i job): Direct VPC egress più Cloud NAT con IP riservato in europe-west3, circa 5 €/mese (da verificare con il calcolatore prezzi);
  - si limita l'accesso al database a quell'IP;
  - l'accesso amministrativo del Gestore passa dalla dashboard HTTPS di Supabase, non coperta dalle restrizioni, oppure da job cloud;
  - **la console non richiede l'IP del PC**, perché gira come job Cloud Run (ADR-0011).
  - Il rischio residuo scende a basso. Questo ADR resta come registro.
- **Se non disponibili:**
  - il rischio residuo (medio) si **registra nella DPIA** con i controlli 1-10 e si riconferma esplicitamente;
  - nella DPIA si rivalutano Supabase Pro e altri PostgreSQL gestiti con isolamento di rete.

## Rischio residuo
- Una vulnerabilità remota non autenticata del pooler o di PostgreSQL, finché il provider non la corregge.
- Il furto della credenziale di `menu_app` o di `menu_backup` (controllo 4).
- Entrambi sono mitigabili solo con l'isolamento di rete (piano per M1).

## Eventi che riaprono la decisione
- L'esito della verifica V-1 (prima di M1).
- Un passaggio a un piano a pagamento.
- Un incidente o un sospetto di compromissione delle credenziali.
- Una vulnerabilità critica su Supavisor o PostgreSQL.
- In ogni caso, la DPIA prima dell'apertura al pubblico.

## Conseguenze
- Il security-engineer aggiorna il threat model (§7 e §12) con questa revisione e verifica i controlli 1-10 nell'audit.
- Il devops:
  - inserisce i controlli e le verifiche V-1, V-2 e V-4 nella checklist di `docs/09-release.md`;
  - prepara la configurazione dell'IP statico, pronta per M1.
- Il data-architect aggiunge `maint_role_activity()`, i `CONNECTION LIMIT` e le revoche su `public`, con i quattro ruoli di ADR-0003.
