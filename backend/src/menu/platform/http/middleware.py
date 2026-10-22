"""Middleware ASGI puri (SR-023, SR-046, SR-060; THR-102, THR-110).

`EnvelopeMiddleware` (esterno) avvolge ogni risposta, anche quelle generate dagli altri
middleware o dall'errore imprevisto: header di sicurezza, `no-store`, ID di correlazione,
log della richiesta. `BodyGuardMiddleware` (interno) applica `Content-Type`, limite del
corpo e profondità JSON prima che la richiesta arrivi al router.
"""

import re
import time
import traceback
import uuid

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from menu.common import ErrorCode, ValidationCode
from menu.platform.http.problem import field_error, problem_response

MAX_BODY_BYTES = 64 * 1024
MAX_JSON_DEPTH = 10
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'; require-trusted-types-for 'script'; trusted-types 'none'"
    ),
}

# Stringhe JSON (saltate) oppure parentesi strutturali; forma "unrolled", senza backtracking.
_JSON_TOKENS = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"|[\[\]{}]', re.DOTALL)
_log = structlog.get_logger("menu.http")


def is_json_content_type(value: str | None) -> bool:
    return value is not None and value.split(";")[0].strip().lower() == "application/json"


def is_json_like_content_type(value: str | None) -> bool:
    """Come FastAPI: senza `Content-Type`, `application/json` e `application/*+json` sono JSON."""
    if not value or not value.split(";")[0].strip():
        return True
    media = value.split(";")[0].strip().lower()
    return media == "application/json" or (
        media.startswith("application/") and media.endswith("+json")
    )


def json_depth_exceeds(body: bytes, limit: int) -> bool:
    """True se i contenitori JSON annidati superano `limit` (senza interpretare il JSON)."""
    depth = 0
    for token in _JSON_TOKENS.finditer(body):
        char = token.group()
        if char in (b"{", b"["):
            depth += 1
            if depth > limit:
                return True
        elif char in (b"}", b"]"):
            depth -= 1
    return False


def json_charset_is_utf8(value: str | None) -> bool:
    """True se `Content-Type` non dichiara un charset diverso da utf-8."""
    for param in (value or "").split(";")[1:]:
        key, _, val = param.partition("=")
        if key.strip().lower() == "charset" and val.strip().strip('"').lower() != "utf-8":
            return False
    return True


def json_body_rejected(body: bytes, limit: int) -> bool:
    """True se il corpo JSON va rifiutato: contiene NUL (UTF-16/32) o è troppo profondo.

    Il JSON UTF-8 valido non contiene mai byte NUL; UTF-16/32 sì, sempre.
    """
    return b"\x00" in body or json_depth_exceeds(body, limit)


def describe_exception(error: BaseException) -> str:
    """Solo i tipi della catena di cause e i punti dello stack: mai i messaggi (CWE-532).

    I messaggi di psycopg e Pydantic riportano valori (`DETAIL`, `input_value`).
    """
    names: list[str] = []
    current: BaseException | None = error
    while current is not None and len(names) < 6:
        names.append(type(current).__name__)
        nested = getattr(current, "orig", None)
        if isinstance(nested, BaseException):
            names.append(type(nested).__name__)
        current = current.__cause__ or current.__context__
    frames = [
        f"{frame.filename.rsplit('/', 1)[-1]}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_tb(error.__traceback__)
    ]
    return " <- ".join(names) + " @ " + " > ".join(frames[-12:])


def too_deep_response() -> Response:
    errors = [field_error("", ValidationCode.INVALID_VALUE)]
    return problem_response(ErrorCode.VALIDATION, errors=errors)


class BodyGuardMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        content_type = headers.get("content-type")
        is_json = is_json_content_type(content_type)
        json_like = is_json_like_content_type(content_type)
        if scope["method"] in UNSAFE_METHODS and not is_json:
            await problem_response(ErrorCode.UNSUPPORTED_MEDIA_TYPE)(scope, receive, send)
            return
        if json_like and not json_charset_is_utf8(content_type):
            await problem_response(ErrorCode.UNSUPPORTED_MEDIA_TYPE)(scope, receive, send)
            return
        too_large = problem_response(ErrorCode.PAYLOAD_TOO_LARGE, {"maxBytes": MAX_BODY_BYTES})
        # Fail closed (CR-SL00a-007): il corpo si legge sempre, con o senza `Content-Length`
        # (HTTP/2 non lo richiede), e non oltre il limite.
        chunks: list[bytes] = []
        total = 0
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                return  # client disconnesso
            chunk: bytes = message.get("body", b"")
            total += len(chunk)
            chunks.append(chunk)
            if total > MAX_BODY_BYTES:
                # Un JSON troppo profondo è un 422 anche se supera pure la dimensione.
                too_deep = json_like and json_body_rejected(b"".join(chunks), MAX_JSON_DEPTH)
                await (too_deep_response() if too_deep else too_large)(scope, receive, send)
                return
            more = message.get("more_body", False)
        body = b"".join(chunks)

        if json_like and json_body_rejected(body, MAX_JSON_DEPTH):
            await too_deep_response()(scope, receive, send)
            return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class EnvelopeMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        correlation_id = uuid.uuid4()
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
                headers.setdefault("Cache-Control", "no-store")
            await send(message)

        with structlog.contextvars.bound_contextvars(correlation_id=str(correlation_id)):
            try:
                await self.app(scope, receive, send_wrapper)
            except Exception as error:
                _log.error(
                    "http.unhandled_exception",
                    exception=describe_exception(error),
                )
                if response_started:
                    raise
                await problem_response(ErrorCode.INTERNAL)(scope, receive, send_wrapper)
            _log.info(
                "http.request",
                method=scope["method"],
                path=scope["path"],
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
