"""Static, read-only SAMPLE data for the Phase 1 console skeleton.

Everything in this module is illustrative placeholder data. It exists only so
the UI has something to render before gateway integration is built. It is NOT
sourced from a live system and must never be presented as authoritative.

Boundary notes:
  - These structures are plain dicts defined locally. The console intentionally
    does NOT import basis-core models. In the production interaction model the
    console has no direct dependency on basis-core; it would obtain policy,
    decision, and audit data through basis-gateway APIs (a later phase).
  - The shapes loosely mirror basis-core's DecisionRequest / AuditEvent so the
    eventual swap to live gateway data is a small change, but the console never
    evaluates, produces, or reinterprets any of this — it only displays it.
"""

from __future__ import annotations

from typing import Any

# Marker surfaced in every view so operators are never misled into thinking the
# console is showing live system state in Phase 1.
SAMPLE_DATA_NOTICE = (
    "Sample data — illustrative only. Live policy, decision, and audit data will "
    "be sourced from basis-gateway in a later phase."
)


def sample_policies() -> list[dict[str, Any]]:
    """Illustrative loaded-policy summaries. Read-only placeholder data."""
    return [
        {
            "rule_name": "ot-operator-rbac",
            "rule_type": "RolePolicyRule",
            "description": "Operators may read telemetry; only admins may write setpoints.",
            "actions": [
                "read:sensor:telemetry",
                "write:hvac:setpoint",
            ],
            "roles": ["admin", "operator", "viewer"],
            "resource_scope": "hvac:*",
        },
        {
            "rule_name": "maintenance-window-guard",
            "rule_type": "ConditionPolicyRule",
            "description": "Write actions permitted only during an approved maintenance window.",
            "actions": ["write:hvac:setpoint", "execute:device:command"],
            "roles": ["admin"],
            "resource_scope": "site:plant-1",
        },
    ]


def sample_decisions() -> list[dict[str, Any]]:
    """Illustrative recent authorization outcomes. Read-only placeholder data."""
    return [
        {
            "request_id": "8f1d4c2a-0000-4a00-9c00-000000000001",
            "subject_id": "alice",
            "subject_roles": ["admin"],
            "action": "write:hvac:setpoint",
            "resource_id": "hvac:zone-a",
            "outcome": "allow",
            "reason": "matched rule ot-operator-rbac",
            "timestamp": "2026-06-11T14:02:11Z",
        },
        {
            "request_id": "8f1d4c2a-0000-4a00-9c00-000000000002",
            "subject_id": "bob",
            "subject_roles": ["viewer"],
            "action": "write:hvac:setpoint",
            "resource_id": "hvac:zone-a",
            "outcome": "deny",
            "reason": "no rule grants write:hvac:setpoint to role viewer",
            "timestamp": "2026-06-11T14:03:47Z",
        },
        {
            "request_id": "8f1d4c2a-0000-4a00-9c00-000000000003",
            "subject_id": "carol",
            "subject_roles": ["operator"],
            "action": "read:sensor:telemetry",
            "resource_id": "hvac:zone-b",
            "outcome": "allow",
            "reason": "matched rule ot-operator-rbac",
            "timestamp": "2026-06-11T14:05:09Z",
        },
    ]


def sample_audit_events() -> list[dict[str, Any]]:
    """Illustrative audit records. Read-only placeholder data.

    Loosely mirrors basis-core's AuditEvent so a later phase can render live
    gateway-sourced records with minimal template change. The console only
    displays these — it never produces, supplements, or alters audit records.
    """
    return [
        {
            "event_id": "a1000000-0000-4000-8000-000000000001",
            "event_type": "authorization_decision",
            "correlation_id": "c1000000-0000-4000-8000-000000000001",
            "subject_id": "alice",
            "subject_roles": ["admin"],
            "action": "write:hvac:setpoint",
            "resource_id": "hvac:zone-a",
            "outcome": "allow",
            "reason": "matched rule ot-operator-rbac",
            "evaluated_by": "basis-core",
            "policy_version": "2026.06.0",
            "timestamp": "2026-06-11T14:02:11Z",
        },
        {
            "event_id": "a1000000-0000-4000-8000-000000000002",
            "event_type": "authorization_decision",
            "correlation_id": "c1000000-0000-4000-8000-000000000002",
            "subject_id": "bob",
            "subject_roles": ["viewer"],
            "action": "write:hvac:setpoint",
            "resource_id": "hvac:zone-a",
            "outcome": "deny",
            "reason": "no rule grants write:hvac:setpoint to role viewer",
            "evaluated_by": "basis-core",
            "policy_version": "2026.06.0",
            "timestamp": "2026-06-11T14:03:47Z",
        },
    ]
