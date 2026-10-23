"""Logout: la sessione si cancella sul server e l'evento `auth.logout` resta nel registro."""

from menu import tenancy
from menu.audit import EventType, SecurityEvent, security_log
from menu.common import RequestContext
from menu.identity.models import SessionInfo
from menu.identity.sessions import delete_session


def end_session(session: SessionInfo, ctx: RequestContext, ip: str | None) -> None:
    """Cancella la sessione e scrive l'evento nella stessa transazione (AC-001.4, SR-020)."""
    with tenancy.account_tx(session.account_id) as tx:
        delete_session(session, tx)
        security_log(
            SecurityEvent(
                event_type=EventType.AUTH_LOGOUT,
                outcome="success",
                actor_kind="account",
                actor_account_id=session.account_id,
                actor_role=ctx.role,
                family_id=ctx.family_id,
                target_type="session",
                target_id=session.session_id,
                ip=ip,
                correlation_id=ctx.correlation_id,
            ),
            tx,
        )
