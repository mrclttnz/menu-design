"""0008: eventi di modifica `change_event` (sola aggiunta).

Revisione: 0008 (M0, SL-05). docs/05-data.md §4.2 (`change_event`), §5, §6.1, §6.3, §6.4, §10;
ADR-0012 (registrazione applicativa, autore come persona, formato compatto v1, immutabilità);
FR-061, SR-022, SR-042, SR-047, SR-057; US-049 (AC-049.2, AC-049.3); THR-117.

- Tabella di famiglia con RLS abilitata e forzata, ma **senza** `p_family FOR ALL`: per
  `menu_app` solo `p_family_select FOR SELECT` e `p_family_insert FOR INSERT ... WITH CHECK`
  (05-data §6.1). Più `p_owner` e `p_backup` come le altre tabelle di famiglia.
- Privilegi: `menu_app` SELECT e INSERT (niente UPDATE, DELETE, TRUNCATE: AC-049.3, SR-057),
  `menu_backup` SELECT, `menu_console` nulla. Nessuna funzione SECURITY DEFINER.
- `tg_change_event_immutable` (BEFORE UPDATE FOR EACH ROW) solleva sempre, anche per
  `menu_owner` (THR-117). Nessun trigger su DELETE e TRUNCATE: le cancellazioni avvengono solo
  per cascata dalla famiglia (FK `ON DELETE CASCADE`, eseguita come proprietario), e i test
  svuotano le tabelle con TRUNCATE come proprietario.
- Nessuna colonna può contenere un nome o un'email (AC-049.2, SR-047): le persone sono solo
  identificativi (`actor_person_id`, `subject_person_id`), le colonne di testo sono codici di
  elenchi chiusi (CHECK). `before`/`after` sono jsonb nel formato compatto v1, validato in
  scrittura dal codec (`menu.history.codec`); il database ne controlla solo la forma minima.
- Nessuna FK su `actor_person_id`, `subject_person_id`, `dish_id`: riga di sola aggiunta, il
  piatto mai pianificato può essere cancellato ("piatto eliminato") e la persona diventa un
  tombstone senza riscrivere l'evento (ADR-0012). Unica FK: `family_id → family ON DELETE
  CASCADE` (gli eventi vivono quanto la famiglia, 05-data §9.1).
- Vincoli oltre la tabella di 05-data §4.2 (05-data v10):
  - `ck_change_event_actor_role_person`: con `actor_kind='person'` il ruolo è obbligatorio (FR-061:
    "ruolo dell'autore in quel momento"), altrimenti è NULL;
  - `ck_change_event_meal_type`/`ck_change_event_meal_slot`: stessi domini di `meal` (ADR-0009),
    così ogni colonna di testo è un codice chiuso;
  - `after` NOT NULL (decisione dell'utente, 2026-10-23): ogni evento porta la versione del
    formato e resta decodificabile (AC-028.5);
  - `ck_change_event_payload_size` a 20.480 byte (decisione dell'utente, 2026-10-23): il caso
    peggiore valido di `meal_content` (10 voci libere di 200 caratteri tolte e 10 aggiunte) vale
    5.656 byte in ASCII e 17.656 con caratteri di 4 byte; il CHECK vede la dimensione non
    compressa. `coalesce` su `before`: un NULL renderebbe NULL la somma e il CHECK passerebbe;
  - `ck_change_event_payload_shape`: `before` e `after` sono oggetti JSON, `after` porta la
    versione numerica `v`, `before` no (ADR-0012: "ogni payload ha `v`", in `after`).
- Indici (§5): `ix_change_event_family_time (family_id, occurred_at DESC, id)` per la
  cronologia a cursore e i KPI per settimana; `ix_change_event_family_day (family_id,
  meal_date) WHERE meal_date IS NOT NULL` per la cronologia per giorno e pasto. Entrambi
  iniziano con `family_id` e servono anche alla cascata dalla famiglia.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "menu_app"
BACKUP_ROLE = "menu_backup"

CREATE_TABLE = """
create table app.change_event (
    id uuid not null default pg_catalog.gen_random_uuid(),
    family_id uuid not null,
    occurred_at timestamptz not null default app.now_utc(),
    actor_kind text not null,
    actor_person_id uuid,
    actor_role text,
    unit_type text not null,
    op text not null,
    meal_date date,
    meal_type text,
    meal_slot smallint,
    subject_person_id uuid,
    dish_id uuid,
    before jsonb,
    after jsonb not null,
    correlation_id uuid,
    constraint pk_change_event primary key (id),
    constraint fk_change_event_family_id_family foreign key (family_id)
        references app.family (id) on delete cascade,
    constraint ck_change_event_actor_kind
        check (actor_kind in ('person', 'platform_operator', 'system')),
    constraint ck_change_event_actor_person
        check ((actor_kind = 'person') = (actor_person_id is not null)),
    constraint ck_change_event_actor_role check (actor_role in ('admin', 'planner', 'member')),
    constraint ck_change_event_actor_role_person
        check ((actor_kind = 'person') = (actor_role is not null)),
    constraint ck_change_event_unit_type
        check (unit_type in ('meal_content', 'meal_guests', 'attendance', 'typical_week',
                             'dish', 'membership')),
    constraint ck_change_event_op
        check (op in ('set', 'clear', 'move', 'swap', 'copy', 'status_change', 'archive',
                      'restore', 'role_change')),
    constraint ck_change_event_meal_type
        check (meal_type in ('breakfast', 'lunch', 'snack', 'dinner', 'other')),
    constraint ck_change_event_meal_slot
        check (meal_slot is null
               or (meal_type <> 'other' and meal_slot = 0)
               or (meal_type = 'other' and meal_slot between 0 and 4)),
    constraint ck_change_event_key
        check (case unit_type
                   when 'meal_content' then
                       meal_date is not null and meal_type is not null and meal_slot is not null
                   when 'meal_guests' then
                       meal_date is not null and meal_type is not null and meal_slot is not null
                   when 'attendance' then
                       meal_date is not null and meal_type is not null and meal_slot is not null
                       and subject_person_id is not null
                   when 'typical_week' then subject_person_id is not null
                   when 'membership' then subject_person_id is not null
                   when 'dish' then dish_id is not null
               end),
    constraint ck_change_event_payload_shape
        check ((before is null
                or (jsonb_typeof(before) = 'object' and not (before ? 'v')))
               and jsonb_typeof(after) = 'object'
               and jsonb_typeof(after -> 'v') = 'number'),
    constraint ck_change_event_payload_size
        check (coalesce(pg_column_size(before), 0) + pg_column_size(after) <= 20480)
)
"""

INDEXES: tuple[str, ...] = (
    "create index ix_change_event_family_time "
    "on app.change_event (family_id, occurred_at desc, id)",
    "create index ix_change_event_family_day "
    "on app.change_event (family_id, meal_date) where meal_date is not null",
)

PRED = "family_id = app.current_family_id()"

SECURITY: tuple[str, ...] = (
    "alter table app.change_event enable row level security",
    "alter table app.change_event force row level security",
    # Nessuna policy FOR ALL: insieme ai privilegi, UPDATE e DELETE non hanno righe visibili.
    f"create policy p_family_select on app.change_event for select to {APP_ROLE} using ({PRED})",
    f"create policy p_family_insert on app.change_event for insert to {APP_ROLE} "
    f"with check ({PRED})",
    "create policy p_owner on app.change_event for all to menu_owner "
    "using (true) with check (true)",
    f"create policy p_backup on app.change_event for select to {BACKUP_ROLE} using (true)",
    # Sola aggiunta (05-data §3.2): niente UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER.
    f"revoke all on app.change_event from {APP_ROLE}, menu_console, {BACKUP_ROLE}",
    f"grant select, insert on app.change_event to {APP_ROLE}",
    f"grant select on app.change_event to {BACKUP_ROLE}",
)

IMMUTABLE_FUNCTION = """
create function app.tg_change_event_immutable() returns trigger
language plpgsql as $fn$
begin
    -- SR-022, SR-057, THR-117: un evento non si modifica mai, nemmeno dal proprietario.
    raise exception using
        errcode = 'insufficient_privilege',
        message = 'change_event is append-only: events are immutable';
end
$fn$
"""

TRIGGER = (
    "create trigger tg_change_event_immutable before update on app.change_event "
    "for each row execute function app.tg_change_event_immutable()"
)


def upgrade() -> None:
    op.execute(CREATE_TABLE)
    for ddl in INDEXES:
        op.execute(ddl)
    for stmt in SECURITY:
        op.execute(stmt)
    op.execute(IMMUTABLE_FUNCTION)
    op.execute("revoke all on function app.tg_change_event_immutable() from public")
    op.execute(TRIGGER)


def downgrade() -> None:
    op.execute("drop trigger tg_change_event_immutable on app.change_event")
    op.execute("drop function app.tg_change_event_immutable()")
    # Policy, grant e indici spariscono con la tabella.
    op.execute("drop table app.change_event")
