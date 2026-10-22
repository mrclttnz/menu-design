"""Inventari del catalogo (08 §6.4-6.7, §10): funzioni pure su una connessione psycopg.

Ogni controllo restituisce l'elenco dei problemi (vuoto = ok). I test lo applicano al
database reale e, per provare che il controllo SA fallire, a oggetti sintetici costruiti
apposta (tabelle di prova con policy sbagliate, funzioni con `now()` nudo, ...).
Tabelle e funzioni attese sono elenchi chiusi trascritti da `docs/05-data.md`; chi aggiunge
una tabella o una funzione li aggiorna nella stessa slice.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import psycopg

from .owner import Owner

APP_ROLE, OWNER_ROLE, CONSOLE_ROLE, BACKUP_ROLE = (
    "menu_app",
    "menu_owner",
    "menu_console",
    "menu_backup",
)
LOGIN_ROLES = frozenset({OWNER_ROLE, APP_ROLE, CONSOLE_ROLE, BACKUP_ROLE})
# docs/05-data.md §3.1: rolconnlimit per ruolo.
CONNECTION_LIMITS = {OWNER_ROLE: 3, APP_ROLE: 20, CONSOLE_ROLE: 2, BACKUP_ROLE: 2}
# docs/05-data.md §3.1: impostazioni per ruolo (rolconfig).
ROLE_SETTINGS = {
    APP_ROLE: {
        "statement_timeout": "5s",
        "lock_timeout": "3s",
        "idle_in_transaction_session_timeout": "15s",
    },
    CONSOLE_ROLE: {"statement_timeout": "30s"},
    BACKUP_ROLE: {"statement_timeout": "0"},
}

# docs/05-data.md §6.3: tabelle senza RLS di famiglia (elenco chiuso).
NON_FAMILY_TABLES = frozenset(
    {
        "account",
        "password_credential",
        "account_token",
        "auth_flow",
        "signup_pending",
        "session",
        "creation_code",
        "security_event",
        "deletion_log",
        "export_file",
        "job",
        "periodic_task_run",
        "rate_counter",
        "rate_block",
        "alembic_version",
    }
)
# RLS per account (non di famiglia): ENABLE + FORCE + p_owner + p_backup.
ACCOUNT_RLS_TABLES = frozenset({"session", "export_file"})
# SL-02: tabelle di famiglia create da questa slice (05-data §4.2: `family` filtra su `id`,
# le altre su `family_id`); ogni slice successiva estende questi elenchi.
EXPECTED_FAMILY_TABLES_NOW = frozenset(
    {"family", "family_default_meal", "person", "family_bootstrap", "course"}
)
# Tabelle non di famiglia presenti alla fine di SL-02 (05-data §6.3).
EXPECTED_OTHER_TABLES_NOW = frozenset({"security_event", "alembic_version"})
EXPECTED_TABLES_NOW = EXPECTED_FAMILY_TABLES_NOW | EXPECTED_OTHER_TABLES_NOW
# docs/05-data.md §3.3: inventario SECURITY DEFINER atteso alla fine di SL-02 (tutte e solo
# `console_*`, eseguibili solo da `menu_console`, ADR-0011).
EXPECTED_SECDEF_NOW: frozenset[str] = frozenset(
    {"console_bootstrap_family", "console_security_events", "console_audit_note"}
)
# docs/05-data.md §11.1 / 08 §6.7: elenco chiuso delle funzioni LANGUAGE sql (intero, a regime).
INLINABLE_SQL_FUNCTIONS = frozenset(
    {
        "now_utc",
        "current_family_id",
        "current_account_id",
        "search_norm",
        "family_today",
        "effective_meals",
        "effective_attendance",
    }
)
# Funzioni LANGUAGE sql create fino a questa slice (0001 + `family_today` di SL-02).
SQL_FUNCTIONS_NOW = frozenset(
    {"now_utc", "current_family_id", "current_account_id", "search_norm", "family_today"}
)

_FORBIDDEN_TIME = re.compile(
    r"\bnow\s*\(|\bcurrent_timestamp\b|\bcurrent_date\b|\bcurrent_time\b|\blocaltimestamp\b"
    r"|\blocaltime\b|\btransaction_timestamp\s*\(|\bstatement_timestamp\s*\(|"
    r"\bclock_timestamp\s*\(|\btimeofday\s*\(|'(?:now|today|tomorrow|yesterday)'\s*::",
    re.IGNORECASE,
)


def forbidden_time_expressions(text: str) -> list[str]:
    return [m.group(0).strip() for m in _FORBIDDEN_TIME.finditer(text)]


def _rows(conn: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    return conn.execute(query.encode(), params or None).fetchall()


# --- ruoli ------------------------------------------------------------------------------------


def login_roles(conn: psycopg.Connection) -> set[str]:
    """Ruoli di login non superutente (il superutente del cluster non è un ruolo dell'app)."""
    return {
        r[0] for r in _rows(conn, "select rolname from pg_roles where rolcanlogin and not rolsuper")
    }


def role_rows(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    cols = (
        "select rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, "
        "rolinherit, rolconnlimit, rolconfig from pg_roles where rolname like 'menu\\_%'"
    )
    out = {}
    for name, sup, crole, cdb, repl, byp, inh, lim, cfg in _rows(conn, cols):
        settings = dict(c.split("=", 1) for c in (cfg or []))
        out[name] = {
            "super": sup,
            "createrole": crole,
            "createdb": cdb,
            "replication": repl,
            "bypassrls": byp,
            "inherit": inh,
            "connlimit": lim,
            "settings": settings,
        }
    return out


def schema_create_grantees(conn: psycopg.Connection, schema: str) -> set[str]:
    """Chi può fare CREATE nello schema: ruoli non superutente con il privilegio, e PUBLIC."""
    grantees = {
        r[0]
        for r in _rows(
            conn,
            "select rolname from pg_roles where not rolsuper "
            "and has_schema_privilege(rolname, %s, 'CREATE')",
            (schema,),
        )
    }
    public = _rows(
        conn,
        "select 1 from pg_namespace n, aclexplode(n.nspacl) a "
        "where n.nspname = %s and a.grantee = 0 and a.privilege_type = 'CREATE'",
        (schema,),
    )
    if public:
        grantees.add("PUBLIC")
    return grantees


# --- funzioni ---------------------------------------------------------------------------------


def app_functions(conn: psycopg.Connection) -> list[dict[str, Any]]:
    out = []
    for oid, name, lang, secdef, owner, config, acl, vol, strict in _rows(
        conn,
        "select p.oid, p.proname, l.lanname, p.prosecdef, pg_get_userbyid(p.proowner), "
        "p.proconfig, p.proacl, p.provolatile, p.proisstrict "
        "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "join pg_language l on l.oid = p.prolang "
        "where n.nspname = 'app' and p.prokind in ('f', 'p') "
        "and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')",
    ):
        out.append(
            {
                "oid": oid,
                "name": name,
                "language": lang,
                "secdef": secdef,
                "owner": owner,
                "config": config or [],
                "acl": [str(a) for a in (acl or [])],
                "volatility": vol,
                "strict": strict,
            }
        )
    return out


def public_can_execute(conn: psycopg.Connection, oid: int) -> bool:
    return bool(
        _rows(
            conn,
            "select 1 from pg_proc p, aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a"
            " where p.oid = %s and a.grantee = 0 and a.privilege_type = 'EXECUTE'",
            (oid,),
        )
    )


def secdef_problems(conn: psycopg.Connection, expected: frozenset[str]) -> list[str]:
    """Inventario chiuso delle SECURITY DEFINER (THR-044): insieme, owner, search_path, grant."""
    problems = []
    found = {f["name"]: f for f in app_functions(conn) if f["secdef"]}
    for name in sorted(set(found) - expected):
        problems.append(f"funzione SECURITY DEFINER non prevista: {name}")
    for name in sorted(expected - set(found)):
        problems.append(f"funzione SECURITY DEFINER attesa e assente: {name}")
    for name, f in found.items():
        if f["owner"] != OWNER_ROLE:
            problems.append(f"{name}: proprietario {f['owner']}, atteso {OWNER_ROLE}")
        if "search_path=app, pg_temp" not in f["config"]:
            problems.append(f"{name}: search_path non fissato a 'app, pg_temp' ({f['config']})")
        if public_can_execute(conn, f["oid"]):
            problems.append(f"{name}: EXECUTE concesso a PUBLIC")
    return problems


def sql_function_problems(conn: psycopg.Connection, expected_present: frozenset[str]) -> list[str]:
    """08 §6.7: ogni funzione LANGUAGE sql è nell'elenco chiuso; quelle attese esistono."""
    problems = []
    sql_funcs = {f["name"] for f in app_functions(conn) if f["language"] == "sql"}
    for name in sorted(sql_funcs - INLINABLE_SQL_FUNCTIONS):
        problems.append(f"funzione LANGUAGE sql fuori dall'elenco INLINABLE_SQL_FUNCTIONS: {name}")
    for name in sorted(expected_present - sql_funcs):
        problems.append(f"funzione LANGUAGE sql attesa e assente: {name}")
    for name in sorted(sql_funcs - expected_present):
        problems.append(f"funzione LANGUAGE sql non ancora prevista in questa slice: {name}")
    return problems


# --- RLS --------------------------------------------------------------------------------------


def app_tables(conn: psycopg.Connection) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}
    for oid, name, rls, force in _rows(
        conn,
        "select c.oid, c.relname, c.relrowsecurity, c.relforcerowsecurity from pg_class c "
        "join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'app' and c.relkind in ('r', 'p')",
    ):
        cols = {
            r[0]
            for r in _rows(
                conn,
                "select attname from pg_attribute where attrelid = %s "
                "and attnum > 0 and not attisdropped",
                (oid,),
            )
        }
        pols = {}
        for pname, cmd, roles, qual, check in _rows(
            conn,
            "select polname, polcmd, array(select rolname from pg_roles r "
            "where r.oid = any(polroles)), pg_get_expr(polqual, polrelid), "
            "pg_get_expr(polwithcheck, polrelid) "
            "from pg_policy where polrelid = %s",
            (oid,),
        ):
            pols[pname] = {"cmd": cmd, "roles": set(roles), "using": qual, "check": check}
        tables[name] = {"oid": oid, "rls": rls, "force": force, "columns": cols, "policies": pols}
    return tables


def is_family_table(name: str, info: dict[str, Any]) -> bool:
    return name not in NON_FAMILY_TABLES and ("family_id" in info["columns"] or name == "family")


def family_tables(conn: psycopg.Connection) -> list[str]:
    return sorted(n for n, i in app_tables(conn).items() if is_family_table(n, i))


def _standard_policy_problems(name: str, info: dict[str, Any], *, family: bool) -> list[str]:
    problems = []
    pols = info["policies"]
    if not (info["rls"] and info["force"]):
        problems.append(f"{name}: RLS non abilitata e forzata")
    if "p_owner" not in pols:
        problems.append(f"{name}: policy p_owner assente")
    elif pols["p_owner"]["using"] != "true" or pols["p_owner"]["roles"] != {OWNER_ROLE}:
        problems.append(f"{name}: p_owner deve essere USING (true) per {OWNER_ROLE}")
    if "p_backup" not in pols:
        problems.append(f"{name}: policy p_backup assente")
    elif (
        pols["p_backup"]["cmd"] != "r"
        or pols["p_backup"]["using"] != "true"
        or pols["p_backup"]["roles"] != {BACKUP_ROLE}
    ):
        problems.append(f"{name}: p_backup deve essere FOR SELECT USING (true) per {BACKUP_ROLE}")
    if family:
        full = "p_family" in pols
        split = "p_family_select" in pols and "p_family_insert" in pols
        if not (full or split):
            problems.append(f"{name}: policy p_family (o p_family_select/insert) assente")
        for pname in ("p_family", "p_family_insert"):
            pol = pols.get(pname)
            if pol is not None and pol["check"] is None:
                problems.append(f"{name}: {pname} senza WITH CHECK")
        for pname, pol in pols.items():
            if pname.startswith("p_family") and pol["using"] in (None, "true"):
                problems.append(f"{name}: {pname} non filtra per famiglia ({pol['using']})")
            if pname.startswith("p_family") and pol["roles"] != {APP_ROLE}:
                problems.append(f"{name}: {pname} deve valere solo per {APP_ROLE}")
    return problems


def rls_problems(conn: psycopg.Connection) -> list[str]:
    """08 §6.4 / 05-data §6.3: ogni tabella è classificata e, se di famiglia, protetta."""
    problems = []
    for name, info in sorted(app_tables(conn).items()):
        if is_family_table(name, info):
            problems += _standard_policy_problems(name, info, family=True)
        elif name in ACCOUNT_RLS_TABLES:
            problems += _standard_policy_problems(name, info, family=False)
        elif name not in NON_FAMILY_TABLES:
            problems.append(f"{name}: tabella non classificata (né di famiglia né in §6.3)")
    return problems


# --- tempo ------------------------------------------------------------------------------------


def bare_time_problems(conn: psycopg.Connection) -> list[str]:
    """08 §10 punto 8 / 05-data §11.1: nessun `now()` nudo; eccezione: il corpo di now_utc()."""
    found: list[tuple[str, str]] = []
    for name, definition in _rows(
        conn,
        "select p.proname, pg_get_functiondef(p.oid) from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace "
        "where n.nspname = 'app' and p.prokind in ('f', 'p') "
        "and not (p.proname = 'now_utc' and p.pronargs = 0)",
    ):
        found.append((f"funzione {name}", definition))
    for rel, col, expr in _rows(
        conn,
        "select c.relname, a.attname, pg_get_expr(d.adbin, d.adrelid) from pg_attrdef d "
        "join pg_class c on c.oid = d.adrelid join pg_namespace n on n.oid = c.relnamespace "
        "join pg_attribute a on a.attrelid = d.adrelid and a.attnum = d.adnum "
        "where n.nspname = 'app'",
    ):
        found.append((f"default {rel}.{col}", expr))
    for rel, pol, qual, check in _rows(
        conn,
        "select c.relname, p.polname, coalesce(pg_get_expr(p.polqual, p.polrelid), ''), "
        "coalesce(pg_get_expr(p.polwithcheck, p.polrelid), '') from pg_policy p "
        "join pg_class c on c.oid = p.polrelid join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'app'",
    ):
        found.append((f"policy {rel}.{pol}", qual + " " + check))
    for view, definition in _rows(
        conn,
        "select viewname, definition from pg_views where schemaname = 'app' "
        "union all select matviewname, definition from pg_matviews where schemaname = 'app'",
    ):
        found.append((f"vista {view}", definition))
    for rel, con, definition in _rows(
        conn,
        "select c.relname, k.conname, pg_get_constraintdef(k.oid) from pg_constraint k "
        "join pg_class c on c.oid = k.conrelid join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'app' and k.contype in ('c', 'x')",
    ):
        found.append((f"vincolo {rel}.{con}", definition))
    for rel, trg, definition in _rows(
        conn,
        "select c.relname, t.tgname, pg_get_triggerdef(t.oid) from pg_trigger t "
        "join pg_class c on c.oid = t.tgrelid join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'app' and not t.tgisinternal",
    ):
        found.append((f"trigger {rel}.{trg}", definition))
    return [
        f"{where}: {', '.join(bad)}"
        for where, text in found
        if (bad := forbidden_time_expressions(text))
    ]


# --- istantanea dello schema (ciclo upgrade/downgrade, bootstrap idempotente) ----------------


def schema_snapshot(conn: psycopg.Connection) -> list[str]:
    q: list[tuple[str, str]] = [
        (
            "role",
            "select concat_ws('|', rolname, rolcanlogin, rolsuper, rolbypassrls, rolconnlimit,"
            " rolconfig) from pg_roles where rolname like 'menu\\_%'",
        ),
        (
            "schema",
            "select concat_ws('|', nspname, pg_get_userbyid(nspowner), nspacl) "
            "from pg_namespace where nspname in ('app', 'public', 'extensions')",
        ),
        (
            "ext",
            "select concat_ws('|', e.extname, n.nspname) from pg_extension e "
            "join pg_namespace n on n.oid = e.extnamespace where e.extname in "
            "('unaccent', 'pg_trgm')",
        ),
        (
            "func",
            "select concat_ws('|', pg_get_functiondef(p.oid), p.proacl, "
            "pg_get_userbyid(p.proowner)) from pg_proc p join pg_namespace n "
            "on n.oid = p.pronamespace where n.nspname = 'app'",
        ),
        (
            "rel",
            "select concat_ws('|', c.relname, c.relkind, c.relrowsecurity, "
            "c.relforcerowsecurity, pg_get_userbyid(c.relowner), c.relacl) from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'app' "
            "and c.relkind in ('r', 'p', 'v', 'm', 'S')",
        ),
        (
            "col",
            "select concat_ws('|', c.relname, a.attname, format_type(a.atttypid, "
            "a.atttypmod), a.attnotnull, pg_get_expr(d.adbin, d.adrelid)) "
            "from pg_attribute a join pg_class c on c.oid = a.attrelid join pg_namespace n "
            "on n.oid = c.relnamespace left join pg_attrdef d on d.adrelid = a.attrelid "
            "and d.adnum = a.attnum where n.nspname = 'app' and a.attnum > 0 "
            "and not a.attisdropped and c.relkind in ('r', 'p')",
        ),
        (
            "pol",
            "select concat_ws('|', c.relname, p.polname, p.polcmd, "
            "pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid)) "
            "from pg_policy p join pg_class c on c.oid = p.polrelid",
        ),
        (
            "con",
            "select concat_ws('|', c.relname, k.conname, pg_get_constraintdef(k.oid)) "
            "from pg_constraint k join pg_class c on c.oid = k.conrelid join pg_namespace n "
            "on n.oid = c.relnamespace where n.nspname = 'app'",
        ),
        ("idx", "select indexdef from pg_indexes where schemaname = 'app'"),
        (
            "trg",
            "select pg_get_triggerdef(t.oid) from pg_trigger t join pg_class c on "
            "c.oid = t.tgrelid join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'app' and not t.tgisinternal",
        ),
        (
            "dacl",
            "select concat_ws('|', pg_get_userbyid(defaclrole), defaclobjtype, defaclacl) "
            "from pg_default_acl",
        ),
    ]
    out = []
    for tag, query in q:
        out += sorted(f"{tag}|{r[0]}" for r in _rows(conn, query))
    return out


# --- RLS generico per tabelle di famiglia ----------------------------------------------------


@dataclass(frozen=True)
class FamilyTableSpec:
    """Come popolare e scrivere una tabella di famiglia nel test RLS generico."""

    seed: Callable[[Owner, UUID], None]  # una riga per la famiglia indicata, via owner
    insert_sql: Callable[[UUID], tuple[str, tuple[Any, ...]]]  # INSERT eseguito da menu_app
    key_column: str = "family_id"  # colonna su cui filtra la RLS (`id` per la tabella `family`)


def family_isolation_problems(
    table: str, spec: FamilyTableSpec, owner: Owner, fam_a: UUID, fam_b: UUID, connect_app: Any
) -> list[str]:
    """08 §6.4: senza contesto zero righe; A non vede B; INSERT/UPDATE altrui rifiutati."""
    problems: list[str] = []
    key = spec.key_column
    spec.seed(owner, fam_a)
    spec.seed(owner, fam_b)

    def in_ctx(conn: psycopg.Connection, family: UUID | None) -> None:
        if family is not None:
            conn.execute("select set_config('app.family_id', %s, true)", (str(family),))

    # Il nome della tabella viene dal catalogo (identificatore), mai da input utente.
    with connect_app() as conn:
        conn.autocommit = False
        n = conn.execute(f"select count(*) from app.{table}".encode()).fetchone()  # noqa: S608  (identificatore generato dal test o dal catalogo)
        if n is None or n[0] != 0:
            problems.append(f"{table}: senza contesto legge {n and n[0]} righe (attese 0)")
        conn.rollback()
        in_ctx(conn, fam_a)
        other = conn.execute(
            f"select count(*) from app.{table} where {key} = %s".encode(),  # noqa: S608  (identificatore generato dal test o dal catalogo)
            (fam_b,),
        ).fetchone()
        mine = conn.execute(
            f"select count(*) from app.{table} where {key} = %s".encode(),  # noqa: S608  (identificatore generato dal test o dal catalogo)
            (fam_a,),
        ).fetchone()
        if other is None or other[0] != 0:
            problems.append(f"{table}: con il contesto A legge righe di B")
        if mine is None or mine[0] < 1:
            problems.append(f"{table}: con il contesto A non vede le proprie righe")
        upd = conn.execute(
            f"update app.{table} set {key} = {key} where {key} = %s".encode(),  # noqa: S608  (identificatore generato dal test o dal catalogo)
            (fam_b,),
        )
        if upd.rowcount != 0:
            problems.append(f"{table}: UPDATE di righe di B dal contesto A ha toccato righe")
        dele = conn.execute(
            f"delete from app.{table} where {key} = %s".encode(),  # noqa: S608  (identificatore generato dal test o dal catalogo)
            (fam_b,),
        )
        if dele.rowcount != 0:
            problems.append(f"{table}: DELETE di righe di B dal contesto A ha toccato righe")
        conn.rollback()

        in_ctx(conn, fam_a)
        query, params = spec.insert_sql(fam_b)
        try:
            conn.execute(query.encode(), params)
            problems.append(f"{table}: INSERT con family_id di B accettato dal contesto A")
        except psycopg.errors.InsufficientPrivilege:
            pass
        finally:
            conn.rollback()

        in_ctx(conn, fam_a)
        try:
            conn.execute(
                f"update app.{table} set {key} = %s where {key} = %s".encode(),  # noqa: S608  (identificatore generato dal test o dal catalogo)
                (fam_b, fam_a),
            )
            problems.append(f"{table}: UPDATE che sposta una riga in B accettato")
        except psycopg.errors.InsufficientPrivilege:
            pass
        finally:
            conn.rollback()
    return problems
