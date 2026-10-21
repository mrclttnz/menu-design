"""Errori applicativi: `ErrorCode` è l'unica enumerazione dei codici (ADR-0010).

Gli stati HTTP corrispondenti stanno in `menu.platform.http.problem`; un test verifica che
questa enumerazione coincida con la tabella di ADR-0010.
"""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    VALIDATION = "validation"
    NOT_FOUND = "not_found"
    FORBIDDEN = "forbidden"
    UNAUTHENTICATED = "unauthenticated"
    REAUTH_REQUIRED = "reauth_required"
    REAUTH_WRONG_ACCOUNT = "reauth_wrong_account"
    CSRF_FAILED = "csrf_failed"
    CONFLICT = "conflict"
    PRECONDITION_REQUIRED = "precondition_required"
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    FAMILY_PENDING_DELETION = "family_pending_deletion"
    INVITE_INVALID = "invite_invalid"
    CODE_INVALID = "code_invalid"
    AGE_DECLARATION_BLOCKED = "age_declaration_blocked"
    ALREADY_IN_FAMILY = "already_in_family"
    LAST_ADMIN = "last_admin"
    DISH_ALREADY_PLANNED = "dish_already_planned"
    DISH_NOT_PLANNED = "dish_not_planned"
    COURSE_IN_USE = "course_in_use"
    QUOTA_EXCEEDED = "quota_exceeded"
    RANGE_TOO_LARGE = "range_too_large"
    COURSE_NOT_ALLOWED = "course_not_allowed"
    PERSON_BEFORE_JOIN = "person_before_join"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    INTERNAL = "internal"


class ValidationCode(StrEnum):
    """Insieme chiuso dei codici di `errors[].code` (piano §4.1)."""

    REQUIRED = "required"
    STRING_TOO_LONG = "string_too_long"
    LIMIT_REACHED = "limit_reached"
    URL_INVALID = "url_invalid"
    COURSE_REQUIRED = "course_required"
    GUESTS_RANGE = "guests_range"
    PRIORITY_RANGE = "priority_range"
    DATE_INVALID = "date_invalid"
    RANGE_ORDER = "range_order"
    DUPLICATE_COURSE = "duplicate_course"
    INVALID_VALUE = "invalid_value"
    UNKNOWN_FIELD = "unknown_field"
    DISH_ARCHIVED = "dish_archived"


class AppError(Exception):
    """Unica eccezione del dominio: codice stabile e parametri, mai testi per l'utente."""

    def __init__(self, code: ErrorCode, params: dict[str, Any] | None = None) -> None:
        super().__init__(code.value)
        self.code = code
        self.params: dict[str, Any] = {} if params is None else params
