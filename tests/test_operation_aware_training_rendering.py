"""Route-level tests for operation-aware Training-mode educational rendering (PR 5).

Covers the required test categories from the PR 5 task: Training visibility,
preview education, outcome-specific education (ALLOW/DENY/NOT_APPLICABLE),
governed-failure education (parameterized over the closed failure-reason
enum), generic/client-failure education, null/absent-evidence education,
context/producer education, identifier education, provenance labelling,
accessibility, and legacy regression.

Runtime-parity proof (identical request/client-call/presentation/evidence
across modes) lives in ``test_operation_aware_mode_parity.py``; this file
focuses on the *content* of the Training-only markup itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from basis_console.gateway import GatewayClient
from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "super-secret-token-abc123"

OA_FORM = {
    "evaluation_type": "operation_aware",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
}

LEGACY_FORM = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
}


@contextmanager
def _client(monkeypatch, mode: str | None, handler=None) -> Iterator[TestClient]:
    if mode is None:
        monkeypatch.delenv("BASIS_CONSOLE_MODE", raising=False)
    else:
        monkeypatch.setenv("BASIS_CONSOLE_MODE", mode)
    reset_readiness_state()
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        transport = httpx.MockTransport(handler) if handler is not None else None
        client.app.state.gateway_client = GatewayClient(
            base_url=GATEWAY_URL, bearer_token=TOKEN, transport=transport
        )
        yield client


def _json_handler(status: int, payload: dict[str, object]):
    correlation_id = payload.get("correlation_id")
    headers = {"X-Correlation-ID": str(correlation_id)} if correlation_id else None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers)

    return handler


ALLOW_BODY = {
    "request_id": "req-allow",
    "correlation_id": "corr-allow",
    "evaluation_status": "completed",
    "outcome": "allow",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "disposition": "allow",
    "reason_code": "ALLOW_RULE_MATCHED",
    "explanation": "Matched an allow rule.",
    "trace_id": "trace-allow",
}

DENY_BODY = {
    "request_id": "req-deny",
    "correlation_id": "corr-deny",
    "evaluation_status": "completed",
    "outcome": "deny",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "disposition": "deny",
}

NOT_APPLICABLE_BODY = {
    "request_id": "req-na",
    "correlation_id": "corr-na",
    "evaluation_status": "completed",
    "outcome": "not_applicable",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "disposition": "deny",
}

MINIMAL_ALLOW_BODY = {
    # No reason_code, no explanation, no trace_id — exercises the null/absent
    # evidence guidance paths.
    "request_id": "req-min",
    "correlation_id": "corr-min",
    "evaluation_status": "completed",
    "outcome": "allow",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "disposition": "allow",
}

FAILURE_REASON_HTTP_STATUS = {
    "invalid_request": 400,
    "unsupported_schema_version": 400,
    "invalid_policy_bundle": 503,
    "policy_validation_failure": 503,
    "condition_evaluation_error": 500,
    "internal_evaluation_error": 500,
}


# ---------------------------------------------------------------------------
# Training visibility
# ---------------------------------------------------------------------------


def test_operation_aware_training_content_appears_only_in_training_mode(monkeypatch):
    with _client(monkeypatch, None) as operator, _client(monkeypatch, "training") as training:
        op = operator.post("/simulate", data={**OA_FORM, "mode": "preview"})
        tr = training.post("/simulate", data={**OA_FORM, "mode": "preview"})
        assert "Learn: how this operation-aware evaluation works" not in op.text
        assert "oa-training-content" not in op.text
        assert "Learn: how this operation-aware evaluation works" in tr.text
        assert "oa-training-content" in tr.text


def test_generic_training_banner_still_present_alongside_new_content(monkeypatch):
    with _client(monkeypatch, "training") as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "preview"})
        assert "Training mode is enabled" in r.text
        assert "Learn: how this operation-aware evaluation works" in r.text


def test_legacy_simulator_training_callout_is_not_replaced(monkeypatch):
    with _client(monkeypatch, "training") as training:
        r = training.get("/simulate")
        # The pre-existing generic "What this page teaches" callout content.
        assert "You build a request from a bare verb" in r.text
        # The new operation-aware section is not shown for the default
        # (legacy) evaluation type.
        assert "Learn: how this operation-aware evaluation works" not in r.text


def test_legacy_evaluation_type_never_shows_operation_aware_training_content(monkeypatch):
    with _client(monkeypatch, "training") as training:
        r = training.post("/simulate", data={**LEGACY_FORM, "mode": "preview"})
        assert "oa-training-content" not in r.text


# ---------------------------------------------------------------------------
# Preview education
# ---------------------------------------------------------------------------


def test_preview_education_states_no_gateway_call_and_no_decision(monkeypatch):
    with _client(monkeypatch, "training") as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "preview"})
        text = r.text
        assert "This request has not been sent to basis-gateway." in text
        assert "No authentication has occurred through this preview." in text
        assert "No policy bundle has been evaluated." in text
        assert "No outcome or enforcement disposition exists for this preview." in text
        assert "No correlation ID or trace ID exists for this preview." in text
        assert "submitted input" in text
        # No live-result wording.
        assert "What this result means" not in text


# ---------------------------------------------------------------------------
# ALLOW education
# ---------------------------------------------------------------------------


def test_allow_education(monkeypatch):
    handler = _json_handler(200, ALLOW_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert r.status_code == 200
        assert ">allow<" in text or "allow" in text  # returned evidence unchanged
        assert "kernel outcome was allow" in text
        assert "does not claim which specific rule allowed the action" in text
        assert "console explanation" in text


# ---------------------------------------------------------------------------
# DENY education
# ---------------------------------------------------------------------------


def test_deny_education(monkeypatch):
    handler = _json_handler(403, DENY_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert r.status_code == 200
        assert "does not distinguish an explicit deny rule" in text
        assert "does not invent that distinction" in text


# ---------------------------------------------------------------------------
# NOT_APPLICABLE education
# ---------------------------------------------------------------------------


def test_not_applicable_education(monkeypatch):
    handler = _json_handler(403, NOT_APPLICABLE_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert r.status_code == 200
        assert "not_applicable" in text
        assert "coverage gap" in text
        assert "never shown as deny" in text
        # Bundle identity remains visible.
        assert "site-a-bundle" in text
        # The kernel-outcome dt/dd pair itself must never read "deny".
        outcome_idx = text.index("Kernel outcome")
        outcome_snippet = text[outcome_idx : outcome_idx + 300]
        assert "not_applicable" in outcome_snippet or "not applicable" in outcome_snippet


# ---------------------------------------------------------------------------
# Governed failure education (exhaustive over the closed enum)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("failure_reason", sorted(FAILURE_REASON_HTTP_STATUS))
def test_governed_failure_education(monkeypatch, failure_reason):
    body = {
        "request_id": "req-f",
        "correlation_id": "corr-f",
        "evaluation_status": "failed",
        "failure_reason": failure_reason,
        "disposition": "deny",
    }
    handler = _json_handler(FAILURE_REASON_HTTP_STATUS[failure_reason], body)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert r.status_code == 200
        assert failure_reason in text
        assert "no allow, deny, or not_applicable exists for this call" in text
        assert "not a policy denial" in text
        # No outcome value rendered anywhere (the dt for "Kernel outcome" is
        # only rendered when applicable=True, i.e. on a completed evaluation).
        assert "<dt>Kernel outcome</dt>" not in text


# ---------------------------------------------------------------------------
# Generic / client failure education
# ---------------------------------------------------------------------------


def test_generic_failure_education_for_connection_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert r.status_code == 200
        assert "No trusted governed decision is available for this call." in text
        assert "does not present a kernel outcome" in text
        assert "<dt>Kernel outcome</dt>" not in text


def test_generic_failure_education_for_capability_unavailable(monkeypatch):
    handler = _json_handler(404, {"detail": "Not Found"})
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert r.status_code == 200
        assert "No trusted governed decision is available for this call." in text


# ---------------------------------------------------------------------------
# Null / absent evidence education
# ---------------------------------------------------------------------------


def test_absent_evidence_guidance_shown_when_fields_are_absent(monkeypatch):
    handler = _json_handler(200, MINIMAL_ALLOW_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert "No additional evaluator explanation was provided" in text  # returned-evidence copy
        assert "A null evaluator explanation is a normal" in text
        assert "No reason code was returned for this result." in text
        assert "No trace reference was returned for this call." in text


def test_absent_evidence_guidance_omitted_when_fields_are_present(monkeypatch):
    handler = _json_handler(200, ALLOW_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        # ALLOW_BODY supplies explanation, reason_code, and trace_id — none of
        # the absence-guidance sentences should appear.
        assert "A null evaluator explanation is a normal" not in text
        assert "No reason code was returned for this result." not in text
        assert "No trace reference was returned for this call." not in text


def test_absence_guidance_only_shows_relevant_entries(monkeypatch):
    """A response with *some* fields present and others absent shows only the
    guidance relevant to the absent ones (not every absence sentence at once).
    """
    body = dict(ALLOW_BODY)
    body.pop("reason_code")
    handler = _json_handler(200, body)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert "No reason code was returned for this result." in text
        assert "A null evaluator explanation is a normal" not in text
        assert "No trace reference was returned for this call." not in text


# ---------------------------------------------------------------------------
# Context and producer-trust education
# ---------------------------------------------------------------------------


def test_context_and_producer_education_present_regardless_of_result(monkeypatch):
    with _client(monkeypatch, "training") as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "preview"})
        text = r.text
        assert "Why there's no identity or context control here" in text
        assert "gateway derives it exclusively from the verified Bearer token" in text
        assert TOKEN not in text
        assert "trusted operation producer" in text


def test_context_education_does_not_reenable_legacy_controls_and_server_still_rejects(monkeypatch):
    with _client(monkeypatch, "training") as training:
        r = training.post("/simulate", data={**OA_FORM, "context": "a=b", "mode": "preview"})
        assert r.status_code == 200
        assert "does not accept a context value" in r.text
        # The legacy-only context control remains disabled in the re-rendered form.
        snippet = r.text.split('id="legacy-only-context"')[1][:120]
        assert "disabled" in snippet


# ---------------------------------------------------------------------------
# Identifier education
# ---------------------------------------------------------------------------


def test_identifier_education_distinguishes_request_correlation_and_trace(monkeypatch):
    handler = _json_handler(200, ALLOW_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert "not always console-generated" in text
        assert "not interchangeable with the correlation ID" in text
        assert "not returned by this endpoint today" in text
        assert "No audit-evidence identifier" in text


# ---------------------------------------------------------------------------
# Provenance labelling
# ---------------------------------------------------------------------------


def test_provenance_legend_and_labels_present(monkeypatch):
    handler = _json_handler(200, ALLOW_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert "Provenance legend" in text
        for label in (
            "Submitted input",
            "Returned evidence",
            "Console explanation",
            "Future capability",
        ):
            assert label in text


# ---------------------------------------------------------------------------
# Accessibility
# ---------------------------------------------------------------------------


def test_accessible_markup_present(monkeypatch):
    handler = _json_handler(200, ALLOW_BODY)
    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**OA_FORM, "mode": "gateway"})
        text = r.text
        assert "<h3>Learn: how this operation-aware evaluation works</h3>" in text
        assert "<details" in text
        assert "<summary>" in text
        assert '<th scope="col">' in text
        assert "<script" not in text.split("oa-training-content")[1]


# ---------------------------------------------------------------------------
# Legacy regression
# ---------------------------------------------------------------------------


def test_legacy_gateway_evaluation_unaffected_by_training_enrichment(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "req-legacy",
                "outcome": "allow",
                "correlation_id": "corr-legacy",
            },
            headers={"X-Correlation-ID": "corr-legacy"},
        )

    with _client(monkeypatch, "training", handler) as training:
        r = training.post("/simulate", data={**LEGACY_FORM, "mode": "gateway"})
        assert r.status_code == 200
        assert "Gateway response" in r.text
        assert "oa-training-content" not in r.text
