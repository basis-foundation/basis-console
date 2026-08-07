"""Server-rendered HTML views for basis-console.

Pages (all read-only with respect to system state):
  GET  /                  — health / landing page showing the console is running
  GET  /workspace         — Operator Workspace / Overview: orientation across all areas
  GET  /policies          — policy viewer placeholder (sample data, read-only)
  GET  /simulate          — decision-simulator request builder (Phase 3)
  POST /simulate          — validate input + render a normalized request preview
  GET  /simulate/examples — sample simulator scenarios (read-only)
  GET  /audit             — Audit Explorer: decision events + gateway evidence (sample data)
  GET  /identity          — Identity & Access Explorer (sample data, read-only)
  GET  /resources         — Resource Explorer: resources, identifiers, request shapes (sample data)
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
from basis_console.diagnostics import (
    REDACTION_ASSURANCE_NOTICE,
    connection_state_guide,
    gather_gateway_diagnostics,
)
from basis_console.gateway import GatewayClient, GatewayStatusReport
from basis_console.identity import (
    IDENTITY_BOUNDARY_NOTICE,
    IDENTITY_SAMPLE_NOTICE,
    future_identity_integrations,
    sample_access_preview,
    sample_identity_preview,
)
from basis_console.operation_aware_presentation import build_operation_aware_presentation
from basis_console.resources import (
    IDENTIFIER_EXPLANATION_NOTICE,
    RESOURCE_BOUNDARY_NOTICE,
    RESOURCE_SAMPLE_NOTICE,
    future_resource_integrations,
    sample_resources,
)
from basis_console.sample_data import (
    SAMPLE_DATA_NOTICE,
    sample_policies,
    sample_simulator_scenarios,
)
from basis_console.simulator import (
    FIELD_EXPLANATIONS,
    EvaluationType,
    build_operation_aware_simulation,
    build_simulation,
    parse_evaluation_type,
)
from basis_console.vocabulary import ACTION_VERBS, RESOURCE_TYPES
from basis_console.workspace import (
    WORKSPACE_INTRO,
    WORKSPACE_SUMMARY_NOTICE,
    capability_cards,
    data_maturity,
    operational_flow,
    operational_questions,
    operator_path,
)

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

# Note explaining the operation-aware preview boundary (PR 4). Distinct from
# SIMULATOR_NO_EVAL_NOTICE because the operation-aware preview shows a
# strictly narrower, differently-shaped request (Section 4 of the
# operation-aware console integration plan) and must never be confused with
# the legacy preview's subject/context-inclusive shape.
OPERATION_AWARE_NO_EVAL_NOTICE = (
    "Operation-aware preview does not evaluate a decision. It validates your "
    "input and shows the exact request that would be submitted to "
    "basis-gateway's /v1/evaluate/operation-aware endpoint. No allow, deny, or "
    "not_applicable outcome is produced, and no call is made to basis-gateway "
    "or basis-core."
)

# Note explaining why operation-aware evaluation has no context control at
# all, unlike the legacy path's context textarea (Section 4.5 of the
# integration plan).
OPERATION_AWARE_CONTEXT_NOTICE = (
    "Operation-aware evaluation submits only action, resource type, and "
    "resource ID — no subject and no context. Unlike legacy evaluation, this "
    "endpoint has no field for caller-supplied context: operation-aware "
    "context is owned by trusted operation producers (adapters, identity), "
    "not by an ordinary console session, so there is no context control here."
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
    ("Workspace", "/workspace"),
    ("Policies", "/policies"),
    ("Simulate", "/simulate"),
    ("Audit", "/audit"),
    ("Identity", "/identity"),
    ("Resources", "/resources"),
    ("Gateway", "/gateway"),
]


def _console_mode(request: Request) -> str:
    """Return the configured presentation mode, defaulting to operator.

    Reads ``app.state.config`` set during startup. Falls back to ``operator`` if
    config is unavailable (e.g. a failed startup) so pages still render cleanly
    in the default operator mode rather than erroring.
    """
    config = getattr(request.app.state, "config", None)
    mode = getattr(config, "basis_console_mode", "operator")
    return mode if mode in ("operator", "training") else "operator"


def _base_context(request: Request, active: str) -> dict[str, object]:
    mode = _console_mode(request)
    return {
        "request": request,
        "nav": _NAV,
        "active": active,
        # Presentation mode, available to every template (and base.html) so
        # training-only panels render without duplicating logic per view.
        "console_mode": mode,
        "is_training_mode": mode == "training",
    }


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


@router.get(
    "/workspace",
    response_class=HTMLResponse,
    summary="Operator Workspace / Overview (orientation, read-only)",
)
def workspace(request: Request) -> HTMLResponse:
    """Render the Operator Workspace / Overview.

    An orientation landing page that brings the existing console areas — Identity
    & Access, Resources, Decision Simulator, Gateway Diagnostics, Audit Explorer —
    together and organizes them around operational questions (Who? What? Can
    they? Is the boundary healthy? What happened?).

    This page adds no backend authority. It links to the existing pages rather
    than re-implementing them, and it distinguishes live/configurable data from
    sample/explanatory data and future integrations. The only live datum is the
    gateway connection/readiness state, reused from the existing Gateway
    Diagnostics aggregator — no new diagnostics logic and no basis-core call.
    """
    ctx = _base_context(request, active="/workspace")
    ctx["intro"] = WORKSPACE_INTRO
    ctx["summary_notice"] = WORKSPACE_SUMMARY_NOTICE
    ctx["flow"] = operational_flow()
    ctx["cards"] = capability_cards()
    ctx["questions"] = operational_questions()
    ctx["maturity"] = data_maturity()
    ctx["path_steps"] = operator_path()
    # Reuse the existing diagnostics aggregator for an honest readiness snapshot.
    # No duplicated logic; the page links to /gateway for the full view.
    ctx["diagnostics"] = gather_gateway_diagnostics(_gateway_client(request))
    return templates.TemplateResponse(request, "workspace.html", ctx)


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
    ctx["operation_aware_no_eval_notice"] = OPERATION_AWARE_NO_EVAL_NOTICE
    ctx["operation_aware_context_notice"] = OPERATION_AWARE_CONTEXT_NOTICE
    ctx["action_verbs"] = ACTION_VERBS
    ctx["resource_types"] = RESOURCE_TYPES
    ctx["field_explanations"] = FIELD_EXPLANATIONS
    ctx["scenarios"] = sample_simulator_scenarios()
    # Gateway-evaluation availability (no network call — config inspection only).
    # Shared identically by the legacy and operation-aware paths: both use the
    # same GatewayClient and the same configured/has_token gates.
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
    # Evaluation-type selection (PR 4) — independent of `mode` above. Defaults
    # to legacy so every old link/bookmark/test that predates this field
    # renders exactly as before.
    ctx["evaluation_type"] = EvaluationType.LEGACY.value
    ctx["oa_request_summary"] = None
    ctx["oa_preview_only"] = False
    ctx["oa_presentation"] = None
    ctx["oa_diagnostics_json"] = None
    ctx["oa_diagnostics_headers_json"] = None
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


def _empty_values_echo(form: dict[str, str]) -> dict[str, str]:
    """Echo back whatever of ``_EMPTY_VALUES``'s keys were submitted, stripped.

    Used only for the two "fail before either builder runs" cases (an invalid
    ``evaluation_type``) so the form can still repopulate with whatever the
    caller sent, matching the "preserve submitted values after a validation
    error" requirement even though neither `build_simulation` nor
    `build_operation_aware_simulation` ran.
    """
    return {key: (form.get(key) or "").strip() for key in _EMPTY_VALUES}


@router.post("/simulate", response_class=HTMLResponse, summary="Build a preview or evaluate")
async def simulate_submit(request: Request) -> HTMLResponse:
    """Handle the simulator's two independent axes: submission mode and evaluation contract.

    Submission behavior (unchanged): ``mode=preview`` (default) validates and
    sanitizes input and renders a request-shape preview only, never contacting
    the gateway. ``mode=gateway`` additionally submits the request live and
    displays the response verbatim.

    Evaluation contract (new, PR 4): ``evaluation_type=legacy`` (default,
    absent-compatible) preserves every existing legacy behavior below
    unchanged, submitting to ``basis-gateway``'s ``/v1/evaluate`` via
    ``GatewayClient.evaluate()``. ``evaluation_type=operation_aware`` builds a
    typed ``OperationAwareEvaluationRequest`` (no subject, no context — see
    ``simulator.build_operation_aware_simulation``) and, in gateway mode,
    submits it via ``GatewayClient.evaluate_operation_aware()`` exactly once,
    then renders the shared, mode-independent
    ``build_operation_aware_presentation()`` result. In preview mode it
    displays the exact request that would be submitted without ever calling
    the gateway or fabricating a decision. Operator and Training modes run
    this exact same code path — nothing here branches on console mode.

    An invalid ``evaluation_type`` value fails validation safely: no gateway
    call, no local evaluation, whatever was submitted is echoed back.
    """
    body = await request.body()
    form = _parse_form_body(body)
    mode = (form.get("mode") or "preview").strip().lower()
    evaluation_type = parse_evaluation_type(form.get("evaluation_type"))

    ctx = _simulate_context(request)

    if evaluation_type is None:
        ctx["evaluation_type"] = (form.get("evaluation_type") or "").strip()
        message = (
            "Invalid evaluation type. Must be one of: "
            f"{EvaluationType.LEGACY.value}, {EvaluationType.OPERATION_AWARE.value}."
        )
        ctx["errors"] = [message]
        ctx["field_errors"] = {"evaluation_type": message}
        ctx["values"] = _empty_values_echo(form)
        return templates.TemplateResponse(request, "simulate.html", ctx)

    ctx["evaluation_type"] = evaluation_type.value

    if evaluation_type is EvaluationType.OPERATION_AWARE:
        return _render_operation_aware_submission(request, ctx, form, mode)

    # ---- Legacy path (evaluation_type == LEGACY) — unchanged from Phase 4/6 ----
    result = build_simulation(form)

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


def _render_operation_aware_submission(
    request: Request, ctx: dict[str, object], form: dict[str, str], mode: str
) -> HTMLResponse:
    """Handle ``evaluation_type=operation_aware`` for both submission modes.

    Identical code path in Operator and Training modes — this function reads
    no console-mode value and takes no mode-shaped parameter. Preview mode
    never calls the gateway and never fabricates a decision; gateway mode
    calls ``GatewayClient.evaluate_operation_aware()`` exactly once and passes
    its typed result straight into ``build_operation_aware_presentation()``
    with no intermediate raw-JSON parsing.
    """
    oa_result = build_operation_aware_simulation(form)

    # Echo the full legacy-shaped values dict too (subject_id/subject_type/
    # context are not part of the operation-aware request, but the shared
    # template still renders their inputs — see "Design Decisions" in the PR
    # report — so submitted values there are preserved across a validation
    # error exactly like every other field).
    ctx["values"] = {
        "subject_id": (form.get("subject_id") or "").strip(),
        "subject_type": (form.get("subject_type") or "").strip(),
        "action_verb": oa_result.values.get("action_verb", ""),
        "resource_type": oa_result.values.get("resource_type", ""),
        "resource_id": oa_result.values.get("resource_id", ""),
        "context": (form.get("context") or "").strip(),
        "composed_action": "",
        "composed_resource_id": "",
    }
    ctx["errors"] = oa_result.errors
    ctx["field_errors"] = oa_result.field_errors

    if not oa_result.ok or oa_result.request is None:
        return templates.TemplateResponse(request, "simulate.html", ctx)

    oa_request = oa_result.request
    ctx["oa_request_summary"] = {
        "action": oa_request.action,
        "resource_type": oa_request.resource_type,
        "resource_id": oa_request.resource_id,
    }

    if mode == "gateway":
        client = _gateway_client(request)
        oa_gateway_result = client.evaluate_operation_aware(oa_request)
        presentation = build_operation_aware_presentation(oa_request, oa_gateway_result)
        ctx["oa_presentation"] = presentation
        diagnostics = presentation.transport.diagnostics
        if diagnostics is not None:
            ctx["oa_diagnostics_json"] = (
                json.dumps(diagnostics.response_body, indent=2, sort_keys=False)
                if diagnostics.response_body
                else None
            )
            ctx["oa_diagnostics_headers_json"] = (
                json.dumps(diagnostics.headers, indent=2, sort_keys=False)
                if diagnostics.headers
                else None
            )
    else:
        # Preview: request-shape preview only. No gateway call, no local
        # evaluation, no fabricated outcome/disposition/evidence.
        ctx["oa_preview_only"] = True

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
    ctx["state_guide"] = connection_state_guide()
    ctx["redaction_assurance"] = REDACTION_ASSURANCE_NOTICE
    return templates.TemplateResponse(request, "gateway.html", ctx)


@router.get(
    "/resources",
    response_class=HTMLResponse,
    summary="Resource Explorer (operational visibility, read-only, sample data)",
)
def resources(request: Request) -> HTMLResponse:
    """Render the Resource Explorer.

    Makes visible what BASIS reasons about — resources, actions, resource
    identifiers, adapter sources, and gateway request shapes — so operators can
    see how OT/platform resources become normalized authorization targets. It
    displays a sample catalog of normalized resources across every current adapter
    family, each with local and canonical identifiers, supported actions, an
    example gateway request shape, and a redacted raw payload.

    This is operational visibility, not inventory. The console does not discover
    devices, connect to OT protocols, call adapters directly, mutate resources,
    edit policies, call ``basis-core``, or own a resource inventory.
    ``basis-adapters`` does not yet expose a live resource-inventory service and
    ``basis-gateway`` does not yet expose a resource-catalog endpoint, so the
    resources are sample/demo data (labelled as such). Sensitive fields are
    redacted defensively before display.
    """
    ctx = _base_context(request, active="/resources")
    ctx["notice"] = RESOURCE_SAMPLE_NOTICE
    ctx["boundary_notice"] = RESOURCE_BOUNDARY_NOTICE
    ctx["identifier_notice"] = IDENTIFIER_EXPLANATION_NOTICE
    ctx["resources"] = sample_resources()
    ctx["future_integrations"] = future_resource_integrations()
    return templates.TemplateResponse(request, "resources.html", ctx)
