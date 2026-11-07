"""0009: piano dei pasti `meal`, `meal_item`, `app.effective_meals()`; chiavi di `change_event`.

Revisione: 0009 (M0, SL-06a). docs/05-data.md §4 ("Regola ON DELETE"), §4.2 (`meal`,
`meal_item`, `change_event`), §5, §6.1, §7.1, §8 (Q2, Q3), §11.1, §12; ADR-0007, ADR-0009;
FR-036, FR-038, FR-039, FR-052; SR-008, SR-041, SR-060; AC-007.6, AC-008.9, AC-033.3, AC-052.7;
ASM-068; CR-SL05-004.

- `meal`: PK naturale (`family_id`, `meal_date`, `meal_type`, `meal_slot`), come l'indirizzo
  dell'API `/meals/{date}/{mealType}/{slot}` (ADR-0009). `meal_slot` 0-4 solo per `other`
  (al massimo 5 "Altro pasto" attivi, ASM-068, garantiti dal CHECK perché le righe rimosse si
  riusano); `presence='inherit'` solo nello slot 0. `name` è un testo `text` + CHECK (regola
  della v6), solo per `other`. `guests_note` resta `varchar(200)` come nei test (eccezione voluta,
  come `dish.notes`), con in più un CHECK di non vuoto: il codec v1 ammette `gn` da 1 a 200.
- `meal_item`: al massimo 10 voci per pasto nel database (AC-008.9) con `position BETWEEN 0 AND 9`
  e `UNIQUE (..., position) DEFERRABLE INITIALLY IMMEDIATE` (riordino con
  `SET CONSTRAINTS ... DEFERRED`). CK di forma: piatto (`dish_id`, `course_id`, niente testo) o
  voce libera (testo, niente piatto, portata né "non cucinato").
- FK (§4, "Regola ON DELETE"): diretta `family_id → family ON DELETE CASCADE` su entrambe (anche
  sulla parte `meal_item`, come `dish_course` in 0007); `meal_item → meal` CASCADE (contenitore →
  parti); `meal_item → dish` e `→ course` NO ACTION, composite con `family_id` (SR-041): un piatto
  o una portata in uso non si elimina, anche in corsa (AC-007.6, AC-033.3). La portata non è una
  FK verso `dish_course`: togliere una portata a un piatto non altera i pasti passati.
  `meal → person` (autori delle due unità) NO ACTION: le persone non si cancellano, diventano
  tombstone (§7.3).
- Indici (§5): solo `ix_meal_item_dish (family_id, dish_id, meal_date) WHERE kind = 'dish'` per
  "ultima volta cucinato" (Q3). Il piano (Q2) e le cascate usano i prefissi delle PK/UNIQUE.
- RLS abilitata e forzata con `p_family`, `p_owner`, `p_backup` (§6.1). `menu_app`: SELECT,
  INSERT, UPDATE, DELETE (§3.2); `menu_backup`: SELECT; `menu_console`: nulla (SR-040).
- `app.effective_meals(p_from, p_to)`: LANGUAGE sql, STABLE, SECURITY INVOKER, senza `SET`,
  un solo SELECT (inlinabile in FROM, §11.1); EXECUTE al solo `menu_app`. Lavora nel contesto
  di famiglia e sotto RLS: senza contesto non restituisce nulla. I giorni come serie di interi
  sommati a una data, non `generate_series` su timestamp (che dipenderebbe dal TimeZone).
- `change_event` (CR-SL05-004): `ck_change_event_meal_slot` rifiuta uno slot senza tipo;
  `ck_change_event_key` richiede **esattamente** le colonne chiave del tipo di unità e vieta le
  altre. Il `downgrade` ripristina le definizioni di 0008. Le righe esistenti (solo eventi
  `dish` con il solo `dish_id`, scritti da SL-05) rispettano già i vincoli nuovi.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "menu_app"
BACKUP_ROLE = "menu_backup"

FAMILY_TABLES: tuple[str, ...] = ("meal", "meal_item")

CREATE_TABLES: tuple[str, ...] = (
    """
    create table app.meal (
        family_id uuid not null,
        meal_date date not null,
        meal_type text not null,
        meal_slot smallint not null default 0,
        name text,
        presence text not null default 'inherit',
        special_kind text,
        content_version integer not null default 0,
        content_modified_by uuid,
        content_modified_at timestamptz,
        guests_count smallint not null default 0,
        guests_note varchar(200),
        guests_version integer not null default 0,
        guests_modified_by uuid,
        guests_modified_at timestamptz,
        constraint pk_meal primary key (family_id, meal_date, meal_type, meal_slot),
        constraint fk_meal_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_meal_family_id_content_modified_by_person
            foreign key (family_id, content_modified_by) references app.person (family_id, id),
        constraint fk_meal_family_id_guests_modified_by_person
            foreign key (family_id, guests_modified_by) references app.person (family_id, id),
        constraint ck_meal_meal_type
            check (meal_type in ('breakfast', 'lunch', 'snack', 'dinner', 'other')),
        constraint ck_meal_meal_slot
            check ((meal_type <> 'other' and meal_slot = 0)
                   or (meal_type = 'other' and meal_slot between 0 and 4)),
        constraint ck_meal_name
            check (name is null
                   or (meal_type = 'other' and char_length(name) between 1 and 40
                       and btrim(name) <> '')),
        constraint ck_meal_presence check (presence in ('inherit', 'added', 'removed')),
        constraint ck_meal_presence_slot check (meal_slot = 0 or presence <> 'inherit'),
        constraint ck_meal_special_kind check (special_kind in ('away', 'restaurant', 'skipped')),
        constraint ck_meal_content_version check (content_version >= 0),
        constraint ck_meal_guests_count check (guests_count between 0 and 50),
        constraint ck_meal_guests_note check (btrim(guests_note) <> ''),
        constraint ck_meal_guests_version check (guests_version >= 0)
    )
    """,
    """
    create table app.meal_item (
        id uuid not null default pg_catalog.gen_random_uuid(),
        family_id uuid not null,
        meal_date date not null,
        meal_type text not null,
        meal_slot smallint not null,
        position smallint not null,
        kind text not null,
        dish_id uuid,
        course_id uuid,
        free_text varchar(200),
        not_cooked boolean not null default false,
        constraint pk_meal_item primary key (id),
        constraint uq_meal_item_family_id_id unique (family_id, id),
        constraint uq_meal_item_meal_position
            unique (family_id, meal_date, meal_type, meal_slot, position)
            deferrable initially immediate,
        constraint fk_meal_item_family_id_family foreign key (family_id)
            references app.family (id) on delete cascade,
        constraint fk_meal_item_meal foreign key (family_id, meal_date, meal_type, meal_slot)
            references app.meal (family_id, meal_date, meal_type, meal_slot) on delete cascade,
        constraint fk_meal_item_family_id_dish_id_dish foreign key (family_id, dish_id)
            references app.dish (family_id, id),
        constraint fk_meal_item_family_id_course_id_course foreign key (family_id, course_id)
            references app.course (family_id, id),
        constraint ck_meal_item_position check (position between 0 and 9),
        constraint ck_meal_item_kind check (kind in ('dish', 'free_text')),
        constraint ck_meal_item_free_text
            check (char_length(free_text) between 1 and 200 and btrim(free_text) <> ''),
        constraint ck_meal_item_shape
            check ((kind = 'dish' and dish_id is not null and course_id is not null
                    and free_text is null)
                   or (kind = 'free_text' and free_text is not null and dish_id is null
                       and course_id is null and not not_cooked))
    )
    """,
)

INDEXES: tuple[str, ...] = (
    "create index ix_meal_item_dish on app.meal_item (family_id, dish_id, meal_date) "
    "where kind = 'dish'",
)

# 05-data §7.1. Due rami disgiunti, quindi nessun duplicato:
# 1. righe `added` in qualunque giorno dell'intervallo (congelato o no);
# 2. giorni dopo `frozen_through`: i tipi di default nello slot 0, se non c'è una riga o la riga
#    è `inherit` (una riga `added` è già nel ramo 1, una `removed` nasconde il pasto).
EFFECTIVE_MEALS = """
create function app.effective_meals(p_from date, p_to date)
returns table (meal_date date, meal_type text, meal_slot smallint)
language sql stable parallel safe
as $fn$
    select m.meal_date, m.meal_type, m.meal_slot
    from app.meal m
    where m.family_id = app.current_family_id()
      and m.meal_date between p_from and p_to
      and m.presence = 'added'
    union all
    select g.day, d.meal_type, 0::smallint
    from app.family f
    join app.family_default_meal d on d.family_id = f.id
    cross join lateral (select greatest(p_from, f.frozen_through + 1) as first_day) s
    cross join lateral (
        select s.first_day + n as day
        from pg_catalog.generate_series(0, p_to - s.first_day) n
    ) g
    where f.id = app.current_family_id()
      and not exists (
          select 1 from app.meal x
          where x.family_id = f.id
            and x.meal_date between p_from and p_to  -- limite esplicito: range scan sulla PK
            and x.meal_date = g.day
            and x.meal_type = d.meal_type
            and x.meal_slot = 0
            and x.presence <> 'inherit'
      )
