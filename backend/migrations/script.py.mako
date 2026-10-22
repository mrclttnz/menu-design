"""${message}

Revisione: ${up_revision}
Precedente: ${down_revision | comma,n}
Creata: ${create_date}

Regole (docs/05-data.md §12): RLS, policy, grant, trigger e funzioni nella stessa revisione della
tabella, in SQL esplicito con op.execute; downgrade in ordine inverso; solo app.now_utc() come
orologio; nessun dato sintetico. Se il downgrade perde dati, dichiararlo qui con LOSSY.
"""

from collections.abc import Sequence

from alembic import op
${imports if imports else ""}
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
