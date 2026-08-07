"""Unit tests for the shared operation-aware presentation model (PR 3).

Builds directly against PR 2's typed request/result objects — no HTTP mocking
(that belongs to ``test_gateway_evaluate_operation_aware.py``) and no route or
template involvement (none exists yet).
"""

from __future__ import annotations

import dataclasses
import inspect

import pytest

from basis_console.gateway import (
    OperationAwareDisposition,
    OperationAwareEvaluationRequest,
    OperationAwareEvaluationResponse,
    OperationAwareEvaluationResult,
    OperationAwareEvaluationState,
    OperationAwareEvaluationStatus,
    OperationAwareFailureReason,
    OperationAwareOutcome,
)
from basis_console.operation_aware_presentation import (
    ContentSource,
    EvaluationResultSection,
    EvidenceSection,
    OperationAwarePresentation,
    PolicyBundleSection,
    PresentationBuildError,
    PresentationContentItem,
    RequestSummarySection,
    TransportSection,
    build_operation_aware_presentation,
)

# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _request(**overrides: object) -> OperationAwareEvaluationRequest:
    defaults: dict[str, object] = {
        "action": "read",
        "resource_type": "ahu",
        "resource_id": "rooftop-1",
        "request_id": None,
    }
    defaults.update(overrides)
    return OperationAwareEvaluationRequest(**defaults)  # type: ignore[arg-type]


def _allow_response(**overrides: object) -> OperationAwareEvaluationResponse:
    defaults: dict[str, object] = {
        "request_id": "req-1",
        "evaluation_status": OperationAwareEvaluationState.COMPLETED,
        "disposition": OperationAwareDisposition.ALLOW,
        "correlation_id": "corr-1",
        "outcome": OperationAwareOutcome.ALLOW,
        "failure_reason": None,
        "bundle_id": "site-a-bundle",
        "bundle_version": "1.0.0",
        "trace_id": "trace-1",
        "reason_code": "ALLOW_RULE_MATCHED",
        "explanation": "Matched an allow rule.",
    }
    defaults.update(overrides)
    return OperationAwareEvaluationResponse(**defaults)  # type: ignore[arg-type]


def _governed_failure_response(
    failure_reason: OperationAwareFailureReason, **overrides: object
) -> OperationAwareEvaluationResponse:
    defaults: dict[str, object] = {
        "request_id": "req-f",
        "evaluation_status": OperationAwareEvaluationState.FAILED,
        "disposition": OperationAwareDisposition.DENY,
        "correlation_id": "corr-f",
        "outcome": None,
        "failure_reason": failure_reason,
        "bundle_id": "site-a-bundle",
        "bundle_version": "1.0.0",
    }
    defaults.update(overrides)
    return OperationAwareEvaluationResponse(**defaults)  # type: ignore[arg-type]


def _completed_result(
    response: OperationAwareEvaluationResponse, http_status: int = 200
) -> OperationAwareEvaluationResult:
    return OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.EVALUATION_COMPLETED,
        http_status=http_status,
        response=response,
        correlation_id=response.correlation_id,
    )


def _failed_result(
    response: OperationAwareEvaluationResponse, http_status: int
) -> OperationAwareEvaluationResult:
    return OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.EVALUATION_FAILED,
        http_status=http_status,
        response=response,
        correlation_id=response.correlation_id,
    )


ALL_SECTION_TYPES = (
    RequestSummarySection,
    EvaluationResultSection,
    PolicyBundleSection,
    EvidenceSection,
    TransportSection,
)


# ---------------------------------------------------------------------------
# Core construction
# ---------------------------------------------------------------------------


def test_builder_is_deterministic():
    request = _request()
    result = _completed_result(_allow_response())
    first = build_operation_aware_presentation(request, result)
    second = build_operation_aware_presentation(request, result)
    assert first == second


def test_builder_does_not_mutate_inputs():
    request = _request()
    response = _allow_response()
    result = _completed_result(response)
    request_before = dataclasses.replace(request)
    result_before = dataclasses.replace(result)

    build_operation_aware_presentation(request, result)

    assert request == request_before
    assert result == result_before


