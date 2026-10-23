"""Avvio del login e callback OIDC (US-001, US-002; SR-001, SR-033, SR-049; THR-001..010).

Il callback non fallisce mai con un errore HTTP: risponde `302` verso `returnTo` (allow-list) o
`/piano`, senza parametri nell'URL; l'esito negativo resta sul server, nella riga `auth_flow`,
e la SPA lo legge una volta da `GET /session`. Il flusso si reclama una volta sola prima dello
scambio del codice (due callback concorrenti: ne vince uno). Il successo avviene in **una sola
transazione**: account (solo se la famiglia lo ammette), persona, riscatto del bootstrap,
sessione nuova (e cancellazione di quella che il browser già aveva), evento `auth.login` e
cancellazione del flusso.
"""

import json
import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import structlog

from menu import tenancy
from menu.audit import EventType, SecurityEvent, security_log
from menu.identity.accounts import find_account, upsert_account
from menu.identity.flows import (
    ClaimedFlow,
    claim_flow,
    forget_flow,
    record_failure,
    start_flow,
)
from menu.identity.models import AuthOutcomeCode, GoogleIdentity, LoginResolver, Member
from menu.identity.oidc import OidcClient, OidcError
from menu.identity.sessions import create_session, drop_session_of_cookie
from menu.identity.tokens import (
    constant_time_equal_bytes,
    digest,
    new_code_verifier,
    new_secret,
)
from menu.tenancy import system_tx

DEFAULT_RETURN = "/piano"
RETURN_TO_MAX = 200
# Percorsi relativi della SPA (ADR-0004 r.2 punto 3): mai URL assoluti, `//`, `\`, `..`.
_RETURN_TO = re.compile(
    r"/(?:piano|piatti|altro)(?:/[A-Za-z0-9_.-]+)*/?(?:\?[A-Za-z0-9_.=&-]*)?", re.ASCII
)
_log = structlog.get_logger("menu.identity")


def sanitize_return_to(value: str | None) -> str | None:
    """Il valore se ammesso, altrimenti `None` (si torna a `/piano`, senza rivelare perché)."""
    if value is None or len(value) > RETURN_TO_MAX or ".." in value:
        return None
    return value if _RETURN_TO.fullmatch(value) else None


def begin_login(
    oidc: OidcClient, return_to: str | None, previous_handle: str | None
) -> tuple[str, str]:
    """Crea il flusso e restituisce `(redirectUrl, valore del cookie __Host-auth_flow)`."""
    handle, state, nonce, verifier = new_secret(), new_secret(), new_secret(), new_code_verifier()
    url = oidc.authorization_url(state=state, nonce=nonce, code_verifier=verifier)
    start_flow(
        handle=handle,
        state=state,
        nonce=nonce,
        code_verifier=verifier,
        return_to=sanitize_return_to(return_to),
        previous_handle=previous_handle,
    )
    return url, handle


@dataclass(frozen=True)
class CallbackResult:
    redirect_to: str
    session_token: str | None = None
    clear_flow_cookie: bool = False


@dataclass(frozen=True)
class CallbackRequest:
    code: str | None
    state: str | None
    error: str | None
    old_session_token: str | None
    ip: str | None
    user_agent: str | None
    correlation_id: UUID


def _record_failure(
    handle: str, request: CallbackRequest, code: AuthOutcomeCode, reason: str
) -> None:
    """Esito negativo + evento di sicurezza, in una sola transazione (best effort)."""
    try:
        with system_tx() as tx:
            record_failure(handle, code, tx=tx)
            security_log(_login_event(request, "failure", reason), tx)
    except Exception as error:
        _log.error("identity.callback_failure_unrecorded", exception=type(error).__name__)


def _login_event(
    request: CallbackRequest,
    outcome: Literal["success", "failure", "denied"],
    reason: str,
    member: Member | None = None,
    session_id: UUID | None = None,
) -> SecurityEvent:
    return SecurityEvent(
        event_type=EventType.AUTH_LOGIN,
        outcome=outcome,
        actor_kind="anonymous" if member is None else "account",
        actor_account_id=None if member is None else member.account_id,
        actor_role=None if member is None else member.role,
        family_id=None if member is None else member.family_id,
        target_type=None if session_id is None else "session",
        target_id=session_id,
        ip=request.ip,
        correlation_id=request.correlation_id,
        details_json=json.dumps({"reason": reason}),
    )


def complete_callback(
    oidc: OidcClient, resolver: LoginResolver, handle: str | None, request: CallbackRequest
) -> CallbackResult:
    flow = claim_flow(handle)
    if handle is None or flow is None:
        return CallbackResult(DEFAULT_RETURN, clear_flow_cookie=True)
    target = sanitize_return_to(flow.return_to) or DEFAULT_RETURN
    try:
        return _complete(oidc, resolver, handle, request, flow, target)
    except Exception as error:
        _log.error("identity.callback_failed", exception=type(error).__name__)
        _record_failure(handle, request, "auth_failed", "internal")
        return CallbackResult(target)


def _complete(
    oidc: OidcClient,
    resolver: LoginResolver,
    handle: str,
    request: CallbackRequest,
    flow: ClaimedFlow,
    target: str,
) -> CallbackResult:
    if request.state is None or not constant_time_equal_bytes(
        digest(request.state), flow.state_hash
    ):
        _record_failure(handle, request, "auth_failed", "state")
        return CallbackResult(target)
    if request.error is not None:
        cancelled = request.error == "access_denied"
        _record_failure(
            handle, request, "auth_cancelled" if cancelled else "auth_failed", "provider_error"
        )
        return CallbackResult(target)
    if request.code is None:
        _record_failure(handle, request, "auth_failed", "no_code")
        return CallbackResult(target)
    try:
        who = oidc.identity_from_code(
            code=request.code, code_verifier=flow.code_verifier, nonce_hash=flow.nonce_hash
        )
    except OidcError as error:
        _log.warning("identity.token_rejected", exception=type(error).__name__)
        _record_failure(handle, request, "auth_failed", "token")
        return CallbackResult(target)
    token = _sign_in(resolver, handle, request, who)
    if token is None:
        return CallbackResult(target)
    return CallbackResult(target, session_token=token, clear_flow_cookie=True)


def _sign_in(
    resolver: LoginResolver, handle: str, request: CallbackRequest, who: GoogleIdentity
) -> str | None:
    """Transazione unica del successo; `None` se la persona non ha una famiglia."""
    with system_tx() as tx:
        existing = find_account(tx, who.subject)
        ensured: list[UUID] = []

        def ensure_account() -> UUID:
            if not ensured:
                ensured.append(upsert_account(tx, who))
            return ensured[0]

        outcome = resolver.resolve(tx, who, existing, ensure_account)
        if not isinstance(outcome, Member):
            record_failure(handle, "not_member", tx=tx)
            security_log(_login_event(request, "denied", "not_member"), tx)
            return None
        ensure_account()
        drop_session_of_cookie(tx, request.old_session_token)
        tenancy.bind_context(tx, account_id=outcome.account_id)
        token, session_id = create_session(
            tx, outcome.account_id, ip=request.ip, user_agent=request.user_agent
        )
        security_log(_login_event(request, "success", "login", outcome, session_id), tx)
        forget_flow(tx, handle)
    return token
