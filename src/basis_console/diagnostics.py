"""Gateway Diagnostics presentation logic (Phase 9).

This module turns the raw probe results from ``basis_console.gateway`` into a
presentation-friendly aggregate the ``/gateway`` view renders. It makes the
gateway's *operational* state — health, readiness, readiness components,
evaluation/policy capability, correlation IDs — understandable to an operator.

Boundary:
  - The console **observes** the gateway; it does not configure, authenticate,
    evaluate, or bypass it. This module performs no authorization and imports no
    ``basis-core``.
  - It probes only the gateway's real endpoints (``/health``, ``/ready``) through
    the gateway client. It invents no endpoints and fabricates no data: when the
    gateway does not expose a datum (e.g. ``policy_version`` is not on ``/health``
    or ``/ready``), the UI says so rather than inventing it.
  - Sensitive values are redacted upstream in the client before they reach here
    (see ``basis_console.gateway.redaction``).

Future identity diagnostics (OIDC/JWKS/JWT inspection) will integrate through the
future ``basis-identity`` service, not through console-owned protocol logic — see
the Identity & Access Explorer (``/identity``) and ``docs/architecture.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from basis_console.gateway import GatewayClient, GatewayProbeResult

# Readiness component names that describe evaluation/policy capability. Used only
# to surface a focused capability view IN ADDITION to rendering every component
# dynamically — the console never assumes this is the complete or only set.
_POLICY_CAPABILITY_COMPONENTS: tuple[str, ...] = (
    "evaluator_initialized",
    "policy_loaded",
    "oidc_configured",
    "jwks_available",
)

# Message shown when a policy datum is not exposed by the gateway's operational
# endpoints (the gateway returns policy_version only on /v1/evaluate responses).
POLICY_NOT_EXPOSED_NOTICE = (
    "The gateway does not expose policy name/version on /health or /ready. These "
    "appear only on evaluation responses (seen on the Simulate page when a "
    "decision is returned). The console does not invent a policy endpoint."
)


@dataclass(frozen=True)
class ReadinessComponent:
    """One readiness component reported by the gateway's ``/ready`` response.

    ``name`` is rendered as-is so arbitrary, evolving component keys are shown
    safely without the console hard-coding a fixed set. ``reason`` is populated
    only for a not-ready component on a 503 readiness response.
    """

    name: str
    ready: bool
    reason: str | None = None


@dataclass(frozen=True)
class PolicyCapability:
    """Evaluation/policy capability derived from readiness components.

    Each known component is True / False when reported, or None when the gateway
    did not report it. ``policy_version`` / ``policy_name`` are always None here
    because the gateway does not expose them on ``/health`` or ``/ready``;
    ``note`` explains where they do appear.
    """

    components: tuple[ReadinessComponent, ...]
    policy_version: str | None
    policy_name: str | None
    exposed: bool
    note: str


@dataclass(frozen=True)
class CorrelationEntry:
    """A labelled correlation ID captured from a probe response, if present."""

    label: str
    value: str | None
    source: str


@dataclass(frozen=True)
class GatewayDiagnostics:
    """Everything the ``/gateway`` view needs, assembled from live probes."""

    configured: bool
    base_url: str | None
    checked_at: str
    connection_state: str
    connection_summary: str
    health: GatewayProbeResult
    ready: GatewayProbeResult
    components: tuple[ReadinessComponent, ...]
    overall_ready: bool | None
    policy: PolicyCapability
    correlation_ids: tuple[CorrelationEntry, ...]
    health_json: str | None = None
    ready_json: str | None = None
    health_headers: dict[str, str] = field(default_factory=dict)
    ready_headers: dict[str, str] = field(default_factory=dict)


def _pretty(value: Any) -> str | None:
    """Pretty-print a (already-redacted) JSON value, or None when absent."""
    if value is None:
        return None
    return json.dumps(value, indent=2, sort_keys=False)


def _extract_components(ready: GatewayProbeResult) -> tuple[ReadinessComponent, ...]:
    """Build readiness components dynamically from the ``/ready`` body.

    Renders *whatever* component keys the gateway returns (sorted for stable
    display), so the view does not depend on a fixed component set. Reasons from a
    503 ``reasons`` map are attached to their component when present.
    """
    body = ready.response_json or {}
    raw_components = body.get("components")
    if not isinstance(raw_components, dict):
        return ()
    reasons = body.get("reasons")
    reason_map = reasons if isinstance(reasons, dict) else {}

    components: list[ReadinessComponent] = []
    for name in sorted(raw_components, key=str):
        value = raw_components[name]
        reason = reason_map.get(name)
        components.append(
            ReadinessComponent(
                name=str(name),
                ready=bool(value),
                reason=str(reason) if isinstance(reason, str) else None,
            )
        )
    return tuple(components)


def _build_policy_capability(components: tuple[ReadinessComponent, ...]) -> PolicyCapability:
    """Derive an evaluation/policy capability view from readiness components."""
    by_name = {component.name: component for component in components}
    capability = tuple(by_name[name] for name in _POLICY_CAPABILITY_COMPONENTS if name in by_name)
    return PolicyCapability(
        components=capability,
        policy_version=None,
        policy_name=None,
        exposed=bool(capability),
        note=POLICY_NOT_EXPOSED_NOTICE,
    )


def _connection_state(
    configured: bool,
    health: GatewayProbeResult,
    ready: GatewayProbeResult,
) -> tuple[str, str]:
    """Classify overall connection state and a human-readable summary."""
    if not configured:
        return (
            "not_configured",
            "No gateway base URL is configured. Set GATEWAY_BASE_URL to point the "
            "console at a basis-gateway instance.",
        )
    if not health.reached:
        return (
            "unreachable",
            "The gateway is configured but could not be contacted. The console "
            "surfaces no live state and never falls back to local authorization.",
        )
    if not health.ok:
        return (
            "error",
            f"The gateway answered /health with HTTP {health.http_status}, which is "
            "unexpected for a healthy service.",
        )
    if ready.reached and ready.ok:
        return ("ready", "The gateway is reachable and reports ready.")
    if ready.reached:
        return (
            "reachable",
            f"The gateway is reachable (/health ok) but /ready returned HTTP "
            f"{ready.http_status} — it is up but not reporting ready.",
        )
    return (
        "reachable",
        "The gateway answered /health but the /ready probe could not be read.",
    )


def gather_gateway_diagnostics(client: GatewayClient) -> GatewayDiagnostics:
    """Probe the gateway and assemble a presentation-friendly diagnostics bundle.

    Pure orchestration over the gateway client: it performs the (already
    redacted, never-raising) ``/health`` and ``/ready`` probes and derives display
    state. It makes no authorization decision and contacts nothing but the
    gateway's operational endpoints.
    """
    configured = client.configured
    health = client.get_health()
    ready = client.get_ready()

    components = _extract_components(ready)
    policy = _build_policy_capability(components)
    state, summary = _connection_state(configured, health, ready)

    overall_ready: bool | None
    if not configured or not ready.reached:
        overall_ready = None
    else:
        body = ready.response_json or {}
        status_value = body.get("status")
        overall_ready = ready.ok and status_value == "ready"

    correlation_ids = (
        CorrelationEntry(
            label="Last /health correlation ID",
            value=health.correlation_id,
            source="X-Correlation-ID response header",
        ),
        CorrelationEntry(
            label="Last /ready correlation ID",
            value=ready.correlation_id,
            source="X-Correlation-ID response header",
        ),
    )

    return GatewayDiagnostics(
        configured=configured,
        base_url=client.base_url,
        checked_at=health.checked_at or ready.checked_at,
        connection_state=state,
        connection_summary=summary,
        health=health,
        ready=ready,
        components=components,
        overall_ready=overall_ready,
        policy=policy,
        correlation_ids=correlation_ids,
        health_json=_pretty(health.response_json),
        ready_json=_pretty(ready.response_json),
        health_headers=health.headers,
        ready_headers=ready.headers,
    )
