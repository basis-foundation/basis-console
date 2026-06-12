"""Operational (machine-facing) routes for basis-console.

Endpoints:
  GET /health  — liveness probe (always 200 while the process is up)
  GET /ready   — readiness probe (200 when initialized, 503 otherwise)

These are JSON endpoints intended for load balancers, reverse proxies, and
orchestration health checks. The human-facing HTML pages live in
``basis_console.ui.views``.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from basis_console.gateway import GatewayClient
from basis_console.readiness import get_readiness_state

router = APIRouter()

_SERVICE_NAME = "basis-console"


def _gateway_client(request: Request) -> GatewayClient:
    """Return the app's gateway client, falling back to a not-configured one."""
    client: GatewayClient | None = getattr(request.app.state, "gateway_client", None)
    if client is None:
        return GatewayClient(base_url=None)
    return client


class HealthResponse(BaseModel):
    status: str
    service: str


class GatewayInfo(BaseModel):
    status: str
    base_url: str | None = None
    reachable: bool = False
    ready: bool = False


class ReadyResponse(BaseModel):
    status: str
    service: str
    components: dict[str, bool] | None = None
    gateway: GatewayInfo | None = None
    reason: str | None = None


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    """Return 200 while the console process is running."""
    return HealthResponse(status="ok", service=_SERVICE_NAME)


@router.get(
    "/ready",
    summary="Readiness probe",
    response_model=ReadyResponse,
    responses={503: {"model": ReadyResponse}},
)
def ready(request: Request) -> JSONResponse:
    """Return console readiness, including gateway integration state.

    The console's own readiness depends only on its configuration loading. In
    Phase 2 an unreachable or unconfigured gateway does NOT make the console
    unready — gateway connectivity is reported additively so operators can see
    it without the console flapping when the gateway is down.
    """
    state = get_readiness_state()
    report = _gateway_client(request).check_status()

    components = dict(state.components)
    components["gateway_configured"] = report.configured
    components["gateway_reachable"] = report.reachable

    gateway = GatewayInfo(
        status=report.status.value,
        base_url=report.base_url,
        reachable=report.reachable,
        ready=report.ready,
    )

    if state.is_ready:
        body = ReadyResponse(
            status="ready",
            service=_SERVICE_NAME,
            components=components,
            gateway=gateway,
        )
        return JSONResponse(status_code=200, content=body.model_dump(exclude_none=True))

    body = ReadyResponse(
        status="not_ready",
        service=_SERVICE_NAME,
        components=components,
        gateway=gateway,
        reason=state.reason or "console not initialized",
    )
    return JSONResponse(status_code=503, content=body.model_dump(exclude_none=True))
