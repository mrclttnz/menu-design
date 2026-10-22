"""`email_sha256` identico tra script della console e servizio (I-03, ADR-0011; 08 §8.2).
SL-02. Profilo `ci-small`: 20 esempi, derandomizzato.

"Script" = `menu.console_client` (hash negli argomenti del job); "servizio" =
`menu.common.email_sha256`; oracolo indipendente = la definizione di ADR-0011 riscritta qui.
Contratto del client come in `tests/unit/test_console_client.py`.
"""

import hashlib
import importlib
import re
import subprocess
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from menu.common import email_sha256

pytestmark = pytest.mark.property

HEX64 = re.compile(r"^[0-9a-f]{64}$")
LETTERS = "abcxyzABCXYZ0123456789._-ëËéÉàÀüÜßñÑçÇ"
local = st.text(alphabet=LETTERS, min_size=1, max_size=12).filter(lambda s: s.strip() == s)
domain = st.text(alphabet="abcdxyzABCDXYZ", min_size=1, max_size=8)
emails = st.builds(lambda a, d: f"{a}@{d}.test", local, domain)
padding = st.text(alphabet=" \t\n", max_size=3)


def oracle(email: str) -> bytes:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).digest()


def _hash_sent_by_the_script(email: str) -> str:
    main: Any = importlib.import_module("menu.console_client").main  # contratto assunto

    calls: list[list[str]] = []

    def runner(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "ok\n", "")

    assert (
        main(
            ["family", "bootstrap", "--name", "Famiglia Alfa"],
            prompt=lambda _: email,
            runner=runner,
        )
        == 0
    )
    found = [t for a in calls[0] for t in re.split(r"[=,]", a) if HEX64.match(t)]
    assert len(found) == 1
    return found[0]


@settings(max_examples=20, derandomize=True, deadline=None)
@given(email=emails, left=padding, right=padding)
def test_script_and_service_hash_the_same_value(email: str, left: str, right: str) -> None:
    typed = f"{left}{email}{right}"
    sent = _hash_sent_by_the_script(typed)
    assert sent == email_sha256(typed).hex() == oracle(typed).hex()


@settings(max_examples=20, derandomize=True, deadline=None)
@given(email=emails, left=padding, right=padding)
def test_hash_ignores_surrounding_whitespace_and_has_32_bytes(
    email: str, left: str, right: str
) -> None:
    digest = email_sha256(f"{left}{email}{right}")
    assert len(digest) == 32
    assert digest == email_sha256(email)


@settings(max_examples=20, derandomize=True, deadline=None)
@given(
    email=st.builds(
        lambda a, d: f"{a}@{d}.test",
        st.text(alphabet="abcxyzABCXYZ019", min_size=1, max_size=10),
        domain,
    )
)
def test_hash_ignores_ascii_case(email: str) -> None:
    assert email_sha256(email.upper()) == email_sha256(email.lower()) == email_sha256(email)
