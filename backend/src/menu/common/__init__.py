"""Modulo common (strato 0): errori, contesto della richiesta, hash dell'email, registro export.

Ammesse solo libreria standard e Pydantic (piano §2.1).
"""

from menu.common.context import RequestContext
from menu.common.email import email_sha256
from menu.common.errors import AppError, ErrorCode, ValidationCode
from menu.common.export import (
    ExportContributor,
    ExportRows,
    export_contributors,
    register_export_contributor,
)

__all__ = [
    "AppError",
    "ErrorCode",
    "ExportContributor",
    "ExportRows",
    "RequestContext",
    "ValidationCode",
    "email_sha256",
    "export_contributors",
    "register_export_contributor",
]
