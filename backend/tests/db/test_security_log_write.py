"""Percorso di scrittura di `menu.audit.security_log` come `menu_app` (CR-SL02-007).

È l'unico punto in cui l'app scrive nel registro (SR-020, SR-057): il test prova l'INSERT reale
(cast `inet`, `varchar`, `jsonb`) e che il log strutturato porta solo `ip_prefix`, mai l'IP
completo (SR-051, SR-058).
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
import sqlalchemy.exc

from menu import tenancy
from menu.audit import SecurityEvent, security_log
from menu.platform.logging import configure_logging
from support.owner import Owner

FULL_IP = "203.0.113.77"
FULL_IP6 = "2001:db8:1234:5678::1"


@pytest.fixture
def as_app(app_url: str) -> Iterator[None]:
    tenancy.init(app_url)
    configure_logging()
    try:
        yield
    finally:
        tenancy.dispose()


def _log_lines(out: str) -> list[dict[str, Any]]:
    records = []
    for line in out.splitlines():
        if line.startswith("{"):
            record = json.loads(line)
            if record.get("event") == "security_event":
                records.append(record)
    return records


def test_security_log_inserts_the_row_as_menu_app(
    owner: Owner, as_app: None, frozen_now: Any
) -> None:
    frozen_now(datetime(2026, 10, 22, 9, 30, tzinfo=UTC))
    family, account, target, corr = uuid4(), uuid4(), uuid4(), uuid4()
    security_log(
        SecurityEvent(
            "console.audit_note",
            "denied",
            "account",
            actor_account_id=account,
            actor_role="planner",
            family_id=family,
            target_type="family",
            target_id=target,
            ip=FULL_IP,
            correlation_id=corr,
            details_json='{"k": "v"}',
        )
    )
    rows = owner.rows(
        "select event_type, outcome, actor_kind, actor_account_id, actor_role, family_id, "
        "target_type, target_id, host(ip), correlation_id, details, occurred_at "
        "from app.security_event"
    )
    assert rows == [
        (
            "console.audit_note",
            "denied",
            "account",
            account,
            "planner",
            family,
            "family",
            target,
            FULL_IP,
            corr,
            {"k": "v"},
            datetime(2026, 10, 22, 9, 30, tzinfo=UTC),
        )
    ], "il database conserva l'IP completo (la retention lo tronca a 90 giorni)"


def test_security_log_with_only_required_fields_stores_nulls(owner: Owner, as_app: None) -> None:
    security_log(SecurityEvent("console.audit_note", "success", "system"))
    row = owner.rows(
        "select actor_account_id, actor_role, family_id, target_type, target_id, ip, "
        "correlation_id, details from app.security_event"
    )
    assert row == [(None,) * 8]


def test_security_log_inside_an_external_transaction_writes_with_the_caller(
    owner: Owner, as_app: None
) -> None:
    with tenancy.system_tx() as tx:
        security_log(SecurityEvent("console.audit_note", "success", "system"), tx)
        assert owner.scalar("select count(*) from app.security_event") == 0, "non ancora commit"
    assert owner.scalar("select count(*) from app.security_event") == 1


@pytest.mark.parametrize(
    ("ip", "prefix"),
    [(FULL_IP, "203.0.113.0/24"), (FULL_IP6, "2001:db8:1234::/48"), (None, None)],
)
def test_security_log_logs_only_the_ip_prefix(
    as_app: None, capfd: pytest.CaptureFixture[str], ip: str | None, prefix: str | None
) -> None:
    security_log(SecurityEvent("console.audit_note", "success", "system", ip=ip))
    out = capfd.readouterr().out
    records = _log_lines(out)
    assert len(records) == 1
    record = records[0]
    assert record["ip_prefix"] == prefix
    assert "ip" not in record
    for full in (FULL_IP, FULL_IP6):
        assert full not in out, "l'IP completo non compare mai nel log (SR-051)"
    assert record["event_type"] == "console.audit_note"
    assert record["outcome"] == "success"


def test_security_log_never_logs_the_details_payload(
    as_app: None, capfd: pytest.CaptureFixture[str]
) -> None:
    security_log(
        SecurityEvent(
            "console.audit_note", "success", "system", details_json='{"request_ref": "CANARY-REF"}'
        )
    )
    out = capfd.readouterr().out
    assert _log_lines(out)
    assert "CANARY-REF" not in out


@pytest.mark.parametrize(
    "event",
    [
        pytest.param(
            SecurityEvent("console.audit_note", "success", "system", ip="not-an-ip"),
            id="ip-non-valido",
        ),
        pytest.param(
            SecurityEvent(
                "console.audit_note",
                "success",
                "system",
                details_json='{"k": "' + "x" * 2000 + '"}',
            ),
            id="details-oltre-1-KiB",
        ),
    ],
)
def test_a_failed_insert_leaves_no_row_and_logs_no_event(
    owner: Owner, as_app: None, capfd: pytest.CaptureFixture[str], event: SecurityEvent
) -> None:
    """CR-SL02-007: la riga di log segue l'INSERT riuscito; se l'INSERT fallisce stdout non
    dichiara un evento che il database non ha (gli allarmi SR-058 contano i log)."""
    with pytest.raises(sqlalchemy.exc.DBAPIError):
        security_log(event)
    assert owner.scalar("select count(*) from app.security_event") == 0
    assert _log_lines(capfd.readouterr().out) == []


def test_with_an_external_transaction_the_log_line_follows_the_commit(
    owner: Owner, as_app: None, capfd: pytest.CaptureFixture[str]
) -> None:
    with tenancy.system_tx() as tx:
        security_log(SecurityEvent("console.audit_note", "success", "system"), tx)
        assert _log_lines(capfd.readouterr().out) == [], "nulla nel log prima del commit"
    assert len(_log_lines(capfd.readouterr().out)) == 1
    assert owner.scalar("select count(*) from app.security_event") == 1


def test_with_an_external_transaction_that_rolls_back_nothing_is_logged(
    owner: Owner, as_app: None, capfd: pytest.CaptureFixture[str]
) -> None:
    """SR-058: gli allarmi contano le righe di log; un rollback non deve lasciarne una."""

    class BoomError(Exception):
        pass

    def rolled_back() -> None:
        with tenancy.system_tx() as tx:
            security_log(SecurityEvent("console.audit_note", "success", "system"), tx)
            raise BoomError

    with pytest.raises(BoomError):
        rolled_back()
    assert owner.scalar("select count(*) from app.security_event") == 0
    assert _log_lines(capfd.readouterr().out) == []
