"""SR-021 / SR-051 / THR-110: redazione dei log con canarini, ritorni a capo, correlazione."""

import json
import re
import uuid
from typing import Any

import pytest
import structlog
from fastapi.testclient import TestClient

from support.probe import LOG_CANARIES

FORGED = "FORGED-LINE-CANARY"
REQUEST_CANARIES = [
    "CANARY-REQ-COOKIE",
    "CANARY-REQ-AUTH",
    "CANARY-REQ-QUERY",
    "CANARY-REQ-BODY",
    "CANARY-REQ-CSRF",
]


def captured(capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture) -> str:
    out = capfd.readouterr()
    return out.out + out.err + caplog.text


def json_records(text: str) -> list[dict[str, object]]:
    records = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def canary_values() -> list[str]:
    flat: list[Any] = []
    for v in LOG_CANARIES.values():
        flat.extend(v.values() if isinstance(v, dict) else [v])
    return flat


def test_forbidden_keys_are_dropped_from_logs(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    capfd.readouterr()
    assert probe_client.get("/_probe/log").status_code == 200
    text = captured(capfd, caplog)
    records = [r for r in json_records(text) if r.get("event") == "probe.logged"]
    assert len(records) == 1, "l'evento di prova deve uscire come JSON su stdout"
    for canary in canary_values():
        assert canary not in text, canary


def test_unlisted_fields_are_dropped_by_allow_list(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    capfd.readouterr()
    probe_client.get("/_probe/log")
    assert "CANARY-LOG-UNLISTED" not in captured(capfd, caplog)


def test_log_record_has_required_fields_and_correlation_id(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    capfd.readouterr()
    probe_client.get("/_probe/log")
    record = next(
        r for r in json_records(captured(capfd, caplog)) if r.get("event") == "probe.logged"
    )
    assert {"severity", "timestamp", "correlation_id", "event"} <= set(record)
    uuid.UUID(str(record["correlation_id"]))  # UUID valido


def test_correlation_id_differs_between_requests(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    capfd.readouterr()
    probe_client.get("/_probe/log")
    probe_client.get("/_probe/log")
    ids = [
        r["correlation_id"]
        for r in json_records(captured(capfd, caplog))
        if r.get("event") == "probe.logged"
    ]
    assert len(ids) == 2
    assert ids[0] != ids[1]


def test_newlines_in_values_are_neutralised(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    capfd.readouterr()
    structlog.get_logger("test").info(
        f"test.newline\r\n{FORGED} severity=CRITICAL\nrest", path=f"/x\n{FORGED}2"
    )
    text = captured(capfd, caplog)
    assert FORGED in text
    events = [r["event"] for r in json_records(text) if FORGED in str(r.get("event"))]
    assert events == [f"test.newline\\r\\n{FORGED} severity=CRITICAL\\nrest"]
    for line in text.splitlines():
        if FORGED in line:
            assert line.lstrip().startswith("{"), "riga forgiata: ritorno a capo non neutralizzato"
            json.loads(line)
    for record in json_records(text):
        for value in record.values():
            if isinstance(value, str):
                assert "\n" not in value
                assert "\r" not in value


def test_requests_never_log_cookie_authorization_query_or_body(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    capfd.readouterr()
    headers = {
        "Cookie": "__Host-session=CANARY-REQ-COOKIE",
        "Authorization": "Bearer CANARY-REQ-AUTH",
        "X-CSRF-Token": "CANARY-REQ-CSRF",
        "Content-Type": "application/json",
    }
    probe_client.post(
        "/_probe/echo?code=CANARY-REQ-QUERY&state=CANARY-REQ-QUERY",
        content=b'{"note": "CANARY-REQ-BODY"}',
        headers=headers,
    )
    probe_client.post(
        "/_probe/validated?x=CANARY-REQ-QUERY",
        content=b'{"name": "CANARY-REQ-BODY", "count": 1}',
        headers=headers,
    )
    probe_client.get("/_probe/boom?x=CANARY-REQ-QUERY", headers=headers)
    probe_client.put(
        "/_probe/versioned/1?x=CANARY-REQ-QUERY",
        content=b"{}",
        headers={**headers, "If-Match": "*"},
    )
    text = captured(capfd, caplog)
    for canary in REQUEST_CANARIES:
        assert canary not in text, canary


def test_unhandled_exception_is_logged_with_correlation_id(
    probe_client: TestClient, capfd: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """Piano §5.2: stack trace solo nel log del server, con correlation_id."""
    capfd.readouterr()
    assert probe_client.get("/_probe/boom").status_code == 500
    text = captured(capfd, caplog)
    assert "RuntimeError" in text
    ids = re.findall(r'"correlation_id":\s*"([0-9a-f-]{36})"', text)
    assert ids, "l'errore 500 deve riportare correlation_id nel log"
