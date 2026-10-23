"""`limit_subject` in isolamento (SEC-SL03b-001): chiave per i limiti per IP."""

import pytest

from menu.platform.http.client_ip import limit_subject


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("2001:db8:1:2:aaaa:bbbb:cccc:dddd", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:1::1", "2001:db8:1:2::/64"),  # stesso /64, stessa chiave
        ("::ffff:192.0.2.7", "192.0.2.7"),
        ("192.0.2.7", "192.0.2.7"),
        ("unknown", "unknown"),
    ],
)
def test_limit_subject(ip: str, expected: str) -> None:
    assert limit_subject(ip) == expected
