"""0004: funzioni della console di M0 (SECURITY DEFINER).

Revisione: 0004 (M0, SL-02). docs/05-data.md §3.3; ADR-0011; SR-012, SR-020, SR-033, SR-040,
SR-051, SR-057; THR-044, THR-051, THR-053.

- `console_bootstrap_family(p_family_name text, p_email_sha256 bytea) → uuid`
- `console_security_events(p_since timestamptz, p_limit integer) → setof (righe del registro
  con l'IP troncato a /24 o /48)`
- `console_audit_note(p_ref text) → void`

Regole comuni (§3.3): proprietario `menu_owner`, search_path fissato a `app, pg_temp`, plpgsql,
nessun SQL dinamico, EXECUTE revocato a PUBLIC e concesso al solo `menu_console`.
Ogni chiamata riuscita scrive **esattamente un** evento `console.<comando>` con
`actor_kind='platform_operator'` e `correlation_id` letto da `app.correlation_id` (ADR-0011).
Un argomento non valido solleva `invalid_parameter_value` (22023): la transazione non lascia
righe (nemmeno l'evento). I messaggi d'errore non ripetono mai i valori ricevuti.
Nessuna funzione scrive l'hash dell'email nel registro (I-01).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSOLE_ROLE = "menu_console"

FUNCTIONS: tuple[tuple[str, str], ...] = (
    (
        "app.console_bootstrap_family(text, bytea)",
        """
        create function app.console_bootstrap_family(p_family_name text, p_email_sha256 bytea)
        returns uuid
        language plpgsql volatile security definer set search_path = app, pg_temp
        as $fn$
        declare
            v_family uuid := pg_catalog.gen_random_uuid();
            v_timezone constant text := 'Europe/Rome';
            -- app.correlation_id: impostato dal job con set_config(..., true) (ADR-0011).
            v_correlation uuid :=
                nullif(pg_catalog.current_setting('app.correlation_id', true), '')::uuid;
        begin
            if p_family_name is null or pg_catalog.char_length(p_family_name) > 60
               or pg_catalog.btrim(p_family_name) = ''
               or p_family_name ~ '[\\x01-\\x1f\\x7f\\u0080-\\u009f\\u2028\\u2029]' then
                raise exception using
                    errcode = 'invalid_parameter_value',
                    message = 'console_bootstrap_family: family name must be 1-60 characters';
            end if;
            if p_email_sha256 is null or pg_catalog.octet_length(p_email_sha256) <> 32 then
                raise exception using
                    errcode = 'invalid_parameter_value',
                    message = 'console_bootstrap_family: email hash must be 32 bytes';
            end if;

            -- frozen_through = oggi locale - 1 (ADR-0007, ADR-0009).
            insert into app.family (id, name, timezone, frozen_through)
            values (v_family, p_family_name, v_timezone,
                    (app.now_utc() at time zone v_timezone)::pg_catalog.date - 1);

            -- Pranzo e Cena (ASM-063).
            insert into app.family_default_meal (family_id, meal_type)
            values (v_family, 'lunch'), (v_family, 'dinner');

            -- Le 8 portate base (FR-021); l'etichetta la traduce il client (ADR-0010).
            insert into app.course (family_id, base_code)
            select v_family, c.code
            from pg_catalog.unnest(array['starter', 'first', 'second', 'side', 'one_dish',
                                         'dessert', 'drink', 'other']) as c(code);

            -- Scadenza a 7 giorni (SR-033); created_at = app.now_utc() (default).
            insert into app.family_bootstrap (family_id, email_sha256, expires_at)
            values (v_family, p_email_sha256, app.now_utc() + interval '168 hours');

            insert into app.security_event
                (event_type, outcome, actor_kind, family_id, target_type, target_id,
                 correlation_id)
            values ('console.family_bootstrap', 'success', 'platform_operator', v_family,
                    'family', v_family, v_correlation);

            return v_family;
        end
        $fn$
        """,
    ),
    (
        "app.console_security_events(timestamptz, integer)",
        """
        create function app.console_security_events(p_since timestamptz, p_limit integer)
        returns table (
            id bigint,
            occurred_at timestamptz,
            event_type varchar,
            outcome text,
            actor_kind text,
            actor_account_id uuid,
            actor_role text,
            family_id uuid,
            target_type varchar,
            target_id uuid,
            ip inet,
            correlation_id uuid,
            details jsonb
        )
        language plpgsql volatile security definer set search_path = app, pg_temp
        as $fn$
        #variable_conflict use_column
        declare
            -- app.correlation_id: impostato dal job con set_config(..., true) (ADR-0011).
            v_correlation uuid :=
                nullif(pg_catalog.current_setting('app.correlation_id', true), '')::uuid;
        begin
            if p_since is null then
                raise exception using
                    errcode = 'invalid_parameter_value',
                    message = 'console_security_events: p_since is required';
            end if;
            if p_limit is null or p_limit < 1 or p_limit > 1000 then
                raise exception using
                    errcode = 'invalid_parameter_value',
                    message = 'console_security_events: p_limit must be between 1 and 1000';
            end if;

            -- IP sempre troncato (ADR-0011, SR-051): /24 per IPv4, /48 per IPv6.
            return query
                select e.id, e.occurred_at, e.event_type, e.outcome, e.actor_kind,
                       e.actor_account_id, e.actor_role, e.family_id, e.target_type,
                       e.target_id,
                       pg_catalog.network(pg_catalog.set_masklen(
                           e.ip,
                           case pg_catalog.family(e.ip) when 4 then 24 else 48 end
                       ))::inet,
                       e.correlation_id, e.details
                from app.security_event e
                where e.occurred_at >= p_since
                order by e.occurred_at, e.id
                limit p_limit;

            -- L'evento del comando si scrive dopo la lettura: non compare nel proprio output.
            insert into app.security_event
                (event_type, outcome, actor_kind, correlation_id, details)
            values ('console.security_log', 'success', 'platform_operator', v_correlation,
                    pg_catalog.jsonb_build_object('since', p_since, 'limit', p_limit));
            return;
        end
        $fn$
        """,
    ),
    (
        "app.console_audit_note(text)",
        """
        create function app.console_audit_note(p_ref text)
        returns void
        language plpgsql volatile security definer set search_path = app, pg_temp
        as $fn$
        declare
            -- app.correlation_id: impostato dal job con set_config(..., true) (ADR-0011).
            v_correlation uuid :=
                nullif(pg_catalog.current_setting('app.correlation_id', true), '')::uuid;
        begin
            -- Formato di request_ref (ADR-0011): codice di pratica, senza dati personali.
            if p_ref is null
               or p_ref collate "C" !~ '^[A-Z]{2,5}-[0-9]{8}-[0-9]{1,3}$' then
                raise exception using
                    errcode = 'invalid_parameter_value',
                    message = 'console_audit_note: malformed request_ref';
            end if;

            insert into app.security_event
                (event_type, outcome, actor_kind, correlation_id, details)
            values ('console.audit_note', 'success', 'platform_operator', v_correlation,
                    pg_catalog.jsonb_build_object('request_ref', p_ref));
        end
        $fn$
        """,
    ),
)


def upgrade() -> None:
    for signature, ddl in FUNCTIONS:
        op.execute(ddl)
        op.execute(f"revoke all on function {signature} from public")
        op.execute(f"grant execute on function {signature} to {CONSOLE_ROLE}")


def downgrade() -> None:
    for signature, _ in reversed(FUNCTIONS):
        op.execute(f"drop function {signature}")
