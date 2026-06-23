"""Provisional, console-local action-vocabulary bridge (Phases 6–7).

WHY THIS EXISTS
───────────────
``basis-core`` requires every ``DecisionRequest.action`` to match the
``{verb}:{domain}[:{object}]`` naming convention — concretely, two or more
colon-separated lowercase segments (see ``basis_core.decisions.models`` and
``basis-architecture/docs/architecture/action-vocabulary.md``). A *bare* verb
such as ``read`` is rejected by the kernel.

Composition is owned by ``basis-gateway`` (the gateway composition boundary).
The gateway accepts an *adapter/console-normalized* request — a bare ``action``
verb plus a ``resource_type`` — and composes the canonical ``{verb}:{domain}``
action **and** the typed ``{type}:{id}`` resource identifier before handing the
request to the kernel. The console therefore submits the normalized inputs and
does **not** pre-compose the canonical strings itself.

This module helps the console (a) offer a small, valid verb/resource-type
vocabulary and (b) *preview* what the gateway will compose, so an operator can
see the canonical action/resource the gateway will derive. The compose helpers
below are **preview mirrors** of gateway behavior, not the authoritative
composition step.

THIS MODULE IS NOT THE VOCABULARY AUTHORITY
───────────────────────────────────────────
The lists below are a deliberately small, provisional *mirror* — just enough to
let an operator build a structurally valid request and to explain the contract.
They are NOT canonical and the console must never be treated as the source of
truth for the action vocabulary or the resource taxonomy.

The authoritative long-term home for the action vocabulary (and for the request,
response, audit, and event schemas) should be a dedicated ``basis-schemas``
package. Until that exists, the governing references are:

  - ``basis-architecture/docs/architecture/action-vocabulary.md`` — governance,
    naming structure, the controlled verb set, reserved prefixes.
  - ``basis-core`` — the enforced ``DecisionRequest.action`` validation regex.
  - ``basis-gateway`` — the runtime action/resource composition boundary.

When ``basis-schemas`` (or an equivalent shared contract package) lands, this
module should be deleted and the simulator should consume the shared definitions
instead of these local copies. See README and ``docs/architecture.md``
("Future basis-schemas Extraction").

SCOPE NOTE — ``resource_type`` IS DUAL-PURPOSE
──────────────────────────────────────────────
In the gateway-normalized request, ``resource_type`` is a single field the
gateway uses to compose *both* the action domain (``{verb}:{resource_type}``)
and the resource identifier prefix (``{resource_type}:{local_id}``). The console
mirrors that: it carries one ``resource_type`` field rather than a separate
"action domain" and a merely-descriptive "resource type" that could drift apart.
Whether the action domain and the resource type *should* be the same concept is
a real open question owned by ``basis-architecture`` / future ``basis-schemas``;
the console does not resolve it here.

The verb set here mirrors the five normalized verbs ``basis-adapters`` emits and
that earlier console phases accepted (``read`` / ``write`` / ``execute`` /
``browse`` / ``subscribe``). The architecture governance document currently
lists a partially different controlled set (it uses ``command`` / ``configure``
rather than ``execute`` / ``browse``); that divergence is recorded in
``docs/architecture.md`` and is explicitly *not* resolved here.
"""

from __future__ import annotations

import re

# ── Provisional verb set (console-local mirror; NOT authoritative) ──────────────
# Mirrors the normalized verbs basis-adapters emits and that the console accepted
# in Phases 3–6. Do NOT add new verbs here: introducing a verb is a vocabulary
# decision that belongs to basis-architecture / future basis-schemas, not to the
# console.
ACTION_VERBS: tuple[str, ...] = ("read", "write", "execute", "browse", "subscribe")

# ── Provisional starter resource types / action domains (NOT authoritative) ─────
# A conservative, illustrative set grounded in the project's sample data. This is
# intentionally NOT an exhaustive OT ontology. Real types/domains are governed by
# basis-architecture and would be owned by basis-schemas; the console only offers
# a few sensible starters so an operator can build a valid normalized request.
#
# This single list serves the dual-purpose ``resource_type`` field — it is both
# the action domain the gateway composes into ``{verb}:{domain}`` and the
# resource-identifier prefix the gateway composes into ``{type}:{local_id}``.
RESOURCE_TYPES: tuple[str, ...] = (
    "ahu",
    "setpoint",
    "telemetry",
    "device",
    "schedule",
    "command",
)

# Structural contract mirrored from basis-core (``basis_core.decisions.models``):
# two or more colon-separated lowercase segments, each starting with a letter and
# continuing with letters, digits, hyphens, or underscores. This is the SHAPE the
# gateway/kernel enforces; we mirror it here only to fail fast and keep a
# previewed composition honest — basis-core remains the enforcing authority.
_ACTION_RE = re.compile(r"^[a-z][a-z0-9_-]*(:[a-z][a-z0-9_-]*)+$")

# A single lowercase segment (verb or resource type), mirroring the gateway's
# per-segment rule. Used to keep previewed composition output structurally valid.
_SEGMENT_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


def is_supported_verb(verb: str) -> bool:
    """True when ``verb`` is in the provisional console-local verb mirror."""
    return verb in ACTION_VERBS


def is_supported_resource_type(resource_type: str) -> bool:
    """True when ``resource_type`` is in the provisional console-local mirror."""
    return resource_type in RESOURCE_TYPES


def matches_action_format(action: str) -> bool:
    """True when ``action`` matches basis-core's ``{verb}:{domain}[:{object}]`` shape.

    This mirrors the kernel's structural rule so the console can recognise a
    fully-typed (kernel-compatible) action. It does not re-implement
    authorization or vocabulary governance — only the string shape.
    """
    return bool(_ACTION_RE.match(action))


def is_typed_identifier(value: str) -> bool:
    """True when ``value`` is already a typed/composite identifier (contains ``:``).

    The gateway treats a ``resource_id`` containing a colon as already typed
    (``{type}:{qualifier}``) and an action containing a colon as already
    composite. The console uses the same simple rule to decide which normalized
    request shape it is building and to reject ambiguous combinations.
    """
    return ":" in value


def compose_action(verb: str, resource_type: str) -> str:
    """Preview the canonical action the gateway will compose from verb + type.

    Produces the two-segment ``{verb}:{resource_type}`` form (e.g. ``read:ahu``),
    which satisfies basis-core's "two or more colon-separated segments" rule.

    This is a **preview mirror** of the gateway's composition, shown to the
    operator for legibility. The console does not submit this composed string to
    the gateway — it submits the bare verb and ``resource_type`` and lets the
    gateway compose. Inputs are assumed already validated/stripped by the caller.
    """
    return f"{verb}:{resource_type}"


def compose_resource_id(resource_type: str, local_resource_id: str) -> str:
    """Preview the canonical resource id the gateway will compose.

    Produces the ``{resource_type}:{local_resource_id}`` form (e.g.
    ``ahu:rooftop-1``) the gateway derives from a normalized request that carries
    a ``resource_type`` and a *local* (untyped) ``resource_id``.

    This is a **preview mirror** of the gateway's composition, not the
    authoritative step: the console submits the normalized inputs and the gateway
    owns composition. Inputs are assumed already validated/stripped.
    """
    return f"{resource_type}:{local_resource_id}"
