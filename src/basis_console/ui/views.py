"""Server-rendered HTML views for basis-console.

Phase 1 pages (all read-only):
  GET /          — health / landing page showing the console is running
  GET /policies  — policy viewer placeholder (sample data, read-only)
  GET /simulate  — decision simulator placeholder (form, not wired to gateway)
  GET /audit     — audit viewer placeholder (sample data, read-only)

Rendering uses Jinja2 with templates and static assets served locally from this
package, so the console has no CDN or internet dependency and works air-gapped.

Boundary reminder: none of these views evaluate authorization, authenticate
users, or contact basis-core. The simulator form does not submit anywhere in
Phase 1 — it only establishes the UI pattern.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from basis_console.gateway import GatewayClient, GatewayStatusReport
from basis_console.sample_data import (
    SAMPLE_DATA_NOTICE,
    sample_audit_events,
    sample_decisions,
    sample_policies,
)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()

# Navigation shared by every page (label, path).
_NAV = [
    ("Home", "/"),
    ("Policies", "/policies"),
    ("Simulate", "/simulate"),
    ("Audit", "/audit"),
]


def _base_context(request: Request, active: str) -> dict[str, object]:
    return {"request": request, "nav": _NAV, "active": active}


def _gateway_status(request: Request) -> GatewayStatusReport:
    """Probe gateway connectivity for display. Never raises into the view."""
    client: GatewayClient | None = getattr(request.app.state, "gateway_client", None)
    if client is None:
        client = GatewayClient(base_url=None)
    return client.check_status()


@router.get("/", response_class=HTMLResponse, summary="Console home / status page")
def index(request: Request) -> HTMLResponse:
    ctx = _base_context(request, active="/")
    ctx["gateway"] = _gateway_status(request)
    return templates.TemplateResponse(request, "index.html", ctx)


@router.get("/policies", response_class=HTMLResponse, summary="Policy viewer (read-only)")
def policies(request: Request) -> HTMLResponse:
    ctx = _base_context(request, active="/policies")
    ctx["notice"] = SAMPLE_DATA_NOTICE
    ctx["policies"] = sample_policies()
    return templates.TemplateResponse(request, "policies.html", ctx)


@router.get("/simulate", response_class=HTMLResponse, summary="Decision simulator (placeholder)")
def simulate(request: Request) -> HTMLResponse:
    ctx = _base_context(request, active="/simulate")
    ctx["notice"] = SAMPLE_DATA_NOTICE
    return templates.TemplateResponse(request, "simulate.html", ctx)


@router.get("/audit", response_class=HTMLResponse, summary="Audit viewer (read-only)")
def audit(request: Request) -> HTMLResponse:
    ctx = _base_context(request, active="/audit")
    ctx["notice"] = SAMPLE_DATA_NOTICE
    ctx["decisions"] = sample_decisions()
    ctx["events"] = sample_audit_events()
    return templates.TemplateResponse(request, "audit.html", ctx)
