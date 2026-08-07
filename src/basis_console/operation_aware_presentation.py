"""Shared, mode-independent presentation model for operation-aware evaluation (PR 3).

WHAT THIS MODULE IS
────────────────────
A pure, typed transformation from the PR 2 gateway-client contract —
``OperationAwareEvaluationRequest`` (what was submitted) and
``OperationAwareEvaluationResult`` (the typed, already-redacted, already-parsed
result of a ``GatewayClient.evaluate_operation_aware()`` call) — into one
``OperationAwarePresentation`` object that later routes/templates can render
for **either** Operator or Training mode, unchanged.

``build_operation_aware_presentation(request, result)`` is the single entry
point. It performs no I/O, reads no configuration, accepts no console-mode
argument, and never mutates its inputs. The same typed input always produces
an equal presentation object (see the determinism test in
``tests/test_operation_aware_presentation.py``).

WHAT THIS MODULE IS NOT
────────────────────────
This module does not call the gateway (that is ``basis_console.gateway``'s
job), does not add a route/template/form/navigation entry, does not import
``basis-core`` or any ``basis_core.*`` symbol, does not infer a subject or a
producer-trust classification, does not recompute or reinterpret the kernel's
outcome/disposition/failure_reason, and does not know or care which console
presentation mode (operator/training) is active. Training mode's fuller
educational rendering and Operator mode's concise rendering are both later,
mode-owned decisions about *which* fields of this same object to show and how
— never a decision this module makes.

CONTENT PROVENANCE
───────────────────
Every displayable fact is wrapped in a :class:`PresentationContentItem`
carrying a closed :class:`ContentSource` tag. There are four categories, and
the first two are deliberately kept separate even though both are "exact,
never console-invented" data — they answer different questions ("what did we
send" vs. "what did the gateway tell us"), and a submitted value must never
be presented as if the gateway had confirmed or returned it:

  - ``SUBMITTED_INPUT`` — an exact value from the typed
    ``OperationAwareEvaluationRequest`` this builder was given, i.e. what the
    console sent (or would send). Used only for
    :class:`RequestSummarySection`'s ``action``/``resource_type``/
    ``resource_id``/``request_id``. Never a gateway confirmation of that
    value — the gateway may accept, reject, or (for ``request_id``) default
    it independently.
  - ``RETURNED_EVIDENCE`` — an exact value copied from the typed gateway
    result (``OperationAwareEvaluationResult`` / its parsed
    ``OperationAwareEvaluationResponse``). Never a console interpretation of
    that value, and never a value the console itself supplied.
  - ``CONSOLE_EXPLANATION`` — educational or diagnostic prose authored by
    ``basis-console`` itself (e.g. "No additional evaluator explanation was
    provided.", a NOT_APPLICABLE clarification, a governed-failure one-liner,
    the safe per-status display copy, or ``OperationAwareEvaluationResult
    .detail`` — which is itself documented as a console-side note, never
    gateway-authored prose).
  - ``FUTURE_CAPABILITY`` — a capability that is not returned or implemented
    today. The only current example is an embedded ``evaluation_trace``.

A :class:`PresentationContentItem`'s ``description`` field, when set, is
*always* console-authored framing text about the field — regardless of the
item's ``source`` — the same way a form label's help text is authored
independently of whether the field's value came from the user or the server.
``source`` classifies the ``value``, not the ``description``.

Two booleans complete each item's state, distinguishing three cases a
template must be able to render differently:

  - ``applicable=False`` — this concept does not exist in the current
    evaluation state at all (e.g. ``outcome`` when ``evaluation_status`` is
    ``failed``; ``bundle_id`` when no governed response exists). ``value`` is
    always ``None`` here.
  - ``applicable=True, present=False`` — the concept exists and the gateway
    validly returned it as null/absent (e.g. a null ``explanation``, an
    absent ``reason_code``). This is a first-class, valid contract state —
    never treated as malformed or missing data.
  - ``applicable=True, present=True`` — a real value is available; render
    ``value``.

MODE INDEPENDENCE
──────────────────
This module takes no ``console_mode``/``is_training_mode`` argument, performs
no mode conditional, and imports nothing from ``basis_console.config`` or any
other mode-configuration source (enforced by
``tests/test_operation_aware_presentation_boundary.py``, alongside the
existing no-``basis_core`` guard).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from basis_console.gateway import (
    OperationAwareEvaluationRequest,
    OperationAwareEvaluationResponse,
    OperationAwareEvaluationResult,
    OperationAwareEvaluationState,
    OperationAwareEvaluationStatus,
    OperationAwareFailureReason,
    OperationAwareOutcome,
)

# ---------------------------------------------------------------------------
# Content provenance
# ---------------------------------------------------------------------------


class ContentSource(str, Enum):
    """Where a :class:`PresentationContentItem`'s ``value`` came from. Closed."""

    SUBMITTED_INPUT = "submitted_input"
    RETURNED_EVIDENCE = "returned_evidence"
    CONSOLE_EXPLANATION = "console_explanation"
    FUTURE_CAPABILITY = "future_capability"


