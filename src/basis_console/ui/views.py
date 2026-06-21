"""Server-rendered HTML views for basis-console.

Pages (all read-only with respect to system state):
  GET  /                  — health / landing page showing the console is running
  GET  /policies          — policy viewer placeholder (sample data, read-only)
  GET  /simulate          — decision-simulator request builder (Phase 3)
  POST /simulate          — validate input + render a normalized request preview
  GET  /simulate/examples — sample simulator scenarios (read-only)
  GET  /audit             — audit viewer placeholder (sample data, read-only)

Rendering uses Jinja2 with templates and static assets served locally from this
package, so the console has no CDN or internet dependency and works air-gapped.

Boundary reminder: none of these views evaluate authorization, authenticate
users, or contact basis-core. As of Phase 3 the simulator POST builds a preview
of the request shape only — it performs no evaluation and makes no call to
basis-gateway. Live evaluation through the gateway is a later phase.
"""

from __future__ import annotations

import json
import urllib.parse
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
    sample_simulator_scenarios,
)
from basis_console.simulator import (
    ALLOWED_ACTIONS,
    FIELD_EXPLANATIONS,
    build_simulation,
)

# Note explaining the Phase 3 boundary, surfaced on the simulator page.
SIMULATOR_NO_EVAL_NOTICE = (
    "This simulator does not evaluate decisions. It validates your input and "
    "builds a preview of the request shape only. No allow/deny outcome is "
    "produced and no call is made to basis-gateway or basis-core."
)

# Empty form values used to render the simulator before any input is submitted.
_EMPTY_VALUES = {
    "subject_id": "",
    "subject_type": "",
    "action": "",
    "resource_id": "",
    "resource_type": "",
    "context": "",
}

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


def _simulate_context(request: Request) -> dict[str, object]:
    """Shared template context for the simulator page."""
    ctx = _base_context(request, active="/simulate")
    ctx["notice"] = SAMPLE_DATA_NOTICE
    ctx["no_eval_notice"] = SIMULATOR_NO_EVAL_NOTICE
    ctx["allowed_actions"] = ALLOWED_ACTIONS
    ctx["field_explanations"] = FIELD_EXPLANATIONS
    ctx["scenarios"] = sample_simulator_scenarios()
    return ctx


def _parse_form_body(body: bytes) -> dict[str, str]:
    """Parse an application/x-www-form-urlencoded body without python-multipart.

    Phase 3 keeps the console dependency-light and air-gap friendly: rather than
    add a form-parsing dependency, the simulator POST body (a small urlencoded
    form) is decoded with the standard library.
    """
    parsed = urllib.parse.parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


@router.get("/simulate", response_class=HTMLResponse, summary="Decision simulator request builder")
def simulate(request: Request, example: str | None = None) -> HTMLResponse:
    """Render the simulator form.

    No evaluation happens here. An optional ``?example=<slug>`` preloads one of
    the sample scenarios into the form so an operator can inspect or submit it.
    """
    ctx = _simulate_context(request)
    values = dict(_EMPTY_VALUES)
    if example:
        for scenario in sample_simulator_scenarios():
            if scenario["slug"] == example:
                for key in _EMPTY_VALUES:
                    values[key] = str(scenario.get(key, ""))
                ctx["loaded_example"] = scenario["title"]
                break
    ctx["values"] = values
    ctx["preview_json"] = None
    ctx["errors"] = []
    ctx["field_errors"] = {}
    return templates.TemplateResponse(request, "simulate.html", ctx)


@router.post("/simulate", response_class=HTMLResponse, summary="Build a normalized request preview")
async def simulate_submit(request: Request) -> HTMLResponse:
    """Validate submitted fields and render a normalized request preview.

    This intentionally does NOT contact the gateway and does NOT evaluate the
    request. It only sanitizes input and renders the request shape as formatted
    JSON, or user-friendly errors when input is invalid.
    """
    body = await request.body()
    form = _parse_form_body(body)
    result = build_simulation(form)

    ctx = _simulate_context(request)
    ctx["values"] = result.values
    ctx["errors"] = result.errors
    ctx["field_errors"] = result.field_errors
    ctx["preview_json"] = (
        json.dumps(result.preview, indent=2, sort_keys=False) if result.ok else None
    )
    return templates.TemplateResponse(request, "simulate.html", ctx)


@router.get(
    "/simulate/examples",
    response_class=HTMLResponse,
    summary="Sample simulator scenarios (read-only)",
)
def simulate_examples(request: Request) -> HTMLResponse:
    ctx = _base_context(request, active="/simulate")
    ctx["notice"] = SAMPLE_DATA_NOTICE
    ctx["no_eval_notice"] = SIMULATOR_NO_EVAL_NOTICE
    ctx["scenarios"] = sample_simulator_scenarios()
    return templates.TemplateResponse(request, "examples.html", ctx)


@router.get("/audit", response_class=HTMLResponse, summary="Audit viewer (read-only)")
def audit(request: Request) -> HTMLResponse:
    ctx = _base_context(request, active="/audit")
    ctx["notice"] = SAMPLE_DATA_NOTICE
    ctx["decisions"] = sample_decisions()
    ctx["events"] = sample_audit_events()
    return templates.TemplateResponse(request, "audit.html", ctx)
