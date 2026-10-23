"""Modulo platform (strato 1): config, logging, middleware HTTP, problem+json, `AuthzRoute`."""

from menu.platform.config import GOOGLE_ISSUER, Settings
from menu.platform.http.client_ip import client_ip
from menu.platform.http.if_match import expected_version
from menu.platform.logging import configure_logging
from menu.platform.routing import AuthzRoute, assert_all_routes_declare_authz

__all__ = [
    "GOOGLE_ISSUER",
    "AuthzRoute",
    "Settings",
    "assert_all_routes_declare_authz",
    "client_ip",
    "configure_logging",
    "expected_version",
]
