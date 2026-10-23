"""Schema delle tabelle di famiglia di SL-02 (05-data §4.2, §4 "Regola ON DELETE"): vincoli,
FK composite (SR-041) e `ON DELETE NO ACTION` con cascata dalla famiglia (punto aperto di §4:
"da verificare con un test nella prima slice"). Prima esecuzione reale del DDL.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest

from support.accounts import make_account
from support.owner import Owner

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
Connect = Callable[..., psycopg.Connection]


def _family(owner: Owner, **cols: Any) -> UUID:
    family = uuid4()
    values: dict[str, Any] = {
        "id": family,
        "name": "Famiglia Schema",
        "frozen_through": "2026-01-01",
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.family ({names}) values ({marks})", tuple(values.values()))  # noqa: S608
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
    if values["account_id"] is not None:
        make_account(owner, account_id=values["account_id"])  # SL-03a: FK person.account_id
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.person ({names}) values ({marks})", tuple(values.values()))  # noqa: S608
    return person


def _bootstrap(owner: Owner, family: UUID, **cols: Any) -> None:
    values: dict[str, Any] = {
        "family_id": family,
        "email_sha256": bytes(32),
        "created_at": T0,
        "expires_at": T0 + timedelta(days=7),
    }
    values.update(cols)
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(
        f"insert into app.family_bootstrap ({names}) values ({marks})",  # noqa: S608
        tuple(values.values()),
    )


# --- family ---------------------------------------------------------------------------------------


def test_family_defaults(owner: Owner) -> None:
    family = _family(owner)
    row = owner.rows("select timezone, status from app.family where id = %s", (family,))[0]
    assert row == ("Europe/Rome", "active")


@pytest.mark.parametrize("name", ["", "   ", "N" * 61])
def test_family_name_must_be_1_to_60_characters(owner: Owner, name: str) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _family(owner, name=name)


@pytest.mark.parametrize("timezone", ["Mars/Olympus", "", "europe rome", "UTC+2; drop table x"])
def test_family_timezone_must_exist_in_the_timezone_catalog(owner: Owner, timezone: str) -> None:
    """ADR-0009: trigger `tg_family_timezone_valid`."""
    with pytest.raises(psycopg.DatabaseError):
        _family(owner, timezone=timezone)
    assert owner.scalar("select count(*) from app.family") == 0


def test_family_accepts_a_valid_non_default_timezone(owner: Owner) -> None:
    family = _family(owner, timezone="America/New_York")
    assert owner.scalar("select timezone from app.family where id = %s", (family,)) == (
        "America/New_York"
    )


def test_family_timezone_cannot_be_updated_to_an_invalid_one(owner: Owner) -> None:
    family = _family(owner)
    with pytest.raises(psycopg.DatabaseError):
        owner.execute("update app.family set timezone = 'Nowhere/Land' where id = %s", (family,))
    assert owner.scalar("select timezone from app.family where id = %s", (family,)) == "Europe/Rome"


def test_family_status_is_active_or_pending_deletion(owner: Owner) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _family(owner, status="archived")


def test_family_deletion_columns_are_coherent_with_status(owner: Owner) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        _family(owner, status="pending_deletion")  # date e richiedente mancanti
    family = _family(owner)
    with pytest.raises(psycopg.errors.CheckViolation):
        owner.execute(
            "update app.family set deletion_requested_at = %s where id = %s", (T0, family)
        )


# --- family_bootstrap ---------------------------------------------------------------------------


def test_bootstrap_hash_must_be_32_bytes(owner: Owner) -> None:
    family = _family(owner)
    for size in (0, 31, 33):
        with pytest.raises(psycopg.errors.CheckViolation):
            _bootstrap(owner, family, email_sha256=bytes(size))


def test_bootstrap_expiry_is_exactly_seven_days_after_creation(owner: Owner) -> None:
    """SR-033."""
    family = _family(owner)
    with pytest.raises(psycopg.errors.CheckViolation):
        _bootstrap(owner, family, expires_at=T0 + timedelta(days=8))
    with pytest.raises(psycopg.errors.CheckViolation):
        _bootstrap(owner, family, expires_at=T0 + timedelta(days=6))
    _bootstrap(owner, family)


def test_bootstrap_hash_must_be_cleared_when_redeemed(owner: Owner) -> None:
    """Minimizzazione (05-data §4.2): dopo il riscatto l'hash dell'email non resta."""
    family = _family(owner)
    person = _person(owner, family)
    with pytest.raises(psycopg.errors.CheckViolation):
        _bootstrap(owner, family, redeemed_at=T0, redeemed_person_id=person)
    _bootstrap(owner, family, email_sha256=None, redeemed_at=T0, redeemed_person_id=person)


def test_one_bootstrap_per_family(owner: Owner) -> None:
    family = _family(owner)
    _bootstrap(owner, family)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _bootstrap(owner, family)


def test_bootstrap_cannot_reference_a_person_of_another_family(owner: Owner) -> None:
    """SR-041: FK composita (family_id, redeemed_person_id) → person(family_id, id)."""
    alfa, beta = _family(owner), _family(owner)
    stranger = _person(owner, beta)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        _bootstrap(owner, alfa, email_sha256=None, redeemed_at=T0, redeemed_person_id=stranger)


# --- person ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cols",
    [
        pytest.param({"account_id": None}, id="account-senza-account_id"),
        pytest.param({"role": None}, id="account-senza-ruolo"),
        pytest.param({"display_name": "Mario"}, id="account-con-nome-proprio"),
        pytest.param({"role": "gestore"}, id="ruolo-sconosciuto"),
        pytest.param({"kind": "robot"}, id="tipo-sconosciuto"),
        pytest.param({"status": "ghost"}, id="stato-sconosciuto"),
        pytest.param(
            {"kind": "profile", "account_id": None, "role": None, "display_name": "Bimbo"},
            id="profilo-senza-dichiarazione",
        ),
        pytest.param({"status": "former", "former_reason": None}, id="tombstone-senza-motivo"),
        pytest.param(
            {"status": "former", "former_reason": "left"}, id="tombstone-con-legame-e-ruolo"
        ),
    ],
)
def test_person_state_constraints(owner: Owner, cols: dict[str, Any]) -> None:
    """05-data §4.2: ck_person_active_account, ck_person_active_profile, ck_person_former."""
    family = _family(owner)
    with pytest.raises(psycopg.errors.CheckViolation):
        _person(owner, family, **cols)


def test_tombstone_person_without_name_and_account_is_accepted_and_stored_bare(
    owner: Owner,
) -> None:
    """SR-047: l'ex membro non ha nome né legame."""
    family = _family(owner)
    person = _person(
        owner,
        family,
        status="former",
        former_reason="left",
        account_id=None,
        role=None,
    )
    row = owner.rows(
        "select status, former_reason, account_id, role, display_name from app.person "
        "where id = %s",
        (person,),
    )
    assert row == [("former", "left", None, None, None)]