@dataclass(frozen=True)
class PresentationContentItem:
    """One displayable fact or explanation, tagged with its provenance.

    Fields
    ──────
    key          Stable internal identifier (e.g. ``"response.outcome"``),
                 for template/test addressing — never displayed as a label.
    label        Human-facing label (e.g. "Kernel outcome").
    value        The exact returned value (as a string) or console-authored
                 text, or ``None`` when ``applicable`` is ``False`` or the
                 underlying field is validly null/absent.
    source       See :class:`ContentSource`.
    applicable   ``False`` when this concept does not exist in the current
                 evaluation state (e.g. ``outcome`` on a failed evaluation).
                 ``value`` is always ``None`` when ``applicable`` is ``False``.
    present      ``True`` iff ``applicable`` is ``True`` and ``value`` is not
                 ``None``. ``applicable=True, present=False`` is the
                 first-class "validly null/absent" state.
    description  Optional, console-authored framing text about the field.
                 Always console-authored regardless of ``source`` — see the
                 module docstring.
    """

    key: str
    label: str
    value: str | None
    source: ContentSource
    applicable: bool = True
    present: bool = False
    description: str | None = None


def _item(
    key: str,
    label: str,
    value: str | None,
    source: ContentSource,
    *,
    description: str | None = None,
    applicable: bool = True,
) -> PresentationContentItem:
    """Construct one content item, normalizing ``value`` when inapplicable."""
    effective_value = value if applicable else None
    return PresentationContentItem(
        key=key,
        label=label,
        value=effective_value,
        source=source,
        applicable=applicable,
        present=applicable and effective_value is not None,
        description=description,
    )


# ---------------------------------------------------------------------------
# Console-authored copy (all CONSOLE_EXPLANATION / FUTURE_CAPABILITY content)
# ---------------------------------------------------------------------------

_REQUEST_ID_OMITTED_DESCRIPTION = (
    "When omitted, the gateway defaults request_id to the generated correlation_id."
)

_NULL_EXPLANATION_NOTE = "No additional evaluator explanation was provided."

_NOT_APPLICABLE_NOTE = (
    "No policy bundle applied to this request's domain or scope. The gateway "
    "enforces this as a fail-closed disposition (HTTP 403, disposition=deny), "
    "but the kernel's outcome here — not_applicable — is distinct from an "
    "explicit or default policy denial: it means no bundle covered this "
    "request at all, not that a bundle evaluated it and said no."
)

_EVALUATION_TRACE_DESCRIPTION = (
    "An embedded evaluation trace is not returned by this endpoint today — its "
    "current contract always returns evaluation_trace as null/absent. This is "
    "not evidence that a trace exists or was evaluated locally."
)

_IDENTITY_PROCESSING_NOTE = (
    "The gateway authenticated this request before evaluation ran. Trusted-"
    "producer classification is a separate gateway processing stage. Neither "
    "the authenticated subject nor a live producer-trust classification is "
    "returned by this endpoint today, so neither is shown here as evidence — "
    "this note describes a processing stage, not a per-request result."
)

