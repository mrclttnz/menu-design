"""`GET /session` e `POST /auth/logout`: letture e azioni che compongono identità e famiglia.

La sessione si risolve dal cookie `__Host-session` a ogni richiesta e la membership si rilegge
(SR-005). `GET /session` è pubblica: senza sessione risponde `200` anonima, imposta il cookie
`__Host-csrf` se manca e restituisce una sola volta l'esito dell'ultimo accesso. Nessun effetto
oltre a questo; il token CSRF della sessione è quello da ripetere in `X-CSRF-Token`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from menu import family, identity
from menu.platform import AuthzRoute
from menu.views.schemas import (
    AccountView,
    AnonymousSession,
    AuthenticatedSession,
    AuthOutcomeView,
    FamilyView,
    PersonView,
)

router = APIRouter(prefix="/api/v1", route_class=AuthzRoute)

SessionView = AnonymousSession | AuthenticatedSession


def _outcome(request: Request) -> AuthOutcomeView | None:
    read = identity.read_outcome(request.cookies.get(identity.FLOW_COOKIE))
    if read is None:
        return None
    return AuthOutcomeView.model_validate({"code": read.code, "params": read.params})


@router.get(
    "/session",
    operation_id="identity.session.read",
    response_model=SessionView,
    response_model_exclude_unset=True,
    openapi_extra={"x-authz": {"scope": "public"}},
)
def read_session(request: Request, response: Response) -> SessionView:
    token = request.cookies.get(identity.SESSION_COOKIE)
    session = identity.resolve_session(token)
    outcome = _outcome(request)
    identity.ensure_csrf_cookie(request, response)
    if outcome is not None:
        identity.clear_flow_cookie(response)
    if session is None:
        if outcome is None:
            return AnonymousSession(authenticated=False, notices=[])
        return AnonymousSession(authenticated=False, notices=[], auth_outcome=outcome)
    if session.renewed_max_age is not None and token is not None:
        identity.set_session_cookie(response, token, session.renewed_max_age)
    membership = family.membership_for(session, request.state.correlation_id)
    context = membership.context
    brief = membership.family
    family_view: FamilyView | None = None
    if brief is not None:
        family_view = FamilyView(
            id=brief.id,
            name=brief.name,
            timezone=brief.timezone,
            today=brief.today,
            status=brief.status,
        )
        if brief.deletion_due_at is not None:
            family_view.deletion_due_at = brief.deletion_due_at
    person_view: PersonView | None = None
    if context.person_id is not None and context.role is not None:
        person_view = PersonView(id=context.person_id, role=context.role)
    view = AuthenticatedSession(
        authenticated=True,
        csrf_token=session.csrf_token,
        account=AccountView(id=session.account_id, display_name=session.display_name),
        family=family_view,
        person=person_view,
        privacy_review_required=False,
        notices=[],
    )
    if outcome is not None:
        view.auth_outcome = outcome
    return view


@router.post(
    "/auth/logout",
    operation_id="identity.session.logout",
    status_code=204,
    response_class=Response,
    openapi_extra={"x-authz": {"scope": "account", "pendingDeletion": "allowed"}},
)
def logout(
    body: identity.LogoutRequest,
    request: Request,
    response: Response,
    session: Annotated[identity.SessionInfo, Depends(identity.session_guard)],
) -> Response:
    context = family.context_for(session, request.state.correlation_id)
    identity.end_session(session, context, identity.request_ip(request))
    response.status_code = 204
    identity.clear_session_cookie(response)
    return response
