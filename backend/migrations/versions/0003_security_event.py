"""0003: registro di sicurezza `security_event` e trigger d'immutabilità.

Revisione: 0003 (M0, SL-02). docs/05-data.md §4.1, §3.2, §6.3, §9.1; SR-020, SR-051, SR-057.

- Tabella globale, non di famiglia (§6.3): nessuna RLS, nessuna FK (gli eventi sopravvivono ad
  account e famiglie per 12 mesi). Protezione con i privilegi: `menu_app` ha solo INSERT
  (niente SELECT, quindi nemmeno `INSERT ... RETURNING`), `menu_console` nulla (legge con
  `console_security_events`, 0004), `menu_backup` SELECT per il dump.
- `tg_security_event_immutable` (BEFORE UPDATE, anche per `menu_owner`): rifiuta ogni modifica
  salvo quella della sola colonna `ip`, e solo verso NULL o verso l'indirizzo troncato a /24
  (IPv4) o /48 (IPv6), cioè il troncamento a 90 giorni di `maint_security_log_retention()`
  (SL-10a). Le cancellazioni restano del solo proprietario (conservazione a 12 mesi).
- Indice `ix_security_event_time (occurred_at)`: `security-log --since` e conservazione.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CREATE_TABLE = r"""
create table app.security_event (
    id bigint generated always as identity,
    occurred_at timestamptz not null default app.now_utc(),
    event_type varchar(64) not null,
    outcome text not null,
    actor_kind text not null,
    actor_account_id uuid,
    actor_role text,
    family_id uuid,
    target_type varchar(32),
    target_id uuid,
    ip inet,
    correlation_id uuid,
    details jsonb,
    constraint pk_security_event primary key (id),
    constraint ck_security_event_event_type
        check (event_type ~ '^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$'),
    constraint ck_security_event_outcome check (outcome in ('success', 'failure', 'denied')),
    constraint ck_security_event_actor_kind
        check (actor_kind in ('account', 'anonymous', 'platform_operator', 'system')),
    constraint ck_security_event_actor_role check (actor_role in ('admin', 'planner', 'member')),
    constraint ck_security_event_details check (pg_column_size(details) <= 1024)
)
"""

IMMUTABLE_FUNCTION = """
create function app.tg_security_event_immutable() returns trigger
language plpgsql as $fn$
declare
    v_prefix integer;
begin
    if (pg_catalog.to_jsonb(new) operator(pg_catalog.-) 'ip'::text)
       is distinct from (pg_catalog.to_jsonb(old) operator(pg_catalog.-) 'ip'::text) then
        raise exception using
            errcode = 'insufficient_privilege',
            message = 'security_event is append-only: only the ip column may be truncated';
    end if;
    if new.ip is not distinct from old.ip or new.ip is null then
        return new;
    end if;
    if old.ip is not null and pg_catalog.family(new.ip) = pg_catalog.family(old.ip) then
        v_prefix := case pg_catalog.family(old.ip) when 4 then 24 else 48 end;
        if pg_catalog.host(new.ip) = pg_catalog.host(
               pg_catalog.network(pg_catalog.set_masklen(old.ip, v_prefix))) then
            return new;
        end if;
    end if;
    raise exception using
        errcode = 'insufficient_privilege',
        message = 'security_event.ip may only be truncated (/24, /48) or cleared';
end
$fn$
"""


def upgrade() -> None:
    op.execute(CREATE_TABLE)
    op.execute("create index ix_security_event_time on app.security_event (occurred_at)")
    # Sola aggiunta per l'app (05-data §3.2): nessun SELECT, UPDATE, DELETE, TRUNCATE.
    op.execute("revoke all on app.security_event from menu_app, menu_console")
    op.execute("grant insert on app.security_event to menu_app")
    op.execute("grant select on app.security_event to menu_backup")
    op.execute(IMMUTABLE_FUNCTION)
    op.execute("revoke all on function app.tg_security_event_immutable() from public")
    op.execute(
        "create trigger tg_security_event_immutable before update on app.security_event "
        "for each row execute function app.tg_security_event_immutable()"
    )


def downgrade() -> None:
    op.execute("drop trigger tg_security_event_immutable on app.security_event")
    op.execute("drop function app.tg_security_event_immutable()")
    op.execute("drop table app.security_event")
