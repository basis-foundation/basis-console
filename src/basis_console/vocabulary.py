"""Provisional, console-local action-vocabulary bridge (Phase 6).

WHY THIS EXISTS
───────────────
``basis-core`` requires every ``DecisionRequest.action`` to match the
``{verb}:{domain}[:{object}]`` naming convention — concretely, two or more
colon-separated lowercase segments (see ``basis_core.decisions.models`` and
``basis-architecture/docs/architecture/action-vocabulary.md``). A *bare* verb
such as ``read`` is rejected by the gateway with HTTP 400 ``validation_failed``.

Through Phase 5 the console's simulator produced bare verbs, so gateway-backed
evaluation of a simulator-generated request always failed validation. Phase 6
removes that mismatch by helping operators *compose* a gateway-compatible action
string (e.g. ``read:ahu``) from a chosen verb and domain.

THIS MODULE IS NOT THE VOCABULARY AUTHORITY
───────────────────────────────────────────
The lists below are a deliberately small, provisional *mirror* — just enough to
let the simulator build a structurally valid action string and explain the
contract to operators. They are NOT canonical and the console must never be
treated as the source of truth for the action vocabulary.

The authoritative long-term home for the action vocabulary (and for the request,
response, audit, and event schemas) should be a dedicated ``basis-schemas``
package. Until that exists, the governing references are:

  - ``basis-architecture/docs/architecture/action-vocabulary.md`` — governance,
    naming structure, the controlled verb set, reserved prefixes.
  - ``basis-core`` — the enforced ``DecisionRequest.action`` validation regex.

When ``basis-schemas`` (or an equivalent shared contract package) lands, this
module should be deleted and the simulator should consume the shared definitions
instead of these local copies. See README and ``docs/architecture.md``
("Future basis-schemas Extraction").

SCOPE NOTE
──────────
The verb set here mirrors the five normalized verbs ``basis-adapters`` emits and
that earlier console phases already accepted (``read`` / ``write`` / ``execute``
/ ``browse`` / ``subscribe``). The architecture governance document currently
lists a partially different controlled set (it uses ``command`` / ``configure``
rather than ``execute`` / ``browse``). That divergence is a real open question
for the ecosystem; it is recorded in ``docs/architecture.md`` and is explicitly
*not* resolved here, because resolving it is a vocabulary-authority decision the
console does not own.
"""

from __future__ import annotations

import re

# ── Provisional verb set (console-local mirror; NOT authoritative) ──────────────
# Mirrors the normalized verbs basis-adapters emits and that the console accepted
# in Phases 3–5. Do NOT add new verbs here: introducing a verb is a vocabulary
# decision that belongs to basis-architecture / future basis-schemas, not to the
# console.
ACTION_VERBS: tuple[str, ...] = ("read", "write", "execute", "browse", "subscribe")

# ── Provisional starter domains (console-local mirror; NOT authoritative) ───────
# A conservative, illustrative set grounded in the project's sample data. This is
# intentionally NOT an exhaustive OT ontology. Real domains are governed by
# basis-architecture and would be owned by basis-schemas; the console only offers
# a few sensible starters so an operator can compose a valid action string.
ACTION_DOMAINS: tuple[str, ...] = (
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
# gateway/kernel enforces; we mirror it here only to fail fast and keep the
# composed string honest — basis-core remains the enforcing authority.
_ACTION_RE = re.compile(r"^[a-z][a-z0-9_-]*(:[a-z][a-z0-9_-]*)+$")


def is_supported_verb(verb: str) -> bool:
    """True when ``verb`` is in the provisional console-local verb mirror."""
    return verb in ACTION_VERBS


def is_supported_domain(domain: str) -> bool:
    """True when ``domain`` is in the provisional console-local domain mirror."""
    return domain in ACTION_DOMAINS


def matches_action_format(action: str) -> bool:
    """True when ``action`` matches basis-core's ``{verb}:{domain}[:{object}]`` shape.

    This mirrors the kernel's structural rule so the console can reject a
    malformed composition before it would ever reach the gateway. It does not
    re-implement authorization or vocabulary governance — only the string shape.
    """
    return bool(_ACTION_RE.match(action))


def compose_action(verb: str, domain: str) -> str:
    """Compose a gateway-compatible action string from a verb and a domain.

    Produces the two-segment ``{verb}:{domain}`` form (e.g. ``read:ahu``), which
    satisfies basis-core's "two or more colon-separated segments" rule. Inputs
    are assumed already validated/stripped by the caller; composition itself
    attaches no authorization meaning.
    """
    return f"{verb}:{domain}"