def test_presentation_and_sections_are_frozen():
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        presentation.evidence = presentation.evidence  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        presentation.evaluation_result.outcome = presentation.evaluation_result.outcome  # type: ignore[misc]


def test_builder_accepts_no_mode_parameter():
    params = list(inspect.signature(build_operation_aware_presentation).parameters)
    assert params == ["request", "result"]


def test_same_typed_input_always_equal_output():
    request = _request(resource_id="rooftop-2")
    response = _governed_failure_response(OperationAwareFailureReason.CONDITION_EVALUATION_ERROR)
    result = _failed_result(response, http_status=500)
    assert build_operation_aware_presentation(
        request, result
    ) == build_operation_aware_presentation(request, result)


def test_impossible_state_raises_presentation_build_error():
    # status claims a governed response but none is attached — cannot happen
    # from a real GatewayClient.evaluate_operation_aware() call; the builder
    # must fail clearly rather than fabricate a fallback result.
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.EVALUATION_COMPLETED, response=None
    )
    with pytest.raises(PresentationBuildError):
        build_operation_aware_presentation(_request(), result)

    # And the inverse: a response attached but a non-governed status.
    result2 = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.GATEWAY_ERROR, response=_allow_response()
    )
    with pytest.raises(PresentationBuildError):
        build_operation_aware_presentation(_request(), result2)


# ---------------------------------------------------------------------------
# Completed ALLOW
# ---------------------------------------------------------------------------


def test_completed_allow_preserves_semantics():
    request = _request()
    response = _allow_response()
    result = _completed_result(response, http_status=200)
    presentation = build_operation_aware_presentation(request, result)

    rs = presentation.request_summary
    assert rs.action.value == "read"
    assert rs.resource_type.value == "ahu"
    assert rs.resource_id.value == "rooftop-1"

    er = presentation.evaluation_result
    assert er.client_status.value == "evaluation_completed"
    assert er.http_status.value == "200"
    assert er.kernel_evaluation_status.value == "completed"
    assert er.outcome.value == "allow"
    assert er.outcome.applicable and er.outcome.present
    assert er.disposition.value == "allow"
    assert not er.failure_reason.applicable
    assert not er.failure_reason_note.applicable
    assert er.explanation.value == "Matched an allow rule."
    assert not er.explanation_note.present

    pb = presentation.policy_bundle
    assert pb.bundle_id.value == "site-a-bundle"
    assert pb.bundle_version.value == "1.0.0"
    assert not pb.applicability_note.applicable

    ev = presentation.evidence
    assert ev.request_id.value == "req-1"
    assert ev.correlation_id.value == "corr-1"
    assert ev.trace_id.value == "trace-1"
    assert ev.evaluation_trace.applicable
    assert not ev.evaluation_trace.present

    # No invented evidence anywhere: nothing in this response sets a
    # console_explanation-sourced *primary* result field.
    assert er.outcome.source is ContentSource.RETURNED_EVIDENCE
    assert er.disposition.source is ContentSource.RETURNED_EVIDENCE


# ---------------------------------------------------------------------------
# Completed DENY
# ---------------------------------------------------------------------------


def test_completed_deny_preserves_semantics():
    response = _allow_response(
        outcome=OperationAwareOutcome.DENY,
        disposition=OperationAwareDisposition.DENY,
        reason_code="NO_ALLOW_RULE_MATCHED",
    )
    result = _completed_result(response, http_status=403)
    presentation = build_operation_aware_presentation(_request(), result)

    er = presentation.evaluation_result
    assert er.outcome.value == "deny"
    assert er.disposition.value == "deny"
    assert er.reason_code.value == "NO_ALLOW_RULE_MATCHED"
    assert er.reason_code.source is ContentSource.RETURNED_EVIDENCE

    # No field on the model claims explicit-deny vs default-deny; the only
    # sub-cause information is whatever reason_code carries verbatim.
    assert not hasattr(er, "deny_cause")
    assert not er.explanation_note.present  # no explanation was invented


