"""menu.common: ErrorCode (fonte unica ADR-0010), AppError, email_sha256 (ADR-0011)."""

import hashlib

import pytest

from menu.common import AppError, ErrorCode, email_sha256
from support.adr_tables import error_code_table


def test_adr_table_parser_sanity() -> None:
    """Protegge il test successivo da un parser che non legge nulla."""
    table = error_code_table()
    assert len(table) >= 25
    assert table["validation"] == 422
    assert table["precondition_required"] == 428
    assert table["reauth_wrong_account"] == 403  # riga in grassetto


def test_error_code_equals_adr_0010_table() -> None:
    """SL-00a / ADR-0010: l'enumerazione coincide con la tabella, né più né meno."""
    expected = set(error_code_table())
    actual = {member.value for member in ErrorCode}
    assert actual - expected == set(), "codici nell'enum ma non in ADR-0010"
    assert expected - actual == set(), "codici in ADR-0010 ma non nell'enum"


def test_error_code_values_are_unique_lowercase_snake() -> None:
    values = [member.value for member in ErrorCode]
    assert len(values) == len(set(values))
    assert all(v == v.lower() and " " not in v for v in values)


@pytest.mark.parametrize("value", sorted(error_code_table()))
def test_error_code_lookup_by_value(value: str) -> None:
    assert ErrorCode(value).value == value


def test_error_code_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="nope"):
        ErrorCode("nope")


def test_app_error_carries_code_and_params() -> None:
    err = AppError(ErrorCode("conflict"), {"current": 3})
    assert isinstance(err, Exception)
    assert err.code == ErrorCode("conflict")
    assert err.params == {"current": 3}


def test_app_error_params_default_is_empty_and_not_shared() -> None:
    a = AppError(ErrorCode("not_found"))
    b = AppError(ErrorCode("not_found"))
    assert a.params == {}
    a.params["x"] = 1
    assert b.params == {}


def test_email_sha256_matches_definition() -> None:
    """ADR-0011: sha256(email.strip().lower().encode())."""
    digest = email_sha256("  Maria.Rossi@Example.TEST ")
    assert isinstance(digest, bytes)
    assert digest == hashlib.sha256(b"maria.rossi@example.test").digest()
    assert len(digest) == 32


def test_email_sha256_is_case_and_space_insensitive_but_distinguishes_addresses() -> None:
    assert email_sha256("A@example.test") == email_sha256(" a@EXAMPLE.test\n")
    assert email_sha256("a@example.test") != email_sha256("b@example.test")
