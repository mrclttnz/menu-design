"""Servizi di `identity` creati da `create_app` (nessuna richiesta di rete alla creazione)."""

from dataclasses import dataclass

from fastapi import Request

from menu.identity.oidc import OidcClient
from menu.platform import Settings


@dataclass
class IdentityServices:
    oidc: OidcClient

    @classmethod
    def build(cls, settings: Settings) -> IdentityServices:
        secret = settings.google_client_secret
        return cls(
            oidc=OidcClient(
                issuer=settings.oidc_issuer,
                client_id=settings.google_client_id,
                client_secret=None if secret is None else secret.get_secret_value(),
                redirect_uri=settings.google_redirect_uri,
            )
        )

    def close(self) -> None:
        self.oidc.close()


def services_of(request: Request) -> IdentityServices:
    services: IdentityServices = request.app.state.identity
    return services
