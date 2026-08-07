"""Unit tests for GatewayClient.evaluate_operation_aware() (mocked HTTP — no live gateway).

Fixtures are drawn verbatim from ``basis-gateway/docs/operation-aware-endpoint.md``'s
worked examples (Allow / Explicit deny / Default deny / Not applicable / Failed
evaluation / Untrusted-producer-context-rejected / Evaluator unavailable) where the
doc supplies one, and from the same documented field shape for the remaining
governed failure reasons the doc's "Limitations" section notes are not reachable
through a live gateway-to-kernel path in that repository's own suite (their HTTP
classification is fully specified in
``basis_gateway.api.operation_aware_classification`` and reused here unchanged).

Mirrors the structure and discipline of ``test_gateway_evaluate.py``: mocked HTTP
transport, no live gateway, explicit assertions that the Bearer token never leaks.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable

import httpx
import pytest

from basis_console.gateway import (
    GatewayClient,
    OperationAwareDisposition,
    OperationAwareEvaluationRequest,
    OperationAwareEvaluationState,
    OperationAwareEvaluationStatus,
    OperationAwareOutcome,
)

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "secret-token-value-do-not-leak"


def _client(handler: Handler, *, base_url: str | None = GATEWAY_URL, token: str | None = TOKEN):
    transport = httpx.MockTransport(handler)
    return GatewayClient(base_url=base_url, bearer_token=token, transport=transport)


def _json_response(
    status: int, payload: dict[str, object], **headers: str
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers or None)

    return handler


# ---------------------------------------------------------------------------
# Canonical fixtures — verbatim from operation-aware-endpoint.md, plus the
# remaining governed failure reasons built from the same documented shape.
# ---------------------------------------------------------------------------

ALLOW_BODY = {
    "request_id": "c9d8e7f6-0000-0000-0000-000000000000",
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000000",
    "evaluation_status": "completed",
    "outcome": "allow",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "trace_id": "b1e2f3a4-0000-0000-0000-000000000000",
    "disposition": "allow",
}

EXPLICIT_DENY_BODY = {
    "request_id": "c9d8e7f6-0000-0000-0000-000000000001",
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000001",
    "evaluation_status": "completed",
    "outcome": "deny",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "trace_id": "b1e2f3a4-0000-0000-0000-000000000001",
    "disposition": "deny",
}

DEFAULT_DENY_BODY = {
    "request_id": "c9d8e7f6-0000-0000-0000-000000000002",
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000002",
    "evaluation_status": "completed",
    "outcome": "deny",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "trace_id": "b1e2f3a4-0000-0000-0000-000000000002",
    "disposition": "deny",
}

NOT_APPLICABLE_BODY = {
    "request_id": "c9d8e7f6-0000-0000-0000-000000000003",
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000003",
    "evaluation_status": "completed",
    "outcome": "not_applicable",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "trace_id": "b1e2f3a4-0000-0000-0000-000000000003",
    "disposition": "deny",
}

POLICY_VALIDATION_FAILURE_BODY = {
    "request_id": "c9d8e7f6-0000-0000-0000-000000000004",
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000004",
    "evaluation_status": "failed",
    "failure_reason": "policy_validation_failure",
    "disposition": "deny",
}

UNTRUSTED_PRODUCER_CONTEXT_REJECTED_BODY = {
    "error": "validation_failed",
    "message": (
        "caller is not a classified operation producer and may not supply "
        "operation-producer-only field(s): operation_intent"
    ),
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000005",
}

EVALUATOR_UNAVAILABLE_BODY = {
    "error": "evaluator_unavailable",
    "message": "Evaluator not initialized",
    "correlation_id": "c9d8e7f6-0000-0000-0000-000000000006",
}


def _governed_failure_body(failure_reason: str, request_id: str) -> dict[str, object]:
    """Build a governed failure body in the exact documented shape.

    Same field shape as ``POLICY_VALIDATION_FAILURE_BODY`` (the one worked
    failure example the endpoint doc provides) — only ``failure_reason`` and
    ``request_id``/``correlation_id`` vary, per
    ``basis_gateway.api.operation_aware_classification``'s exhaustive mapping.
    Disposition is always ``"deny"`` on a failed evaluation (endpoint doc,
    "Semantic outcome matrix": ``failed -> (null outcome) -> deny``).
    """
    return {
        "request_id": request_id,
        "correlation_id": request_id,
        "evaluation_status": "failed",
        "failure_reason": failure_reason,
        "disposition": "deny",
    }


# ---------------------------------------------------------------------------
# Prerequisites: no call without base URL / token
# ---------------------------------------------------------------------------


def test_not_configured_returns_not_configured():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json=ALLOW_BODY)

    client = GatewayClient(
        base_url=None, bearer_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    result = client.evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))

    assert result.status is OperationAwareEvaluationStatus.NOT_CONFIGURED
    assert result.called_gateway is False
    assert result.response is None
    assert calls == []


def test_missing_token_returns_token_missing():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json=ALLOW_BODY)

    client = GatewayClient(
        base_url=GATEWAY_URL, bearer_token=None, transport=httpx.MockTransport(handler)
    )
    result = client.evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))

    assert result.status is OperationAwareEvaluationStatus.TOKEN_MISSING
    assert result.called_gateway is False
    assert calls == []


# ---------------------------------------------------------------------------
# Request shape + identity boundary
# ---------------------------------------------------------------------------


def test_sends_bearer_token_to_exact_endpoint():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read:ahu", resource_id="ahu:rooftop-1")
    )

    assert seen["path"] == "/v1/evaluate/operation-aware"
    assert seen["auth"] == f"Bearer {TOKEN}"
    assert seen["body"] == {"action": "read:ahu", "resource_id": "ahu:rooftop-1"}


def test_minimum_valid_request_body():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert seen["body"] == {"action": "read"}


def test_omits_optional_fields_when_absent():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read", resource_type=None, resource_id=None)
    )
    body = seen["body"]
    assert "resource_type" not in body
    assert "resource_id" not in body
    assert "request_id" not in body
    assert "context" not in body


def test_includes_resource_type_and_resource_id_when_set():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read", resource_type="ahu", resource_id="rooftop-1")
    )
    assert seen["body"] == {"action": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}


def test_includes_request_id_when_set():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read", request_id="console-req-1")
    )
    assert seen["body"] == {"action": "read", "request_id": "console-req-1"}


def test_body_never_contains_context_subject_or_producer_fields():
    """Defensive: the console has no field capable of setting these, but assert
    the serialized body never carries context, a subject, or any of the nine
    trusted-producer-only fields regardless of what the request model exposes."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(
            action="read", resource_type="ahu", resource_id="rooftop-1", request_id="r1"
        )
    )
    body = seen["body"]
    forbidden_keys = {
        "context",
        "subject_id",
        "subject_roles",
        "subject_attrs",
        "identity_source",
        "authority_mode",
        "operation_intent",
        "location",
        "device",
        "protocol_context",
        "safety_context",
        "environment_context",
        "risk_context",
        "identity_evidence_reference",
        "adapter_evidence_reference",
        "expected_policy_version",
        "evaluation_status",
        "outcome",
        "failure_reason",
        "disposition",
        "bundle_id",
        "bundle_version",
    }
    assert forbidden_keys.isdisjoint(body)