# One console-authored, one-line explanation per governed failure reason.
# Deliberately not a full teaching catalog (that is Training-mode scope,
# PR 5) — a single bounded sentence establishing that the failure is not a
# policy decision, consistent with every other note in this module.
_FAILURE_REASON_NOTES: dict[OperationAwareFailureReason, str] = {
    OperationAwareFailureReason.INVALID_REQUEST: (
        "The request shape did not satisfy the evaluator's contract. This is a "
        "structural problem, not a policy decision."
    ),
    OperationAwareFailureReason.UNSUPPORTED_SCHEMA_VERSION: (
        "The evaluator does not support this request's schema version. This is "
        "a version mismatch, not a policy decision."
    ),
    OperationAwareFailureReason.INVALID_POLICY_BUNDLE: (
        "The gateway's policy dependency is not in the state its startup check "
        "certified. This is a dependency-integrity problem discovered after "
        "startup, not a policy decision about this specific request."
    ),
    OperationAwareFailureReason.POLICY_VALIDATION_FAILURE: (
        "The loaded policy bundle failed validation at evaluation time. This is "
        "a dependency-integrity problem, not a policy decision about this "
        "specific request."
    ),
    OperationAwareFailureReason.CONDITION_EVALUATION_ERROR: (
        "A policy condition could not be evaluated for this request. This is a "
        "per-request evaluation-time failure, not a policy decision."
    ),
    OperationAwareFailureReason.INTERNAL_EVALUATION_ERROR: (
        "The evaluator failed unexpectedly while processing this request. This "
        "is an evaluation-time failure, not a policy decision."
    ),
}

# Client-level statuses for which a governed response exists (``result.response``
# is not ``None``). Used both to decide when identity/producer processing notes
# apply and, defensively, to check that a result's status and its response
# presence agree (see ``PresentationBuildError`` below).
_GOVERNED_RESULT_STATUSES = (
    OperationAwareEvaluationStatus.EVALUATION_COMPLETED,
    OperationAwareEvaluationStatus.EVALUATION_FAILED,
)


class PresentationBuildError(Exception):
    """Raised only when the typed result violates a documented internal invariant.

    Specifically: ``OperationAwareEvaluationResult.response`` must be present
    if and only if ``status`` is ``EVALUATION_COMPLETED`` or
    ``EVALUATION_FAILED`` (see that class's own docstring). A real
    ``GatewayClient.evaluate_operation_aware()`` result can never violate
    this — seeing this error means the contract between this module and
    ``basis_console.gateway.operation_aware_models`` has drifted and needs
    review, not that there is a data condition to render. This module never
    fabricates a fallback authorization result to paper over that case.
    """


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RequestSummarySection:
    """What was requested, built strictly from the typed request.

    Every item here is tagged ``ContentSource.SUBMITTED_INPUT`` — these are
    the exact values the console sent (or would send), not a gateway
    confirmation of them. Never tagged ``RETURNED_EVIDENCE``: the gateway may
    accept, reject, or (for ``request_id``) silently default any of them, and
    conflating "what we sent" with "what the gateway told us" would hide that.

    Deliberately excludes subject identity, roles, bearer-token information,
    arbitrary context, producer-only fields, policy information, and any
    correlation ID generated before one is returned by the gateway.
    """

    action: PresentationContentItem
    resource_type: PresentationContentItem
    resource_id: PresentationContentItem
    request_id: PresentationContentItem


@dataclass(frozen=True)
class EvaluationResultSection:
    """The governed (or absent) evaluation result, with every axis kept distinct.

    ``client_status`` (this call's client-level classification),
    ``kernel_evaluation_status`` (``completed``/``failed``), ``outcome``
    (``allow``/``deny``/``not_applicable``, present iff completed),
    ``disposition`` (``allow``/``deny``, gateway-surfaced), and
    ``http_status`` are five distinct facts never collapsed into one string
    or boolean.
    """

    client_status: PresentationContentItem
    http_status: PresentationContentItem
    kernel_evaluation_status: PresentationContentItem
    outcome: PresentationContentItem
    disposition: PresentationContentItem
    failure_reason: PresentationContentItem
    failure_reason_note: PresentationContentItem
    reason_code: PresentationContentItem
    explanation: PresentationContentItem
    explanation_note: PresentationContentItem


@dataclass(frozen=True)
class PolicyBundleSection:
    """Policy bundle identity, preserved whenever a governed response exists.

    Preserved on ``NOT_APPLICABLE`` and on a governed failure exactly as on
    ``ALLOW``/``DENY`` — this section never hides bundle identity based on
    outcome.
    """

    bundle_id: PresentationContentItem
    bundle_version: PresentationContentItem
    applicability_note: PresentationContentItem