# ---------------------------------------------------------------------------
# Completed NOT_APPLICABLE
# ---------------------------------------------------------------------------


def test_completed_not_applicable_preserves_semantics():
    response = _allow_response(
        outcome=OperationAwareOutcome.NOT_APPLICABLE,
        disposition=OperationAwareDisposition.DENY,
        explanation=None,
        reason_code=None,
    )
    result = _completed_result(response, http_status=403)
    presentation = build_operation_aware_presentation(_request(), result)

    er = presentation.evaluation_result
    assert er.outcome.value == "not_applicable"
    assert er.outcome.value != "deny"
    assert er.disposition.value == "deny"
    assert er.http_status.value == "403"

    pb = presentation.policy_bundle
    assert pb.bundle_id.value == "site-a-bundle"
    assert pb.bundle_version.value == "1.0.0"
    assert pb.applicability_note.applicable
    assert pb.applicability_note.present
    assert pb.applicability_note.source is ContentSource.CONSOLE_EXPLANATION
    assert pb.applicability_note.value  # non-empty console-authored prose


# ---------------------------------------------------------------------------
# Governed failures
# ---------------------------------------------------------------------------


GOVERNED_FAILURES = [
    (OperationAwareFailureReason.INVALID_REQUEST, 400),
    (OperationAwareFailureReason.UNSUPPORTED_SCHEMA_VERSION, 400),
    (OperationAwareFailureReason.INVALID_POLICY_BUNDLE, 503),
    (OperationAwareFailureReason.POLICY_VALIDATION_FAILURE, 503),
    (OperationAwareFailureReason.CONDITION_EVALUATION_ERROR, 500),
    (OperationAwareFailureReason.INTERNAL_EVALUATION_ERROR, 500),
]


@pytest.mark.parametrize("failure_reason,http_status", GOVERNED_FAILURES)
def test_governed_failure_preserves_semantics(failure_reason, http_status):
    response = _governed_failure_response(failure_reason)
    result = _failed_result(response, http_status=http_status)
    presentation = build_operation_aware_presentation(_request(), result)

    er = presentation.evaluation_result
    assert er.failure_reason.value == failure_reason.value
    assert er.failure_reason.source is ContentSource.RETURNED_EVIDENCE
    assert not er.outcome.applicable
    assert er.http_status.value == str(http_status)
    assert er.kernel_evaluation_status.value == "failed"

    assert er.failure_reason_note.present
    assert er.failure_reason_note.source is ContentSource.CONSOLE_EXPLANATION

    # Bundle identity preserved on a governed failure exactly as on success.
    pb = presentation.policy_bundle
    assert pb.bundle_id.value == "site-a-bundle"
    assert pb.bundle_version.value == "1.0.0"

    # Never classified as a policy denial: no field asserts a decision, and
    # client_status stays EVALUATION_FAILED, not EVALUATION_COMPLETED/DENIED.
    assert er.client_status.value == "evaluation_failed"


def test_governed_failure_on_400_is_not_generic_validation_rejection():
    response = _governed_failure_response(OperationAwareFailureReason.INVALID_REQUEST)
    result = _failed_result(response, http_status=400)
    presentation = build_operation_aware_presentation(_request(), result)
    assert presentation.evaluation_result.client_status.value == "evaluation_failed"
    assert presentation.evaluation_result.failure_reason.present


def test_generic_validation_rejection_on_400_is_not_governed_failure():
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.REQUEST_REJECTED,
        http_status=400,
        error_code="validation_failed",
        error_message="bad request",
    )
    presentation = build_operation_aware_presentation(_request(), result)
    er = presentation.evaluation_result
    assert er.client_status.value == "request_rejected"
    assert not er.failure_reason.applicable
    assert not er.outcome.applicable


