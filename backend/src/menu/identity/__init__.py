"""Modulo identity (strato 5): account, sessioni, OIDC con Google, CSRF, `auth_flow`.

Possiede `account`, `session` e `auth_flow`; nessun altro modulo le tocca (05-data §6.1). L'unica
via per leggere un cookie di sessione è `resolve_session`. La parte che dipende dalla famiglia
(chi può entrare, bootstrap) la implementa `family.onboarding` tramite `LoginResolver`.
"""

from menu.common import register_export_contributor
from menu.identity.api import router
from menu.identity.clientinfo import request_ip
from menu.identity.cookies import (
    CSRF_COOKIE,
    clear_flow_cookie,
    clear_session_cookie,
    ensure_csrf_cookie,
    set_session_cookie,
)
from menu.identity.export import IdentityExport
from menu.identity.flows import FLOW_COOKIE, read_outcome
from menu.identity.guards import anonymous_guard, session_guard
from menu.identity.logout import end_session
from menu.identity.models import (
    AuthOutcomeRead,
    GoogleIdentity,
    LoginOutcome,
    LoginResolver,
    Member,
    NotMember,
    SessionInfo,
)
from menu.identity.schemas import LogoutRequest
from menu.identity.services import IdentityServices
from menu.identity.sessions import SESSION_COOKIE, SessionRef, identify_session, resolve_session

register_export_contributor(IdentityExport())

__all__ = [
    "CSRF_COOKIE",
    "FLOW_COOKIE",
    "SESSION_COOKIE",
    "AuthOutcomeRead",
    "GoogleIdentity",
    "IdentityServices",
    "LoginOutcome",
    "LoginResolver",
    "LogoutRequest",
    "Member",
    "NotMember",
    "SessionInfo",
    "SessionRef",
    "anonymous_guard",
    "clear_flow_cookie",
    "clear_session_cookie",
    "end_session",
    "ensure_csrf_cookie",
    "identify_session",
    "read_outcome",
    "request_ip",
    "resolve_session",
    "router",
    "session_guard",
    "set_session_cookie",
]
