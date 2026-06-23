"""Decision-simulator logic for basis-console (Phases 3, 6, and 7).

This module turns operator-supplied form fields into a *normalized request* — a
plain data structure that shows the shape of the authorization request the
console submits to ``basis-gateway`` (and, in preview mode, only displays).

Boundary:
  - Nothing here evaluates authorization. There is no policy logic, no role
    check, no condition evaluation, and no notion of an allow/deny outcome.
    Authorization belongs to ``basis-core``, reached only through
    ``basis-gateway``.
  - Building a preview is a pure, local, in-memory transformation of validated
    input; it makes no network call.
  - The console does not import ``basis-core`` or any kernel model.

Composition is the gateway's job (Phase 7 alignment):
  ``basis-gateway`` is the action/resource composition boundary. The console
  submits an *adapter/console-normalized* request — a **bare action verb**, a
  **resource_type**, and a **local** (untyped) ``resource_id`` — and the gateway
  composes the canonical kernel action (``{verb}:{resource_type}``) and the typed
  resource id (``{resource_type}:{local_id}``). The console no longer pre-composes
  those canonical strings; it can *preview* what the gateway will compose, but the
  composition itself happens at the gateway.

``resource_type`` is dual-purpose: the gateway uses the same field to compose the
action domain and the resource-identifier prefix. The console therefore carries a
single ``resource_type`` field rather than a separate action domain and a merely
descriptive resource type that could drift apart. See ``basis_console.vocabulary``
and ``docs/architecture.md`` for why the console is not the vocabulary authority.

Valid gateway request shapes (see :func:`build_gateway_request`):
  - **Normalized (preferred):** ``{"action": "read", "resource_type": "ahu",
    "resource_id": "rooftop-1"}`` — bare verb + resource_type + *local* id. The
    gateway composes ``read:ahu`` and ``ahu:rooftop-1``. A resource_id may be
    omitted for a domain-level request (gateway composes the action only).
  - **Direct (fully typed):** ``{"action": "read:ahu",
    "resource_id": "ahu:rooftop-1"}`` — used only when an operator intentionally
    enters a kernel-compatible request; ``resource_type`` is omitted. The gateway
    passes these through unchanged.

The console must never send a ``resource_type`` alongside an already-typed
``resource_id`` (a dual source of truth that can drift); :func:`build_gateway_request`
rejects that combination before any call is made.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from basis_console.vocabulary import (
    ACTION_VERBS,
    RESOURCE_TYPES,
    compose_action,
    compose_resource_id,
    is_supported_resource_type,
    is_supported_verb,
    is_typed_identifier,
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
        "Preview-only: live evaluation derives the subject from the gateway's "
        "verified token, never from this field.",
    ),
    (
        "subject_type",
        "What kind of subject this is (e.g. user, service, device). Preview-only; "
        "the gateway resolves real identity and roles from the token.",
    ),
    (
        "action_verb",
        "The bare operation the subject wants to perform. One of: "
        + ", ".join(ACTION_VERBS)
        + ". The gateway composes the canonical action from the verb and the "
        "resource type — the console does not pre-compose it.",
    ),
    (
        "resource_type",
        "The resource type / action domain (e.g. "
        + ", ".join(RESOURCE_TYPES)
        + "). This is NOT merely descriptive: the gateway uses it to compose both "
        "the action (verb:resource_type) and the resource id (resource_type:id).",
    ),
    (
        "resource_id",
        "The LOCAL (untyped) identifier of the target resource (e.g. rooftop-1). "
        "The gateway prefixes it with the resource type to form the canonical id "
        "(e.g. ahu:rooftop-1). Optional — omit it for a domain-level request.",
    ),
    (
        "context",
        "Optional key=value attributes a policy condition might consider "
        "(e.g. maintenance_window=true). One entry per line.",
    ),
)


@dataclass
class GatewayRequestResult:
    """A built gateway request body, or the reasons it could not be built.

    ok       True when a valid request body was assembled.
    payload  The exact JSON body to send to ``/v1/evaluate`` (no subject), or
             None when validation failed.
    errors   Ordered, user-friendly messages explaining why the request shape is
             invalid (empty when ok).
    """

    ok: bool
    payload: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)


def build_gateway_request(
    *,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    context: dict[str, str] | None = None,
) -> GatewayRequestResult:
    """Assemble a gateway-compatible ``/v1/evaluate`` body from normalized inputs.

    This encodes the console's half of the gateway composition contract. The
    gateway owns composition; the console's job is to submit one of two valid
    shapes and to refuse obviously-invalid combinations before any call is made.

    Rules (mirroring ``basis-gateway``):
      - ``resource_type`` present (**normalized**): send a bare verb plus the
        resource_type; the gateway composes the action and (when a *local*
        resource_id is supplied) the typed resource id. A typed resource_id or a
        composite action alongside a resource_type is rejected as a dual source
        of truth. The resource_id may be omitted for a domain-level request.
      - ``resource_type`` absent (**direct**): the action must be fully typed
        (``verb:domain``) and any resource_id must be fully typed
        (``type:qualifier``); the gateway passes them through unchanged.

    No subject is ever included — the gateway derives identity from its token.
    """
    action = action.strip()
    resource_type = resource_type.strip()
    resource_id = resource_id.strip()
    errors: list[str] = []

    if not action:
        return GatewayRequestResult(ok=False, payload=None, errors=["An action is required."])

    typed_action = is_typed_identifier(action)
    has_rt = bool(resource_type)
    has_rid = bool(resource_id)
    typed_rid = is_typed_identifier(resource_id) if has_rid else False

    if has_rt:
        # Normalized shape: gateway composes from the resource_type.
        if typed_action:
            errors.append(
                "When a resource type is given, use a bare action verb (e.g. "
                "read); the gateway composes the typed action from the verb and "
                "the resource type."
            )
        if has_rid and typed_rid:
            errors.append(
                "When a resource type is given, the resource ID must be local "
                "(e.g. rooftop-1), not already typed (e.g. ahu:rooftop-1). "
                "Sending both is a dual source of truth and can drift."
            )
        if errors:
            return GatewayRequestResult(ok=False, payload=None, errors=errors)

        payload: dict[str, Any] = {"action": action, "resource_type": resource_type}
        if has_rid:
            payload["resource_id"] = resource_id
        if context:
            payload["context"] = context
        return GatewayRequestResult(ok=True, payload=payload, errors=[])

    # Direct shape: no resource_type; the request must already be fully typed.
    if not typed_action:
        errors.append(
            "Without a resource type, enter a fully typed action (e.g. read:ahu) "
            "so the gateway has a domain to evaluate."
        )
    if has_rid and not typed_rid:
        errors.append(
            "A local resource ID (e.g. rooftop-1) requires a resource type so the "
            "gateway can compose the identifier; otherwise enter a fully typed "
            "resource ID (e.g. ahu:rooftop-1)."
        )
    if errors:
        return GatewayRequestResult(ok=False, payload=None, errors=errors)

    payload = {"action": action}
    if has_rid:
        payload["resource_id"] = resource_id
    if context:
        payload["context"] = context
    return GatewayRequestResult(ok=True, payload=payload, errors=[])


@dataclass
class SimulationResult:
    """Outcome of validating simulator input and building a preview.

    ok            True when input validated and a preview was built.
    preview       The normalized request preview (only when ok); else None. Shows
                  the bare verb, resource_type, and local resource_id the console
                  submits, plus the (preview-only) subject fields.
    gateway_body  The exact JSON body POSTed to ``/v1/evaluate`` (no subject), or
                  None. The console relays this verbatim; the gateway composes.
    composition   Preview of what the gateway will compose: ``action`` (e.g.
                  ``read:ahu``) and ``resource_id`` (e.g. ``ahu:rooftop-1`` or
                  None for a domain-level request). Educational only.
    errors        Ordered, user-friendly error messages (empty when ok).
    field_errors  Per-field error messages keyed by field name, for inline UI.
    values        The (stripped) submitted values, echoed back to repopulate the
                  form on both success and failure.
    """

    ok: bool
    preview: dict[str, Any] | None = None
    gateway_body: dict[str, Any] | None = None
    composition: dict[str, Any] | None = None
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
    evaluates no authorization. It builds the *normalized* (preferred) request
    shape — a bare action verb, a resource_type, and a *local* resource_id — and
    leaves canonical action/resource composition to the gateway. On any failure
    it returns ``ok=False`` with user-friendly messages and the submitted values
    echoed back so the form can be repopulated.
    """
    subject_id = (raw.get("subject_id") or "").strip()
    subject_type = (raw.get("subject_type") or "").strip()
    action_verb = (raw.get("action_verb") or "").strip()
    resource_type = (raw.get("resource_type") or "").strip()
    resource_id = (raw.get("resource_id") or "").strip()
    context_raw = raw.get("context") or ""

    # Best-effort composition previews for echo/display. Only meaningful (and only
    # rendered) once the relevant segments are present; never sent to the gateway.
    composed_action = (
        compose_action(action_verb, resource_type) if action_verb and resource_type else ""
    )
    composed_resource_id = (
        compose_resource_id(resource_type, resource_id)
        if resource_type and resource_id and not is_typed_identifier(resource_id)
        else ""
    )

    values = {
        "subject_id": subject_id,
        "subject_type": subject_type,
        "action_verb": action_verb,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "context": context_raw,
        "composed_action": composed_action,
        "composed_resource_id": composed_resource_id,
    }

    errors: list[str] = []
    field_errors: dict[str, str] = {}

    _validate_id("subject_id", subject_id, errors, field_errors)
    _validate_slug("subject_type", subject_type, errors, field_errors)

    # Verb must come from the provisional console-local vocabulary; the console
    # never accepts a free-form or composite action from the form.
    if not action_verb:
        msg = "Action verb is required."
        errors.append(msg)
        field_errors["action_verb"] = msg
    elif not is_supported_verb(action_verb):
        msg = f"Action verb must be one of: {', '.join(ACTION_VERBS)}."
        errors.append(msg)
        field_errors["action_verb"] = msg

    # resource_type is required for the normalized form path and drives gateway
    # composition of both the action and the resource id.
    if not resource_type:
        msg = "Resource type is required."
        errors.append(msg)
        field_errors["resource_type"] = msg
    elif not is_supported_resource_type(resource_type):
        msg = f"Resource type must be one of: {', '.join(RESOURCE_TYPES)}."
        errors.append(msg)
        field_errors["resource_type"] = msg

    # resource_id is OPTIONAL (a domain-level request omits it). When present it
    # must be a safe string AND must be LOCAL — an already-typed resource_id
    # alongside a resource_type is a dual source of truth the gateway rejects.
    if resource_id:
        if len(resource_id) > MAX_FIELD_LEN:
            msg = f"Resource id is too long (max {MAX_FIELD_LEN})."
            errors.append(msg)
            field_errors["resource_id"] = msg
        elif not _ID_RE.match(resource_id):
            msg = "Resource id must be a simple safe string (letters, digits, and . _ - : / )."
            errors.append(msg)
            field_errors["resource_id"] = msg
        elif is_typed_identifier(resource_id):
            msg = (
                "Resource id must be local (e.g. rooftop-1), not already typed "
                "(e.g. ahu:rooftop-1). The gateway composes the typed id from the "
                "resource type; sending a typed id here is a dual source of truth."
            )
            errors.append(msg)
            field_errors["resource_id"] = msg

    context, ctx_errors = _parse_context(context_raw)
    if ctx_errors:
        errors.extend(ctx_errors)
        field_errors.setdefault("context", ctx_errors[0])

    if errors:
        return SimulationResult(
            ok=False,
            preview=None,
            gateway_body=None,
            composition=None,
            errors=errors,
            field_errors=field_errors,
            values=values,
        )

    # Assemble the exact gateway body via the shared builder so the preview and
    # the submitted request can never diverge.
    built = build_gateway_request(
        action=action_verb,
        resource_type=resource_type,
        resource_id=resource_id,
        context=context or None,
    )
    if not built.ok or built.payload is None:
        # Defensive: form-level validation should have caught everything above.
        for msg in built.errors:
            errors.append(msg)
            field_errors.setdefault("resource_id", msg)
        return SimulationResult(
            ok=False,
            preview=None,
            gateway_body=None,
            composition=None,
            errors=errors,
            field_errors=field_errors,
            values=values,
        )

    # The preview shows the normalized request (educational subject included).
    preview: dict[str, Any] = {
        "subject_id": subject_id,
        "subject_type": subject_type,
        "action": action_verb,
        "resource_type": resource_type,
    }
    if resource_id:
        preview["resource_id"] = resource_id
    preview["context"] = context

    composition = {
        "action": composed_action,
        "resource_id": composed_resource_id or None,
    }

    return SimulationResult(
        ok=True,
        preview=preview,
        gateway_body=built.payload,
        composition=composition,
        errors=[],
        field_errors={},
        values=values,
    )
