"""Proprietà di `app.search_norm` (08 §8.2; profilo `ci-small`: 20 esempi, derandomizzato)."""

from collections.abc import Iterator

import psycopg
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from support import pg

pytestmark = pytest.mark.property


@pytest.fixture(scope="module")
def conn(worker_db: str) -> Iterator[psycopg.Connection]:
    with pg.connect_as("menu_app", worker_db) as c:
        yield c


text = st.text(
    alphabet=st.characters(blacklist_categories=["Cs"], blacklist_characters="\x00"),
    max_size=40,
)


@settings(max_examples=20, derandomize=True, deadline=None)
@given(value=text)
def test_search_norm_is_idempotent(conn: psycopg.Connection, value: str) -> None:
    once = conn.execute("select app.search_norm(%s)", (value,)).fetchone()
    assert once is not None
    twice = conn.execute("select app.search_norm(%s)", (once[0],)).fetchone()
    assert twice == once


ACCENTED = {"à": "a", "è": "e", "é": "e", "ì": "i", "ò": "o", "ù": "u", "ç": "c",
            "À": "a", "É": "e"}  # fmt: skip
mixed = st.lists(
    st.one_of(st.sampled_from(sorted(ACCENTED)), st.text(alphabet="abcdeiou ABCDEIOU", max_size=3)),
    max_size=12,
).map("".join)


@settings(max_examples=20, derandomize=True, deadline=None)
@given(value=mixed)
def test_search_norm_strips_accents_and_folds_case(conn: psycopg.Connection, value: str) -> None:
    """Accenti rimossi e maiuscole ripiegate: confronto con una trascrizione indipendente."""
    expected = "".join(ACCENTED.get(c, c) for c in value).lower()
    row = conn.execute("select app.search_norm(%s)", (value,)).fetchone()
    assert row == (expected,)


@settings(max_examples=20, derandomize=True, deadline=None)
@given(value=text)
def test_search_norm_is_case_insensitive_for_ascii(conn: psycopg.Connection, value: str) -> None:
    if not value.isascii():
        return
    a = conn.execute("select app.search_norm(%s)", (value,)).fetchone()
    b = conn.execute("select app.search_norm(%s)", (value.upper(),)).fetchone()
    assert a == b
