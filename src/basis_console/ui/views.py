"""Server-rendered HTML views for basis-console.

Pages (all read-only with respect to system state):
  GET  /                  — health / landing page showing the console is running
  GET  /policies          — policy viewer placeholder (sample data, read-only)
  GET  /simulate          — decision-simulator request builder (Phase 3)
  POST /simulate          — validate input + render a normalized request preview
  GET  /simulate/examples — sample simulator scenarios (read-only)
  GET  /audit             — Audit Explorer: decision events + gateway evidence (sample data)
  GET  /identity          — Identity & Access Explorer (sample data, read-only)
  GET  /gateway           — Gateway Diagnostics (live gateway health/readiness)

Rendering uses Jinja2 with templates and static assets served locally from this
package, so the console has no CDN or internet dependency and works air-gapped.

Boundary reminder: none of these views evaluate authorization, authenticate
users, or contact basis-core. The simulator POST always builds a preview of the
request shape (preview mode). As of Phase 4 it can also, when configured,
forward the request to basis-gateway's /v1/evaluate and display the gateway's
decision verbatim (gateway-evaluation mode) — the console never evaluates
locally, never sends a subject (identity comes from the gateway's Bearer token),
and never reinterprets the gateway's decision.
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from basis_console.audit import (
    AUDIT_BOUNDARY_NOTICE,
    AUDIT_SAMPLE_NOTICE,
    future_audit_integrations,
    sample_audit_events,
)
from basis_console.diagnostics import gather_gateway_diagnostics
from basis_console.gateway import GatewayClient, GatewayStatusReport
from basis_console.identity import (
    IDENTITY_BOUNDARY_NOTICE,
    IDENTITY_SAMPLE_NOTICE,
    future_identity_integrations,
    sample_access_preview,
    sample_identity_preview,
)
from basis_console.sample_data import (
    SAMPLE_DATA_NOTICE,
    sample_policies,
    sample_simulator_scenarios,
)
from basis_console.simulator import (
    FIELD_EXPLANATIONS,
    build_simulation,
)
from basis_console.vocabulary import ACTION_VERBS, RESOURCE_TYPES

# Note explaining the preview-mode boundary, surfaced on the simulator page.
SIMULATOR_NO_EVAL_NOTICE = (
    "Preview mode does not evaluate decisions. It validates your input and "
    "builds a preview of the request shape only. No allow/deny outcome is "
    "produced and no call is made to basis-gateway or basis-core."
)

# Note explaining the identity boundary for live gateway evaluation. The gateway
# derives the subject from its verified Bearer token and rejects caller-supplied
# subject fields, so the console must never present the form subject as identity.
SIMULATOR_IDENTITY_NOTICE = (
    "Live gateway evaluation sends only the action verb, resource type, resource "
    "ID, and context. The gateway derives the subject identity from its verified "
    "Bearer token — the subject fields above are preview-only and are not sent as "
    "identity. The gateway composes the canonical action and resource id; the "
    "console does not evaluate the request, it only displays the gateway's response."
)

# Empty form values used to render the simulator before any input is submitted.
# Operators choose a bare ``action_verb`` and a ``resource_type`` and supply a
# *local* ``resource_id``; the gateway composes the canonical action and resource
# id. ``composed_action`` / ``composed_resource_id`` are preview mirrors only.
_EMPTY_VALUES = {
    "subject_id": "",
    "subject_type": "",
    "action_verb": "",
    "resource_type": "",
    "resource_id": "",
    "context": "",
    "composed_action": "",
    "composed_resource_id": "",
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
    ("Identity", "/identity"),
    ("Gateway", "/gateway"),
]


def _base_context(request: Request, active: str) -> dict[str, object]:
    return {"request": request, "nav": _NAV, "active": active}


def _gateway_client(request: Request) -> GatewayClient:
    """Return the app's gateway client, or an unconfigured one as a fallback."""
    client: GatewayClient | None = getattr(request.app.state, "gateway_client", None)
    if client is None:
        client = GatewayClient(base_url=None)
    return client


def _gateway_status(request: Request) -> GatewayStatusReport:
    """Probe gateway connectivity for display. Never raises into the view."""
    return _gateway_client(request).check_status()


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
    ctx["identity_notice"] = SIMULATOR_IDENTITY_NOTICE
    ctx["action_verbs"] = ACTION_VERBS
    ctx["resource_types"] = RESOURCE_TYPES
    ctx["field_explanations"] = FIELD_EXPLANATIONS
    ctx["scenarios"] = sample_simulator_scenarios()
    # Gateway-evaluation availability (no network call — config inspection only).
    client = _gateway_client(request)
    ctx["gateway_configured"] = client.configured
    ctx["gateway_token_present"] = client.has_token
    ctx["gateway_eval_enabled"] = client.evaluation_enabled
    ctx["gateway_base_url"] = client.base_url
    # Defaults for the preview / evaluation sections; POST may override.
    ctx["gateway_body_json"] = None
    ctx["composition"] = None
    ctx["eval_requested"] = False
    ctx["eval_state"] = None
    ctx["evaluation"] = None
    ctx["evaluation_evidence"] = {}
    ctx["evaluation_json"] = None
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


