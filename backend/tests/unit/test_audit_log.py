"""Unit del modulo audit (SR-020, SR-051): catalogo e IP troncato nel log strutturato."""

import pytest

from menu.audit import EVENT_TYPES, SecurityEvent, security_log
from menu.audit.log import ip_prefix


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        ("203.0.113.77", "203.0.113.0/24"),
        ("2001:db8:1234:5678::1", "2001:db8:1234::/48"),
        ("not-an-ip", None),
        (None, None),
    ],
)
def test_ip_prefix_never_keeps_the_full_address(ip: str | None, expected: str | None) -> None:
    assert ip_prefix(ip) == expected


def test_catalog_has_the_console_events() -> None:
    assert {"console.family_bootstrap", "console.security_log", "console.audit_note"} <= EVENT_TYPES


def test_unknown_event_type_is_refused_before_any_write() -> None:
    with pytest.raises(ValueError, match="catalogo"):
        security_log(SecurityEvent("made.up", "success", "system"))