def test_an_account_belongs_to_one_family_only(owner: Owner) -> None:
    """ASM-050: indice unico parziale `ux_person_account_single_family`."""
    alfa, beta = _family(owner), _family(owner)
    account = uuid4()
    _person(owner, alfa, account_id=account)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _person(owner, beta, account_id=account)


# --- course ---------------------------------------------------------------------------------------


def _course(owner: Owner, family: UUID, **cols: Any) -> None:
    values: dict[str, Any] = {"family_id": family, **cols}
    names = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    owner.execute(f"insert into app.course ({names}) values ({marks})", tuple(values.values()))  # noqa: S608


@pytest.mark.parametrize(
    "cols",
    [
        pytest.param({"base_code": "sushi"}, id="base-sconosciuta"),
        pytest.param({}, id="ne-base-ne-nome"),
        pytest.param({"base_code": "starter", "name": "Antipasto"}, id="base-e-nome"),
        pytest.param({"name": ""}, id="nome-vuoto"),
        pytest.param({"name": "N" * 41}, id="nome-41-caratteri"),
    ],
)
def test_course_is_either_a_base_course_or_a_named_one(owner: Owner, cols: dict[str, Any]) -> None:
    family = _family(owner)
    with pytest.raises(psycopg.errors.CheckViolation):
        _course(owner, family, **cols)