@router.post("/simulate", response_class=HTMLResponse, summary="Build a preview or evaluate")
async def simulate_submit(request: Request) -> HTMLResponse:
    """Handle the two simulator modes.

    Preview mode (default): validate and sanitize input, render the normalized
    request shape as JSON. Never contacts the gateway, never evaluates.

    Gateway-evaluation mode (``mode=gateway``): after a valid preview, submit
    the request to ``basis-gateway /v1/evaluate`` and display the gateway's
    response verbatim. The console never evaluates locally, never sends a subject
    (identity comes from the gateway's Bearer token), and never reinterprets the
    decision. Available only when a base URL and Bearer token are configured.
    """
    body = await request.body()
    form = _parse_form_body(body)
    mode = (form.get("mode") or "preview").strip().lower()
    result = build_simulation(form)

    ctx = _simulate_context(request)
    ctx["values"] = result.values
    ctx["errors"] = result.errors
    ctx["field_errors"] = result.field_errors
    ctx["preview_json"] = (
        json.dumps(result.preview, indent=2, sort_keys=False) if result.ok else None
    )
    # The exact normalized body the console submits, and a preview of what the
    # gateway will compose from it. Both are display aids; the gateway owns
    # composition.
    ctx["gateway_body_json"] = (
        json.dumps(result.gateway_body, indent=2, sort_keys=False)
        if result.ok and result.gateway_body
        else None
    )
    ctx["composition"] = result.composition if result.ok else None

    if mode == "gateway":
        ctx["eval_requested"] = True
        client = _gateway_client(request)
        if not result.ok or result.gateway_body is None:
            # Do not call the gateway with invalid input; the form errors show.
            ctx["eval_state"] = "invalid_input"
        elif not client.configured:
            ctx["eval_state"] = "not_configured"
        elif not client.has_token:
            ctx["eval_state"] = "token_missing"
        else:
            gw = result.gateway_body
            resource_type = str(gw["resource_type"]) if gw.get("resource_type") else None
            resource_id = str(gw["resource_id"]) if gw.get("resource_id") else None
            context = gw.get("context") or {}
            evaluation = client.evaluate(
                action=str(gw["action"]),
                resource_type=resource_type,
                resource_id=resource_id,
                context=context,
            )
            ctx["eval_state"] = "result"
            ctx["evaluation"] = evaluation
            ctx["evaluation_evidence"] = evaluation.composition_evidence
            ctx["evaluation_json"] = (
                json.dumps(evaluation.response_json, indent=2) if evaluation.response_json else None
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


@router.get(
    "/audit",
    response_class=HTMLResponse,
    summary="Audit Explorer (audit evidence, read-only, sample data)",
)
def audit(request: Request) -> HTMLResponse:
    """Render the Audit Explorer.

    Displays recent authorization-decision events with structured detail —
    subject, action, resource, policy, gateway composition evidence, and
    correlation IDs — plus a clearly-labelled list of future live audit sources.

    This is operational visibility, not an audit store. The console displays audit
    *evidence* produced by ``basis-core`` and ``basis-gateway``; it does not
    produce, store, or own canonical audit records, define audit semantics, or
    call ``basis-core``. ``basis-gateway`` does not yet expose an audit-history
    endpoint, so the events are sample/demo data (labelled as such); live
    evaluation evidence is visible on the Simulate page. Sensitive fields are
    redacted defensively before display.
    """
    ctx = _base_context(request, active="/audit")
    ctx["notice"] = AUDIT_SAMPLE_NOTICE
    ctx["boundary_notice"] = AUDIT_BOUNDARY_NOTICE
    ctx["events"] = sample_audit_events()
    ctx["future_integrations"] = future_audit_integrations()
    ctx["gateway_eval_enabled"] = _gateway_client(request).evaluation_enabled
    return templates.TemplateResponse(request, "audit.html", ctx)


@router.get(
    "/identity",
    response_class=HTMLResponse,
    summary="Identity & Access Explorer (read-only, sample data)",
)
def identity(request: Request) -> HTMLResponse:
    """Render the Identity & Access Explorer.

    This page is render/inspect/explain only. It displays a SAMPLE normalized
    subject, an unverified token/claims preview, the claim→subject mapping the
    gateway would perform, a link into the existing simulator (which never sends
    the subject as identity), and a clearly-labelled list of future
    ``basis-identity`` integrations.

    The console does not authenticate, authorize, verify tokens, evaluate policy,
    or call ``basis-core`` here. Nothing on this page submits to the gateway; the
    data is sample/demo data, labelled as such.
    """
    preview = sample_identity_preview()
    ctx = _base_context(request, active="/identity")
    ctx["notice"] = IDENTITY_SAMPLE_NOTICE
    ctx["boundary_notice"] = IDENTITY_BOUNDARY_NOTICE
    ctx["identity"] = preview
    # Pretty-printed claim set for safe nested rendering. Jinja autoescaping makes
    # the string inert; the console performs no token verification.
    ctx["claims_json"] = json.dumps(preview.claims.raw, indent=2, sort_keys=False)
    ctx["access"] = sample_access_preview()
    ctx["future_integrations"] = future_identity_integrations()
    return templates.TemplateResponse(request, "identity.html", ctx)


@router.get(
    "/gateway",
    response_class=HTMLResponse,
    summary="Gateway Diagnostics (operational visibility, read-only)",
)
def gateway_diagnostics(request: Request) -> HTMLResponse:
    """Render the Gateway Diagnostics view.

    Probes the gateway's real ``/health`` and ``/ready`` endpoints (through the
    gateway client) and displays the results: connection summary, health,
    readiness with dynamically-rendered components, evaluation/policy capability,
    correlation IDs, and the raw redacted responses.

    This is observability only. The console does not configure the gateway,
    authenticate users, evaluate policy, call ``basis-core``, or bypass the
    gateway. Sensitive headers/fields are redacted defensively before display.
    Live data is shown when the gateway is reachable; clear offline / unconfigured
    states are shown otherwise.
    """
    client = _gateway_client(request)
    ctx = _base_context(request, active="/gateway")
    ctx["diagnostics"] = gather_gateway_diagnostics(client)
    return templates.TemplateResponse(request, "gateway.html", ctx)