$fn$
"""
EFFECTIVE_MEALS_SIGNATURE = "app.effective_meals(date, date)"

# --- change_event: chiavi per tipo di unità (CR-SL05-004) ----------------------------------------

SLOT_CHECK_0009 = """
    check (meal_slot is null
           or (meal_type is not null
               and ((meal_type <> 'other' and meal_slot = 0)
                    or (meal_type = 'other' and meal_slot between 0 and 4))))
"""
KEY_CHECK_0009 = """
    check (case unit_type
               when 'meal_content' then
                   meal_date is not null and meal_type is not null and meal_slot is not null
                   and subject_person_id is null and dish_id is null
               when 'meal_guests' then
                   meal_date is not null and meal_type is not null and meal_slot is not null
                   and subject_person_id is null and dish_id is null
               when 'attendance' then
                   meal_date is not null and meal_type is not null and meal_slot is not null
                   and subject_person_id is not null and dish_id is null
               when 'typical_week' then
                   subject_person_id is not null and meal_date is null and meal_type is null
                   and meal_slot is null and dish_id is null
               when 'membership' then
                   subject_person_id is not null and meal_date is null and meal_type is null
                   and meal_slot is null and dish_id is null
               when 'dish' then
                   dish_id is not null and meal_date is null and meal_type is null
                   and meal_slot is null and subject_person_id is null
               else false
           end)
