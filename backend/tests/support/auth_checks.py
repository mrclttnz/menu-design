"""Controlli condivisi dai test dell'accesso (SL-03a): hash dei segreti, perdite, cookie.

Il formato esatto dei token (esadecimale, base64url) non è fissato dal contratto: `hashes_of`
ammette le forme naturali, e `leaks` cerca un segreto in tutte le sue forme (testo, esadecimale
dei byte UTF-8, byte decodificati), così il controllo "nessun segreto in chiaro" non dipende
dalla scelta di codifica dell'implementazione (SR-037, THR-005).
"""

import base64
import binascii
import contextlib
import hashlib
import re

from support.browser_sim import SetCookie
from support.owner import Owner

DOCUMENT_TABLES_SQL = (
    "select tablename from pg_tables where schemaname = 'app' and tablename <> 'alembic_version' "
    "order by 1"
)


def _decodings(secret: str) -> list[bytes]:
    forms = [secret.encode("utf-8")]
    if re.fullmatch(r"[0-9a-fA-F]+", secret) and len(secret) % 2 == 0:
        forms.append(bytes.fromhex(secret))
    with contextlib.suppress(binascii.Error, ValueError):
        forms.append(base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4)))
    return forms


def hashes_of(secret: str) -> set[bytes]:
    """SHA-256 del segreto nelle forme naturali (testo UTF-8, byte esadecimali, byte base64url)."""
    return {hashlib.sha256(form).digest() for form in _decodings(secret)}


def database_dump_text(owner: Owner) -> str:
    """Tutte le righe di tutte le tabelle dello schema `app`, come testo (bytea in esadecimale)."""
    chunks = []
    for (table,) in owner.rows(DOCUMENT_TABLES_SQL):
        for (row,) in owner.rows(f'select t::text from app."{table}" t'):  # noqa: S608  (tabella dal catalogo)
            chunks.append(f"{table}: {row}")
    return "\n".join(chunks)


def leaks(dump: str, secret: str) -> bool:
    """Il segreto compare nel testo del database in una qualunque forma di codifica?"""
    if secret in dump:
        return True
    lowered = dump.lower()
    return any(form.hex() in lowered for form in _decodings(secret) if len(form) >= 8)


def assert_cookie(
    cookie: SetCookie,
    *,
    http_only: bool,
    same_site: str,
    max_age: int | None = None,
    max_age_at_most: int | None = None,
) -> None:
    """Attributi richiesti per i cookie `__Host-` (SR-005, SR-037): Secure, Path=/, nessun."""
    assert cookie.name.startswith("__Host-"), cookie.name
    assert cookie.flag("secure"), f"{cookie.name}: manca Secure"
    assert cookie.attrs.get("path") == "/", f"{cookie.name}: Path deve essere /"
    assert "domain" not in cookie.attrs, f"{cookie.name}: __Host- vieta Domain"
    assert cookie.flag("httponly") is http_only, f"{cookie.name}: HttpOnly deve essere {http_only}"
    assert cookie.attrs.get("samesite", "").lower() == same_site.lower(), cookie.name
    if max_age is not None:
        assert cookie.attrs.get("max-age") == str(max_age), (cookie.name, cookie.attrs)
    if max_age_at_most is not None:
        assert 0 < int(cookie.attrs.get("max-age", "0")) <= max_age_at_most, cookie.attrs
