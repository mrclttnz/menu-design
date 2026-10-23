"""0007: archivio piatti `dish`, `dish_course`, `dish_source`.

Revisione: 0007 (M0, SL-04). docs/05-data.md §4 ("Regola ON DELETE"), §4.2, §5, §6.1, §8 (Q4),
§11; FR-020, FR-024, FR-029, FR-030, FR-032; SR-008, SR-024, SR-041, SR-060; THR-020, THR-021.

- `dish` senza le colonne di M2 (`priority`, `promotion_dismissed_on`): arrivano con una
  migrazione di espansione (`ADD COLUMN ... DEFAULT 5 NOT NULL`, istantanea in PostgreSQL 17).
  `dish_tag` (M2) e `dish_like` (M1) non si creano.
- `name`, `notes`, `dish_source.reference/page/note` sono `varchar(n)` come in §4.2: un valore
  troppo lungo dà `string_data_right_truncation` (22001). Il nome ha in più un CHECK "non vuoto
  e non solo spazi" (stessa regola di `family.name` e `course.name`).
- `name_search` è generata da `app.search_norm(name)` (minuscole senza accenti, FR-030):
  la ricerca Q4 confronta `name_search LIKE '%' || app.search_norm(:q) || '%'`.
- `ck_dish_archived_requires_planned` (FR-029, AC-007.7) e il trigger
  `tg_dish_ever_planned_monotonic` (`ever_planned` non torna mai falso, decisione dell'utente
  del 2026-10-18). Trigger plpgsql SECURITY INVOKER, EXECUTE revocato a PUBLIC.
- Al massimo 10 fonti per piatto nel database (FR-024): `position BETWEEN 0 AND 9` più
  `UNIQUE (family_id, dish_id, position) DEFERRABLE INITIALLY IMMEDIATE` (riordino in una
  transazione con `SET CONSTRAINTS ... DEFERRED`). I link accettano solo `http`/`https`
  (SR-024, CHECK senza distinzione tra maiuscole e minuscole).
- FK composite `(family_id, ...)` (SR-041): verso `dish` ON DELETE CASCADE (contenitore → parti),
  verso `course` e `person` NO ACTION (una portata in uso non si elimina, AC-033.3).
- Anche `dish_course` e `dish_source` hanno la FK diretta `family_id → family ON DELETE CASCADE`
  (05-data §4, "Regola ON DELETE"). Per `dish_course` è necessaria: PostgreSQL accoda i trigger
  RI delle cascate in ampiezza, quindi senza di essa il controllo NO ACTION su `course` (livello
  2: famiglia → portata) scatterebbe prima della cascata piatto → `dish_course` (livello 2,
  accodata dopo) e `DELETE FROM family` fallirebbe. Con la FK diretta le righe spariscono al
  livello 1, prima di ogni controllo. Verificato su PostgreSQL 17 (test_dish_schema).
- RLS abilitata e forzata con `p_family`, `p_owner`, `p_backup` (§6.1). `menu_app`: DML
  completo sotto RLS (§3.2; le regole del Membro, sola lettura fino a SL-17, stanno in `access`).
  `menu_backup`: SELECT. `menu_console`: nulla. Nessuna funzione SECURITY DEFINER.
- Indici (§5): `ix_dish_family_name (family_id, name_search)` per l'elenco ordinato per nome con
  cursore su (`name_search`, `id`): lo spareggio per `id` si ottiene con un ordinamento
  incrementale sui pochi omonimi, senza ordinare l'intera famiglia; `ix_dish_course_course
  (family_id, course_id)` per il filtro per portata e il controllo FK all'eliminazione di una
  portata. Niente trigram (al massimo 2.000 piatti per famiglia, §5).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "menu_app"
BACKUP_ROLE = "menu_backup"

FAMILY_TABLES: tuple[str, ...] = ("dish", "dish_course", "dish_source")

CREATE_TABLES: tuple[str, ...] = (
    """
    create table app.dish (
        id uuid not null default pg_catalog.gen_random_uuid(),
        family_id uuid not null,
        name varchar(120) not null,
        name_search text not null generated always as (app.search_norm(name)) stored,
        status text not null default 'to_try',
        notes varchar(2000),
        prep_time text,
        archived_at timestamptz,
        ever_planned boolean not null default false,
        created_by uuid not null,
        created_at timestamptz not null default app.now_utc(),
        version integer not null default 1,
        modified_by uuid,
        modified_at timestamptz not null default app.now_utc(),
        constraint pk_dish primary key (id),
        constraint uq_dish_family_id_id unique (family_id, id),
        constraint fk_dish_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_dish_family_id_created_by_person
            foreign key (family_id, created_by) references app.person (family_id, id),
        constraint fk_dish_family_id_modified_by_person
            foreign key (family_id, modified_by) references app.person (family_id, id),
        constraint ck_dish_name
            check (char_length(name) between 1 and 120 and btrim(name) <> ''),
        constraint ck_dish_status check (status in ('to_try', 'tested')),
        constraint ck_dish_prep_time check (prep_time in ('under_30', '30_60', 'over_60')),
        constraint ck_dish_archived_requires_planned check (archived_at is null or ever_planned),
        constraint ck_dish_version check (version >= 1)
    )
    """,
    """
    create table app.dish_course (
        family_id uuid not null,
        dish_id uuid not null,
        course_id uuid not null,
        constraint pk_dish_course primary key (family_id, dish_id, course_id),
        constraint fk_dish_course_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_dish_course_family_id_dish_id_dish foreign key (family_id, dish_id)
            references app.dish (family_id, id) on delete cascade,
        constraint fk_dish_course_family_id_course_id_course foreign key (family_id, course_id)
            references app.course (family_id, id)
    )
    """,
    """
    create table app.dish_source (
        id uuid not null default pg_catalog.gen_random_uuid(),
        family_id uuid not null,
        dish_id uuid not null,
        position smallint not null,
        kind text not null,
        reference varchar(500) not null,
        page varchar(20),
        note varchar(500),
        constraint pk_dish_source primary key (id),
        constraint uq_dish_source_family_id_dish_id_position
            unique (family_id, dish_id, position) deferrable initially immediate,
        constraint fk_dish_source_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_dish_source_family_id_dish_id_dish foreign key (family_id, dish_id)
            references app.dish (family_id, id) on delete cascade,
        constraint ck_dish_source_position check (position between 0 and 9),
        constraint ck_dish_source_kind check (kind in ('link', 'book', 'magazine', 'other')),
        constraint ck_dish_source_reference check (btrim(reference) <> ''),
        constraint ck_dish_source_link_http check (kind <> 'link' or reference ~* '^https?://'),
        constraint ck_dish_source_page check (page is null or kind in ('book', 'magazine'))
    )
    """,
)

INDEXES: tuple[str, ...] = (
    "create index ix_dish_family_name on app.dish (family_id, name_search)",
    "create index ix_dish_course_course on app.dish_course (family_id, course_id)",
)

TRIGGER_FUNCTION = """
create function app.tg_dish_ever_planned_monotonic() returns trigger
language plpgsql as $fn$
begin
    -- FR-029, lettura letterale (decisione dell'utente del 2026-10-18): un piatto pianificato
    -- almeno una volta resta tale anche se poi viene tolto dal pasto.
    if old.ever_planned and not new.ever_planned then
        raise exception using
            errcode = 'check_violation',
            constraint = 'tg_dish_ever_planned_monotonic',
            message = 'dish.ever_planned cannot go back to false';
    end if;
    return new;
end
$fn$
"""

TRIGGER = (
    "create trigger tg_dish_ever_planned_monotonic before update of ever_planned "
    "on app.dish for each row execute function app.tg_dish_ever_planned_monotonic()"
)


def _rls(table: str) -> list[str]:
    pred = "family_id = app.current_family_id()"
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
    for ddl in INDEXES:
        op.execute(ddl)
    for table in FAMILY_TABLES:
        for stmt in _rls(table):
            op.execute(stmt)
    op.execute(TRIGGER_FUNCTION)
    op.execute("revoke all on function app.tg_dish_ever_planned_monotonic() from public")
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("drop trigger tg_dish_ever_planned_monotonic on app.dish")
    op.execute("drop function app.tg_dish_ever_planned_monotonic()")
    # Policy, grant e indici spariscono con le tabelle.
    op.execute("drop table app.dish_source")
    op.execute("drop table app.dish_course")
    op.execute("drop table app.dish")
