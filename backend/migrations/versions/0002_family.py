"""0002: tabelle di famiglia di M0, trigger, `app.family_today()`.

Revisione: 0002 (M0, SL-02). docs/05-data.md §4 ("Regola ON DELETE"), §4.2, §6.1, §7.1, §11.1.

- `family`, `family_default_meal`, `person`, `family_bootstrap`, `course` (portate base e
  personalizzate). Le righe di ogni famiglia (pasti di default, 8 portate base, bootstrap) le
  crea `console_bootstrap_family` (0004), mai una migrazione (ADR-0005 rev. 5).
- FK composite `(family_id, ...)` → `person(family_id, id)` (SR-041), `ON DELETE CASCADE` dalla
  famiglia, `NO ACTION` sui riferimenti storici a `person`.
- `person.account_id` senza FK: la FK verso `account` (ON DELETE RESTRICT) arriva con SL-03a.
- RLS abilitata e forzata con `p_family` (menu_app), `p_owner`, `p_backup`; `person` ha in più
  `p_person_self` (§6.1). DML completo a `menu_app` (matrice §3.2); nessun privilegio a
  `menu_console`.
- Trigger: `tg_family_timezone_valid` (ADR-0009) e il vincolo differito
  `tg_person_admin_invariant` (FR-011, SR-011, difesa aggiuntiva al lock applicativo).
- `app.family_today()`: LANGUAGE sql, STABLE, SECURITY INVOKER, EXECUTE al solo `menu_app`.

Scelte verificate su PostgreSQL 17 e riportate in 05-data (v6):
- testi con lunghezza massima come `text` + CHECK (non `varchar(n)`): un valore troppo lungo
  dà `check_violation` col nome del vincolo, non `string_data_right_truncation`;
- scadenze in ore (`interval '168 hours'`), non in giorni: `timestamptz + interval '7 days'`
  dipende dal TimeZone della sessione nei giorni di cambio dell'ora legale.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "menu_app"
BACKUP_ROLE = "menu_backup"

# (tabella, colonna su cui filtra la RLS). `family` filtra su `id` (05-data §4.2).
FAMILY_TABLES: tuple[tuple[str, str], ...] = (
    ("family", "id"),
    ("family_default_meal", "family_id"),
    ("person", "family_id"),
    ("family_bootstrap", "family_id"),
    ("course", "family_id"),
)

CREATE_TABLES: tuple[str, ...] = (
    """
    create table app.family (
        id uuid not null default pg_catalog.gen_random_uuid(),
        name text not null,
        timezone text not null default 'Europe/Rome',
        frozen_through date not null,
        status text not null default 'active',
        deletion_requested_at timestamptz,
        deletion_due_at timestamptz,
        deletion_requested_by uuid,
        created_at timestamptz not null default app.now_utc(),
        constraint pk_family primary key (id),
        constraint ck_family_name
            check (char_length(name) between 1 and 60 and btrim(name) <> ''),
        constraint ck_family_status check (status in ('active', 'pending_deletion')),
        constraint ck_family_deletion_coherent check (
            (status = 'active' and deletion_requested_at is null and deletion_due_at is null
                and deletion_requested_by is null)
            or (status = 'pending_deletion' and deletion_requested_at is not null
                and deletion_due_at is not null and deletion_requested_by is not null)
        ),
        constraint ck_family_deletion_due
            check (deletion_due_at = deletion_requested_at + interval '168 hours')
    )
    """,
    """
    create table app.family_default_meal (
        family_id uuid not null,
        meal_type text not null,
        constraint pk_family_default_meal primary key (family_id, meal_type),
        constraint fk_family_default_meal_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint ck_family_default_meal_meal_type
            check (meal_type in ('breakfast', 'lunch', 'snack', 'dinner', 'other'))
    )
    """,
    """
    create table app.person (
        id uuid not null default pg_catalog.gen_random_uuid(),
        family_id uuid not null,
        kind text not null,
        status text not null default 'active',
        account_id uuid,
        role text,
        display_name text,
        guardian_declared_at timestamptz,
        guardian_declared_by uuid,
        joined_on date not null,
        former_reason text,
        created_at timestamptz not null default app.now_utc(),
        constraint pk_person primary key (id),
        constraint uq_person_family_id_id unique (family_id, id),
        constraint fk_person_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_person_family_id_guardian_declared_by_person
            foreign key (family_id, guardian_declared_by) references app.person (family_id, id),
        constraint ck_person_kind check (kind in ('account', 'profile')),
        constraint ck_person_status check (status in ('active', 'former')),
        constraint ck_person_role check (role in ('admin', 'planner', 'member')),
        constraint ck_person_display_name
            check (char_length(display_name) between 1 and 60 and btrim(display_name) <> ''),
        constraint ck_person_former_reason check (
            former_reason in ('left', 'removed', 'profile_deleted', 'account_deleted',
                              'link_merged')
        ),
        constraint ck_person_active_account check (
            status <> 'active' or kind <> 'account'
            or (account_id is not null and role is not null and display_name is null)
        ),
        constraint ck_person_active_profile check (
            status <> 'active' or kind <> 'profile'
            or (account_id is null and role is null and display_name is not null
                and guardian_declared_at is not null and guardian_declared_by is not null)
        ),
        constraint ck_person_former check (
            status <> 'former'
            or (account_id is null and role is null and display_name is null
                and former_reason is not null)
        )
    )
    """,
    # ASM-050: un account ha al massimo una persona (attiva) in tutto il sistema.
    "create unique index ux_person_account_single_family on app.person (account_id) "
    "where account_id is not null",
    # Riferimento circolare family → person, annullabile (05-data §4.2).
    "alter table app.family add constraint fk_family_id_deletion_requested_by_person "
    "foreign key (id, deletion_requested_by) references app.person (family_id, id)",
    """
    create table app.family_bootstrap (
        id uuid not null default pg_catalog.gen_random_uuid(),
        family_id uuid not null,
        email_sha256 bytea,
        created_at timestamptz not null default app.now_utc(),
        expires_at timestamptz not null,
        redeemed_at timestamptz,
        redeemed_person_id uuid,
        constraint pk_family_bootstrap primary key (id),
        constraint uq_family_bootstrap_family_id unique (family_id),
        constraint fk_family_bootstrap_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_family_bootstrap_family_id_redeemed_person_id_person
            foreign key (family_id, redeemed_person_id) references app.person (family_id, id),
        constraint ck_family_bootstrap_email_sha256 check (octet_length(email_sha256) = 32),
        constraint ck_family_bootstrap_hash_until_redeemed
            check ((redeemed_at is null) = (email_sha256 is not null)),
        constraint ck_family_bootstrap_redeemed_coherent
            check ((redeemed_at is null) = (redeemed_person_id is null)),
        constraint ck_family_bootstrap_expires_at
            check (expires_at = created_at + interval '168 hours')
    )
    """,
    """
    create table app.course (
        id uuid not null default pg_catalog.gen_random_uuid(),
        family_id uuid not null,
        base_code text,
        name text,
        name_key text generated always as (lower(btrim(name))) stored,
        created_at timestamptz not null default app.now_utc(),
        constraint pk_course primary key (id),
        constraint uq_course_family_id_id unique (family_id, id),
        constraint uq_course_family_id_base_code unique (family_id, base_code),
        constraint uq_course_family_id_name_key unique (family_id, name_key),
        constraint fk_course_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint ck_course_base_code check (
            base_code in ('starter', 'first', 'second', 'side', 'one_dish', 'dessert', 'drink',
                          'other')
        ),
        constraint ck_course_base_or_name check ((base_code is null) <> (name is null)),
        constraint ck_course_name
            check (char_length(name) between 1 and 40 and btrim(name) <> '')
    )
    """,
)

# Funzioni trigger: plpgsql, SECURITY INVOKER, nomi qualificati (nessuna dipendenza dal
# search_path del chiamante). EXECUTE revocato a PUBLIC: i trigger non lo richiedono.
TRIGGER_FUNCTIONS: tuple[tuple[str, str], ...] = (
    (
        "app.tg_family_timezone_valid()",
        """
        create function app.tg_family_timezone_valid() returns trigger
        language plpgsql as $fn$
        begin
            if not exists (
                select 1 from pg_catalog.pg_timezone_names z where z.name = new.timezone
            ) then
                raise exception using
                    errcode = 'check_violation',
                    constraint = 'tg_family_timezone_valid',
                    message = 'family.timezone is not a known IANA time zone';
            end if;
            return new;
        end
        $fn$
        """,
    ),
    (
        "app.tg_person_admin_invariant()",
        """
        create function app.tg_person_admin_invariant() returns trigger
        language plpgsql as $fn$
        begin
            -- Al commit: la famiglia, se esiste ancora e ha persone collegate a un account,
            -- ha almeno un Amministratore attivo (05-data §4.2). La cascata dalla famiglia
            -- e una famiglia appena creata dalla console (senza persone) non la violano.
            if exists (select 1 from app.family f where f.id = old.family_id)
               and exists (
                   select 1 from app.person p
                   where p.family_id = old.family_id and p.account_id is not null
               )
               and not exists (
                   select 1 from app.person p
                   where p.family_id = old.family_id and p.status = 'active'
                     and p.role = 'admin'
               ) then
                raise exception using
                    errcode = 'check_violation',
                    constraint = 'tg_person_admin_invariant',
                    message = 'the family must keep at least one active admin';
            end if;
            return null;
        end
        $fn$
        """,
    ),
)

TRIGGERS: tuple[tuple[str, str, str], ...] = (
    (
        "tg_family_timezone_valid",
        "app.family",
        "create trigger tg_family_timezone_valid before insert or update of timezone "
        "on app.family for each row execute function app.tg_family_timezone_valid()",
    ),
    (
        "tg_person_admin_invariant",
        "app.person",
        "create constraint trigger tg_person_admin_invariant after update or delete "
        "on app.person deferrable initially deferred for each row "
        "execute function app.tg_person_admin_invariant()",
    ),
)

FAMILY_TODAY = (
    "create function app.family_today() returns date "
    "language sql stable parallel safe "
    "as $$ select (app.now_utc() at time zone f.timezone)::pg_catalog.date "
    "from app.family f where f.id = app.current_family_id() $$"
)


def _rls(table: str, key: str) -> list[str]:
    pred = f"{key} = app.current_family_id()"
    return [
        f"alter table app.{table} enable row level security",
        f"alter table app.{table} force row level security",
        f"create policy p_family on app.{table} for all to {APP_ROLE} "
        f"using ({pred}) with check ({pred})",
        f"create policy p_owner on app.{table} for all to menu_owner "
        "using (true) with check (true)",
        f"create policy p_backup on app.{table} for select to {BACKUP_ROLE} using (true)",
        f"grant select, insert, update, delete on app.{table} to {APP_ROLE}",
        f"grant select on app.{table} to {BACKUP_ROLE}",
    ]


def upgrade() -> None:
    for ddl in CREATE_TABLES:
        op.execute(ddl)
    for table, key in FAMILY_TABLES:
        for stmt in _rls(table, key):
            op.execute(stmt)
    # Risoluzione della membership della sessione senza SECURITY DEFINER (05-data §6.1).
    op.execute(
        f"create policy p_person_self on app.person for select to {APP_ROLE} "
        "using (account_id = app.current_account_id())"
    )
    for signature, ddl in TRIGGER_FUNCTIONS:
        op.execute(ddl)
        op.execute(f"revoke all on function {signature} from public")
    for _, _, ddl in TRIGGERS:
        op.execute(ddl)
    op.execute(FAMILY_TODAY)
    op.execute("revoke all on function app.family_today() from public")
    op.execute(f"grant execute on function app.family_today() to {APP_ROLE}")


def downgrade() -> None:
    op.execute("drop function app.family_today()")
    for name, table, _ in reversed(TRIGGERS):
        op.execute(f"drop trigger {name} on {table}")
    for signature, _ in reversed(TRIGGER_FUNCTIONS):
        op.execute(f"drop function {signature}")
    # Le policy e i grant spariscono con le tabelle.
    op.execute("drop table app.course")
    op.execute("drop table app.family_bootstrap")
    op.execute("alter table app.family drop constraint fk_family_id_deletion_requested_by_person")
    op.execute("drop table app.person")
    op.execute("drop table app.family_default_meal")
    op.execute("drop table app.family")
