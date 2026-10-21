"""Unità di `menu.platform`: stati per codice, `client_ip`, profondità JSON, traduzione Pydantic."""

import pytest

from menu.common import ErrorCode
from menu.platform.http.client_ip import client_ip_from
from menu.platform.http.middleware import json_depth_exceeds
from menu.platform.http.problem import STATUS_BY_CODE


def test_every_error_code_has_an_http_status() -> None:
    assert set(STATUS_BY_CODE) == set(ErrorCode)


@pytest.mark.parametrize(
    ("forwarded", "peer", "hops", "expected"),
    [
        ([], "10.0.0.1", 0, "10.0.0.1"),
        (["1.2.3.4"], "10.0.0.1", 0, "10.0.0.1"),  # senza proxy fidati l'header è ignorato
        (["6.6.6.6, 203.0.113.9"], "10.0.0.1", 1, "203.0.113.9"),  # falsificato: ultima voce
        (["6.6.6.6", "203.0.113.9"], "10.0.0.1", 1, "203.0.113.9"),  # header ripetuto
        (["6.6.6.6, 203.0.113.9, 10.1.1.1"], "10.0.0.1", 2, "203.0.113.9"),
        ([], "10.0.0.1", 1, "10.0.0.1"),
        (["203.0.113.9"], "10.0.0.1", 2, "10.0.0.1"),  # meno voci dei proxy: peer
        (["not-an-ip"], "10.0.0.1", 1, "10.0.0.1"),
        (["2001:db8::1"], None, 1, "2001:db8::1"),
        ([], None, 0, "unknown"),
    ],
)
def test_client_ip(forwarded: list[str], peer: str | None, hops: int, expected: str) -> None:
    assert client_ip_from(forwarded, peer, hops) == expected


@pytest.mark.parametrize(
    ("body", "exceeds"),
    [
        (b'{"a":[{"b":[{"c":[{"d":[{"e":[{}]}]}]}]}]}', True),  # 11 contenitori
        (b'{"a":[{"b":[{"c":[{"d":[{"e":[]}]}]}]}]}', False),  # 10 contenitori
        (b'{"s":"[[[[[[[[[[[[[[[[[[[["}', False),  # parentesi dentro una stringa
        (b'{"s":"\\"[[[[[[[[[[[[[[[[[["}', False),  # virgolette con escape
        (b'"unterminated [[[[[[[[[[[[[[[[[[[[', True),  # JSON malformato: prudenza
    ],
)
def test_json_depth_exceeds(body: bytes, exceeds: bool) -> None:
    assert json_depth_exceeds(body, 10) is exceeds
