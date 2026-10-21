"""GET /healthz: rotta pubblica, senza DB in SL-00a (il controllo del DB arriva con SL-00b)."""

from fastapi import APIRouter
from pydantic import BaseModel

from menu.platform import AuthzRoute


class Health(BaseModel):
    status: str


router = APIRouter(route_class=AuthzRoute)


@router.get(
    "/healthz",
    operation_id="platform.health.read",
    openapi_extra={"x-authz": {"scope": "public"}},
)
async def read_health() -> Health:
    return Health(status="ok")
