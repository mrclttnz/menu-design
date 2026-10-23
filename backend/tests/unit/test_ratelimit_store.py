"""Chiavi dei contatori (ADR-0006): HMAC-SHA-256 con pepper e nome della regola."""

import hashlib
import hmac

from menu.ratelimit import API_SESSION, WRITE_SESSION
from menu.ratelimit.store import counter_key

PEPPER = b"unit-test-pepper-0123456789abcdef0123456789abcdef"


def test_key_is_a_32_byte_hmac_of_rule_and_identifier() -> None:
    key = counter_key(PEPPER, API_SESSION, "abc")
    assert key == hmac.new(PEPPER, b"api_session\x00abc", hashlib.sha256).digest()
    assert len(key) == 32


def test_same_identifier_in_two_rules_or_with_two_peppers_gives_different_keys() -> None:
    assert counter_key(PEPPER, API_SESSION, "abc") != counter_key(PEPPER, WRITE_SESSION, "abc")
    assert counter_key(PEPPER, API_SESSION, "abc") != counter_key(PEPPER + b"x", API_SESSION, "abc")
