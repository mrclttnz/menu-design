-- =============================================================================================
-- Menu Design: prerequisiti del database fuori da Alembic (docs/05-data.md §3.1, §12; ADR-0003,
-- ADR-0014, ADR-0015, ADR-0016). SL-00b.
--
-- Come si esegue:
--   * Supabase: una volta, dall'editor SQL del progetto, come `postgres` (incollare tutto il file).
--   * Locale / CI / test: come superutente del cluster, sul database dell'applicazione.
-- Nessun meta-comando di psql: il file è SQL puro e funziona in entrambi i casi.
--
-- Idempotente: si può rieseguire (anche dopo un ripristino, §13) e porta sempre allo stesso stato.
--
-- Il file NON contiene credenziali. Subito dopo la prima esecuzione, nell'editor e fuori dal file,
-- si imposta per ogni ruolo il solo verificatore calcolato in Cloud Shell con
-- `scripts/role-secret.sh` (ADR-0015, ADR-0016 controllo 1):
--     ALTER ROLE menu_app PASSWORD '<verificatore>';
--
-- Cosa crea / garantisce:
--   1. i quattro ruoli di login, senza privilegi di cluster, con CONNECTION LIMIT e timeout (§3.1);
--   2. le estensioni `unaccent` e `pg_trgm` nello schema `extensions`;
--   3. lo schema `app` di proprietà di `menu_owner`;
--   4. le revoche verso PUBLIC e, se esistono (Supabase), verso `anon` e `authenticated`;
--   5. i privilegi predefiniti sugli oggetti futuri di `menu_owner`.
-- La migrazione 0001 controlla questi prerequisiti e fallisce con un messaggio chiaro se mancano.
-- =============================================================================================


-- ---------------------------------------------------------------------------------------------
-- 1. Ruoli di login (§3.1). CREATE ROLE non ha IF NOT EXISTS: blocco DO.
--    Gli attributi negativi si fissano alla creazione (un ruolo non superutente come il `postgres`
--    di Supabase non può modificare quegli attributi con ALTER ROLE). Se un ruolo esiste già con
--    attributi privilegiati, la migrazione 0001 rifiuta di procedere.
-- ---------------------------------------------------------------------------------------------
DO $bootstrap$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT v.name, v.conn_limit
        FROM (VALUES ('menu_owner', 3), ('menu_app', 20), ('menu_console', 2), ('menu_backup', 2))
            AS v(name, conn_limit)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r.name) THEN
            EXECUTE pg_catalog.format(
                'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION '
                'NOBYPASSRLS INHERIT CONNECTION LIMIT %s',
                r.name, r.conn_limit);
        END IF;
        -- Rieseguibile: riallinea login e limite anche su un ruolo già esistente.
        EXECUTE pg_catalog.format('ALTER ROLE %I LOGIN CONNECTION LIMIT %s', r.name, r.conn_limit);
    END LOOP;
END
$bootstrap$;

-- Impostazioni per ruolo (§3.1). Il pooler in modalità transazione le rispetta.
-- `menu_owner`: lock_timeout e statement_timeout li imposta `backend/migrations/env.py`.
ALTER ROLE menu_app SET statement_timeout = '5s';
ALTER ROLE menu_app SET lock_timeout = '3s';
ALTER ROLE menu_app SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE menu_console SET statement_timeout = '30s';
ALTER ROLE menu_backup SET statement_timeout = 0;


-- ---------------------------------------------------------------------------------------------
-- Supabase: `postgres` non è superutente. Per creare lo schema per conto di `menu_owner` e per
-- impostarne i privilegi predefiniti serve, per la durata dello script, l'appartenenza a
-- `menu_owner`; la si concede qui e la si revoca alla fine (sezione 6). Con un superutente
-- (PostgreSQL locale, CI) non serve e non si concede nulla.
-- ---------------------------------------------------------------------------------------------
DO $bootstrap$
BEGIN
    IF NOT (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user)
       AND NOT pg_catalog.pg_has_role(current_user, 'menu_owner', 'USAGE') THEN
        EXECUTE pg_catalog.format(
            'GRANT menu_owner TO %I WITH INHERIT TRUE, SET TRUE', current_user);
    END IF;
END
$bootstrap$;


