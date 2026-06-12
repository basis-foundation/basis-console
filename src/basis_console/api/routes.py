"""Operational (machine-facing) routes for basis-console.

Endpoints:
  GET /health  — liveness probe (always 200 while the process is up)
  GET /ready   — readiness probe (200 when initialized, 503 otherwise)

These are JSON endpoints intended for load balancers, reverse proxies, and
orchestration health checks. The human-facing HTML pages live in
``basis_console.ui.views``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from basis_console.readiness import get_readiness_state

router = APIRouter()

_SERVICE_NAME = "basis-console"


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    service: str
    components: dict[str, bool] | None = None
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
def ready() -> JSONResponse:
    """Return 200 when the console is initialized, 503 otherwise."""
    state = get_readiness_state()
    if state.is_ready:
        body = ReadyResponse(
            status="ready",
            service=_SERVICE_NAME,
            components=state.components,
        )
        return JSONResponse(status_code=200, content=body.model_dump(exclude_none=True))

    body = ReadyResponse(
        status="not_ready",
        service=_SERVICE_NAME,
        components=state.components,
        reason=state.reason or "console not initialized",
    )
    return JSONResponse(status_code=503, content=body.model_dump(exclude_none=True))
