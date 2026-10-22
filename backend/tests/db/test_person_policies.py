"""Invariante dell'Amministratore e policy `p_person_self` (CR-SL02-003).

- `tg_person_admin_invariant`: constraint trigger DEFERRABLE INITIALLY DEFERRED, difesa del
  database per FR-011/SR-011 (05-data §4.2: "verificato in SL-02").
- `p_person_self`: l'unica policy che concede righe a prescindere da `app.current_family_id()`;
  insieme all'indice ASM-050 tiene una sessione con contesto di account fuori dalle persone delle
  altre famiglie (SR-042).
"""

from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from support.owner import Owner

Connect = Callable[..., psycopg.Connection]

CONSTRAINT = "tg_person_admin_invariant"


def _family(owner: Owner) -> UUID:
    family = uuid4()
    owner.execute(
        "insert into app.family (id, name, frozen_through) values (%s, 'Famiglia Persone', "
        "'2026-01-01')",
        (family,),
    )
    return family


def _person(owner: Owner, family: UUID, **cols: Any) -> UUID:
    person = uuid4()
    values: dict[str, Any] = {
        "id": person,
        "family_id": family,
        "kind": "account",
        "status": "active",
        "account_id": uuid4(),
        "role": "admin",
        "joined_on": "2026-01-01",
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.person ({names}) values ({marks})", tuple(values.values()))  # noqa: S608
    return person


def _profile(owner: Owner, family: UUID, declared_by: UUID) -> UUID:
    return _person(
        owner,
        family,
        kind="profile",
        account_id=None,
        role=None,
        display_name="Profilo",
        guardian_declared_at="2026-01-01T00:00:00Z",
        guardian_declared_by=declared_by,
    )


def _roles(owner: Owner, family: UUID) -> dict[UUID, str | None]:
    rows = owner.rows("select id, role from app.person where family_id = %s", (family,))
    return {r[0]: r[1] for r in rows}


def _in_family_tx(conn: psycopg.Connection, family: UUID) -> None:
    conn.execute("select set_config('app.family_id', %s, true)", (str(family),))


TOMBSTONE = "status = 'former', former_reason = 'left', account_id = null, role = null"


# --- tg_person_admin_invariant ------------------------------------------------------------------


def test_admin_handover_in_one_transaction_commits(owner: Owner, connect_app: Connect) -> None:
    """Passaggio di consegne: promuovere il secondo e degradare il primo nella stessa
    transazione va a buon fine (il controllo è al commit)."""
    family = _family(owner)
    first = _person(owner, family, role="admin")
    second = _person(owner, family, role="member")
    with connect_app(autocommit=False) as conn:
        _in_family_tx(conn, family)
        conn.execute("update app.person set role = 'admin' where id = %s", (second,))
        conn.execute("update app.person set role = 'member' where id = %s", (first,))
        conn.commit()
    assert _roles(owner, family) == {first: "member", second: "admin"}


def test_demoting_the_only_admin_fails_at_commit(owner: Owner, connect_app: Connect) -> None:
    family = _family(owner)
    admin = _person(owner, family, role="admin")
    _person(owner, family, role="member")
    with connect_app(autocommit=False) as conn:
        _in_family_tx(conn, family)
        conn.execute("update app.person set role = 'member' where id = %s", (admin,))
        with pytest.raises(psycopg.errors.CheckViolation) as raised:
            conn.commit()
    assert raised.value.diag.constraint_name == CONSTRAINT
    assert _roles(owner, family)[admin] == "admin", "la transazione è stata annullata"


def test_the_check_is_deferred_not_per_statement(owner: Owner, connect_app: Connect) -> None:
    """Lo stato intermedio senza amministratori è ammesso finché il commit non lo vede."""
    family = _family(owner)
    admin = _person(owner, family, role="admin")
    other = _person(owner, family, role="member")
    with connect_app(autocommit=False) as conn:
        _in_family_tx(conn, family)
        conn.execute("update app.person set role = 'member' where id = %s", (admin,))
        conn.execute("update app.person set role = 'admin' where id = %s", (other,))
        conn.commit()
    assert _roles(owner, family) == {admin: "member", other: "admin"}


def test_making_the_only_admin_a_tombstone_fails_at_commit(
    owner: Owner, connect_app: Connect
) -> None:
    """Uscita dell'ultimo amministratore (status → former) mentre resta un membro."""
    family = _family(owner)
    admin = _person(owner, family, role="admin")
    _person(owner, family, role="member")
    with connect_app(autocommit=False) as conn:
        _in_family_tx(conn, family)
        conn.execute(f"update app.person set {TOMBSTONE} where id = %s", (admin,))  # noqa: S608
        with pytest.raises(psycopg.errors.CheckViolation) as raised:
            conn.commit()
    assert raised.value.diag.constraint_name == CONSTRAINT


def test_deleting_the_only_admin_while_a_member_stays_fails_at_commit(
    owner: Owner, connect_app: Connect
) -> None:
    family = _family(owner)
    admin = _person(owner, family, role="admin")
    member = _person(owner, family, role="member")
    with connect_app(autocommit=False) as conn:
        _in_family_tx(conn, family)
        conn.execute("delete from app.person where id = %s", (admin,))
        with pytest.raises(psycopg.errors.CheckViolation) as raised:
            conn.commit()
    assert raised.value.diag.constraint_name == CONSTRAINT
    assert set(_roles(owner, family)) == {admin, member}


def test_the_trigger_also_binds_the_table_owner(owner: Owner) -> None:
    """Non è una regola della sola applicazione: vale anche per `menu_owner`."""
    family = _family(owner)
    admin = _person(owner, family, role="admin")
    _person(owner, family, role="member")
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute("update app.person set role = 'member' where id = %s", (admin,))


def test_a_family_with_only_tombstones_has_no_admin_requirement(owner: Owner) -> None:
    family = _family(owner)
    tomb = _person(owner, family, status="former", former_reason="left", account_id=None, role=None)
    owner.execute("update app.person set former_reason = 'removed' where id = %s", (tomb,))
    owner.execute("delete from app.person where id = %s", (tomb,))
    assert _roles(owner, family) == {}


def test_a_family_with_only_profiles_has_no_admin_requirement(owner: Owner) -> None:
    """Nessuna persona collegata a un account: nessun requisito (famiglia appena creata)."""
    family = _family(owner)
    declarer = _person(
        owner, family, status="former", former_reason="left", account_id=None, role=None
    )
    profile = _profile(owner, family, declarer)
    owner.execute("update app.person set display_name = 'Altro' where id = %s", (profile,))
    owner.execute("delete from app.person where id = %s", (profile,))
    assert _roles(owner, family) == {declarer: None}


def test_the_last_account_person_leaving_is_not_a_violation(owner: Owner) -> None:
    """Se non resta nessuna persona collegata a un account, l'invariante non si applica."""
    family = _family(owner)
    admin = _person(owner, family, role="admin")
    owner.execute(f"update app.person set {TOMBSTONE} where id = %s", (admin,))  # noqa: S608
    assert _roles(owner, family) == {admin: None}


def test_the_invariant_is_per_family(owner: Owner) -> None:
    """Un'altra famiglia con il suo amministratore non soddisfa l'invariante."""
    alfa, beta = _family(owner), _family(owner)
    admin_a = _person(owner, alfa, role="admin")
    _person(owner, alfa, role="member")
    _person(owner, beta, role="admin")
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute("update app.person set role = 'member' where id = %s", (admin_a,))


def test_deleting_the_family_cascades_without_violating_the_invariant(
    owner: Owner, connect_app: Connect
) -> None:
    family = _family(owner)
    _person(owner, family, role="admin")
    _person(owner, family, role="member")
    other = _family(owner)
    _person(owner, other, role="admin")
    with connect_app(autocommit=False) as conn:
        _in_family_tx(conn, family)
        assert conn.execute("delete from app.family where id = %s", (family,)).rowcount == 1
        conn.commit()
    assert owner.scalar("select count(*) from app.person where family_id = %s", (family,)) == 0
    assert owner.scalar("select count(*) from app.person where family_id = %s", (other,)) == 1


# --- p_person_self ------------------------------------------------------------------------------


def _world(owner: Owner) -> dict[str, Any]:
    """Famiglia A (admin, member, profilo) e famiglia B (admin, member)."""
    fam_a, fam_b = _family(owner), _family(owner)
    acc_a1, acc_a2, acc_b1, acc_b2 = uuid4(), uuid4(), uuid4(), uuid4()
    a1 = _person(owner, fam_a, account_id=acc_a1, role="admin")
    return {
        "fam_a": fam_a,
        "fam_b": fam_b,
        "acc_a1": acc_a1,
        "acc_b1": acc_b1,
        "a1": a1,
        "a2": _person(owner, fam_a, account_id=acc_a2, role="member"),
        "a_profile": _profile(owner, fam_a, a1),
        "b1": _person(owner, fam_b, account_id=acc_b1, role="admin"),
        "b2": _person(owner, fam_b, account_id=acc_b2, role="member"),
    }


def _visible(
    connect_app: Connect, *, family: UUID | None = None, account: UUID | None = None
) -> set[UUID]:
    with connect_app(autocommit=False) as conn:
        if family is not None:
            conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        if account is not None:
            conn.execute("select set_config('app.account_id', %s, true)", (str(account),))
        rows = conn.execute("select id from app.person").fetchall()
    return {r[0] for r in rows}


def test_account_context_alone_sees_exactly_its_own_person(
    owner: Owner, connect_app: Connect
) -> None:
    """SR-042: con il solo `app.account_id` la sessione risolve la propria membership."""
    w = _world(owner)
    assert _visible(connect_app, account=w["acc_a1"]) == {w["a1"]}
    assert _visible(connect_app, account=w["acc_b1"]) == {w["b1"]}


def test_without_any_context_no_person_is_visible(owner: Owner, connect_app: Connect) -> None:
    _world(owner)
    assert _visible(connect_app) == set()


def test_an_unknown_account_sees_no_person(owner: Owner, connect_app: Connect) -> None:
    _world(owner)
    assert _visible(connect_app, account=uuid4()) == set()


def test_family_context_with_a_foreign_account_adds_only_that_one_row(
    owner: Owner, connect_app: Connect
) -> None:
    """Famiglia A + account di B: tutte le persone di A più la sola riga dell'account, mai le
    altre persone di B."""
    w = _world(owner)
    seen = _visible(connect_app, family=w["fam_a"], account=w["acc_b1"])
    assert seen == {w["a1"], w["a2"], w["a_profile"], w["b1"]}
    assert w["b2"] not in seen


def test_family_context_with_its_own_account_adds_nothing(
    owner: Owner, connect_app: Connect
) -> None:
    w = _world(owner)
    seen = _visible(connect_app, family=w["fam_a"], account=w["acc_a1"])
    assert seen == {w["a1"], w["a2"], w["a_profile"]}


def test_the_self_policy_is_read_only(owner: Owner, connect_app: Connect) -> None:
    """`p_person_self` è solo SELECT: con il solo contesto di account non si modifica né si
    cancella nulla, nemmeno la propria riga."""
    w = _world(owner)
    with connect_app(autocommit=False) as conn:
        conn.execute("select set_config('app.account_id', %s, true)", (str(w["acc_a1"]),))
        updated = conn.execute("update app.person set role = 'member' where id = %s", (w["a1"],))
        deleted = conn.execute("delete from app.person where id = %s", (w["a1"],))
        assert (updated.rowcount, deleted.rowcount) == (0, 0)
        conn.commit()
    assert _roles(owner, w["fam_a"])[w["a1"]] == "admin"


def test_the_self_policy_does_not_allow_inserting_into_another_family(
    owner: Owner, connect_app: Connect
) -> None:
    w = _world(owner)
    with connect_app(autocommit=False) as conn:
        conn.execute("select set_config('app.account_id', %s, true)", (str(w["acc_a1"]),))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute(
                "insert into app.person (family_id, kind, status, account_id, role, joined_on) "
                "values (%s, 'account', 'active', %s, 'member', '2026-01-01')",
                (w["fam_b"], uuid4()),
            )