"""
# Definizioni di 0008, ripristinate dal downgrade.
SLOT_CHECK_0008 = """
    check (meal_slot is null
           or (meal_type <> 'other' and meal_slot = 0)
           or (meal_type = 'other' and meal_slot between 0 and 4))
"""
KEY_CHECK_0008 = """
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
           end)
"""


def _replace_event_checks(slot_check: str, key_check: str) -> None:
    """Stessi nomi, un solo ALTER; `NOT VALID` e poi `VALIDATE` (05-data §12, tabelle grandi):
    la convalida prende solo SHARE UPDATE EXCLUSIVE e non blocca gli INSERT degli eventi."""
    op.execute(
        "alter table app.change_event "
        "drop constraint ck_change_event_meal_slot, "
        "drop constraint ck_change_event_key, "
        f"add constraint ck_change_event_meal_slot {slot_check} not valid, "
        f"add constraint ck_change_event_key {key_check} not valid"
    )
    op.execute("alter table app.change_event validate constraint ck_change_event_meal_slot")
    op.execute("alter table app.change_event validate constraint ck_change_event_key")


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
    op.execute(EFFECTIVE_MEALS)
    op.execute(f"revoke all on function {EFFECTIVE_MEALS_SIGNATURE} from public")
    op.execute(f"grant execute on function {EFFECTIVE_MEALS_SIGNATURE} to {APP_ROLE}")
    _replace_event_checks(SLOT_CHECK_0009, KEY_CHECK_0009)


def downgrade() -> None:
    _replace_event_checks(SLOT_CHECK_0008, KEY_CHECK_0008)
    op.execute(f"drop function {EFFECTIVE_MEALS_SIGNATURE}")
    # Policy, grant e indici spariscono con le tabelle.
    op.execute("drop table app.meal_item")
    op.execute("drop table app.meal")
