"""Modulo common (strato 0): errori applicativi, hash dell'email.

Ammesse solo libreria standard e Pydantic (piano §2.1).
"""

from menu.common.email import email_sha256
from menu.common.errors import AppError, ErrorCode, ValidationCode

__all__ = ["AppError", "ErrorCode", "ValidationCode", "email_sha256"]