def test_course_base_code_is_unique_per_family_but_not_across_families(owner: Owner) -> None:
    alfa, beta = _family(owner), _family(owner)
    _course(owner, alfa, base_code="starter")
    _course(owner, beta, base_code="starter")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _course(owner, alfa, base_code="starter")


def test_custom_course_names_are_unique_ignoring_case_and_spaces(owner: Owner) -> None:
    """AC-033.2: `name_key = lower(btrim(name))` unico per famiglia."""
    family = _family(owner)
    _course(owner, family, name="Zuppa")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _course(owner, family, name="  zUPPA ")
    assert owner.scalar("select name_key from app.course where name = 'Zuppa'") == "zuppa"


# --- ON DELETE: NO ACTION con cascata dalla famiglia (05-data §4, punto aperto) --------------


def _family_with_history(owner: Owner) -> tuple[UUID, UUID]:
    """Famiglia con persona, bootstrap riscattato e richiesta di eliminazione: due riferimenti
    `NO ACTION` verso `person` (family_bootstrap.redeemed_person_id, family.deletion_requested_by)
    che puntano a una persona della stessa famiglia."""
    family = _family(owner)
    person = _person(owner, family)
    _bootstrap(owner, family, email_sha256=None, redeemed_at=T0, redeemed_person_id=person)
    owner.execute(
        "update app.family set status = 'pending_deletion', deletion_requested_at = %s, "
        "deletion_due_at = %s, deletion_requested_by = %s where id = %s",
        (T0, T0 + timedelta(days=7), person, family),
    )
    for code in ("starter", "first"):
        _course(owner, family, base_code=code)
    owner.execute("insert into app.family_default_meal values (%s, 'lunch')", (family,))
    return family, person


def _rows_of(owner: Owner, family: UUID) -> dict[str, int]:
    return {
        "family": owner.scalar("select count(*) from app.family where id = %s", (family,)),
        "person": owner.scalar("select count(*) from app.person where family_id = %s", (family,)),
        "bootstrap": owner.scalar(
            "select count(*) from app.family_bootstrap where family_id = %s", (family,)
        ),
        "course": owner.scalar("select count(*) from app.course where family_id = %s", (family,)),
        "meal": owner.scalar(
            "select count(*) from app.family_default_meal where family_id = %s", (family,)
        ),
    }


def test_isolated_delete_of_a_referenced_person_is_refused(owner: Owner) -> None:
    """NO ACTION: una persona ancora referenziata non si cancella da sola."""
    family, person = _family_with_history(owner)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        owner.execute("delete from app.person where id = %s", (person,))
    assert _rows_of(owner, family)["person"] == 1


def test_deleting_the_family_cascades_despite_no_action_references(owner: Owner) -> None:
    """Il controllo NO ACTION è a fine istruzione: la cascata dalla famiglia, che toglie
    genitori e figli nella stessa istruzione, è ammessa."""
    family, _ = _family_with_history(owner)
    other, _ = _family_with_history(owner)
    owner.execute("delete from app.family where id = %s", (family,))
    assert _rows_of(owner, family) == {
        "family": 0,
        "person": 0,
        "bootstrap": 0,
        "course": 0,
        "meal": 0,
    }
    assert _rows_of(owner, other) == {
        "family": 1,
        "person": 1,
        "bootstrap": 1,
        "course": 2,
        "meal": 1,
    }


def test_menu_app_can_delete_its_own_family_with_cascade(
    owner: Owner, connect_app: Connect
) -> None:
    """Eliminazione definitiva (M2) eseguita da `menu_app` nel contesto della famiglia."""
    family, _ = _family_with_history(owner)
    with connect_app(autocommit=False) as conn:
        conn.execute("select set_config('app.family_id', %s, true)", (str(family),))
        deleted = conn.execute("delete from app.family where id = %s", (family,))
        assert deleted.rowcount == 1
        conn.commit()
    assert _rows_of(owner, family) == {
        "family": 0,
        "person": 0,
        "bootstrap": 0,
        "course": 0,
        "meal": 0,
    }
