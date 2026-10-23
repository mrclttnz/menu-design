"""Segreti dell'accesso: generazione con `secrets`, hash SHA-256, token CSRF (SR-037, THR-007).

Nessun segreto si conserva in chiaro: nel database stanno solo gli hash. Il token CSRF di una
sessione non è memorizzato, perché `GET /session` deve restituire sempre lo stesso valore:
è derivato con HMAC-SHA256 dal token di sessione (che il server riceve a ogni richiesta nel
cookie `HttpOnly`) e se ne conserva l'hash in `session.csrf_token_hash`.
"""

import base64
import hashlib
import hmac
import re
import secrets

SECRET_BYTES = 32  # 256 bit (SR-037 chiede almeno 128)
_SHAPE = re.compile(r"[A-Za-z0-9_-]{22,128}")
_CSRF_CONTEXT = b"menu-design/csrf/v1"


def new_secret() -> str:
    """Token opaco di 256 bit in base64url (43 caratteri)."""
    return secrets.token_urlsafe(SECRET_BYTES)


def new_code_verifier() -> str:
    """`code_verifier` PKCE (RFC 7636): 64 caratteri dell'alfabeto non riservato."""
    return secrets.token_urlsafe(48)


def digest(value: str) -> bytes:
    """SHA-256 (32 byte) del valore come testo UTF-8: la forma conservata nel database."""
    return hashlib.sha256(value.encode("utf-8")).digest()


def well_formed(value: str | None) -> bool:
    """Forma plausibile di un segreto ricevuto: evita query per valori palesemente estranei."""
    return value is not None and _SHAPE.fullmatch(value) is not None


def csrf_token_for(session_token: str) -> str:
    mac = hmac.new(session_token.encode("utf-8"), _CSRF_CONTEXT, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def constant_time_equal_bytes(left: bytes, right: bytes) -> bool:
    return hmac.compare_digest(left, right)
