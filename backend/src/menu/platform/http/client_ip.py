"""IP del client (THR-012, SR-059): unica funzione, mai la voce più a sinistra.

Con `TRUSTED_PROXY_HOPS = n` si usa la n-esima voce da destra di `X-Forwarded-For`, cioè
quella aggiunta dal proxy fidato più vicino al servizio. Con 0 si usa l'indirizzo del peer.
"""

import ipaddress

from fastapi import Request

UNKNOWN = "unknown"


def _valid(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def client_ip_from(forwarded_for: list[str], peer: str | None, hops: int) -> str:
    if hops > 0:
        entries = [e for header in forwarded_for for e in header.split(",")]
        if len(entries) >= hops:
            picked = _valid(entries[-hops])
            if picked is not None:
                return picked
    return (_valid(peer) if peer else None) or UNKNOWN


def limit_subject(ip: str) -> str:
    """Chiave per i limiti per IP (SEC-SL03b-001): IPv6 ridotto al /64, IPv4-mappato a IPv4."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def client_ip(request: Request) -> str:
    hops: int = request.app.state.settings.trusted_proxy_hops
    peer = request.client.host if request.client else None
    return client_ip_from(request.headers.getlist("x-forwarded-for"), peer, hops)