-- ---------------------------------------------------------------------------------------------
-- 2. Estensioni nello schema `extensions` (esiste già su Supabase).
--    Il codice le qualifica sempre: `extensions.unaccent(...)`, `extensions.similarity(...)`.
-- ---------------------------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;
-- `app.search_norm` è SECURITY INVOKER: chi la esegue (o la crea) deve poter usare lo schema.
GRANT USAGE ON SCHEMA extensions TO menu_owner, menu_app;


-- ---------------------------------------------------------------------------------------------
-- 3. Schema applicativo. Rieseguendo lo script, la proprietà torna a `menu_owner`.
-- ---------------------------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION menu_owner;
ALTER SCHEMA app OWNER TO menu_owner;


-- ---------------------------------------------------------------------------------------------
-- 4. Privilegi sugli schemi (§3.1 "Supabase e schemi"). Nessun ruolo diverso da `menu_owner`
--    può creare oggetti in `app` o in `public` (THR-044).
-- ---------------------------------------------------------------------------------------------
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA app FROM menu_app, menu_console, menu_backup;
REVOKE CREATE ON SCHEMA public FROM menu_app, menu_console, menu_backup;
GRANT USAGE ON SCHEMA app TO menu_app, menu_console, menu_backup;

-- Nemmeno il proprietario di `public` (`pg_database_owner` da PostgreSQL 15; `postgres` su
-- Supabase) conserva CREATE: l'applicazione non usa `public` e §6.4 vuole che solo `menu_owner`
-- possa creare oggetti. Il proprietario può riconcederselo in ogni momento (GRANT).
DO $bootstrap$
BEGIN
    EXECUTE pg_catalog.format(
        'REVOKE CREATE ON SCHEMA public FROM %I',
        (SELECT pg_catalog.pg_get_userbyid(nspowner) FROM pg_catalog.pg_namespace
         WHERE nspname = 'public'));
END
$bootstrap$;

-- Ruoli predefiniti di Supabase: solo se esistono (un PostgreSQL locale non li ha).
DO $bootstrap$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated']
    LOOP
        IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = r) THEN
            EXECUTE pg_catalog.format('REVOKE ALL ON SCHEMA app FROM %I', r);
            EXECUTE pg_catalog.format('REVOKE CREATE ON SCHEMA public FROM %I', r);
            EXECUTE pg_catalog.format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE pg_catalog.format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE ALL ON SEQUENCES FROM %I', r);
            EXECUTE pg_catalog.format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE ALL ON FUNCTIONS FROM %I', r);
            EXECUTE pg_catalog.format(
                'ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE ALL ON TYPES FROM %I', r);
        END IF;
    END LOOP;
END
$bootstrap$;


-- ---------------------------------------------------------------------------------------------
-- 5. Privilegi predefiniti sugli oggetti futuri di `menu_owner`.
--    * Funzioni: nessun EXECUTE a PUBLIC; ogni migrazione concede EXECUTE al solo ruolo previsto
--      (§3.2, §3.3).
--    * Tabelle e sequenze di `app`: SELECT a `menu_backup` (dump con --enable-row-security e
--      policy `p_backup`, ADR-0015). Il DML di `menu_app` è concesso tabella per tabella nelle
--      migrazioni (matrice §3.2), mai per default. `menu_console` non ha privilegi su tabelle.
-- ---------------------------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner IN SCHEMA app GRANT SELECT ON TABLES TO menu_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE menu_owner IN SCHEMA app GRANT SELECT ON SEQUENCES TO menu_backup;


-- ---------------------------------------------------------------------------------------------
-- 6. Fine: revoca dell'appartenenza temporanea concessa sopra (solo Supabase). `postgres` resta
--    inutilizzato dopo il bootstrap (§3.1).
-- ---------------------------------------------------------------------------------------------
DO $bootstrap$
BEGIN
    IF NOT (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user)
       AND EXISTS (
           SELECT 1 FROM pg_catalog.pg_auth_members m
           WHERE m.roleid = 'menu_owner'::regrole
             AND m.member = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
             AND m.grantor = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = current_user)
       ) THEN
        EXECUTE pg_catalog.format(
            'REVOKE menu_owner FROM %I GRANTED BY %I', current_user, current_user);
    END IF;
END
$bootstrap$;
