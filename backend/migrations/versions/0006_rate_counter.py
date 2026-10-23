"""0006: contatori dei limiti di frequenza `rate_counter`.

Revisione: 0006 (M0, SL-03b). docs/05-data.md §3.2, §3.4, §4.1, §5, §6.3, §10, §13; ADR-0006
(rev. 5); SR-003, SR-059, SR-070; THR-011, THR-012, THR-013, THR-044, THR-103.

- Tabella globale, non di famiglia (§6.3): nessuna RLS, nessuna `family_id`, nessuna FK. Le
  chiavi sono HMAC-SHA-256 con pepper (32 byte) di regola e identificativo: nessun IP, email o
  ID in chiaro (minimizzazione, §10).
- Tabella normale, non UNLOGGED: SR-059 chiede che i contatori sopravvivano ai riavvii.
- `menu_app`: DML completo (un solo upsert multiriga per richiesta e pulizia oraria del worker
  con SQL normale in `system_tx()`, ADR-0006). `menu_backup`: solo SELECT. `menu_console`:
  nulla. Nessuna funzione SECURITY DEFINER.
- `ix_rate_counter_window_start (window_start)`: la pulizia oraria (`DELETE ... WHERE
  window_start < now - 2 giorni`, SL-10a) non può usare la PK, che inizia con `key`. Il numero
  di righe dipende anche da chi attacca (una chiave per IP), quindi la pulizia resta un range
  scan anche sotto abuso. L'upsert aggiorna solo `count` (HOT), l'indice costa una voce per
  finestra nuova.
- `rate_block` è rinviata con CHG-020 (05-data §4.3): non si crea.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "menu_app"
BACKUP_ROLE = "menu_backup"

CREATE_TABLE = """
create table app.rate_counter (
    key bytea not null,
    window_start timestamptz not null,
    count integer not null default 1,
    constraint pk_rate_counter primary key (key, window_start),
    constraint ck_rate_counter_key check (octet_length(key) = 32),
    constraint ck_rate_counter_count check (count >= 1)
)
"""

# Pulizia oraria delle finestre più vecchie di 2 giorni (05-data §3.4, §5).
CREATE_INDEX = "create index ix_rate_counter_window_start on app.rate_counter (window_start)"

GRANTS: tuple[str, ...] = (
    f"grant select, insert, update, delete on app.rate_counter to {APP_ROLE}",
    f"grant select on app.rate_counter to {BACKUP_ROLE}",
)


def upgrade() -> None:
    op.execute(CREATE_TABLE)
    op.execute(CREATE_INDEX)
    for stmt in GRANTS:
        op.execute(stmt)


def downgrade() -> None:
    # Indice e grant spariscono con la tabella.
    op.execute("drop table app.rate_counter")