def test_governed_failure_on_503_is_not_simple_gateway_unavailability():
    response = _governed_failure_response(OperationAwareFailureReason.INVALID_POLICY_BUNDLE)
    result = _failed_result(response, http_status=503)
    presentation = build_operation_aware_presentation(_request(), result)
    assert presentation.evaluation_result.client_status.value == "evaluation_failed"
    assert presentation.evaluation_result.failure_reason.value == "invalid_policy_bundle"


def test_generic_evaluator_unavailable_503_has_no_governed_decision():
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.EVALUATOR_UNAVAILABLE,
        http_status=503,
        error_code="evaluator_unavailable",
        error_message="Evaluator not initialized",
    )
    presentation = build_operation_aware_presentation(_request(), result)
    er = presentation.evaluation_result
    assert not er.failure_reason.applicable
    assert not er.outcome.applicable
    assert not er.disposition.applicable


def test_contract_invalid_not_displayed_as_failure_or_denial():
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.CONTRACT_INVALID,
        http_status=403,
        detail="HTTP 403 response carried no governed evaluation body",
    )
    presentation = build_operation_aware_presentation(_request(), result)
    er = presentation.evaluation_result
    assert not er.outcome.applicable
    assert not er.disposition.applicable
    assert not er.failure_reason.applicable
    assert presentation.transport.detail.value == (
        "HTTP 403 response carried no governed evaluation body"
    )
    assert presentation.transport.detail.source is ContentSource.CONSOLE_EXPLANATION


# ---------------------------------------------------------------------------
# Generic / client failures
# ---------------------------------------------------------------------------


NO_CALL_STATUSES = [
    OperationAwareEvaluationStatus.NOT_CONFIGURED,
    OperationAwareEvaluationStatus.TOKEN_MISSING,
]

CALLED_GENERIC_STATUSES = [
    OperationAwareEvaluationStatus.UNAUTHORIZED,
    OperationAwareEvaluationStatus.CAPABILITY_UNAVAILABLE,
    OperationAwareEvaluationStatus.REQUEST_REJECTED,
    OperationAwareEvaluationStatus.EVALUATOR_UNAVAILABLE,
    OperationAwareEvaluationStatus.CONTRACT_INVALID,
    OperationAwareEvaluationStatus.UNAVAILABLE,
    OperationAwareEvaluationStatus.GATEWAY_ERROR,
]


@pytest.mark.parametrize("status", NO_CALL_STATUSES)
def test_no_call_statuses_have_no_governed_decision(status):
    result = OperationAwareEvaluationResult(status=status)
    presentation = build_operation_aware_presentation(_request(), result)
    er = presentation.evaluation_result
    assert not er.outcome.applicable
    assert not er.disposition.applicable
    assert not er.failure_reason.applicable
    assert not presentation.policy_bundle.bundle_id.applicable
    assert er.explanation.value is None
    assert presentation.transport.status_explanation.present
    assert presentation.transport.status_explanation.source is ContentSource.CONSOLE_EXPLANATION
    assert presentation.identity_processing_notes == ()
    assert not presentation.transport.called_gateway


@pytest.mark.parametrize("status", CALLED_GENERIC_STATUSES)
def test_called_generic_statuses_have_no_governed_decision(status):
    result = OperationAwareEvaluationResult(
        status=status,
        http_status=418,  # arbitrary but present; exact code not the point here
        error_code="some_error",
        error_message="some message",
        detail="console-side note"
        if status == OperationAwareEvaluationStatus.CONTRACT_INVALID
        else None,
        response_json={"error": "some_error"},
        headers={"content-type": "application/json"},
    )
    presentation = build_operation_aware_presentation(_request(), result)
    er = presentation.evaluation_result
    assert not er.outcome.applicable
    assert not er.disposition.applicable
    assert not er.failure_reason.applicable
    assert not presentation.policy_bundle.bundle_id.applicable
    assert not presentation.policy_bundle.bundle_version.applicable
    assert not presentation.evidence.request_id.applicable
    assert presentation.transport.status_explanation.present
    assert presentation.identity_processing_notes == ()

    # Error code/message are relayed as returned evidence (from the gateway's
    # generic ErrorResponse body), never invented.
    assert presentation.transport.error_code.value == "some_error"
    assert presentation.transport.error_code.source is ContentSource.RETURNED_EVIDENCE
    assert presentation.transport.error_message.source is ContentSource.RETURNED_EVIDENCE

    # Diagnostics remain redacted diagnostic material, not evidence.
    diagnostics = presentation.transport.diagnostics
    assert diagnostics is not None
    assert diagnostics.response_body == {"error": "some_error"}
    assert diagnostics.headers == {"content-type": "application/json"}