@dataclass(frozen=True)
class EvidenceSection:
    """Correlation and identifier evidence, kept distinct per identifier kind.

    ``request_id`` here is the gateway-returned governed value (see
    :class:`RequestSummarySection` for the caller-supplied one, which may
    differ or be absent). ``trace_id`` and ``correlation_id`` are never
    treated as interchangeable.
    """

    request_id: PresentationContentItem
    correlation_id: PresentationContentItem
    trace_id: PresentationContentItem
    evaluation_trace: PresentationContentItem


@dataclass(frozen=True)
class RedactedDiagnostics:
    """Already-redacted diagnostic material, retained without reinterpretation.

    Populated only when no governed response exists (generic/client failures
    and contract-invalid results) — governed states already expose every
    fact through typed sections above. Never presented as evaluator evidence.
    """

    response_body: dict[str, object] | None
    headers: dict[str, str]


@dataclass(frozen=True)
class TransportSection:
    """Client-level/transport facts distinct from any governed decision."""

    called_gateway: bool
    timed_out: bool
    error_code: PresentationContentItem
    error_message: PresentationContentItem
    detail: PresentationContentItem
    status_explanation: PresentationContentItem
    diagnostics: RedactedDiagnostics | None


@dataclass(frozen=True)
class OperationAwarePresentation:
    """The complete, mode-independent presentation of one operation-aware call."""

    request_summary: RequestSummarySection
    evaluation_result: EvaluationResultSection
    policy_bundle: PolicyBundleSection
    evidence: EvidenceSection
    transport: TransportSection
    identity_processing_notes: tuple[PresentationContentItem, ...]


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_operation_aware_presentation(
    request: OperationAwareEvaluationRequest,
    result: OperationAwareEvaluationResult,
) -> OperationAwarePresentation:
    """Build the shared, mode-independent presentation for one evaluation call.

    Pure: no I/O, no configuration reads, no console-mode input, no mutation
    of ``request``/``result``. The same typed input always produces an equal
    output. Consumes ``result``'s existing classification as authoritative —
    never reparses ``result.response_json`` to derive new semantic fields.
    """
    if (result.status in _GOVERNED_RESULT_STATUSES) != (result.response is not None):
        raise PresentationBuildError(
            f"result.status ({result.status.value!r}) and result.response "
            f"presence ({result.response is not None}) are inconsistent; this "
            "violates OperationAwareEvaluationResult's documented invariant."
        )

    return OperationAwarePresentation(
        request_summary=_build_request_summary(request),
        evaluation_result=_build_evaluation_result(result, result.response),
        policy_bundle=_build_policy_bundle(result.response),
        evidence=_build_evidence(result, result.response),
        transport=_build_transport(result),
        identity_processing_notes=_build_identity_notes(result),
    )


def _build_request_summary(request: OperationAwareEvaluationRequest) -> RequestSummarySection:
    return RequestSummarySection(
        action=_item("request.action", "Action", request.action, ContentSource.SUBMITTED_INPUT),
        resource_type=_item(
            "request.resource_type",
            "Resource type",
            request.resource_type,
            ContentSource.SUBMITTED_INPUT,
        ),
        resource_id=_item(
            "request.resource_id",
            "Resource ID",
            request.resource_id,
            ContentSource.SUBMITTED_INPUT,
        ),
        request_id=_item(
            "request.request_id",
            "Caller-supplied request ID",
            request.request_id,
            ContentSource.SUBMITTED_INPUT,
            description=None if request.request_id else _REQUEST_ID_OMITTED_DESCRIPTION,
        ),
    )


