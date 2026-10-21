"""ADR-0008 / ADR-0010 / THR-107 (A-23): If-Match assente 428; malformato 422 invalid_value."""

import pytest
from fastapi.testclient import TestClient

URL = "/_probe/versioned/5"
JSON = {"Content-Type": "application/json"}
BIGINT_MAX = 2**63 - 1


def test_missing_if_match_is_428(probe_client: TestClient, probe_calls: list[str]) -> None:
    resp = probe_client.put(URL, content=b"{}", headers=JSON)
    assert resp.status_code == 428
    assert resp.json()["code"] == "precondition_required"
    assert probe_calls == []


@pytest.mark.parametrize(
    ("header", "version"),
    [('"0"', 0), ('"1"', 1), ('"42"', 42), ('"999999999999999999"', 999999999999999999)],
)
def test_valid_if_match_is_accepted_and_parsed_as_int(
    probe_client: TestClient, header: str, version: int
) -> None:
    resp = probe_client.put(URL, content=b"{}", headers={**JSON, "If-Match": header})
    assert resp.status_code == 200
    assert resp.json()["version"] == version
    assert version <= BIGINT_MAX


@pytest.mark.parametrize(
    "value",
    [
        "*",
        'W/"3"',
        'w/"3"',
        '"-1"',
        "-1",
        "3",  # senza virgolette
        "abc",
        '"abc"',
        '"1.5"',
        '"1e3"',
        '"+1"',
        '"01"',
        '"00"',
        '"1 "',
        '""',
        "",  # header vuoto: 422, non 428 (ADR-0008)
        '"1", "2"',
        '"1","2"',
        '"1"x',
        '"9223372036854775807"',  # 19 cifre, anche se entro bigint: fuori dalla regex
        '"9223372036854775808"',  # bigint + 1
        '"9999999999999999999"',  # 19 cifre (THR-107)
        '"' + "9" * 40 + '"',
        '"' + "9" * 5000 + '"',
    ],
)
def test_malformed_if_match_is_422_invalid_value_never_500(
    probe_client: TestClient, probe_calls: list[str], value: str
) -> None:
    resp = probe_client.put(URL, content=b"{}", headers={**JSON, "If-Match": value})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation"
    assert body["errors"] == [{"field": "If-Match", "code": "invalid_value"}]
    assert probe_calls == [], "nessuna scrittura su If-Match non valido"
    # THR-107: il valore ricevuto non e' riflesso nell'errore.
    if len(value) > 3:
        assert value not in resp.text


def test_repeated_if_match_headers_are_422(
    probe_client: TestClient, probe_calls: list[str]
) -> None:
    resp = probe_client.put(
        URL, content=b"{}", headers=[*JSON.items(), ("If-Match", '"1"'), ("If-Match", '"2"')]
    )
    assert resp.status_code == 422
    assert resp.json()["errors"] == [{"field": "If-Match", "code": "invalid_value"}]
    assert probe_calls == []


def test_malformed_if_match_with_valid_body_is_422_on_if_match_field(
    probe_client: TestClient, probe_calls: list[str]
) -> None:
    """Corpo JSON valido e If-Match malformato: l'errore è sul campo If-Match."""
    resp = probe_client.put(URL, content=b"{}", headers={**JSON, "If-Match": "*"})
    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"] == "If-Match"
    assert probe_calls == []