def test_request_model_has_no_settable_context_field():
    """The request model's own type surface makes a context field impossible to
    set — this is a static/structural assertion, not just a serialization test."""
    field_names = {f.name for f in dataclasses.fields(OperationAwareEvaluationRequest)}
    assert "context" not in field_names
    for producer_field in (
        "operation_intent",
        "location",
        "device",
        "protocol_context",
        "safety_context",
        "environment_context",
        "risk_context",
        "identity_evidence_reference",
        "adapter_evidence_reference",
    ):
        assert producer_field not in field_names


def test_caller_request_object_is_frozen_and_not_mutated():
    request = OperationAwareEvaluationRequest(action="read", resource_id="ahu:rooftop-1")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(request)

    # Unchanged after the call.
    assert request.action == "read"
    assert request.resource_id == "ahu:rooftop-1"
    assert request.resource_type is None
    assert request.request_id is None
    # And structurally impossible to mutate at all.
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.action = "write"  # type: ignore[misc]


def test_token_never_appears_in_body():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ALLOW_BODY)

    _client(handler).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert TOKEN not in json.dumps(seen["body"])


# ---------------------------------------------------------------------------
# Completed outcomes
# ---------------------------------------------------------------------------


def test_allow_200():
    result = _client(_json_response(200, ALLOW_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read:ahu", resource_id="ahu:rooftop-1")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.http_status == 200
    assert result.response is not None
    assert result.response.evaluation_status is OperationAwareEvaluationState.COMPLETED
    assert result.response.outcome is OperationAwareOutcome.ALLOW
    assert result.response.disposition is OperationAwareDisposition.ALLOW
    assert result.response.failure_reason is None
    assert result.response.bundle_id == "site-a-bundle"
    assert result.response.bundle_version == "1.0.0"
    assert result.response.trace_id == "b1e2f3a4-0000-0000-0000-000000000000"
    assert result.response.request_id == "c9d8e7f6-0000-0000-0000-000000000000"
    assert result.response.correlation_id == "c9d8e7f6-0000-0000-0000-000000000000"
    assert result.correlation_id == "c9d8e7f6-0000-0000-0000-000000000000"
    # Null/absent fields preserved as None, not synthesized.
    assert result.response.reason_code is None
    assert result.response.explanation is None


def test_explicit_deny_403():
    result = _client(_json_response(403, EXPLICIT_DENY_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="write:ahu", resource_id="ahu:rooftop-1")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.http_status == 403
    assert result.response is not None
    assert result.response.outcome is OperationAwareOutcome.DENY
    assert result.response.disposition is OperationAwareDisposition.DENY


def test_default_deny_403():
    result = _client(_json_response(403, DEFAULT_DENY_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="execute:override", resource_id="ahu:rooftop-1")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.response is not None
    assert result.response.outcome is OperationAwareOutcome.DENY


def test_not_applicable_403_is_never_relabelled_deny():
    result = _client(_json_response(403, NOT_APPLICABLE_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read:other_domain")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.http_status == 403
    assert result.response is not None
    # Outcome stays not_applicable — never collapsed to deny by the client,
    # even though disposition and HTTP status both match a deny.
    assert result.response.outcome is OperationAwareOutcome.NOT_APPLICABLE
    assert result.response.disposition is OperationAwareDisposition.DENY
    # Bundle identity is preserved on NOT_APPLICABLE.
    assert result.response.bundle_id == "site-a-bundle"
    assert result.response.bundle_version == "1.0.0"


def test_correlation_id_header_only_is_accepted_onto_governed_response():
    """Header-only correlation id (rule 3) is accepted as the reconciled value
    on both the parsed governed response and the result wrapper — see the
    dedicated correlation-ID-reconciliation test section below for the full
    equal/body-only/header-only/absent/mismatch matrix."""
    body = dict(ALLOW_BODY)
    del body["correlation_id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body, headers={"X-Correlation-ID": "hdr-corr-1"})

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.response is not None
    assert result.response.correlation_id == "hdr-corr-1"
    assert result.correlation_id == "hdr-corr-1"


def test_absent_optional_fields_are_valid_not_malformed():
    minimal_allow = {
        "request_id": "req-minimal",
        "evaluation_status": "completed",
        "outcome": "allow",
        "disposition": "allow",
    }
    result = _client(_json_response(200, minimal_allow)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.response is not None
    assert result.response.correlation_id is None
    assert result.response.bundle_id is None
    assert result.response.bundle_version is None
    assert result.response.trace_id is None
    assert result.response.reason_code is None
    assert result.response.explanation is None


def test_reason_code_preserved_verbatim_when_present():
    body = dict(NOT_APPLICABLE_BODY)
    body["reason_code"] = "no_applicable_bundle"
    result = _client(_json_response(403, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read:other_domain")
    )
    assert result.response is not None
    assert result.response.reason_code == "no_applicable_bundle"


def test_explanation_null_is_valid_and_preserved_as_none():
    body = dict(ALLOW_BODY)
    body["explanation"] = None
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.response is not None
    assert result.response.explanation is None


# ---------------------------------------------------------------------------
# Governed failures — every documented failure_reason at its documented status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("failure_reason", "http_status"),
    [
        ("invalid_request", 400),
        ("unsupported_schema_version", 400),
        ("invalid_policy_bundle", 503),
        ("policy_validation_failure", 503),
        ("condition_evaluation_error", 500),
        ("internal_evaluation_error", 500),
    ],
)
def test_governed_failure_parsed_not_downgraded_to_generic_error(failure_reason, http_status):
    body = _governed_failure_body(failure_reason, request_id=f"req-{failure_reason}")
    result = _client(_json_response(http_status, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_FAILED
    assert result.http_status == http_status
    assert result.response is not None
    assert result.response.evaluation_status is OperationAwareEvaluationState.FAILED
    assert result.response.outcome is None
    assert result.response.disposition is OperationAwareDisposition.DENY
    assert result.response.failure_reason is not None
    assert result.response.failure_reason.value == failure_reason


def test_documented_failed_evaluation_example_503():
    result = _client(_json_response(503, POLICY_VALIDATION_FAILURE_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_FAILED
    assert result.response is not None
    assert result.response.failure_reason is not None
    assert result.response.failure_reason.value == "policy_validation_failure"
    assert result.response.request_id == "c9d8e7f6-0000-0000-0000-000000000004"


# ---------------------------------------------------------------------------
# Generic (ungoverned) errors — never produce a fake kernel outcome
# ---------------------------------------------------------------------------


def test_401_unauthorized_is_generic_not_governed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": "authentication_failed", "message": "Token verification failed"}
        )

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.UNAUTHORIZED
    assert result.response is None
    assert result.error_code == "authentication_failed"
    assert result.error_message == "Token verification failed"


def test_documented_untrusted_producer_context_rejected_400():
    result = _client(
        _json_response(400, UNTRUSTED_PRODUCER_CONTEXT_REJECTED_BODY)
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read:ahu"))
    assert result.status is OperationAwareEvaluationStatus.REQUEST_REJECTED
    assert result.response is None
    assert result.error_code == "validation_failed"
    assert "operation_intent" in (result.error_message or "")
    assert result.correlation_id == "c9d8e7f6-0000-0000-0000-000000000005"


def test_generic_request_validation_rejection_400():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": "validation_failed", "message": "action: bad format"}
        )

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.REQUEST_REJECTED
    assert result.response is None


def test_documented_evaluator_unavailable_503():
    result = _client(_json_response(503, EVALUATOR_UNAVAILABLE_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATOR_UNAVAILABLE
    assert result.response is None
    assert result.error_code == "evaluator_unavailable"
    assert result.correlation_id == "c9d8e7f6-0000-0000-0000-000000000006"


def test_framework_404_capability_unavailable_not_denied():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CAPABILITY_UNAVAILABLE
    assert result.response is None
    assert result.response_json == {"detail": "Not Found"}


def test_unexpected_generic_500_maps_to_gateway_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal_error"})

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.GATEWAY_ERROR
    assert result.response is None


# ---------------------------------------------------------------------------
# Contract-invalid responses
# ---------------------------------------------------------------------------


def test_invalid_json_is_contract_invalid_not_downgraded():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"not json at all", headers={"content-type": "application/json"}
        )

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.GATEWAY_ERROR
    assert result.response is None


def test_non_object_json_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    # No governed evaluation_status key can be found on a non-dict body, and
    # 200 is not a recognized generic-error status, so this falls through to
    # the unexpected/gateway-error bucket rather than being trusted as anything.
    assert result.status is OperationAwareEvaluationStatus.GATEWAY_ERROR
    assert result.response is None


def test_missing_required_field_request_id():
    body = dict(ALLOW_BODY)
    del body["request_id"]
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    assert result.response is None
    assert result.detail is not None


def test_missing_required_field_disposition():
    body = dict(ALLOW_BODY)
    del body["disposition"]
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_unknown_evaluation_status_value():
    body = dict(ALLOW_BODY)
    body["evaluation_status"] = "bogus"
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_unknown_outcome_value():
    body = dict(ALLOW_BODY)
    body["outcome"] = "maybe"
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_unknown_failure_reason_value():
    body = _governed_failure_body("something_new", request_id="req-x")
    result = _client(_json_response(500, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_unknown_disposition_value():
    body = dict(ALLOW_BODY)
    body["disposition"] = "sideways"
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_completed_without_outcome_is_invalid():
    body = {
        "request_id": "req-1",
        "evaluation_status": "completed",
        "disposition": "allow",
    }
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_failed_without_failure_reason_is_invalid():
    body = {
        "request_id": "req-1",
        "evaluation_status": "failed",
        "disposition": "deny",
    }
    result = _client(_json_response(500, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_contradictory_outcome_and_failure_reason_together():
    body = dict(ALLOW_BODY)
    body["failure_reason"] = "invalid_request"
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_disposition_inconsistent_with_outcome_is_invalid():
    body = dict(ALLOW_BODY)
    body["disposition"] = "deny"  # outcome=allow but disposition=deny
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_non_null_evaluation_trace_is_contract_invalid():
    body = dict(ALLOW_BODY)
    body["evaluation_trace"] = {"steps": []}
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_malformed_correlation_id_field_type():
    body = dict(ALLOW_BODY)
    body["correlation_id"] = 12345  # type: ignore[assignment]
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_malformed_request_id_field_type():
    body = dict(ALLOW_BODY)
    body["request_id"] = 42  # type: ignore[assignment]
    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID


def test_403_without_governed_body_is_contract_invalid():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "forbidden", "message": "no."})

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="write")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    assert result.response is None


# ---------------------------------------------------------------------------
# Transport failures
# ---------------------------------------------------------------------------


def test_connection_failure_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.UNAVAILABLE
    assert result.http_status is None
    assert result.detail is not None
    assert result.timed_out is False


def test_timeout_maps_to_unavailable_with_timed_out_flag():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.UNAVAILABLE
    assert result.timed_out is True


def test_unexpected_client_exception_maps_to_gateway_error_and_does_not_raise():
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("something the HTTP layer did not expect")

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.GATEWAY_ERROR
    assert result.detail is not None


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_token_never_appears_on_result():
    """No field of the result object should ever contain the bearer token."""
    result = _client(_json_response(200, ALLOW_BODY)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    for value in vars(result).values():
        assert TOKEN not in str(value)


def test_sensitive_headers_are_redacted():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ALLOW_BODY,
            headers={
                "Set-Cookie": "session=abc123",
                # Matches ALLOW_BODY's own correlation_id so this exercises a
                # normal, fully-agreeing EVALUATION_COMPLETED response — header
                # redaction on a mismatch is covered separately below.
                "X-Correlation-ID": ALLOW_BODY["correlation_id"],
            },
        )

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.headers.get("set-cookie") == "[redacted]"
    assert result.headers.get("x-correlation-id") == ALLOW_BODY["correlation_id"]


def test_redaction_applied_to_generic_error_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={
                "error": "authentication_failed",
                "message": "invalid",
                "correlation_id": "corr-1",
                "access_token": "should-never-appear-unredacted",
            },
        )

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.response_json is not None
    assert result.response_json.get("access_token") == "[redacted]"


def test_redaction_applied_to_contract_invalid_diagnostics():
    body = dict(ALLOW_BODY)
    body["evaluation_status"] = "bogus"
    body["client_secret"] = "should-never-appear-unredacted"

    result = _client(_json_response(200, body)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    assert result.response_json is not None
    assert result.response_json.get("client_secret") == "[redacted]"


# ---------------------------------------------------------------------------
# Correlation-ID reconciliation (evidence-integrity correction)
#
# The gateway contract states the response body's correlation_id and the
# X-Correlation-ID response header identify the same request. Both are
# consulted; when both are present they must agree, or the response is
# treated as a contract violation rather than one value being silently
# preferred over the other (see operation_aware_models._reconcile_correlation_id).
# ---------------------------------------------------------------------------


def _with_header_correlation(
    body: dict[str, object], status: int, header_correlation_id: str | None
) -> Callable[[httpx.Request], httpx.Response]:
    headers = {"X-Correlation-ID": header_correlation_id} if header_correlation_id else None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, headers=headers)

    return handler


# -- Governed responses: completed outcome --------------------------------


def test_governed_completed_equal_body_and_header_correlation_id_accepted():
    body = dict(ALLOW_BODY)
    result = _client(
        _with_header_correlation(body, 200, str(body["correlation_id"]))
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.response is not None
    assert result.response.correlation_id == body["correlation_id"]
    assert result.correlation_id == body["correlation_id"]


def test_governed_completed_body_only_correlation_id_accepted():
    body = dict(ALLOW_BODY)
    result = _client(_with_header_correlation(body, 200, None)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.response is not None
    assert result.response.correlation_id == body["correlation_id"]
    assert result.correlation_id == body["correlation_id"]


def test_governed_completed_header_only_correlation_id_accepted():
    body = dict(ALLOW_BODY)
    del body["correlation_id"]
    result = _client(_with_header_correlation(body, 200, "hdr-only-corr")).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.response is not None
    assert result.response.correlation_id == "hdr-only-corr"
    assert result.correlation_id == "hdr-only-corr"


def test_governed_completed_absence_of_both_is_preserved_as_none():
    body = dict(ALLOW_BODY)
    del body["correlation_id"]
    result = _client(_with_header_correlation(body, 200, None)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_COMPLETED
    assert result.response is not None
    assert result.response.correlation_id is None
    assert result.correlation_id is None


def test_governed_completed_mismatched_correlation_id_is_contract_invalid():
    body = dict(ALLOW_BODY)
    result = _client(
        _with_header_correlation(body, 200, "a-completely-different-id")
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    # No trusted parsed decision is exposed, and the client does not select
    # either candidate value as authoritative.
    assert result.response is None
    assert result.correlation_id is None
    assert result.detail is not None
    assert "correlation_id" in result.detail


# -- Governed responses: failed evaluation ---------------------------------


def test_governed_failed_equal_body_and_header_correlation_id_accepted():
    body = dict(POLICY_VALIDATION_FAILURE_BODY)
    result = _client(
        _with_header_correlation(body, 503, str(body["correlation_id"]))
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_FAILED
    assert result.response is not None
    assert result.response.correlation_id == body["correlation_id"]
    assert result.correlation_id == body["correlation_id"]


def test_governed_failed_header_only_correlation_id_accepted():
    body = dict(POLICY_VALIDATION_FAILURE_BODY)
    del body["correlation_id"]
    result = _client(
        _with_header_correlation(body, 503, "hdr-only-failure-corr")
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.EVALUATION_FAILED
    assert result.response is not None
    assert result.response.correlation_id == "hdr-only-failure-corr"


def test_governed_failed_mismatched_correlation_id_is_contract_invalid():
    body = dict(POLICY_VALIDATION_FAILURE_BODY)
    result = _client(
        _with_header_correlation(body, 503, "mismatched-failure-corr")
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    assert result.response is None
    assert result.correlation_id is None


# -- Generic (ungoverned) errors --------------------------------------------


def test_generic_error_equal_body_and_header_correlation_id_accepted():
    body = {"error": "authentication_failed", "message": "invalid", "correlation_id": "corr-x"}
    result = _client(_with_header_correlation(body, 401, "corr-x")).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.UNAUTHORIZED
    assert result.correlation_id == "corr-x"
    assert result.error_code == "authentication_failed"


def test_generic_error_body_only_correlation_id_accepted():
    body = {"error": "validation_failed", "message": "bad request", "correlation_id": "corr-y"}
    result = _client(_with_header_correlation(body, 400, None)).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.REQUEST_REJECTED
    assert result.correlation_id == "corr-y"


def test_generic_error_header_only_correlation_id_accepted():
    body = {"error": "evaluator_unavailable", "message": "not ready"}
    result = _client(
        _with_header_correlation(body, 503, "hdr-only-generic-corr")
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.EVALUATOR_UNAVAILABLE
    assert result.correlation_id == "hdr-only-generic-corr"


def test_generic_error_mismatched_correlation_id_is_contract_invalid():
    body = {
        "error": "authentication_failed",
        "message": "invalid",
        "correlation_id": "body-corr-value",
    }
    result = _client(
        _with_header_correlation(body, 401, "header-corr-value")
    ).evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    # No fake kernel outcome or governed response, and the generic error
    # fields are not relayed alongside an unresolved correlation conflict.
    assert result.response is None
    assert result.correlation_id is None
    assert result.error_code is None
    assert result.error_message is None


# -- Redaction of mismatch diagnostics --------------------------------------


def test_mismatch_diagnostics_do_not_expose_bearer_token():
    body = dict(ALLOW_BODY)
    result = _client(_with_header_correlation(body, 200, "mismatched-id")).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    for value in vars(result).values():
        assert TOKEN not in str(value)


def test_mismatch_diagnostics_redact_sensitive_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ALLOW_BODY,
            headers={"Set-Cookie": "session=abc123", "X-Correlation-ID": "mismatched-id"},
        )

    result = _client(handler).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    assert result.headers.get("set-cookie") == "[redacted]"


def test_mismatch_diagnostics_retain_only_redacted_response_details():
    body = dict(ALLOW_BODY)
    body["client_secret"] = "should-never-appear-unredacted"
    result = _client(_with_header_correlation(body, 200, "mismatched-id")).evaluate_operation_aware(
        OperationAwareEvaluationRequest(action="read")
    )
    assert result.status is OperationAwareEvaluationStatus.CONTRACT_INVALID
    assert result.response_json is not None
    assert result.response_json.get("client_secret") == "[redacted]"
    # The raw (redacted) body is available for diagnosis, but no parsed,
    # trusted decision is ever produced from it.
    assert result.response is None


# ---------------------------------------------------------------------------
# Legacy regression / cross-contract isolation
# ---------------------------------------------------------------------------


def test_legacy_evaluate_still_uses_legacy_endpoint_and_model():
    """The two client methods must never converge on endpoint or model."""
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"request_id": "r", "outcome": "allow"})

    client = _client(handler)
    legacy_result = client.evaluate(action="read")

    assert seen_paths == ["/v1/evaluate"]
    from basis_console.gateway import GatewayEvaluationResult

    assert isinstance(legacy_result, GatewayEvaluationResult)
    assert not hasattr(legacy_result, "response")
    assert not hasattr(legacy_result, "evaluation_status")


def test_operation_aware_evaluate_uses_only_operation_aware_endpoint():
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json=ALLOW_BODY)

    client = _client(handler)
    result = client.evaluate_operation_aware(OperationAwareEvaluationRequest(action="read"))

    assert seen_paths == ["/v1/evaluate/operation-aware"]
    from basis_console.gateway.operation_aware_models import OperationAwareEvaluationResult

    assert isinstance(result, OperationAwareEvaluationResult)


def test_models_are_not_interchangeable():
    """Structural proof the two contracts share no fields by casting/duck-typing."""
    from basis_console.gateway import GatewayEvaluationResult, GatewayEvaluationStatus
    from basis_console.gateway.operation_aware_models import OperationAwareEvaluationResult

    legacy_fields = {f.name for f in dataclasses.fields(GatewayEvaluationResult)}
    oa_fields = {f.name for f in dataclasses.fields(OperationAwareEvaluationResult)}

    # response/evaluation_status live only on the operation-aware result.
    assert "response" in oa_fields
    assert "response" not in legacy_fields
    assert GatewayEvaluationStatus is not OperationAwareEvaluationStatus
