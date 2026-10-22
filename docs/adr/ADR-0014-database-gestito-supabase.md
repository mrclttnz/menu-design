# ADR-0014: Database gestito Supabase Free a Francoforte, usato come PostgreSQL standard

- **Stato:** ACCEPTED (decisione dell'utente, 2026-10-18)
- **Data:** 2026-10-18
- **Decisori:** utente, architect
- **Requisiti collegati:** NFR-004, NFR-005, NFR-014, NFR-016, SR-027, SR-028, SR-052, SR-062
- **ADR collegati:** ADR-0003 (isolamento), ADR-0015 (backup), ADR-0016 (endpoint esposto)

## Contesto
Serve un PostgreSQL gestito, gratuito, nell'UE, sempre disponibile per i controlli ogni 5 minuti (NFR-005), con ruoli personalizzati e RLS (ADR-0003). In origine la scelta faceva parte di ADR-0005, revisione 1.

## Criteri di decisione
| Criterio | Peso (1-5) |
|---|---|
| Residenza UE garantita | 5 |
| Compatibilità con controlli ogni 5 minuti (niente sospensioni o quote di calcolo) | 5 |
| PostgreSQL completo (ruoli, RLS, estensioni) | 4 |
| Spazio e limiti | 3 |
| Backup del provider | 2 |

## Opzioni considerate
| Criterio | Supabase Free (eu-central-1) | Neon Free (Francoforte) | Aiven Free | Render Postgres Free |
|---|---|---|---|---|
| Residenza UE (5) | 5 | 5 | 2 | 4 |
| Controlli ogni 5 minuti (5) | 5 | 1 | 4 | 4 |
| PostgreSQL completo (4) | 5 | 5 | 4 | 4 |
| Spazio (3) | 3 | 3 | 4 | 4 |
| Backup del provider (2) | 1 | 2 | 4 | 1 |
| **Totale pesato** | **81** | **63** | **66** | **70** |

- **Neon:** 100 CU-ora al mese e scale-to-zero dopo 5 minuti non disattivabile. Un controllo ogni 5 minuti lo terrebbe acceso per circa 182 CU-ora, oltre la quota.
- **Aiven:** si riserva di cambiare provider o regione del servizio gratuito.
- **Render:** il database gratuito viene cancellato dopo 30 giorni.

## Decisione
**Supabase Free, progetto in eu-central-1 (Francoforte)**, usato come PostgreSQL standard:
- PostgreSQL 17, la stessa major in sviluppo;
- **Data API (PostgREST) disattivata**, schema applicativo `app` non esposto, privilegi di default revocati ai ruoli `anon` e `authenticated`;
- nessun uso di Supabase Auth, Storage, Edge Functions o SDK. Il codice conosce solo una stringa di connessione (NFR-014);
- connessione tramite il pooler Supavisor in modalità transazione (IPv4), TLS `verify-full` con la CA di Supabase, psycopg con `prepare_threshold=None` (ADR-0003);
- ruoli e privilegi come in ADR-0003, con password casuali di almeno 32 caratteri;
- account Supabase con MFA (SR-040), DPA da accettare prima di M1 (SR-052);
- cifratura a riposo del provider (SR-028).

### Limiti noti e mitigazioni
- **500 MB:** allarme al 70%.
  - La stima analitica di `docs/05-data.md` §14 supera quella iniziale: circa 270 MB nell'anno 1 nello scenario pieno (50 famiglie da subito), circa 100 MB in quello realistico.
  - Gli eventi compatti decisi da M0 (ADR-0012) riducono la tabella più pesante del 30-50%.
  - La misura reale si fa nella prima slice (R-01).
- **Pausa dopo 7 giorni di inattività:** non scatta, grazie ai controlli ogni 5 minuti.
- **Nessun backup nel piano Free:** i backup sono nostri (ADR-0015).
- **Endpoint pubblico:** accettato con controlli compensativi (ADR-0016).

### Verifiche aperte per il devops, alla creazione del progetto
Sono punti non verificati durante il design. Vanno controllati sul progetto reale e annotati in `docs/09-release.md`:
1. **Ruoli personalizzati:**
   - lo script `db/bootstrap.sql`, eseguito come `postgres`, deve poter creare i ruoli `LOGIN` `menu_*` con `NOBYPASSRLS` e impostazioni per ruolo (`statement_timeout`);
   - va verificato se Supabase permette di concedere `BYPASSRLS` a un ruolo personalizzato. Il design non ne ha più bisogno (ADR-0003, revisione 3): l'informazione serve solo a sapere se esiste un'alternativa.
2. **Come Supabase misura il limite di 500 MB:**
   - se è `pg_database_size` dell'intero database (schemi di sistema compresi) o solo dei dati utente;
   - se conta WAL o indici;
   - cosa succede al superamento (sola lettura? avviso? sospensione?).
   - Da questo dipendono la soglia dell'allarme al 70% calcolata da `maint_db_size()` e la stima di `docs/05-data.md` §14.
3. **Connessione per `pg_dump`:** il pooler in modalità sessione (IPv4) accetta `pg_dump --enable-row-security` con `menu_backup` (ADR-0015).
4. **Major version** di PostgreSQL del progetto (attesa 17) e disponibilità di `unaccent` e `pg_trgm` nello schema `extensions`.
   - *Nota del data-architect (SL-02, 2026-10-22):* le migrazioni `0002`-`0004` sono verificate su PostgreSQL 17 locale e usano solo funzioni standard: colonne `GENERATED ALWAYS AS IDENTITY`, colonne generate `STORED`, `CONSTRAINT TRIGGER … DEFERRABLE`, plpgsql, RLS forzata, `SECURITY DEFINER` di `menu_owner`. Il trigger `tg_family_timezone_valid` legge `pg_catalog.pg_timezone_names`. Sul progetto va solo verificato che `alembic upgrade head` riesca come `menu_owner` e che `SELECT count(*) FROM pg_timezone_names WHERE name = 'Europe/Rome'` restituisca 1. Nessuna funzione specifica di Supabase.
5. **Disattivazione della Data API** e revoca dei privilegi di default ad `anon` e `authenticated`, verificate con una richiesta REST che deve fallire.
6. **Ban automatici** sui tentativi di autenticazione falliti, attivi (ADR-0016, controllo 5).

## Conseguenze
- Positive: PostgreSQL completo, gratuito, con regione fissa nell'UE.
- Negative e costi: spazio limitato, nessun backup del provider, endpoint raggiungibile da Internet.

## Quando rivedere
- Spazio oltre il 70% → Supabase Pro (circa 25 $/mese, con backup giornalieri) o un altro PostgreSQL gestito UE.
- Cambio delle condizioni del piano Free.
- DPIA prima dell'apertura al pubblico.

## Fonti
- [Supabase, pricing](https://supabase.com/pricing)
- [Supabase, regioni](https://supabase.com/docs/guides/platform/regions)
- [Supabase, GDPR](https://supabase.com/docs/guides/security/gdpr-compliance)
- [Supabase, protezione della Data API](https://supabase.com/docs/guides/api/securing-your-api)
- [Neon, pricing](https://neon.com/pricing)
- [Aiven, piano Free di PostgreSQL](https://aiven.io/docs/products/postgresql/concepts/pg-free-tier)
- [Render, piani gratuiti 2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026.md)
