# ADR-0015: Backup giornalieri cifrati, rotazione entro 30 giorni, ripristino trimestrale con riapplicazione delle cancellazioni

- **Stato:** ACCEPTED (decisione dell'utente, 2026-10-18: frequenza giornaliera). Esecuzione e storage su Google Cloud in europe-west3 (ADR-0005).
- **Data:** 2026-10-19, revisione 4, consolidata. Storia:
  - revisione 2: `menu_backup` senza `BYPASSRLS`;
  - revisione 3: azioni A-14 e A-16 del threat model;
  - revisione 4: obiezioni OBJ-03 e OBJ-08 della revisione critica, con le decisioni dell'utente del 2026-10-19:
    - gestione di `postgres` e delle password dei ruoli;
    - ripristino reale;
    - niente riconciliazione giornaliera.
- **Decisori:** utente, architect. Revisione di devops e security-engineer.
- **Requisiti collegati:** NFR-006, NFR-016, SR-017, SR-018, SR-028, SR-029, SR-048, SR-074

## Contesto
NFR-006 chiede:
- backup completo almeno settimanale (RPO ≤ 7 giorni), cifrato e conservato nell'UE;
- rotazione entro 30 giorni;
- ripristino provato ogni 3 mesi con RTO ≤ 24 ore, riapplicando le cancellazioni (SR-048).

Supabase Free non fa backup (ADR-0014). L'utente chiede la soluzione più semplice che rispetti gli obblighi reali.

## Opzioni considerate (frequenza)
| Criterio (peso) | Giornaliero | Settimanale |
|---|---|---|
| RPO (5) | 5 (≤ 1 giorno) | 2 (≤ 7 giorni) |
| Costo (3) | 4 (centesimi al mese) | 5 |
| Complessità (3) | 5 (identica) | 5 |
| **Totale pesato** | **52** | **40** |

## Decisione

### Backup
- **Frequenza:** **giornaliera** (RPO ≤ 1 giorno), alle 03:00 Europe/Rome, con il job Cloud Run `menu-backup` avviato da Cloud Scheduler.
- **Esecuzione:**
  - immagine con il client `pg_dump` della stessa major del server e `age`;
  - ruolo `menu_backup`, senza `BYPASSRLS` (policy `p_backup`, ADR-0003);
  - connessione al pooler in **modalità sessione** (`pg_dump` non funziona in modalità transazione), da verificare all'installazione (ADR-0014).
- **Formato e cifratura:**
  - `pg_dump -Fc --schema=app --enable-row-security` in streaming, cifrato con `age` (1.3.2) verso una **chiave pubblica**;
  - la chiave privata sta solo nel gestore di password del Gestore, con una copia offline. Mai nel cloud;
  - nessun file in chiaro su disco.
- **Storage:**
  - bucket Cloud Storage in europe-west3, privato, con accesso uniforme e prevenzione dell'accesso pubblico;
  - account del job con permesso di sola creazione;
  - ciclo di vita che **cancella dopo 30 giorni** (SR-017, SR-018);
  - **retention policy di 27 giorni**, non bloccata (A-16): nessuno può cancellare o sovrascrivere un backup prima di 27 giorni;
  - versioning disattivato.
- **Copia offline (R-05):** una volta al mese il Gestore scarica un backup cifrato e lo conserva offline nell'UE. Anche questa copia ruota entro 30 giorni.

### Registro delle cancellazioni (SR-048)
- Ogni cancellazione scrive una riga in `deletion_log` (nel database) **e** l'evento strutturato `deletion.executed` (solo identificativi e istante). L'evento è instradato in un bucket di log UE dedicato, con conservazione di 35 giorni.
- **Nessuna riconciliazione giornaliera** (OBJ-08). La fusione dei due registri è un passo del runbook di ripristino (sotto).

### Credenziali amministrative (OBJ-03)
- **Utente `postgres` di Supabase:**
  - password casuale conservata **solo offline** nel gestore di password del Gestore;
  - non entra nel Secret Manager né in nessun job;
  - si usa solo dalla dashboard di Supabase (MFA).
- **`db/bootstrap.sql`** (ruoli, estensioni, schema, revoche) si esegue **una volta** dall'editor SQL della dashboard di Supabase. Crea i ruoli **senza password**.
- **Password dei ruoli** (`menu_owner`, `menu_app`, `menu_console`, `menu_backup`), generate in **Cloud Shell** con uno script del repository (`scripts/role-secret.sh <ruolo>`):
  1. genera una password casuale (32 byte);
  2. scrive l'URL di connessione completo direttamente nel Secret Manager (`gcloud secrets versions add … --data-file=-`), senza mostrarlo;
  3. stampa solo il **verificatore SCRAM-SHA-256** (non la password), calcolato con la libreria standard di Python, da incollare nell'editor SQL come `ALTER ROLE <ruolo> PASSWORD 'SCRAM-SHA-256$…'`.
  - In Cloud Shell passano solo segreti, mai dati personali.
  - La stessa procedura vale per la rotazione (ADR-0016, controllo 8).
- **`maint replay-deletions`** gira con l'**identità del job di migrazione** (`menu-migrate`, ruolo `menu_owner`), non con un job dedicato, e non dal PC.

### Ripristino di prova trimestrale (RTO ≤ 24 ore)
1. Creare un progetto Supabase Free temporaneo a Francoforte, con password di `postgres` casuale (gestore di password).
2. Eseguire `db/bootstrap.sql` dall'editor SQL del progetto temporaneo. Creare con `scripts/role-secret.sh` i segreti **temporanei** dei ruoli (`menu-restore-*`).
3. **Dal PC del Gestore** (nell'UE, dove sta la chiave privata):
   - `gcloud storage cat gs://<bucket>/<dump>.age | age -d -i <chiave> | pg_restore --no-owner --role=menu_owner -d "$(gcloud secrets versions access latest --secret=menu-restore-owner-url)"`;
   - l'URL resta in memoria nel processo e non viene scritto su disco;
   - poi verificare `alembic current`.
4. **Fusione dei registri delle cancellazioni** (runbook, OBJ-08):
   - in Cloud Shell, `gcloud logging read 'jsonPayload.event="deletion.executed" AND timestamp>="<istante del backup>"' --format=json`, che contiene solo identificativi;
   - salvare l'esito in un oggetto di un bucket di servizio (`restore/`, ciclo di vita a 1 giorno);
   - eseguire il job `menu-migrate` con il comando `maint replay-deletions --input /mnt/restore/deletions.json`, con il bucket montato come volume in sola lettura e l'URL del database di destinazione;
   - il comando **unisce** quel file con il `deletion_log` presente nel database ripristinato, toglie i duplicati e chiama `maint_apply_deletion`, che è idempotente.
5. Smoke test, compresi i test di isolamento con `menu_app`.
6. Registrare esito e tempi in `docs/09-release.md`. Il test include un account cancellato dopo il backup.
7. Cancellare il progetto temporaneo e i segreti `menu-restore-*`.

### Ripristino reale (OBJ-03)
1. Mettere il servizio in manutenzione: `max-instances=0` del servizio web e pausa dello scheduler.
2. Ripristinare sul progetto di produzione, se recuperabile, oppure su un **nuovo** progetto Supabase a Francoforte.
   - Per un nuovo progetto valgono i passi 1-2 della prova, con segreti definitivi. Poi si aggiornano gli URL nel Secret Manager (`scripts/role-secret.sh` per ogni ruolo).
3. Passo 3 della prova, dal PC verso il progetto di destinazione.
   - Se le restrizioni di rete sono attive (ADR-0016), l'IP del PC si aggiunge **temporaneamente** all'allow-list e si rimuove al termine.
   - L'operazione si registra in seguito con `audit note`.
4. Passo 4 della prova (fusione e riapplicazione delle cancellazioni), **prima** di riaprire il servizio.
5. Smoke test, riapertura del servizio, annotazione nel runbook e nel registro delle violazioni, se pertinente (SR-053).

## Conseguenze
- Positive:
  - RPO di un giorno a costo trascurabile;
  - cifratura indipendente dal fornitore;
  - nessun segreto di `postgres` nel cloud;
  - password dei ruoli mai mostrate;
  - cancellazioni rispettate dopo un ripristino;
  - meno automazioni da mantenere (niente riconciliazione).
- Negative e costi:
  - la chiave privata è un punto critico: se si perde, i backup sono inutilizzabili. Il runbook prevede due copie;
  - prova trimestrale e ripristino sono procedure manuali;
  - durante un ripristino il PC si collega al database, solo temporaneamente.
- Azioni successive:
  - il devops scrive il runbook, compresi `scripts/role-secret.sh` e la rotazione delle chiavi `age`;
  - il tester verifica `maint replay-deletions` (fusione e idempotenza).

## Quando rivedere
- Se si passa a un piano con backup e PITR del provider: questi backup restano come seconda copia indipendente.
- Prima dell'apertura al pubblico.