# ---------------------------------------------------------------------------
# Null / optional evidence
# ---------------------------------------------------------------------------


def test_null_explanation_produces_console_note_not_fabricated_evidence():
    response = _allow_response(explanation=None)
    presentation = build_operation_aware_presentation(_request(), _completed_result(response))
    er = presentation.evaluation_result
    assert er.explanation.value is None
    assert er.explanation.applicable
    assert not er.explanation.present
    assert er.explanation_note.present
    assert "No additional evaluator explanation" in (er.explanation_note.value or "")
    assert er.explanation_note.source is ContentSource.CONSOLE_EXPLANATION
    assert er.explanation.value != er.explanation_note.value


def test_present_explanation_produces_no_console_note():
    response = _allow_response(explanation="Matched allow rule X.")
    presentation = build_operation_aware_presentation(_request(), _completed_result(response))
    er = presentation.evaluation_result
    assert er.explanation.value == "Matched allow rule X."
    assert not er.explanation_note.present


def test_absent_reason_code_preserved():
    response = _allow_response(reason_code=None)
    presentation = build_operation_aware_presentation(_request(), _completed_result(response))
    rc = presentation.evaluation_result.reason_code
    assert rc.value is None
    assert rc.applicable
    assert not rc.present


def test_absent_bundle_identity_preserved():
    response = _allow_response(bundle_id=None, bundle_version=None)
    presentation = build_operation_aware_presentation(_request(), _completed_result(response))
    pb = presentation.policy_bundle
    assert pb.bundle_id.value is None
    assert pb.bundle_id.applicable
    assert not pb.bundle_id.present
    assert pb.bundle_version.value is None


def test_absent_trace_id_preserved():
    response = _allow_response(trace_id=None)
    presentation = build_operation_aware_presentation(_request(), _completed_result(response))
    trace = presentation.evidence.trace_id
    assert trace.value is None
    assert trace.applicable
    assert not trace.present


def test_absent_correlation_id_preserved():
    response = _allow_response(correlation_id=None)
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.EVALUATION_COMPLETED,
        http_status=200,
        response=response,
        correlation_id=None,
    )
    presentation = build_operation_aware_presentation(_request(), result)
    assert presentation.evidence.correlation_id.value is None


def test_evaluation_trace_absent_for_every_governed_state():
    allow_presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    failed_presentation = build_operation_aware_presentation(
        _request(),
        _failed_result(
            _governed_failure_response(OperationAwareFailureReason.INTERNAL_EVALUATION_ERROR), 500
        ),
    )
    for presentation in (allow_presentation, failed_presentation):
        et = presentation.evidence.evaluation_trace
        assert et.source is ContentSource.FUTURE_CAPABILITY
        assert not et.present
        assert et.applicable


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_returned_evidence_items_tagged_correctly():
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    for item in (
        presentation.evaluation_result.client_status,
        presentation.evaluation_result.http_status,
        presentation.evaluation_result.kernel_evaluation_status,
        presentation.evaluation_result.outcome,
        presentation.evaluation_result.disposition,
        presentation.evaluation_result.reason_code,
        presentation.evaluation_result.explanation,
        presentation.policy_bundle.bundle_id,
        presentation.policy_bundle.bundle_version,
        presentation.evidence.request_id,
        presentation.evidence.correlation_id,
        presentation.evidence.trace_id,
        presentation.transport.error_code,
        presentation.transport.error_message,
    ):
        assert item.source is ContentSource.RETURNED_EVIDENCE