def _build_evaluation_result(
    result: OperationAwareEvaluationResult,
    response: OperationAwareEvaluationResponse | None,
) -> EvaluationResultSection:
    client_status = _item(
        "result.status", "Client status", result.status.value, ContentSource.RETURNED_EVIDENCE
    )
    http_status = _item(
        "result.http_status",
        "HTTP status",
        str(result.http_status) if result.http_status is not None else None,
        ContentSource.RETURNED_EVIDENCE,
        applicable=result.http_status is not None,
    )

    if response is None:
        return EvaluationResultSection(
            client_status=client_status,
            http_status=http_status,
            kernel_evaluation_status=_item(
                "response.evaluation_status",
                "Kernel evaluation status",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            outcome=_item(
                "response.outcome",
                "Kernel outcome",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            disposition=_item(
                "response.disposition",
                "Gateway disposition",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            failure_reason=_item(
                "response.failure_reason",
                "Failure reason",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            failure_reason_note=_item(
                "presentation.failure_reason_note",
                "Failure reason explanation",
                None,
                ContentSource.CONSOLE_EXPLANATION,
                applicable=False,
            ),
            reason_code=_item(
                "response.reason_code",
                "Reason code",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            explanation=_item(
                "response.explanation",
                "Evaluator explanation",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            explanation_note=_item(
                "presentation.explanation_note",
                "Explanation note",
                None,
                ContentSource.CONSOLE_EXPLANATION,
                applicable=False,
            ),
        )

    kernel_evaluation_status = _item(
        "response.evaluation_status",
        "Kernel evaluation status",
        response.evaluation_status.value,
        ContentSource.RETURNED_EVIDENCE,
    )
    disposition = _item(
        "response.disposition",
        "Gateway disposition",
        response.disposition.value,
        ContentSource.RETURNED_EVIDENCE,
    )
    reason_code = _item(
        "response.reason_code", "Reason code", response.reason_code, ContentSource.RETURNED_EVIDENCE
    )
    explanation = _item(
        "response.explanation",
        "Evaluator explanation",
        response.explanation,
        ContentSource.RETURNED_EVIDENCE,
    )
    explanation_note = _item(
        "presentation.explanation_note",
        "Explanation note",
        None if response.explanation is not None else _NULL_EXPLANATION_NOTE,
        ContentSource.CONSOLE_EXPLANATION,
    )

    if response.evaluation_status is OperationAwareEvaluationState.COMPLETED:
        outcome = _item(
            "response.outcome",
            "Kernel outcome",
            response.outcome.value if response.outcome is not None else None,
            ContentSource.RETURNED_EVIDENCE,
        )
        failure_reason = _item(
            "response.failure_reason",
            "Failure reason",
            None,
            ContentSource.RETURNED_EVIDENCE,
            applicable=False,
        )
        failure_reason_note = _item(
            "presentation.failure_reason_note",
            "Failure reason explanation",
            None,
            ContentSource.CONSOLE_EXPLANATION,
            applicable=False,
        )
    else:
        outcome = _item(
            "response.outcome",
            "Kernel outcome",
            None,
            ContentSource.RETURNED_EVIDENCE,
            applicable=False,
        )
        failure_reason_value = response.failure_reason
        failure_reason = _item(
            "response.failure_reason",
            "Failure reason",
            failure_reason_value.value if failure_reason_value is not None else None,
            ContentSource.RETURNED_EVIDENCE,
        )
        failure_reason_note = _item(
            "presentation.failure_reason_note",
            "Failure reason explanation",
            _FAILURE_REASON_NOTES.get(failure_reason_value)
            if failure_reason_value is not None
            else None,
            ContentSource.CONSOLE_EXPLANATION,
        )

    return EvaluationResultSection(
        client_status=client_status,
        http_status=http_status,
        kernel_evaluation_status=kernel_evaluation_status,
        outcome=outcome,
        disposition=disposition,
        failure_reason=failure_reason,
        failure_reason_note=failure_reason_note,
        reason_code=reason_code,
        explanation=explanation,
        explanation_note=explanation_note,
    )


def _build_policy_bundle(
    response: OperationAwareEvaluationResponse | None,
) -> PolicyBundleSection:
    if response is None:
        return PolicyBundleSection(
            bundle_id=_item(
                "response.bundle_id",
                "Bundle ID",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            bundle_version=_item(
                "response.bundle_version",
                "Bundle version",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            applicability_note=_item(
                "presentation.applicability_note",
                "Applicability note",
                None,
                ContentSource.CONSOLE_EXPLANATION,
                applicable=False,
            ),
        )

    is_not_applicable = response.outcome is OperationAwareOutcome.NOT_APPLICABLE
    return PolicyBundleSection(
        bundle_id=_item(
            "response.bundle_id", "Bundle ID", response.bundle_id, ContentSource.RETURNED_EVIDENCE
        ),
        bundle_version=_item(
            "response.bundle_version",
            "Bundle version",
            response.bundle_version,
            ContentSource.RETURNED_EVIDENCE,
        ),
        applicability_note=_item(
            "presentation.applicability_note",
            "Applicability note",
            _NOT_APPLICABLE_NOTE if is_not_applicable else None,
            ContentSource.CONSOLE_EXPLANATION,
            applicable=is_not_applicable,
        ),
    )


def _build_evidence(
    result: OperationAwareEvaluationResult,
    response: OperationAwareEvaluationResponse | None,
) -> EvidenceSection:
    correlation_id = _item(
        "result.correlation_id",
        "Correlation ID",
        result.correlation_id,
        ContentSource.RETURNED_EVIDENCE,
    )
    if response is None:
        return EvidenceSection(
            request_id=_item(
                "response.request_id",
                "Request ID",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            correlation_id=correlation_id,
            trace_id=_item(
                "response.trace_id",
                "Trace ID",
                None,
                ContentSource.RETURNED_EVIDENCE,
                applicable=False,
            ),
            evaluation_trace=_item(
                "presentation.evaluation_trace",
                "Evaluation trace",
                None,
                ContentSource.FUTURE_CAPABILITY,
                description=_EVALUATION_TRACE_DESCRIPTION,
                applicable=False,
            ),
        )

    return EvidenceSection(
        request_id=_item(
            "response.request_id",
            "Request ID",
            response.request_id,
            ContentSource.RETURNED_EVIDENCE,
        ),
        correlation_id=correlation_id,
        trace_id=_item(
            "response.trace_id", "Trace ID", response.trace_id, ContentSource.RETURNED_EVIDENCE
        ),
        evaluation_trace=_item(
            "presentation.evaluation_trace",
            "Evaluation trace",
            None,
            ContentSource.FUTURE_CAPABILITY,
            description=_EVALUATION_TRACE_DESCRIPTION,
        ),
    )


def _build_transport(result: OperationAwareEvaluationResult) -> TransportSection:
    error_code = _item(
        "result.error_code", "Error code", result.error_code, ContentSource.RETURNED_EVIDENCE
    )
    error_message = _item(
        "result.error_message",
        "Error message",
        result.error_message,
        ContentSource.RETURNED_EVIDENCE,
    )
    # OperationAwareEvaluationResult.detail is documented as a console-side
    # note (never gateway-authored prose presented as a gateway field) — see
    # operation_aware_models.OperationAwareEvaluationResult's docstring.
    detail = _item(
        "result.detail", "Console diagnostic note", result.detail, ContentSource.CONSOLE_EXPLANATION
    )
    status_explanation = _item(
        "presentation.status_explanation",
        "Status explanation",
        result.explanation or None,
        ContentSource.CONSOLE_EXPLANATION,
    )

    diagnostics: RedactedDiagnostics | None = None
    if result.response is None and (result.response_json is not None or result.headers):
        diagnostics = RedactedDiagnostics(
            response_body=result.response_json, headers=dict(result.headers)
        )

    return TransportSection(
        called_gateway=result.called_gateway,
        timed_out=result.timed_out,
        error_code=error_code,
        error_message=error_message,
        detail=detail,
        status_explanation=status_explanation,
        diagnostics=diagnostics,
    )


def _build_identity_notes(
    result: OperationAwareEvaluationResult,
) -> tuple[PresentationContentItem, ...]:
    """Console-authored identity/producer processing-stage note.

    Shown only when a governed response actually came back (completed or
    failed evaluation) — the one condition the integration plan (§7.1)
    identifies as a true, HTTP-exchange-derivable statement ("the gateway
    authenticated the request when the request reaches evaluation"). Omitted
    for every other status, including CAPABILITY_UNAVAILABLE/UNAUTHORIZED/etc.,
    where no such statement can be made without inference.
    """
    if result.status not in _GOVERNED_RESULT_STATUSES:
        return ()
    return (
        _item(
            "presentation.identity_processing_note",
            "Identity and producer processing",
            _IDENTITY_PROCESSING_NOTE,
            ContentSource.CONSOLE_EXPLANATION,
        ),
    )
