"""Typed contract models for ``POST /v1/evaluate/operation-aware`` (PR 2).

This module is deliberately a sibling of ``gateway/models.py`` rather than an
extension of it (Option B, per the operation-aware console integration plan,
§10.2/§16 "Module Organization"): the legacy ``/v1/evaluate`` contract
(``GatewayEvaluationResult`` / ``GatewayEvaluationStatus``) and the
operation-aware contract defined here must never be interchangeable, cast, or
duck-typed into one another. Keeping them in separate modules makes that
boundary a file boundary, not just a naming convention.

Everything here is derived strictly from the authoritative gateway contract —
``basis-gateway/docs/operation-aware-endpoint.md`` and
``basis_gateway.api.operation_aware_schemas`` /
``basis_gateway.api.operation_aware_classification`` as they exist on the
inspected commit — never from the legacy contract by analogy and never
invented. See ``docs/architecture.md``, "Phase 16", for the commit inspected
and the discrepancies (none) found between the plan and the implementation.

This module defines:
  - ``OperationAwareEvaluationRequest`` — the complete, closed set of fields an
    ordinary authenticated console session may submit. There is no field for
    caller-supplied context, subject data, or any trusted-producer-only
    context (location, device, protocol/safety/environment/risk context,
    evidence references) — the type surface itself makes those fields
    impossible to set from this model.
  - Closed-vocabulary enums for every field the gateway contract defines as
    closed: ``OperationAwareEvaluationState`` (``evaluation_status``),
    ``OperationAwareOutcome`` (``outcome``),
    ``OperationAwareFailureReason`` (``failure_reason``), and
    ``OperationAwareDisposition`` (``disposition``). ``reason_code`` is
    intentionally represented as an opaque ``str | None`` — the contract
    documents it as not yet a closed vocabulary (§5.3 of the integration
    plan) — never as an enum.
  - ``OperationAwareEvaluationResponse`` — the fully-parsed, contract-valid
    governed response body. Does not model ``evaluation_trace``: the current
    endpoint contract returns it only as ``null``/absent, so there is nothing
    typed to carry; a response asserting a non-null trace is treated as a
    contract violation (see ``_parse_operation_aware_response`` below), not
    modeled as a loosely-typed trace viewer.
  - ``OperationAwareEvaluationStatus`` — the console's client-level
    classification of a call to this endpoint (transport/capability/contract
    conditions). This is a distinct axis from ``OperationAwareEvaluationState``:
    the status enum classifies what *kind of result* the console got back
    (governed completion, governed failure, pre-kernel rejection, transport
    failure, contract violation, ...); the state enum is the kernel's own
    ``completed``/``failed`` field, relayed verbatim inside a governed
    response. See ``EVALUATION_COMPLETED``/``EVALUATION_FAILED`` docstrings
    below for exactly how the two relate.
  - ``OperationAwareEvaluationResult`` — the typed result wrapper returned by
    ``GatewayClient.evaluate_operation_aware()``, structurally distinct from
    the legacy ``GatewayEvaluationResult``.

Strict, shape-distinguishing parsing (not status-code-driven)
---------------------------------------------------------------
Per §6 of the integration plan, HTTP status code alone does not determine
response body shape on this endpoint: ``400``, ``403``, ``500``, and ``503``
can each carry either a governed ``OperationAwareEvaluateResponse`` body
(recognizable by an ``evaluation_status`` key) or a generic, ungoverned
``ErrorResponse``/framework body. ``_parse_operation_aware_response`` and
``GatewayClient._interpret_operation_aware`` (in ``client.py``) distinguish
these by inspecting the body itself, never by status code alone, and a
governed body found on any status is parsed and trusted as governed; a body
that looks governed (carries an ``evaluation_status`` key) but violates a
documented contract invariant is classified as contract-invalid rather than
partially trusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from typing import Any


class OperationAwareEvaluationState(str, Enum):
    """The kernel's own ``evaluation_status`` field. Closed, two values.

    COMPLETED  The kernel produced an authorization outcome (``outcome`` is
               present; ``failure_reason`` is absent).
    FAILED     The evaluator could not produce a valid authorization result
               (``failure_reason`` is present; ``outcome`` is absent). Not a
               policy decision of any kind.
    """

    COMPLETED = "completed"
    FAILED = "failed"


class OperationAwareOutcome(str, Enum):
    """The kernel's authorization outcome. Closed, three values.

    ALLOW           An applicable bundle evaluated the request and authorized it.
    DENY            An applicable bundle evaluated the request and denied it
                    (explicit deny rule, or default deny — the response body
                    does not distinguish the two sub-causes).
    NOT_APPLICABLE  No policy bundle covers this request's domain/scope at
                    all. Never equivalent to DENY, even though both produce
                    HTTP 403 on this endpoint — see ``disposition``.
    """

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"


class OperationAwareFailureReason(str, Enum):
    """Governed evaluation-failure reason. Closed, six values.

    Not a policy decision; the evaluator could not produce a trustworthy
    authorization result at all. Exact HTTP classification per
    ``basis_gateway.api.operation_aware_classification``:

      invalid_request              400
      unsupported_schema_version   400
      invalid_policy_bundle        503
      policy_validation_failure    503
      condition_evaluation_error   500
      internal_evaluation_error    500
    """

    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_SCHEMA_VERSION = "unsupported_schema_version"
    INVALID_POLICY_BUNDLE = "invalid_policy_bundle"
    POLICY_VALIDATION_FAILURE = "policy_validation_failure"
    CONDITION_EVALUATION_ERROR = "condition_evaluation_error"
    INTERNAL_EVALUATION_ERROR = "internal_evaluation_error"


class OperationAwareDisposition(str, Enum):
    """The gateway-surfaced, kernel-computed enforcement disposition.

    Closed, two values. Collapses NOT_APPLICABLE into DENY the same way the
    HTTP layer does, but is a labelled response field, not an inferred one.
    Never gateway-recomputed from ``outcome`` — copied verbatim from the
    kernel's own ``EnforcementDisposition``.
    """

    ALLOW = "allow"
    DENY = "deny"


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationAwareEvaluationRequest:
    """The complete, closed set of fields an ordinary console session may send.

    This is the entire public request surface for
    ``POST /v1/evaluate/operation-aware`` as an authenticated (non-trusted-
    producer) caller — Section 4.1 of the integration plan. There is
    deliberately no field here for:
      - a subject (the gateway derives identity from the Bearer token);
      - ``context`` (the endpoint accepts only an empty context; the console
        has no code path capable of submitting a non-empty one because there
        is no field to populate);
      - any of the nine trusted-producer-only fields (``operation_intent``,
        ``location``, ``device``, ``protocol_context``, ``safety_context``,
        ``environment_context``, ``risk_context``,
        ``identity_evidence_reference``, ``adapter_evidence_reference``);
      - any gateway-owned fact (``evaluation_status``, ``outcome``,
        ``bundle_id``, ``expected_policy_version``, ...).

    Frozen, so a caller-held reference can never be mutated by anything this
    package does with it.

    Fields
    ──────
    action         Required. A composite action (``"read:ahu"``) or a bare
                   verb (``"read"``) to be composed with ``resource_type``.
    resource_type  Optional. Domain for a bare-verb action and/or the type
                   for a local ``resource_id``.
    resource_id    Optional. Local (composed with ``resource_type``) or
                   already-typed resource identifier.
    request_id     Optional caller-supplied request identifier. When omitted,
                   the gateway defaults it to the generated ``correlation_id``.
    """

    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    request_id: str | None = None


def _serialize_operation_aware_request(request: OperationAwareEvaluationRequest) -> dict[str, Any]:
    """Build the exact JSON body for ``POST /v1/evaluate/operation-aware``.

    Sends only documented, caller-allowed fields; omits unset optional fields
    rather than sending an explicit ``null``. Never sends ``context`` — there
    is no field on the request model to populate it from, so this function
    has no way to emit one. Never mutates ``request``.
    """
    body: dict[str, Any] = {"action": request.action}
    if request.resource_type:
        body["resource_type"] = request.resource_type
    if request.resource_id:
        body["resource_id"] = request.resource_id
    if request.request_id:
        body["request_id"] = request.request_id
    return body


# ---------------------------------------------------------------------------
# Governed response model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationAwareEvaluationResponse:
    """A fully-parsed, contract-valid governed response body.

    Every field is copied verbatim from the gateway's response; none is
    computed, inferred, or defaulted by the console. Absent/null fields stay
    ``None`` here exactly as the gateway sent them — this is a first-class,
    valid state for ``correlation_id``, ``outcome``, ``failure_reason``,
    ``bundle_id``, ``bundle_version``, ``trace_id``, ``reason_code``, and
    ``explanation`` (never synthesized, never treated as malformed).

    Fields
    ──────
    request_id         Always present.
    evaluation_status   ``completed`` or ``failed`` (closed).
    disposition         ``allow`` or ``deny`` (closed). Always present.
    correlation_id      Usually present; matches ``X-Correlation-ID``.
    outcome              Present iff ``evaluation_status`` is ``completed``.
    failure_reason      Present iff ``evaluation_status`` is ``failed``.
    bundle_id           Present when a trustworthy typed bundle exists.
    bundle_version      Same availability as ``bundle_id``.
    trace_id             Gateway-generated per-call reference, when available.
    reason_code          Opaque string, kernel-populated only; not a closed
                          vocabulary (contract not finalized — never rendered
                          from an invented mapping by this module).
    explanation           Kernel-populated safe prose, or ``None``. ``None`` is
                          a normal, complete contract state, never malformed.

    ``evaluation_trace`` is intentionally not a field here — see this module's
    docstring.
    """

    request_id: str
    evaluation_status: OperationAwareEvaluationState
    disposition: OperationAwareDisposition
    correlation_id: str | None = None
    outcome: OperationAwareOutcome | None = None
    failure_reason: OperationAwareFailureReason | None = None
    bundle_id: str | None = None
    bundle_version: str | None = None
    trace_id: str | None = None
    reason_code: str | None = None
    explanation: str | None = None


class _OperationAwareContractError(Exception):
    """Raised internally when a response body cannot be trusted as governed.

    Never escapes ``gateway`` package boundaries — the client catches this and
    turns it into a redacted ``OperationAwareEvaluationResult`` with status
    ``CONTRACT_INVALID``. The message is safe to surface (it names only field
    names and closed-vocabulary values, never response content that could
    carry a secret).
    """


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise _OperationAwareContractError(f"{field_name} must be a string")
    return value


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _OperationAwareContractError(f"{field_name} must be a string or null")
    return value


def _reconcile_correlation_id(body_value: object, header_value: str | None) -> str | None:
    """Reconcile the response body's ``correlation_id`` with the ``X-Correlation-ID``
    header into a single evidence-integrity fact.

    The gateway contract states the two match — the header is set by the same
    middleware that populates the body field. Silently preferring one over the
    other when both are present but disagree would let the console associate a
    decision with the wrong request/trace/audit chain, so this never picks a
    winner:

      - both present and equal    -> that value
      - only one present          -> that value
      - neither present           -> ``None`` (valid whenever the response
                                     contract allows absence)
      - both present and differ   -> raises ``_OperationAwareContractError``;
                                     the caller must not select either value
                                     and must not treat the response as
                                     governed/trustworthy.

    ``body_value`` is type-checked the same way any other optional string
    field is (``_require_optional_str``) before comparison.
    """
    body_str = _require_optional_str(body_value, "correlation_id")
    if body_str is not None and header_value is not None and body_str != header_value:
        raise _OperationAwareContractError(
            f"correlation_id mismatch between response body ({body_str!r}) and "
            f"X-Correlation-ID header ({header_value!r})"
        )
    return body_str if body_str is not None else header_value


def _parse_operation_aware_response(
    body: dict[str, object], header_correlation_id: str | None
) -> OperationAwareEvaluationResponse:
    """Strictly parse a governed ``OperationAwareEvaluateResponse`` body.

    ``header_correlation_id`` is the ``X-Correlation-ID`` response header
    value, reconciled against the body's own ``correlation_id`` field via
    ``_reconcile_correlation_id`` — a disagreement between the two aborts
    parsing (``_OperationAwareContractError``) before any
    ``OperationAwareEvaluationResponse`` is constructed, exactly like any
    other contract violation this function checks.

    Raises ``_OperationAwareContractError`` on any violation of a documented
    contract invariant (Section "Contract Invariants" of the task; §5/§8/§9
    of the integration plan) rather than partially trusting the body. Never
    called on a body that lacks an ``evaluation_status`` key — the caller
    (``GatewayClient._interpret_operation_aware``) uses that key's presence to
    decide whether a body is governed at all.
    """
    if "request_id" not in body:
        raise _OperationAwareContractError("missing required field: request_id")
    request_id = _require_str(body.get("request_id"), "request_id")

    if "disposition" not in body:
        raise _OperationAwareContractError("missing required field: disposition")
    disposition_raw = _require_str(body.get("disposition"), "disposition")
    try:
        disposition = OperationAwareDisposition(disposition_raw)
    except ValueError:
        raise _OperationAwareContractError(f"unknown disposition: {disposition_raw!r}") from None

    if "evaluation_status" not in body:
        raise _OperationAwareContractError("missing required field: evaluation_status")
    evaluation_status_raw = _require_str(body.get("evaluation_status"), "evaluation_status")
    try:
        evaluation_status = OperationAwareEvaluationState(evaluation_status_raw)
    except ValueError:
        raise _OperationAwareContractError(
            f"unknown evaluation_status: {evaluation_status_raw!r}"
        ) from None

    outcome_raw = body.get("outcome")
    outcome: OperationAwareOutcome | None = None
    if outcome_raw is not None:
        outcome_raw = _require_str(outcome_raw, "outcome")
        try:
            outcome = OperationAwareOutcome(outcome_raw)
        except ValueError:
            raise _OperationAwareContractError(f"unknown outcome: {outcome_raw!r}") from None

    failure_reason_raw = body.get("failure_reason")
    failure_reason: OperationAwareFailureReason | None = None
    if failure_reason_raw is not None:
        failure_reason_raw = _require_str(failure_reason_raw, "failure_reason")
        try:
            failure_reason = OperationAwareFailureReason(failure_reason_raw)
        except ValueError:
            raise _OperationAwareContractError(
                f"unknown failure_reason: {failure_reason_raw!r}"
            ) from None

    if evaluation_status is OperationAwareEvaluationState.COMPLETED:
        if outcome is None:
            raise _OperationAwareContractError("completed evaluation missing outcome")
        if failure_reason is not None:
            raise _OperationAwareContractError(
                "completed evaluation must not carry a failure_reason"
            )
        expected_disposition = (
            OperationAwareDisposition.ALLOW
            if outcome is OperationAwareOutcome.ALLOW
            else OperationAwareDisposition.DENY
        )
        if disposition is not expected_disposition:
            raise _OperationAwareContractError(
                f"disposition {disposition.value!r} inconsistent with outcome {outcome.value!r}"
            )
    else:  # FAILED
        if failure_reason is None:
            raise _OperationAwareContractError("failed evaluation missing failure_reason")
        if outcome is not None:
            raise _OperationAwareContractError("failed evaluation must not carry an outcome")
        if disposition is not OperationAwareDisposition.DENY:
            raise _OperationAwareContractError(
                f"disposition {disposition.value!r} inconsistent with a failed evaluation"
            )

    # Evidence-integrity check: the body's correlation_id and the
    # X-Correlation-ID header must agree. A disagreement aborts parsing here
    # — no OperationAwareEvaluationResponse is constructed from a body whose
    # own correlation evidence is internally inconsistent.
    correlation_id = _reconcile_correlation_id(body.get("correlation_id"), header_correlation_id)
    bundle_id = _require_optional_str(body.get("bundle_id"), "bundle_id")
    bundle_version = _require_optional_str(body.get("bundle_version"), "bundle_version")
    trace_id = _require_optional_str(body.get("trace_id"), "trace_id")
    reason_code = _require_optional_str(body.get("reason_code"), "reason_code")
    explanation = _require_optional_str(body.get("explanation"), "explanation")

    if "evaluation_trace" in body and body.get("evaluation_trace") is not None:
        raise _OperationAwareContractError(
            "evaluation_trace is not null; the current endpoint contract never returns a "
            "non-null trace"
        )

    return OperationAwareEvaluationResponse(
        request_id=request_id,
        evaluation_status=evaluation_status,
        disposition=disposition,
        correlation_id=correlation_id,
        outcome=outcome,
        failure_reason=failure_reason,
        bundle_id=bundle_id,
        bundle_version=bundle_version,
        trace_id=trace_id,
        reason_code=reason_code,
        explanation=explanation,
    )


# ---------------------------------------------------------------------------
# Client-level status and result wrapper
# ---------------------------------------------------------------------------


class OperationAwareEvaluationStatus(str, Enum):
    """Client/transport-level classification of one ``evaluate_operation_aware()`` call.

    This classifies *what kind of result the console got back* — it is a
    different axis from ``OperationAwareEvaluationState`` (the kernel's own
    ``completed``/``failed`` field, carried inside a governed response) and
    never replaces or duplicates the governed ``outcome`` /
    ``failure_reason`` / ``disposition`` fields. In particular, kernel
    ``DENY`` and ``NOT_APPLICABLE`` are both represented by the single status
    ``EVALUATION_COMPLETED`` — they are already distinguished precisely by
    ``OperationAwareEvaluationResult.response.outcome``, so this enum does not
    duplicate that distinction as separate statuses.

    NOT_CONFIGURED           No ``GATEWAY_BASE_URL`` is set; no call attempted.
    TOKEN_MISSING             No ``GATEWAY_BEARER_TOKEN`` is configured; no
                              call attempted.
    UNAUTHORIZED               HTTP 401 — the gateway rejected the token, before
                              any request-body-derived logic ran.
    CAPABILITY_UNAVAILABLE     HTTP 404 with no governed body — the operation-
                              aware route is not registered on this gateway
                              instance (``OPERATION_AWARE_ENABLED`` unset/false).
                              Not a validation error or a denial.
    REQUEST_REJECTED           HTTP 400 with no governed body — a pre-kernel,
                              gateway-owned rejection (bad request shape,
                              non-empty ``context``, an unclassified caller
                              supplying a producer-only field). Not a policy
                              denial.
    EVALUATOR_UNAVAILABLE       HTTP 503 with no governed body — the route is
                              registered but no evaluator is available yet
                              (startup incomplete), or another pre-kernel
                              gateway-owned 503 condition (e.g. audit
                              fail-closed). Not a policy decision.
    EVALUATION_COMPLETED       A governed response body with
                              ``evaluation_status=completed`` was parsed —
                              read ``response.outcome`` (``allow`` / ``deny`` /
                              ``not_applicable``) for the actual result.
    EVALUATION_FAILED          A governed response body with
                              ``evaluation_status=failed`` was parsed — read
                              ``response.failure_reason`` for the governed
                              cause. Never a policy decision.
    CONTRACT_INVALID           The response could not be safely classified as
                              either a governed response or a recognized
                              generic error — malformed JSON, a body that
                              looks governed but violates a documented
                              invariant, or an HTTP 403 without a governed
                              body (this endpoint always returns one on 403).
    UNAVAILABLE                 The gateway could not be reached (connection
                              failure or timeout — see ``timed_out``).
    GATEWAY_ERROR                HTTP 500 with no governed body, or any other
                              unrecognized status/response the console cannot
                              place in a more specific category.
    """

    NOT_CONFIGURED = "not_configured"
    TOKEN_MISSING = "token_missing"
    UNAUTHORIZED = "unauthorized"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    REQUEST_REJECTED = "request_rejected"
    EVALUATOR_UNAVAILABLE = "evaluator_unavailable"
    EVALUATION_COMPLETED = "evaluation_completed"
    EVALUATION_FAILED = "evaluation_failed"
    CONTRACT_INVALID = "contract_invalid"
    UNAVAILABLE = "unavailable"
    GATEWAY_ERROR = "gateway_error"


# Operator-facing, one-line explanation of each client-level status. Mirrors
# ``EVALUATION_STATE_EXPLANATIONS`` in ``models.py`` — kept next to the enum
# so the explanation and the status it describes cannot drift apart. Not
# consumed by any route or template in this PR (no UI changes); provided now
# so PR3's presentation model has a ready-made, reviewed console-explanation
# source to build on rather than inventing its own wording later.
OPERATION_AWARE_STATE_EXPLANATIONS: dict[OperationAwareEvaluationStatus, str] = {
    OperationAwareEvaluationStatus.NOT_CONFIGURED: (
        "No gateway base URL is configured, so no operation-aware evaluation was "
        "attempted. Set GATEWAY_BASE_URL to a running basis-gateway to enable it."
    ),
    OperationAwareEvaluationStatus.TOKEN_MISSING: (
        "No server-side bearer token is configured. The gateway requires a verified "
        "Bearer token on /v1/evaluate/operation-aware and derives the subject from "
        "it, so evaluation is disabled until GATEWAY_BEARER_TOKEN is set."
    ),
    OperationAwareEvaluationStatus.UNAUTHORIZED: (
        "The gateway rejected the bearer token (HTTP 401) before any request-body "
        "logic ran. Check GATEWAY_BEARER_TOKEN against the gateway's configured "
        "authentication mode."
    ),
    OperationAwareEvaluationStatus.CAPABILITY_UNAVAILABLE: (
        "Operation-aware evaluation is not enabled on this gateway (HTTP 404 — the "
        "route is not registered). This is a deployment capability gap, not a "
        "validation error or a denial."
    ),
    OperationAwareEvaluationStatus.REQUEST_REJECTED: (
        "The gateway rejected the request before evaluation (HTTP 400). This is a "
        "pre-kernel, gateway-owned rejection — not a policy denial."
    ),
    OperationAwareEvaluationStatus.EVALUATOR_UNAVAILABLE: (
        "The gateway's operation-aware evaluator is not ready (HTTP 503, before the "
        "kernel ran). This is a startup/readiness condition, not a policy decision."
    ),
    OperationAwareEvaluationStatus.EVALUATION_COMPLETED: (
        "The kernel produced an authorization outcome. See the parsed response's "
        "outcome (allow / deny / not_applicable) for the result — this status alone "
        "does not say which."
    ),
    OperationAwareEvaluationStatus.EVALUATION_FAILED: (
        "The evaluator could not produce a valid authorization result (a governed "
        "failure, not a policy decision). See the parsed response's failure_reason."
    ),
    OperationAwareEvaluationStatus.CONTRACT_INVALID: (
        "The gateway's response could not be read as a valid operation-aware "
        "response or a recognized error. This indicates a version/contract "
        "mismatch worth reporting, not a policy outcome."
    ),
    OperationAwareEvaluationStatus.UNAVAILABLE: (
        "The gateway could not be reached or reported itself unavailable (a "
        "connection error or a timeout). No decision was surfaced."
    ),
    OperationAwareEvaluationStatus.GATEWAY_ERROR: (
        "The gateway returned an unexpected status or response. The console relays "
        "this without reinterpreting it."
    ),
}


@dataclass(frozen=True)
class OperationAwareEvaluationResult:
    """Typed result of a console-initiated ``POST /v1/evaluate/operation-aware`` call.

    Structurally distinct from the legacy ``GatewayEvaluationResult`` — no
    field is shared by casting or duck-typing between the two. The configured
    Bearer token is NEVER stored here, so this object is always safe to
    render.

    Fields
    ──────
    status          Client-level classification (see ``OperationAwareEvaluationStatus``).
    http_status     The HTTP status code returned, or ``None`` when no call
                    was made or the gateway could not be contacted.
    response        The fully-parsed governed response, present iff ``status``
                    is ``EVALUATION_COMPLETED`` or ``EVALUATION_FAILED``.
                    ``None`` for every other status.
    correlation_id  Correlation id from the parsed body when present, else the
                    ``X-Correlation-ID`` response header, else ``None``.
    error_code      Machine-readable error code from a generic ``ErrorResponse``
                    body, when present.
    error_message   Human-readable message from a generic ``ErrorResponse``
                    body, when present.
    detail          Console-side note for transport failures or
                    contract-invalid diagnostics (never gateway-authored
                    prose presented as if it were a gateway field).
    timed_out       True when the call failed specifically because the
                    gateway did not respond within the configured timeout.
    response_json   The parsed, redacted response body, for raw display.
                    Contains no token. Present whenever a body was received
                    and parsed as JSON, regardless of ``status`` — including
                    on ``EVALUATION_COMPLETED``/``EVALUATION_FAILED``, where
                    ``response`` already carries the same data in typed form.
    headers         Selected, redacted response headers (lowercased keys),
                    when a response was received.
    """

    status: OperationAwareEvaluationStatus
    http_status: int | None = None
    response: OperationAwareEvaluationResponse | None = None
    correlation_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    detail: str | None = None
    timed_out: bool = False
    response_json: dict[str, object] | None = None
    headers: dict[str, str] = dataclass_field(default_factory=dict)

    @property
    def called_gateway(self) -> bool:
        """True when an HTTP call to the gateway was actually attempted."""
        return self.status not in (
            OperationAwareEvaluationStatus.NOT_CONFIGURED,
            OperationAwareEvaluationStatus.TOKEN_MISSING,
        )

    @property
    def explanation(self) -> str:
        """A plain, operator-facing explanation of this status category.

        Never reinterprets a parsed governed outcome; for
        ``EVALUATION_COMPLETED``/``EVALUATION_FAILED`` this describes the
        status category only — the specific outcome/failure_reason live on
        ``response``. Returns an empty string only for an unknown status
        (should not happen).
        """
        return OPERATION_AWARE_STATE_EXPLANATIONS.get(self.status, "")
