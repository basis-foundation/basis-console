"""Decision-simulator logic for basis-console (Phase 3).

This module turns operator-supplied form fields into a *normalized request
preview* — a plain data structure that shows the shape of the authorization
request that a later phase would submit to ``basis-gateway``.

Boundary (Phase 3):
  - Nothing here evaluates authorization. There is no policy logic, no role
    check, no condition evaluation, and no notion of an allow/deny outcome.
    Authorization belongs to ``basis-core``, reached only through
    ``basis-gateway``.
  - Nothing here contacts the gateway. Building a preview is a pure, local,
    in-memory transformation of validated input.
  - The console does not import ``basis-core`` or any kernel model. The action
    string is *composed* from a verb and a domain drawn from a provisional,
    console-local vocabulary mirror (``basis_console.vocabulary``); referencing
    that vocabulary is not the same as inventing or owning authorization
    semantics. See that module and ``docs/architecture.md`` for why the console
    is not the vocabulary authority.

Action shape (Phase 6):
  Earlier phases produced a *bare* verb (``read``) as the action, which the
  gateway rejects because ``basis-core`` requires the
  ``{verb}:{domain}[:{object}]`` form (two or more colon-separated lowercase
  segments). The simulator now composes a gateway-compatible action string
  (e.g. ``read:ahu``) from a chosen verb and domain so normal simulator output
  validates against the kernel contract.

The preview deliberately uses ``basis-core`` ``DecisionRequest`` field names
(``subject_id``, ``action``, ``resource_id``, ``context``) so that the eventual
swap to a real gateway-submitted request is a small, legible change. Fields the
gateway/kernel populate on the enforcement path (``request_id``, ``timestamp``,
``subject_roles``, normalized identity) are intentionally NOT fabricated here —
the console previews only what an operator supplies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from basis_console.vocabulary import (
    ACTION_DOMAINS,
    ACTION_VERBS,
    compose_action,
    is_supported_domain,
    is_supported_verb,
    matches_action_format,
)

# Defensive length bound so a preview cannot be ballooned with pathological input.
MAX_FIELD_LEN = 128
MAX_CONTEXT_ENTRIES = 16

# A "simple safe string" for identifiers: starts with a letter or digit, then
# letters, digits, and a conservative set of separators seen in normalized BASIS
# identifiers (colon, underscore, hyphen, dot, slash). No spaces, no quotes, no
# angle brackets — this keeps preview values inert when rendered.
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")

# Types and context keys are conservative slugs.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

# Context values may contain spaces but no markup-significant characters.
_CTX_VALUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.:/-]*$")

# Human-readable explanation of each request field, surfaced in the UI so the
# simulator is educational rather than a bare form.
FIELD_EXPLANATIONS: tuple[tuple[str, str], ...] = (
    (
        "subject_id",
        "Stable identifier of the requester (e.g. a user or service account). "
        "Maps to DecisionRequest.subject_id in basis-core.",
    ),
    (
        "subject_type",
        "What kind of subject this is (e.g. user, service, device). Recorded as "
        "a subject attribute; the gateway resolves real identity and roles.",
    ),
    (
        "action_verb",
        "The operation the subject wants to perform. One of: "
        + ", ".join(ACTION_VERBS)
        + ". Combined with the domain to form the action string.",
    ),
    (
        "action_domain",
        "The functional domain or object the action targets (e.g. "
        + ", ".join(ACTION_DOMAINS)
        + "). Combined with the verb to form the action string.",
    ),
    (
        "action",
        "The composed action string sent to the gateway, in basis-core's "
        "{verb}:{domain} form (e.g. read:ahu). The console builds this from the "
        "verb and domain; it is not the vocabulary authority.",
    ),
    (
        "resource_id",
        "Normalized identifier of the target resource (e.g. hvac:zone-a). Maps "
        "to DecisionRequest.resource_id.",
    ),
    (
        "resource_type",
        "What kind of resource this is (e.g. sensor, actuator, device). Helps an "
        "operator reason about the request; not an authorization input by itself.",
    ),
    (
        "context",
        "Optional key=value attributes a policy condition might consider "
        "(e.g. maintenance_window=true). One entry per line.",
    ),
)


@dataclass
class SimulationResult:
    """Outcome of validating simulator input and building a preview.

    ok            True when input validated and a preview was built.
    preview       The normalized request preview (only when ok); else None.
    errors        Ordered, user-friendly error messages (empty when ok).
    field_errors  Per-field error messages keyed by field name, for inline UI.
    values        The (stripped) submitted values, echoed back to repopulate
                  the form on both success and failure.
    """

    ok: bool
    preview: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    field_errors: dict[str, str] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)


def _parse_context(raw: str) -> tuple[dict[str, str], list[str]]:
    """Parse a ``key=value`` per-line context block.

    Returns the parsed mapping and a list of error strings. Blank lines are
    ignored. Order is preserved. Duplicate keys are an error.
    """
    context: dict[str, str] = {}
    errors: list[str] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        entry = line.strip()
        if not entry:
            continue
        if len(context) >= MAX_CONTEXT_ENTRIES:
            errors.append(f"Too many context entries (max {MAX_CONTEXT_ENTRIES}).")
            break
        if "=" not in entry:
            errors.append(f"Context line {lineno} must be in key=value form.")
            continue
        key, _, value = entry.partition("=")
        key = key.strip()
        value = value.strip()
        if not _SLUG_RE.match(key):
            errors.append(f"Context key {key!r} (line {lineno}) is not a simple safe string.")
            continue
        if len(key) > MAX_FIELD_LEN or len(value) > MAX_FIELD_LEN:
            errors.append(f"Context entry on line {lineno} is too long.")
            continue
        if value and not _CTX_VALUE_RE.match(value):
            errors.append(f"Context value for {key!r} (line {lineno}) is not a simple safe string.")
            continue
        if key in context:
            errors.append(f"Duplicate context key {key!r} (line {lineno}).")
            continue
        context[key] = value
    return context, errors


def _validate_id(label: str, value: str, errors: list[str], field_errors: dict[str, str]) -> None:
    if not value:
        msg = f"{label.replace('_', ' ').capitalize()} is required."
        errors.append(msg)
        field_errors[label] = msg
    elif len(value) > MAX_FIELD_LEN:
        msg = f"{label.replace('_', ' ').capitalize()} is too long (max {MAX_FIELD_LEN})."
        errors.append(msg)
        field_errors[label] = msg
    elif not _ID_RE.match(value):
        msg = (
            f"{label.replace('_', ' ').capitalize()} must be a simple safe string "
            "(letters, digits, and . _ - : / )."
        )
        errors.append(msg)
        field_errors[label] = msg


def _validate_slug(label: str, value: str, errors: list[str], field_errors: dict[str, str]) -> None:
    if not value:
        msg = f"{label.replace('_', ' ').capitalize()} is required."
        errors.append(msg)
        field_errors[label] = msg
    elif len(value) > MAX_FIELD_LEN:
        msg = f"{label.replace('_', ' ').capitalize()} is too long (max {MAX_FIELD_LEN})."
        errors.append(msg)
        field_errors[label] = msg
    elif not _SLUG_RE.match(value):
        pretty = label.replace("_", " ").capitalize()
        msg = f"{pretty} must be a simple slug (letters, digits, _ -)."
        errors.append(msg)
        field_errors[label] = msg


def build_simulation(raw: dict[str, str]) -> SimulationResult:
    """Validate raw form fields and build a normalized request preview.

    This is a pure function: it performs no I/O, makes no network call, and
    evaluates no authorization. On any validation failure it returns
    ``ok=False`` with user-friendly messages and the submitted values echoed
    back so the form can be repopulated.
    """
    subject_id = (raw.get("subject_id") or "").strip()
    subject_type = (raw.get("subject_type") or "").strip()
    action_verb = (raw.get("action_verb") or "").strip()
    action_domain = (raw.get("action_domain") or "").strip()
    resource_id = (raw.get("resource_id") or "").strip()
    resource_type = (raw.get("resource_type") or "").strip()
    context_raw = raw.get("context") or ""

    # Best-effort composed string for echo/display. Only meaningful (and only
    # rendered) once both segments are present; never sent to the gateway unless
    # validation below passes.
    composed_action = (
        compose_action(action_verb, action_domain) if action_verb and action_domain else ""
    )

    values = {
        "subject_id": subject_id,
        "subject_type": subject_type,
        "action_verb": action_verb,
        "action_domain": action_domain,
        "action": composed_action,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "context": context_raw,
    }

    errors: list[str] = []
    field_errors: dict[str, str] = {}

    _validate_id("subject_id", subject_id, errors, field_errors)
    _validate_slug("subject_type", subject_type, errors, field_errors)

    # Action is composed from a verb and a domain. Both must come from the
    # provisional console-local vocabulary; the console never accepts a free-form
    # or bare action and never invents verbs/domains of its own.
    if not action_verb:
        msg = "Action verb is required."
        errors.append(msg)
        field_errors["action_verb"] = msg
    elif not is_supported_verb(action_verb):
        msg = f"Action verb must be one of: {', '.join(ACTION_VERBS)}."
        errors.append(msg)
        field_errors["action_verb"] = msg

    if not action_domain:
        msg = "Action domain is required."
        errors.append(msg)
        field_errors["action_domain"] = msg
    elif not is_supported_domain(action_domain):
        msg = f"Action domain must be one of: {', '.join(ACTION_DOMAINS)}."
        errors.append(msg)
        field_errors["action_domain"] = msg

    _validate_id("resource_id", resource_id, errors, field_errors)
    _validate_slug("resource_type", resource_type, errors, field_errors)

    context, ctx_errors = _parse_context(context_raw)
    if ctx_errors:
        errors.extend(ctx_errors)
        field_errors.setdefault("context", ctx_errors[0])

    # Defense in depth: even with valid verb + domain, refuse to emit a string
    # that does not match basis-core's {verb}:{domain}[:{object}] shape. This
    # should never fire for vocabulary-sourced inputs; it guards against a future
    # vocabulary edit that would silently produce a gateway-invalid action.
    if action_verb and action_domain and not matches_action_format(composed_action):
        msg = (
            f"Composed action {composed_action!r} does not match the required "
            "{verb}:{domain} format."
        )
        errors.append(msg)
        field_errors.setdefault("action_verb", msg)

    if errors:
        return SimulationResult(
            ok=False,
            preview=None,
            errors=errors,
            field_errors=field_errors,
            values=values,
        )

    preview: dict[str, Any] = {
        "subject_id": subject_id,
        "subject_type": subject_type,
        "action": composed_action,
        "resource_id": resource_id,
        "resource_type": resource_type,
        "context": context,
    }
    return SimulationResult(ok=True, preview=preview, errors=[], field_errors={}, values=values)
