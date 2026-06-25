"""Audit Explorer presentation models and SAMPLE data (Phase 10).

WHAT THIS MODULE IS
───────────────────
This module provides the *presentation-oriented* data the Audit Explorer
(``/audit``) renders: recent authorization-decision events, their structured
detail (subject, action, resource, policy, gateway evidence, correlation), and a
clearly-labelled list of future live audit sources.

The structures are named ``*Preview`` deliberately: they describe what the
console *displays*, not what any component *stores*. The console renders and
explains audit *evidence* produced by ``basis-core`` and ``basis-gateway``; it is
**not** an audit store and does **not** own audit semantics.

WHAT THIS MODULE IS NOT
───────────────────────
The console does not authenticate, authorize, evaluate, store canonical audit
records, define an audit schema, or call ``basis-core``. Accordingly this module:

  - holds only **sample/demo** events (clearly labelled), because
    ``basis-gateway`` does not yet expose an audit-history endpoint and the
    console must not invent one;
  - never fabricates correlation IDs for live data (sample events carry obviously
    sample correlation IDs);
  - redacts sensitive fields defensively before any raw payload is rendered
    (see :mod:`basis_console.gateway.redaction`);
  - uses the real ``basis_gateway.*`` composition-evidence keys so the evidence
    panel reflects what the gateway actually records — but composes nothing
    itself.

FUTURE INTEGRATION
──────────────────
Live audit history will eventually be sourced from a ``basis-gateway`` audit
endpoint, governed by a ``basis-core`` / ``basis-schemas`` audit contract, and
enriched by ``basis-identity`` lifecycle events (and optionally forwarded to an
external SIEM/log pipeline). This module's sample builders should then be
replaced with data sourced through the gateway; the presentation models can stay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from basis_console.gateway.redaction import redact_json

# Notice surfaced on the Audit Explorer so an operator is never misled into
# thinking the console is showing live, canonical audit history.
AUDIT_SAMPLE_NOTICE = (
    "Sample audit data — illustrative only. basis-gateway does not yet expose an "
    "audit-history endpoint, so these decision events are demo data with clearly "
    "sample correlation IDs. The console displays audit evidence; it does not "
    "produce, store, or own canonical audit records."
)

# Short statement of the audit boundary, shown near the top of the page.
AUDIT_BOUNDARY_NOTICE = (
    "The console renders and explains audit evidence produced by basis-core and "
    "basis-gateway. It does not authenticate, authorize, evaluate, store canonical "
    "audit records, define audit semantics, or replace SIEM/log infrastructure."
)


@dataclass(frozen=True)
class AuditEvidencePreview:
    """Gateway-owned composition evidence attached to a decision (display only).

    ``entries`` are ``(key, value)`` pairs using the real reserved
    ``basis_gateway.*`` keys the gateway records when it composes a canonical
    action / resource id. The console only *reads* these for display; it never
    sets them (the gateway rejects caller-supplied ``basis_gateway.*`` keys).
    """

    entries: tuple[tuple[str, str], ...] = ()

    @property
    def present(self) -> bool:
        return bool(self.entries)


@dataclass(frozen=True)
class AuditDecisionPreview:
    """The decision portion of an audit event. Relayed, never computed."""

    outcome: str  # "allow" | "deny"
    reason: str
    policy_name: str | None = None
    policy_version: str | None = None


@dataclass(frozen=True)
class AuditEventPreview:
    """One audit-style authorization event, shaped for display.

    ``source`` records where the event came from — ``"sample"`` for the demo data
    in this module. A future live integration would set ``"gateway"`` (or similar)
    so the UI can keep distinguishing live from sample data. ``raw_json`` is the
    full event payload, already **redacted** and pretty-printed for safe display.
    """

    event_id: str
    timestamp: str
    decision: AuditDecisionPreview
    subject_id: str
    subject_type: str
    subject_roles: tuple[str, ...]
    action: str
    resource_id: str
    resource_type: str
    correlation_id: str
    source: str
    evidence: AuditEvidencePreview
    raw_json: str

    @property
    def outcome(self) -> str:
        return self.decision.outcome

    @property
    def is_sample(self) -> bool:
        return self.source == "sample"


@dataclass(frozen=True)
class FutureAuditIntegration:
    """A future source that will populate live audit history. Not implemented here."""

    name: str
    description: str


def _event(
    *,
    event_id: str,
    timestamp: str,
    outcome: str,
    reason: str,
    policy_name: str | None,
    policy_version: str | None,
    subject_id: str,
    subject_type: str,
    subject_roles: tuple[str, ...],
    action: str,
    resource_id: str,
    resource_type: str,
    correlation_id: str,
    evidence: dict[str, str],
    extra_raw: dict[str, Any] | None = None,
) -> AuditEventPreview:
    """Assemble one sample event, redacting its raw payload defensively."""
    raw: dict[str, Any] = {
        "event_id": event_id,
        "event_type": "authorization_decision",
        "timestamp": timestamp,
        "outcome": outcome,
        "reason": reason,
        "subject_id": subject_id,
        "subject_type": subject_type,
        "subject_roles": list(subject_roles),
        "action": action,
        "resource_id": resource_id,
        "policy_name": policy_name,
        "policy_version": policy_version,
        "correlation_id": correlation_id,
        "evaluated_by": "basis-core",
        "composed_by": "basis-gateway",
        # Composition evidence is recorded by the gateway in the evaluation
        # context under reserved basis_gateway.* keys.
        "context": {"site": "bldg-a", **evidence},
    }
    if extra_raw:
        raw.update(extra_raw)

    # Defensive redaction: an audit payload should never carry credentials, but if
    # one ever does, it must not reach the rendered page.
    redacted = redact_json(raw)
    raw_json = json.dumps(redacted, indent=2, sort_keys=False)

    return AuditEventPreview(
        event_id=event_id,
        timestamp=timestamp,
        decision=AuditDecisionPreview(
            outcome=outcome,
            reason=reason,
            policy_name=policy_name,
            policy_version=policy_version,
        ),
        subject_id=subject_id,
        subject_type=subject_type,
        subject_roles=subject_roles,
        action=action,
        resource_id=resource_id,
        resource_type=resource_type,
        correlation_id=correlation_id,
        source="sample",
        evidence=AuditEvidencePreview(entries=tuple(evidence.items())),
        raw_json=raw_json,
    )


def sample_audit_events() -> tuple[AuditEventPreview, ...]:
    """Illustrative authorization-decision events for the Audit Explorer.

    SAMPLE data only — never sourced from a live system and never authoritative.
    Correlation IDs are obviously sample values. The events reflect real BASIS
    concepts and the gateway's real composition-evidence keys:

      - ALLOW ``read:ahu`` on ``ahu:rooftop-1`` — a *composed* request, so the
        full ``basis_gateway.*`` action- and resource-composition evidence is
        shown (one shared ``resource_type``, as the gateway requires).
      - DENY ``write:setpoint`` on ``ahu:rooftop-1`` — a *direct* (already typed)
        request, so no composition evidence was recorded.
      - DENY ``execute:command`` on ``controller:boiler-1`` — also a direct
        request; demonstrates the no-evidence state for a denied action.
    """
    return (
        _event(
            event_id="evt-sample-0001",
            timestamp="2026-06-24T14:02:11Z",
            outcome="allow",
            reason="matched rule ot-operator-rbac (operators may read AHU telemetry)",
            policy_name="ot-operator-rbac",
            policy_version="2026.06.0",
            subject_id="operator-jane",
            subject_type="user",
            subject_roles=("operator", "viewer"),
            action="read:ahu",
            resource_id="ahu:rooftop-1",
            resource_type="ahu",
            correlation_id="sample-corr-0001-rooftop-read",
            # Real gateway evidence keys for a fully-composed (bare verb + shared
            # resource_type) request.
            evidence={
                "basis_gateway.action_composed": "true",
                "basis_gateway.original_action": "read",
                "basis_gateway.composed_action": "read:ahu",
                "basis_gateway.resource_type": "ahu",
                "basis_gateway.resource_composed": "true",
                "basis_gateway.original_resource_id": "rooftop-1",
                "basis_gateway.composed_resource_id": "ahu:rooftop-1",
            },
            # Defensive redaction demonstration: this credential-shaped field must
            # never appear in the rendered raw payload.
            extra_raw={"authorization": "Bearer SAMPLE.do-not-use.value"},
        ),
        _event(
            event_id="evt-sample-0002",
            timestamp="2026-06-24T14:03:47Z",
            outcome="deny",
            reason="no rule grants write:setpoint to role technician outside a maintenance window",
            policy_name="maintenance-window-guard",
            policy_version="2026.06.0",
            subject_id="tech-mike",
            subject_type="user",
            subject_roles=("technician",),
            action="write:setpoint",
            resource_id="ahu:rooftop-1",
            resource_type="",  # direct request — operator submitted typed values
            correlation_id="sample-corr-0002-setpoint-deny",
            evidence={},  # no composition occurred (already canonical)
        ),
        _event(
            event_id="evt-sample-0003",
            timestamp="2026-06-24T14:05:09Z",
            outcome="deny",
            reason="no rule grants execute:command on controller:boiler-1 to service vendor-acme",
            policy_name="ot-operator-rbac",
            policy_version="2026.06.0",
            subject_id="vendor-acme",
            subject_type="service",
            subject_roles=("vendor",),
            action="execute:command",
            resource_id="controller:boiler-1",
            resource_type="",  # direct request — already typed
            correlation_id="sample-corr-0003-boiler-deny",
            evidence={},
        ),
    )


def future_audit_integrations() -> tuple[FutureAuditIntegration, ...]:
    """Future sources that will populate live audit history. Not implemented here."""
    return (
        FutureAuditIntegration(
            "basis-gateway audit history endpoint",
            "A gateway-exposed query API for recent decisions and audit evidence.",
        ),
        FutureAuditIntegration(
            "basis-core audit event schema",
            "The canonical audit event shape produced by the kernel.",
        ),
        FutureAuditIntegration(
            "basis-schemas audit contracts",
            "Shared cross-component audit/event contracts the console will consume.",
        ),
        FutureAuditIntegration(
            "basis-identity lifecycle events",
            "Identity lifecycle events (provisioning, role changes) for context.",
        ),
        FutureAuditIntegration(
            "External SIEM / log pipeline",
            "Forwarding to existing log/SIEM infrastructure — the console never replaces it.",
        ),
    )


# Re-exported so the view and tests can pass redaction-aware raw payloads through
# a single, shared implementation.
__all__ = [
    "AUDIT_BOUNDARY_NOTICE",
    "AUDIT_SAMPLE_NOTICE",
    "AuditDecisionPreview",
    "AuditEventPreview",
    "AuditEvidencePreview",
    "FutureAuditIntegration",
    "future_audit_integrations",
    "sample_audit_events",
]
