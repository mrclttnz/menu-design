"""IP del client per gli eventi di sicurezza e per `session.ip_prefix` (THR-012, SR-051)."""

from fastapi import Request

from menu.platform import client_ip
from menu.platform.http.client_ip import UNKNOWN


def request_ip(request: Request) -> str | None:
    """IP deciso da `client_ip` (mai la voce più a sinistra di XFF); `None` se non determinabile."""
    ip = client_ip(request)
    return None if ip == UNKNOWN else ip
