"""Ruoli di login (05-data §3.1, ADR-0003; SR-075 base, THR-040/044; SR-012/SR-040)."""

from typing import Any

import psycopg
import pytest

from support.inventory import (
    APP_ROLE,
    BACKUP_ROLE,
    CONNECTION_LIMITS,
    CONSOLE_ROLE,
    LOGIN_ROLES,
    OWNER_ROLE,
    ROLE_SETTINGS,
    login_roles,
    role_rows,
)


def test_exactly_four_login_roles(catalog: psycopg.Connection) -> None:
    assert login_roles(catalog) == set(LOGIN_ROLES)


def test_no_role_bypasses_rls_or_is_privileged(catalog: psycopg.Connection) -> None:
    rows = role_rows(catalog)
    assert set(rows) == set(LOGIN_ROLES)
    for name, attrs in rows.items():
        assert attrs["bypassrls"] is False, f"{name} ha BYPASSRLS"
        assert attrs["super"] is False, f"{name} è superutente"
        assert attrs["createdb"] is False, f"{name} ha CREATEDB"
        assert attrs["replication"] is False, f"{name} ha REPLICATION"
        assert attrs["createrole"] is False, f"{name} ha CREATEROLE"


@pytest.mark.parametrize(("role", "limit"), sorted(CONNECTION_LIMITS.items()))
def test_rolconnlimit_matches_05_data_3_1(
    catalog: psycopg.Connection, role: str, limit: int
) -> None:
    assert role_rows(catalog)[role]["connlimit"] == limit


@pytest.mark.parametrize(("role", "settings"), sorted(ROLE_SETTINGS.items()))
def test_role_settings_match_05_data_3_1(
    catalog: psycopg.Connection, role: str, settings: dict[str, str]
) -> None:
    actual = role_rows(catalog)[role]["settings"]
    assert {k: actual.get(k) for k in settings} == settings


def test_app_role_effective_timeouts_over_tls(connect_app: Any) -> None:
    """`menu_app` si connette in TLS e ottiene i timeout del ruolo (il pooler li rispetta)."""
    with connect_app(APP_ROLE) as conn:
        assert conn.execute("select current_user").fetchone() == (APP_ROLE,)
        assert conn.execute("show statement_timeout").fetchone() == ("5s",)
        assert conn.execute("show lock_timeout").fetchone() == ("3s",)
        assert conn.execute("show idle_in_transaction_session_timeout").fetchone() == ("15s",)
        assert conn.execute(
            "select ssl from pg_stat_ssl where pid = pg_backend_pid()"
        ).fetchone() == (True,)


@pytest.mark.parametrize("role", [APP_ROLE, CONSOLE_ROLE, BACKUP_ROLE])
def test_non_owner_roles_cannot_become_the_owner(connect_app: Any, role: str) -> None:
    """THR-044: nessuno può assumere `menu_owner` (né SET ROLE né SET SESSION AUTHORIZATION)."""
    with connect_app(role) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(b"set role menu_owner")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(b"set session authorization menu_owner")


def test_app_role_is_not_a_member_of_other_menu_roles(catalog: psycopg.Connection) -> None:
    assert set(role_rows(catalog)) == set(LOGIN_ROLES), "precondizione: i quattro ruoli esistono"
    members = catalog.execute(
        "select pg_get_userbyid(roleid), pg_get_userbyid(member) from pg_auth_members "
        "where pg_get_userbyid(member) like 'menu\\_%' or pg_get_userbyid(roleid) like 'menu\\_%'"
    ).fetchall()
    assert members == []


def test_owner_role_is_the_owner_of_schema_app(catalog: psycopg.Connection) -> None:
    row = catalog.execute(
        "select pg_get_userbyid(nspowner) from pg_namespace where nspname = 'app'"
    ).fetchone()
    assert row == (OWNER_ROLE,)
