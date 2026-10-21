"""Hash dell'email normalizzata (ADR-0011): unica definizione, usata da servizio e console."""

import hashlib


def email_sha256(email: str) -> bytes:
    """SHA-256 di `email.strip().lower()` codificata in UTF-8 (32 byte)."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).digest()
