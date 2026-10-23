"""0005: identità di M0: `account`, FK `person.account_id`, `session`, `auth_flow`, risolutori.

Revisione: 0005 (M0, SL-03a). docs/05-data.md §3.2, §3.3, §4.1, §4.2 (`person.account_id`),
§6.1, §6.2, §9.1; ADR-0004 (rev. 3: esito del callback sul server); SR-005, SR-014, SR-033,
SR-037, SR-049, SR-051; THR-002, THR-003, THR-005, THR-044.

- `account` (nessuna RLS, decisione dell'utente: solo `system_tx` nel modulo `identity`), con
  `email_sha256` scritto dal servizio (ADR-0011). Identità = (`auth_provider`, `auth_subject`);
  l'email non è unica (SR-033).
- FK `person.account_id` → `account(id)` ON DELETE RESTRICT: un account con una persona attiva
  si elimina solo con la procedura di 05-data §9.2. Nessun dato da migrare: in SL-02 nessuna
  funzione crea persone (il bootstrap crea la famiglia senza `person`).
- `session` con RLS per account: `p_session_self` (ALL, con WITH CHECK), più due policy per la
  pulizia del worker senza contesto (`p_session_expired_select`, `p_session_expired_delete`,
  solo con `app.current_account_id() is null`),
  `p_owner`, `p_backup`. Scadenze in ore: 720 (30 giorni) e 2160 (90 giorni).
- `auth_flow` (`login`, `reauth`; `invite` arriva con l'ordine 14 del piano) con l'esito del
  callback sul server (ADR-0004 rev. 3): `consumed_at`, `outcome_code`, `outcome_params`.
  Il callback reclama la riga una sola volta (`consumed_at IS NULL`), il successo la cancella,
  un esito negativo resta leggibile **una volta** per al massimo 5 minuti da `consumed_at`.
- `session_resolve(bytea)` e `bootstrap_resolve(bytea)`: SECURITY DEFINER, plpgsql,
  `search_path = app, pg_temp`, EXECUTE al solo `menu_app`; restituiscono solo ID, istanti e
  l'hash CSRF (05-data §6.2), e solo per segreti validi e non scaduti.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "menu_app"
BACKUP_ROLE = "menu_backup"

# Sessione valida: ultimo uso entro 30 giorni e creazione entro 90 (AC-001.3, SR-037).
# In ore, non in giorni: indipendenti dal TimeZone della sessione (05-data §11.1).
IDLE_LIMIT = "interval '720 hours'"
ABSOLUTE_LIMIT = "interval '2160 hours'"
SESSION_EXPIRED = (
    f"last_used_at < app.now_utc() - {IDLE_LIMIT} or created_at < app.now_utc() - {ABSOLUTE_LIMIT}"
)

CREATE_TABLES: tuple[str, ...] = (
    """
    create table app.account (
        id uuid not null default pg_catalog.gen_random_uuid(),
        auth_provider text not null default 'google',
        auth_subject varchar(255) not null,
        email varchar(254) not null,
        email_sha256 bytea,
        email_verified_at timestamptz,
        display_name text not null,
        age_declared_at timestamptz,
        privacy_version varchar(20),
        privacy_ack_at timestamptz,
        last_active_on date,
        created_at timestamptz not null default app.now_utc(),
        constraint pk_account primary key (id),
        constraint uq_account_auth_provider_auth_subject unique (auth_provider, auth_subject),
        constraint ck_account_auth_provider check (auth_provider in ('google')),
        constraint ck_account_auth_subject check (auth_subject <> ''),
        constraint ck_account_email check (
            char_length(email) between 3 and 254
            and email ~ '^[^@[:space:][:cntrl:]]+@[^@[:space:][:cntrl:]]+$'
        ),
        constraint ck_account_email_sha256 check (octet_length(email_sha256) = 32),
        constraint ck_account_display_name
            check (char_length(display_name) between 1 and 60 and btrim(display_name) <> ''),
        constraint ck_account_privacy_pair
            check ((privacy_version is null) = (privacy_ack_at is null)),
        constraint ck_account_privacy_version check (privacy_version <> '')
    )
    """,
    # 05-data §4.2: RESTRICT, la cancellazione passa dalla procedura (§7.3, §9.2). La verifica
    # usa `ux_person_account_single_family` (predicato `account_id IS NOT NULL` implicato).
    "alter table app.person add constraint fk_person_account_id_account "
    "foreign key (account_id) references app.account (id) on delete restrict",
    """
    create table app.session (
        id uuid not null default pg_catalog.gen_random_uuid(),
        account_id uuid not null,
        token_hash bytea not null,
        csrf_token_hash bytea not null,
        created_at timestamptz not null default app.now_utc(),
        last_used_at timestamptz not null default app.now_utc(),
        auth_time timestamptz not null,
        device_label varchar(80),
        ip_prefix inet,
        constraint pk_session primary key (id),
        constraint uq_session_token_hash unique (token_hash),
        constraint fk_session_account_id_account foreign key (account_id)
            references app.account (id) on delete cascade,
        constraint ck_session_token_hash check (octet_length(token_hash) = 32),
        constraint ck_session_csrf_token_hash check (octet_length(csrf_token_hash) = 32),
        constraint ck_session_device_label
            check (char_length(device_label) between 1 and 80 and btrim(device_label) <> ''),
        constraint ck_session_ip_prefix check (
            ((pg_catalog.family(ip_prefix) = 4 and pg_catalog.masklen(ip_prefix) = 24)
             or (pg_catalog.family(ip_prefix) = 6 and pg_catalog.masklen(ip_prefix) = 48))
            and ip_prefix = pg_catalog.network(ip_prefix)::inet
        )
    )
    """,
    # Elenco e revoca delle proprie sessioni (SR-038), revoca al recupero (SR-066), cascata
    # dall'account, massimo 20 sessioni (SR-070).
    "create index ix_session_account_id on app.session (account_id)",
    """
    create table app.auth_flow (
        handle_hash bytea not null,
        purpose text not null,
        session_id uuid,
        return_to varchar(200),
        state_hash bytea not null,
        nonce_hash bytea not null,
        code_verifier varchar(128) not null,
        created_at timestamptz not null default app.now_utc(),
        expires_at timestamptz not null,
        consumed_at timestamptz,
        outcome_code text,
        outcome_params jsonb,
        constraint pk_auth_flow primary key (handle_hash),
        constraint fk_auth_flow_session_id_session foreign key (session_id)
            references app.session (id) on delete cascade,
        constraint ck_auth_flow_handle_hash check (octet_length(handle_hash) = 32),
        constraint ck_auth_flow_state_hash check (octet_length(state_hash) = 32),
        constraint ck_auth_flow_nonce_hash check (octet_length(nonce_hash) = 32),
        constraint ck_auth_flow_purpose check (purpose in ('login', 'reauth')),
        constraint ck_auth_flow_reauth_session
            check ((purpose = 'reauth') = (session_id is not null)),
        constraint ck_auth_flow_return_to check (
            return_to ~ '^/[A-Za-z0-9/_.?=&-]*$' and return_to !~ '^//'
        ),
        constraint ck_auth_flow_code_verifier check (
            char_length(code_verifier) between 43 and 128
            and code_verifier ~ '^[A-Za-z0-9._~-]+$'
        ),
        constraint ck_auth_flow_consumed_at check (consumed_at >= created_at),
        constraint ck_auth_flow_expires_at check (
            expires_at > created_at
            and expires_at <= case
                when consumed_at is null then created_at + interval '10 minutes'
                else consumed_at + interval '5 minutes'
            end
        ),
        constraint ck_auth_flow_outcome_code check (
            outcome_code in ('not_member', 'auth_cancelled', 'auth_failed',
                             'reauth_wrong_account')
        ),
        constraint ck_auth_flow_outcome_consumed
            check (outcome_code is null or consumed_at is not null),
        constraint ck_auth_flow_outcome_params check (
            outcome_params is null
            or (outcome_code is not null
                and pg_catalog.jsonb_typeof(outcome_params) = 'object'
                and pg_catalog.pg_column_size(outcome_params) <= 512)
        )
    )
    """,
)

SESSION_POLICIES: tuple[str, ...] = (
    "alter table app.session enable row level security",
    "alter table app.session force row level security",
    f"create policy p_session_self on app.session for all to {APP_ROLE} "
    "using (account_id = app.current_account_id()) "
    "with check (account_id = app.current_account_id())",
    # Pulizia del worker senza contesto (05-data §3.4, §6.1): solo lettura e cancellazione delle
    # righe scadute, mai UPDATE (una sessione scaduta non si riesuma). Solo senza contesto di
    # account: le policy permissive si sommano, e con il contesto di A le righe scadute di B
    # (account_id, device_label, ip_prefix) sarebbero visibili e cancellabili (SEC-SL03a-001).
    f"create policy p_session_expired_select on app.session for select to {APP_ROLE} "
    f"using (({SESSION_EXPIRED}) and app.current_account_id() is null)",
    f"create policy p_session_expired_delete on app.session for delete to {APP_ROLE} "
    f"using (({SESSION_EXPIRED}) and app.current_account_id() is null)",
    "create policy p_owner on app.session for all to menu_owner using (true) with check (true)",
    f"create policy p_backup on app.session for select to {BACKUP_ROLE} using (true)",
)

GRANTS: tuple[str, ...] = tuple(
    stmt
    for table in ("account", "session", "auth_flow")
    for stmt in (
        f"grant select, insert, update, delete on app.{table} to {APP_ROLE}",
        f"grant select on app.{table} to {BACKUP_ROLE}",
    )
)

FUNCTIONS: tuple[tuple[str, str], ...] = (
    (
        "app.session_resolve(bytea)",
        """
        create function app.session_resolve(p_token_hash bytea)
        returns table (
            session_id uuid,
            account_id uuid,
            created_at timestamptz,
            last_used_at timestamptz,
            auth_time timestamptz,
            csrf_token_hash bytea
        )
        language plpgsql stable security definer set search_path = app, pg_temp
        as $fn$
        begin
            -- Risolve il cookie prima di conoscere l'account (05-data §6.2): solo sessioni
            -- valide (30 giorni dall'ultimo uso, 90 dalla creazione, confini inclusi).
            return query
                select s.id, s.account_id, s.created_at, s.last_used_at, s.auth_time,
                       s.csrf_token_hash
                from app.session s
                where s.token_hash = p_token_hash
                  and s.last_used_at >= app.now_utc() - interval '720 hours'
                  and s.created_at >= app.now_utc() - interval '2160 hours';
        end
        $fn$
        """,
    ),
    (
        "app.bootstrap_resolve(bytea)",
        """
        create function app.bootstrap_resolve(p_email_sha256 bytea)
        returns table (bootstrap_id uuid, family_id uuid)
        language plpgsql stable security definer set search_path = app, pg_temp
        as $fn$
        begin
            -- Bootstrap non riscattato e non scaduto (scadenza inclusa, SR-033, AC-002.4).
            -- Solo ID: né il nome della famiglia né l'hash escono (05-data §6.2).
            return query
                select b.id, b.family_id
                from app.family_bootstrap b
                where b.email_sha256 = p_email_sha256
                  and b.redeemed_at is null
                  and b.expires_at >= app.now_utc()
                order by b.created_at, b.id;
        end
        $fn$
        """,
    ),
)


def upgrade() -> None:
    for ddl in CREATE_TABLES:
        op.execute(ddl)
    for stmt in SESSION_POLICIES:
        op.execute(stmt)
    for stmt in GRANTS:
        op.execute(stmt)
    for signature, ddl in FUNCTIONS:
        op.execute(ddl)
        op.execute(f"revoke all on function {signature} from public")
        op.execute(f"grant execute on function {signature} to {APP_ROLE}")


def downgrade() -> None:
    for signature, _ in reversed(FUNCTIONS):
        op.execute(f"drop function {signature}")
    # Policy, indici e grant spariscono con le tabelle.
    op.execute("drop table app.auth_flow")
    op.execute("drop table app.session")
    op.execute("alter table app.person drop constraint fk_person_account_id_account")
    op.execute("drop table app.account")