def test_request_summary_items_tagged_submitted_input():
    request = _request(request_id="caller-req-1")
    presentation = build_operation_aware_presentation(request, _completed_result(_allow_response()))
    rs = presentation.request_summary
    for item in (rs.action, rs.resource_type, rs.resource_id, rs.request_id):
        assert item.source is ContentSource.SUBMITTED_INPUT


def test_no_request_summary_field_is_tagged_returned_evidence():
    # Submitted values must never be presented as if the gateway confirmed or
    # returned them — action/resource_type/resource_id/request_id are what
    # the console sent, not evidence the gateway gave back.
    request = _request(request_id="caller-req-1")
    presentation = build_operation_aware_presentation(request, _completed_result(_allow_response()))
    for field in dataclasses.fields(presentation.request_summary):
        item = getattr(presentation.request_summary, field.name)
        assert item.source is not ContentSource.RETURNED_EVIDENCE
        assert item.source is not ContentSource.CONSOLE_EXPLANATION
        assert item.source is not ContentSource.FUTURE_CAPABILITY


def test_all_four_provenance_categories_are_distinct_and_all_used():
    # A NOT_APPLICABLE, null-explanation presentation exercises every
    # category in one pass: submitted request fields, returned governed
    # fields, console-authored notes, and the future-capability trace item.
    response = _allow_response(outcome=OperationAwareOutcome.NOT_APPLICABLE, explanation=None)
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(response, http_status=403)
    )

    observed_sources: dict[ContentSource, list[str]] = {source: [] for source in ContentSource}
    for section in (
        presentation.request_summary,
        presentation.evaluation_result,
        presentation.policy_bundle,
        presentation.evidence,
        presentation.transport,
    ):
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            if isinstance(value, PresentationContentItem):
                observed_sources[value.source].append(f"{type(section).__name__}.{field.name}")
    for note in presentation.identity_processing_notes:
        observed_sources[note.source].append("identity_processing_notes")

    # All four categories are exactly the enum's four values, and each was
    # exercised at least once by this single presentation.
    assert set(observed_sources) == {
        ContentSource.SUBMITTED_INPUT,
        ContentSource.RETURNED_EVIDENCE,
        ContentSource.CONSOLE_EXPLANATION,
        ContentSource.FUTURE_CAPABILITY,
    }
    for source, items in observed_sources.items():
        assert items, f"no item in this presentation used {source!r}"

    # And request-summary items are exclusively SUBMITTED_INPUT.
    for field in dataclasses.fields(presentation.request_summary):
        item = getattr(presentation.request_summary, field.name)
        assert item.source is ContentSource.SUBMITTED_INPUT


def test_console_explanation_items_tagged_correctly():
    response = _allow_response(outcome=OperationAwareOutcome.NOT_APPLICABLE, explanation=None)
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(response, http_status=403)
    )
    for item in (
        presentation.policy_bundle.applicability_note,
        presentation.evaluation_result.explanation_note,
        presentation.transport.status_explanation,
        presentation.identity_processing_notes[0],
    ):
        assert item.source is ContentSource.CONSOLE_EXPLANATION


def test_future_capability_tag_used_only_for_evaluation_trace():
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    assert presentation.evidence.evaluation_trace.source is ContentSource.FUTURE_CAPABILITY
    # No other item anywhere in the model uses this tag.
    for section in (
        presentation.request_summary,
        presentation.evaluation_result,
        presentation.policy_bundle,
        presentation.transport,
    ):
        for field in dataclasses.fields(section):
            value = getattr(section, field.name)
            if isinstance(value, PresentationContentItem):
                assert value.source is not ContentSource.FUTURE_CAPABILITY


def test_console_copy_never_occupies_returned_explanation_field():
    response = _allow_response(explanation=None)
    presentation = build_operation_aware_presentation(_request(), _completed_result(response))
    er = presentation.evaluation_result
    assert er.explanation.value is None
    assert er.explanation.source is ContentSource.RETURNED_EVIDENCE
    assert er.explanation_note.value is not None
    assert er.explanation_note.source is ContentSource.CONSOLE_EXPLANATION


