"""Middleware dei limiti di frequenza (SR-059, SR-070; THR-011, THR-012, THR-013, THR-103).

Si applica solo a `/api/v1/`: `/healthz` e la SPA non sono contate (THR-106). Per ogni richiesta
un solo upsert con tutte le regole che la riguardano: quelle per IP delle rotte anonime e, se il
cookie porta una sessione valida, quelle per sessione e per account. Oltre il limite: `429`
(`problem+json`, `Retry-After`) prima che la richiesta arrivi all'handler. Se i contatori non
si possono scrivere la richiesta è negata con `503` (fail closed) senza dettagli.
"""

from collections.abc import Callable, Mapping
from typing import Protocol
from uuid import UUID

import structlog
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from menu.audit import EventType, SecurityEvent, security_log
from menu.common import ErrorCode
from menu.platform.http.client_ip import UNKNOWN, client_ip_from, limit_subject
from menu.platform.http.middleware import UNSAFE_METHODS
from menu.platform.http.problem import problem_response
from menu.ratelimit import rules
from menu.ratelimit.store import Exceeded, Hit, Verdict, hit

_log = structlog.get_logger("menu.ratelimit")


class Session(Protocol):
    @property
    def session_id(self) -> UUID: ...

    @property
    def account_id(self) -> UUID: ...


SessionIdentifier = Callable[[Mapping[str, str]], Session | None]
"""Dai cookie alla sessione valida, in sola lettura (non rinnova la finestra mobile)."""


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        pepper: bytes,
        trusted_proxy_hops: int,
        identify: SessionIdentifier,
    ) -> None:
        self.app = app
        self._pepper = pepper
        self._hops = trusted_proxy_hops
        self._identify = identify

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(rules.API_PREFIX):
            await self.app(scope, receive, send)
            return
        denial = await run_in_threadpool(self._evaluate, Request(scope))
        if denial is not None:
            await denial(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _evaluate(self, request: Request) -> Response | None:
        """`None` se la richiesta passa; altrimenti la risposta `429` o `503`."""
        try:
            ip = client_ip_from(
                request.headers.getlist("x-forwarded-for"),
                request.client.host if request.client else None,
                self._hops,
            )
            session = self._identify(request.cookies)
            hits = self._hits(request, ip, session)
            verdict = hit(self._pepper, hits) if hits else None
        except Exception as error:  # fail closed: qualunque guasto nega, senza dettagli (CWE-209)
            _log.error("ratelimit.unavailable", exception=type(error).__name__)
            return JSONResponse({"status": "unavailable"}, status_code=503)
        if verdict is None or verdict.allowed:
            return None
        self._record(request, ip, session, verdict)
        response = problem_response(
            ErrorCode.RATE_LIMITED, {"retryAfterSeconds": verdict.retry_after}
        )
        response.headers["Retry-After"] = str(verdict.retry_after)
        return response

    @staticmethod
    def _hits(request: Request, ip: str, session: Session | None) -> list[Hit]:
        method = request.scope["method"]
        subject = limit_subject(ip)
        out = [
            Hit(rule, subject)
            for rule in rules.ROUTE_RULES.get((method, request.scope["path"]), ())
        ]
        if session is not None:
            out.append(Hit(rules.API_SESSION, str(session.session_id)))
            if (
                method in UNSAFE_METHODS
                and (method, request.scope["path"]) not in rules.WRITE_EXEMPT
            ):
                out.append(Hit(rules.WRITE_SESSION, str(session.session_id)))
                out.append(Hit(rules.WRITE_ACCOUNT, str(session.account_id)))
        return out

    @staticmethod
    def _record(request: Request, ip: str, session: Session | None, verdict: Verdict) -> None:
        """Un evento per regola e finestra (alla prima richiesta oltre il limite): niente flood."""
        crossing: list[Exceeded] = [e for e in verdict.exceeded if e.first_crossing]
        if not crossing:
            return
        event = SecurityEvent(
            event_type=EventType.RATE_LIMIT_EXCEEDED,
            outcome="denied",
            actor_kind="anonymous" if session is None else "account",
            actor_account_id=None if session is None else session.account_id,
            ip=None if ip == UNKNOWN else ip,
            correlation_id=request.scope.get("state", {}).get("correlation_id"),
            details_json='{"rule":"' + crossing[0].rule.name + '"}',
        )
        try:
            security_log(event)
        except Exception as error:  # il 429 resta valido anche se il registro non risponde
            _log.error("ratelimit.event_unrecorded", exception=type(error).__name__)