def test_generic_diagnostic_material_is_not_kernel_evidence():
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.GATEWAY_ERROR,
        http_status=500,
        response_json={"detail": "internal error"},
        headers={"x-request-id": "abc"},
    )
    presentation = build_operation_aware_presentation(_request(), result)
    diagnostics = presentation.transport.diagnostics
    assert diagnostics is not None
    assert diagnostics.response_body == {"detail": "internal error"}
    # RedactedDiagnostics is not a PresentationContentItem and carries no
    # ContentSource tag — it is structurally excluded from ever being read as
    # RETURNED_EVIDENCE by a template that only walks tagged items.
    assert not isinstance(diagnostics, PresentationContentItem)


# ---------------------------------------------------------------------------
# Identity boundaries
# ---------------------------------------------------------------------------


def test_no_subject_field_anywhere_in_presentation():
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    for section in (
        presentation,
        presentation.request_summary,
        presentation.evaluation_result,
        presentation.policy_bundle,
        presentation.evidence,
        presentation.transport,
    ):
        for field in dataclasses.fields(section):
            assert "subject" not in field.name


def test_no_producer_classification_field_anywhere_in_presentation():
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    for section in (
        presentation,
        presentation.request_summary,
        presentation.evaluation_result,
        presentation.policy_bundle,
        presentation.evidence,
        presentation.transport,
    ):
        for field in dataclasses.fields(section):
            assert "producer" not in field.name


def test_result_model_carries_no_token_field():
    # Structural guarantee that no bearer-token value could ever reach this
    # presentation layer via OperationAwareEvaluationResult in the first place.
    assert not any("token" in f.name for f in dataclasses.fields(OperationAwareEvaluationResult))


def test_identity_note_is_console_explanation_and_processing_stage_only():
    presentation = build_operation_aware_presentation(
        _request(), _completed_result(_allow_response())
    )
    assert len(presentation.identity_processing_notes) == 1
    note = presentation.identity_processing_notes[0]
    assert note.source is ContentSource.CONSOLE_EXPLANATION
    assert note.value is not None
    assert "processing stage" in note.value


def test_identity_note_present_on_governed_failure_too():
    response = _governed_failure_response(OperationAwareFailureReason.INTERNAL_EVALUATION_ERROR)
    presentation = build_operation_aware_presentation(_request(), _failed_result(response, 500))
    assert len(presentation.identity_processing_notes) == 1


def test_identity_note_absent_without_a_governed_response():
    result = OperationAwareEvaluationResult(
        status=OperationAwareEvaluationStatus.UNAUTHORIZED, http_status=401
    )
    presentation = build_operation_aware_presentation(_request(), result)
    assert presentation.identity_processing_notes == ()


# ---------------------------------------------------------------------------
# Mode independence
# ---------------------------------------------------------------------------


def test_builder_signature_has_exactly_request_and_result():
    params = list(inspect.signature(build_operation_aware_presentation).parameters)
    assert params == ["request", "result"]
    assert "console_mode" not in params
    assert "is_training_mode" not in params
    assert "mode" not in params


def test_no_dataclass_in_module_has_a_mode_field():
    for cls in (
        OperationAwarePresentation,
        RequestSummarySection,
        EvaluationResultSection,
        PolicyBundleSection,
        EvidenceSection,
        TransportSection,
        PresentationContentItem,
    ):
        for field in dataclasses.fields(cls):
            assert "mode" not in field.name


def test_output_suitable_for_both_modes_without_reevaluation():
    # The same object, built once, contains everything both Operator's
    # concise view and Training's fuller view would need — no second build
    # call or additional gateway interaction is implied by this test's
    # existence (there is none available for it to call).
    request = _request()
    result = _completed_result(_allow_response())
    presentation = build_operation_aware_presentation(request, result)
    same_presentation_again = build_operation_aware_presentation(request, result)
    assert presentation == same_presentation_again
