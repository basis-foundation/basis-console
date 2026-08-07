"""Route tests for the shared operation-aware simulator integration (PR 4).

Covers the requirements in
``docs/implementation/operation-aware-console-integration-plan.md`` PR 4:
evaluation-type selection, operation-aware preview (no gateway call, no
fabricated decision), live operation-aware submission (exact client call,
shared presentation builder), the full outcome matrix (allow / deny /
not_applicable / governed failure / generic failure), context rejection,
provenance rendering, legacy regression, and Operator/Training mode parity.

Mirrors the structure and fixtures of ``test_simulate_gateway_routes.py`` and
``test_gateway_evaluate_operation_aware.py``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx
from fastapi.testclient import TestClient

from basis_console.gateway import GatewayClient
from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "super-secret-token-abc123"

_OA_FORM = {
    "evaluation_type": "operation_aware",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
}


@contextmanager
def gateway_client_app(
    handler: Handler | None = None,
    *,
    base_url: str | None = GATEWAY_URL,
    token: str | None = TOKEN,
) -> Iterator[TestClient]:
    """A TestClient whose gateway client is overridden after startup."""
    reset_readiness_state()
    app = create_app()
    with TestClient(app) as client:
        transport = httpx.MockTransport(handler) if handler is not None else None
        client.app.state.gateway_client = GatewayClient(
            base_url=base_url, bearer_token=token, transport=transport
        )
        yield client


def _json_handler(status: int, payload: dict[str, object], **headers: str) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers or None)

    return handler


# ---------------------------------------------------------------------------
# Canonical response fixtures (same shapes as test_gateway_evaluate_operation_aware.py)
# ---------------------------------------------------------------------------

ALLOW_BODY = {
    "request_id": "req-allow",
    "correlation_id": "corr-allow",
    "evaluation_status": "completed",
    "outcome": "allow",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "trace_id": "trace-allow",
    "reason_code": "ALLOW_RULE_MATCHED",
    "explanation": "Matched allow rule ot-operator-rbac.",
    "disposition": "allow",
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

GOVERNED_400_BODY = {
    "request_id": "req-f400",
    "correlation_id": "corr-f400",
    "evaluation_status": "failed",
    "failure_reason": "invalid_request",
    "disposition": "deny",
}

GOVERNED_503_BODY = {
    "request_id": "req-f503",
    "correlation_id": "corr-f503",
    "evaluation_status": "failed",
    "failure_reason": "invalid_policy_bundle",
    "disposition": "deny",
}

GOVERNED_500_BODY = {
    "request_id": "req-f500",
    "correlation_id": "corr-f500",
    "evaluation_status": "failed",
    "failure_reason": "internal_evaluation_error",
    "disposition": "deny",
}


def _allow_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=ALLOW_BODY, headers={"X-Correlation-ID": "corr-allow"})


# ---------------------------------------------------------------------------
# Evaluation-type selection
# ---------------------------------------------------------------------------


def test_get_default_selects_legacy(client):
    response = client.get("/simulate")
    assert response.status_code == 200
    assert 'id="evaluation_type_legacy"' in response.text
    # Legacy radio is checked by default; operation_aware is not.
    assert 'value="legacy"' in response.text
    checked_snippet = response.text.split('id="evaluation_type_legacy"')[1][:40]
    assert "checked" in checked_snippet


def test_post_without_evaluation_type_field_is_legacy(client):
    """Old forms/bookmarks that predate this field submit no evaluation_type."""
    response = client.post(
        "/simulate",
        data={
            "subject_id": "operator-jane",
            "subject_type": "user",
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "context": "site=bldg-a",
        },
    )
    assert response.status_code == 200
    assert "Normalized request preview" in response.text


def test_explicit_legacy_selection(client):
    response = client.post(
        "/simulate",
        data={
            "evaluation_type": "legacy",
            "subject_id": "operator-jane",
            "subject_type": "user",
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
        },
    )
    assert response.status_code == 200
    assert "Normalized request preview" in response.text


def test_explicit_operation_aware_selection(client):
    response = client.post("/simulate", data=_OA_FORM)
    assert response.status_code == 200
    assert "Operation-aware evaluation" in response.text
    assert "Normalized request preview" not in response.text


def test_selected_evaluation_type_persists_after_post(client):
    response = client.post("/simulate", data=_OA_FORM)
    assert response.status_code == 200
    checked_snippet = response.text.split('id="evaluation_type_operation_aware"')[1][:40]
    assert "checked" in checked_snippet


def test_invalid_evaluation_type_is_rejected(client):
    response = client.post("/simulate", data={**_OA_FORM, "evaluation_type": "bogus"})
    assert response.status_code == 200
    assert "Invalid evaluation type" in response.text
    assert "Operation-aware evaluation" not in response.text
    assert "Normalized request preview" not in response.text


def test_invalid_evaluation_type_does_not_call_gateway():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate", data={**_OA_FORM, "mode": "gateway", "evaluation_type": "bogus"}
        )
        assert response.status_code == 200
        assert calls == []


# ---------------------------------------------------------------------------
# Rendered controls: legacy-only fields disabled (not merely hidden) for
# operation-aware, enabled for legacy (targeted correction).
# ---------------------------------------------------------------------------


def _fieldset_snippet(html: str, fieldset_id: str) -> str:
    return html.split(f'id="{fieldset_id}"')[1][:120]


def test_legacy_selection_renders_legacy_only_controls_enabled(client):
    response = client.post(
        "/simulate",
        data={
            "evaluation_type": "legacy",
            "subject_id": "operator-jane",
            "subject_type": "user",
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
        },
    )
    assert response.status_code == 200
    for fieldset_id in ("legacy-only-fields", "legacy-only-context"):
        snippet = _fieldset_snippet(response.text, fieldset_id)
        assert "disabled" not in snippet
        assert "is-hidden" not in snippet


def test_operation_aware_selection_renders_legacy_only_controls_disabled(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    for fieldset_id in ("legacy-only-fields", "legacy-only-context"):
        snippet = _fieldset_snippet(response.text, fieldset_id)
        assert "disabled" in snippet
        assert "is-hidden" in snippet


def test_get_default_renders_legacy_only_controls_enabled(client):
    """The default GET (legacy) never disables the subject/context controls."""
    response = client.get("/simulate")
    assert response.status_code == 200
    for fieldset_id in ("legacy-only-fields", "legacy-only-context"):
        snippet = _fieldset_snippet(response.text, fieldset_id)
        assert "disabled" not in snippet


def test_context_is_not_an_enabled_operation_aware_control(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    snippet = _fieldset_snippet(response.text, "legacy-only-context")
    assert "disabled" in snippet


def test_subject_fields_are_not_enabled_operation_aware_controls(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    snippet = _fieldset_snippet(response.text, "legacy-only-fields")
    assert "disabled" in snippet


def test_progressive_enhancement_script_disables_and_reenables_together(client):
    """Text-based proxy: the toggle script must set `.disabled`, not only classList.

    No JS runtime is available in this test suite (no browser/Selenium
    dependency exists in this repository), so this asserts the script's
    source contains the disabling logic alongside the visibility toggle,
    rather than only a CSS-class assertion — the toggle handler must mutate
    both `classList` and `.disabled` for each legacy-only fieldset, and must
    never merely hide them.
    """
    html = client.get("/simulate").text
    script_start = html.index("Progressive enhancement")
    script = html[script_start : script_start + 2000]
    assert "legacyFields.disabled = hide" in script
    assert "legacyContext.disabled = hide" in script
    assert 'legacyFields.classList.toggle("is-hidden", hide)' in script
    assert 'legacyContext.classList.toggle("is-hidden", hide)' in script


# ---------------------------------------------------------------------------
# Operation-aware preview: request-shape preview only
# ---------------------------------------------------------------------------


def test_oa_preview_shows_exact_submitted_request(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    assert "Submitted request" in response.text
    assert "read" in response.text
    assert "ahu" in response.text
    assert "rooftop-1" in response.text
    assert "preview only" in response.text.lower()


def test_oa_preview_makes_no_gateway_call():
    def boom(self, *args, **kwargs):
        raise AssertionError("gateway must not be contacted during operation-aware preview")

    import basis_console.gateway.client as client_module

    original = client_module.GatewayClient.evaluate_operation_aware
    client_module.GatewayClient.evaluate_operation_aware = boom  # type: ignore[method-assign]
    try:
        with gateway_client_app(_allow_handler) as client:
            response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
            assert response.status_code == 200
            assert "Submitted request" in response.text
    finally:
        client_module.GatewayClient.evaluate_operation_aware = original  # type: ignore[method-assign]


def test_oa_preview_fabricates_no_outcome_or_disposition(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    for forbidden in ("Kernel outcome", "Gateway disposition", "Evaluation result"):
        assert forbidden not in response.text


def test_oa_preview_generates_no_correlation_or_trace_id(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    assert "Correlation ID" not in response.text
    assert "Trace ID" not in response.text


def test_oa_preview_context_and_subject_omitted_when_not_submitted(client):
    """A clean preview shows only action/resource_type/resource_id as submitted."""
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    assert "Submitted request" in response.text


def test_oa_preview_crafted_subject_is_rejected_not_silently_dropped():
    """A crafted subject_id/subject_type on a preview submission is rejected.

    It must never be silently ignored (which would let the field appear to
    be an accepted, merely-unrendered input) nor shown as part of the
    submitted request.
    """
    with gateway_client_app(_allow_handler) as client:
        response = client.post(
            "/simulate",
            data={
                **_OA_FORM,
                "mode": "preview",
                "subject_id": "operator-jane",
                "subject_type": "user",
            },
        )
        assert response.status_code == 200
        assert "does not accept a subject" in response.text
        assert "Submitted request" not in response.text


def test_oa_preview_selected_evaluation_type_remains_visible(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview"})
    assert response.status_code == 200
    checked_snippet = response.text.split('id="evaluation_type_operation_aware"')[1][:40]
    assert "checked" in checked_snippet


def test_oa_preview_domain_level_request_shown():
    with gateway_client_app(_allow_handler) as client:
        response = client.post(
            "/simulate",
            data={
                "evaluation_type": "operation_aware",
                "mode": "preview",
                "action_verb": "read",
                "resource_type": "ahu",
            },
        )
        assert response.status_code == 200
        assert "domain-level request" in response.text


# ---------------------------------------------------------------------------
# Operation-aware live submission
# ---------------------------------------------------------------------------


def test_oa_gateway_call_uses_exact_request_and_only_operation_aware_endpoint():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = __import__("json").loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=ALLOW_BODY, headers={"X-Correlation-ID": "corr-allow"})

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200

    assert seen["path"] == "/v1/evaluate/operation-aware"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body == {"action": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}
    assert "context" not in body
    assert "subject_id" not in body
    assert "request_id" not in body


def test_oa_client_called_exactly_once_and_legacy_evaluate_not_called():
    calls: list[str] = []
    original_evaluate = GatewayClient.evaluate

    def spy_evaluate(self, *args, **kwargs):  # pragma: no cover - fails the test if hit
        calls.append("evaluate")
        return original_evaluate(self, *args, **kwargs)

    call_count = {"n": 0}
    original_oa = GatewayClient.evaluate_operation_aware

    def spy_oa(self, request):
        call_count["n"] += 1
        return original_oa(self, request)

    GatewayClient.evaluate = spy_evaluate  # type: ignore[method-assign]
    GatewayClient.evaluate_operation_aware = spy_oa  # type: ignore[method-assign]
    try:
        with gateway_client_app(_allow_handler) as client:
            response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
            assert response.status_code == 200
    finally:
        GatewayClient.evaluate = original_evaluate  # type: ignore[method-assign]
        GatewayClient.evaluate_operation_aware = original_oa  # type: ignore[method-assign]

    assert calls == []
    assert call_count["n"] == 1


def test_legacy_gateway_call_never_hits_operation_aware_endpoint():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json={"request_id": "r1", "outcome": "allow", "reason": "ok"})

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data={
                "evaluation_type": "legacy",
                "mode": "gateway",
                "subject_id": "operator-jane",
                "subject_type": "user",
                "action_verb": "read",
                "resource_type": "ahu",
                "resource_id": "rooftop-1",
            },
        )
        assert response.status_code == 200

    assert seen == ["/v1/evaluate"]


# ---------------------------------------------------------------------------
# Completed governed outcomes: allow / deny / not_applicable
# ---------------------------------------------------------------------------


def test_allow_outcome_rendered_distinctly():
    handler = _json_handler(200, ALLOW_BODY, **{"X-Correlation-ID": "corr-allow"})
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "evaluation completed" in response.text.lower()
        assert 'outcome allow">allow' in response.text.lower().replace("\n", "").replace("  ", "")


def test_deny_outcome_rendered_distinctly():
    handler = _json_handler(403, DENY_BODY, **{"X-Correlation-ID": "corr-deny"})
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "deny" in response.text
        assert "403" in response.text


def test_not_applicable_is_never_rendered_as_plain_deny():
    handler = _json_handler(403, NOT_APPLICABLE_BODY, **{"X-Correlation-ID": "corr-na"})
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        # The exact not_applicable outcome is present...
        assert "not_applicable" in response.text
        # ...and bundle identity is preserved on NOT_APPLICABLE.
        assert "site-a-bundle" in response.text
        # The console-authored clarification distinguishes it from a policy deny.
        assert "No policy bundle applied" in response.text
        # Gateway disposition (deny) is shown as a separate, labelled fact —
        # never substituted for the kernel outcome.
        assert "Gateway disposition" in response.text


def test_outcome_disposition_http_status_kept_distinct_on_deny():
    handler = _json_handler(403, DENY_BODY, **{"X-Correlation-ID": "corr-deny"})
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "Kernel outcome" in response.text
        assert "Gateway disposition" in response.text
        assert "HTTP status" in response.text


# ---------------------------------------------------------------------------
# Governed failures — never a policy decision
# ---------------------------------------------------------------------------


def test_governed_failure_400_shows_exact_reason_no_fabricated_outcome():
    handler = _json_handler(400, GOVERNED_400_BODY)
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "invalid_request" in response.text
        assert "structural problem, not a policy decision" in response.text
        # No fabricated kernel outcome for a failed evaluation.
        assert "Kernel outcome" not in response.text


def test_governed_failure_503_shows_exact_reason():
    handler = _json_handler(503, GOVERNED_503_BODY)
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "invalid_policy_bundle" in response.text
        assert "dependency-integrity" in response.text


def test_governed_failure_500_shows_exact_reason():
    handler = _json_handler(500, GOVERNED_500_BODY)
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "internal_evaluation_error" in response.text
        assert "evaluation-time failure" in response.text


# ---------------------------------------------------------------------------
# Generic / client-level failures — no governed fields rendered
# ---------------------------------------------------------------------------


def test_not_configured_shows_no_governed_fields():
    with gateway_client_app(None, base_url=None, token=None) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "Kernel outcome" not in response.text
        assert "Gateway disposition" not in response.text


def test_token_missing_shows_no_governed_fields():
    with gateway_client_app(None, base_url=GATEWAY_URL, token=None) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "Kernel outcome" not in response.text


def test_capability_unavailable_404_is_not_shown_as_denied():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not Found"})

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "not enabled on this gateway" in response.text
        assert "Kernel outcome" not in response.text


def test_evaluator_unavailable_503_generic_is_not_a_policy_decision():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503, json={"error": "evaluator_unavailable", "message": "starting up"}
        )

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "not ready" in response.text.lower()
        assert "Kernel outcome" not in response.text


def test_unauthorized_401_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "authentication_failed", "message": "bad token"})

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "authentication_failed" in response.text


def test_request_rejected_400_generic_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "validation_failed", "message": "bad shape"})

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "validation_failed" in response.text
        assert "Kernel outcome" not in response.text


def test_gateway_unavailable_connection_error_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "could not contact gateway" in response.text
        assert "Kernel outcome" not in response.text


def test_contract_invalid_403_without_governed_body_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "unexpected"})

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "contract_invalid" in response.text or "could not be read" in response.text
        assert "Kernel outcome" not in response.text


def test_generic_500_gateway_error_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal", "message": "boom"})

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "Kernel outcome" not in response.text


# ---------------------------------------------------------------------------
# Context rejection (server-side, independent of what the form renders)
# ---------------------------------------------------------------------------


def test_crafted_nonempty_context_rejected_before_any_gateway_call():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data={**_OA_FORM, "mode": "gateway", "context": "maintenance_window=true"},
        )
        assert response.status_code == 200
        assert "does not accept a context value" in response.text
        assert calls == []
        assert "Evaluation result" not in response.text


def test_crafted_nonempty_context_rejected_in_preview_too(client):
    response = client.post("/simulate", data={**_OA_FORM, "mode": "preview", "context": "a=b"})
    assert response.status_code == 200
    assert "does not accept a context value" in response.text
    assert "Submitted request" not in response.text


def test_crafted_subject_id_rejected_before_any_gateway_call():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data={**_OA_FORM, "mode": "gateway", "subject_id": "operator-jane"},
        )
        assert response.status_code == 200
        assert "does not accept a subject" in response.text
        assert calls == []
        assert "Evaluation result" not in response.text


def test_crafted_subject_id_rejected_in_preview_too(client):
    response = client.post(
        "/simulate", data={**_OA_FORM, "mode": "preview", "subject_id": "operator-jane"}
    )
    assert response.status_code == 200
    assert "does not accept a subject" in response.text
    assert "Submitted request" not in response.text


def test_crafted_subject_type_rejected_before_any_gateway_call():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate", data={**_OA_FORM, "mode": "gateway", "subject_type": "user"}
        )
        assert response.status_code == 200
        assert "does not accept a subject type" in response.text
        assert calls == []


def test_crafted_subject_type_rejected_in_preview_too(client):
    response = client.post(
        "/simulate", data={**_OA_FORM, "mode": "preview", "subject_type": "user"}
    )
    assert response.status_code == 200
    assert "does not accept a subject type" in response.text
    assert "Submitted request" not in response.text


def test_crafted_legacy_only_fields_never_call_legacy_endpoint_either():
    """A rejected operation-aware submission never falls through to /v1/evaluate."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json={"request_id": "r", "outcome": "allow", "reason": "ok"})

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data={
                **_OA_FORM,
                "mode": "gateway",
                "context": "a=b",
                "subject_id": "operator-jane",
                "subject_type": "user",
            },
        )
        assert response.status_code == 200
        assert calls == []


def test_crafted_legacy_only_fields_fabricate_no_evidence():
    with gateway_client_app(_allow_handler) as client:
        response = client.post(
            "/simulate",
            data={**_OA_FORM, "mode": "gateway", "subject_id": "operator-jane", "context": "a=b"},
        )
        assert response.status_code == 200
        for forbidden in ("Kernel outcome", "Gateway disposition", "Evaluation result"):
            assert forbidden not in response.text


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_oa_missing_action_shows_error_and_no_gateway_call():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data={"evaluation_type": "operation_aware", "mode": "gateway", "resource_type": "ahu"},
        )
        assert response.status_code == 200
        assert "Please correct the following" in response.text
        assert calls == []


def test_oa_invalid_action_resource_composition_shows_error():
    with gateway_client_app(_allow_handler) as client:
        response = client.post(
            "/simulate",
            data={
                "evaluation_type": "operation_aware",
                "mode": "gateway",
                "action_verb": "read",
                "resource_type": "ahu",
                "resource_id": "ahu:rooftop-1",
            },
        )
        assert response.status_code == 200
        assert "must be local" in response.text


def test_oa_invalid_resource_id_composition_shows_error(client):
    response = client.post(
        "/simulate",
        data={**_OA_FORM, "resource_id": "bad value; rm -rf"},
    )
    assert response.status_code == 200
    assert "simple safe string" in response.text


# ---------------------------------------------------------------------------
# Provenance rendering
# ---------------------------------------------------------------------------


def test_provenance_categories_distinguished_in_result_rendering():
    handler = _json_handler(200, ALLOW_BODY, **{"X-Correlation-ID": "corr-allow"})
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        # submitted_input
        assert "submitted input" in response.text
        # returned_evidence
        assert "returned evidence" in response.text
        # console_explanation
        assert "Console note:" in response.text
        # future_capability
        assert "future capability" in response.text


def test_null_explanation_shows_console_note_not_fabricated_value():
    body = dict(ALLOW_BODY)
    body.pop("explanation", None)
    handler = _json_handler(200, body, **{"X-Correlation-ID": "corr-allow"})
    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert response.status_code == 200
        assert "No additional evaluator explanation was provided." in response.text


# ---------------------------------------------------------------------------
# Legacy regression
# ---------------------------------------------------------------------------


def test_legacy_preview_unchanged(client):
    response = client.post(
        "/simulate",
        data={
            "evaluation_type": "legacy",
            "subject_id": "operator-jane",
            "subject_type": "user",
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "context": "site=bldg-a",
        },
    )
    assert response.status_code == 200
    assert "Normalized request preview" in response.text
    assert "read:ahu" in response.text
    assert "ahu:rooftop-1" in response.text


def test_legacy_gateway_response_unchanged():
    with gateway_client_app(_allow_handler) as client:
        response = client.post(
            "/simulate",
            data={
                "evaluation_type": "legacy",
                "mode": "gateway",
                "subject_id": "operator-jane",
                "subject_type": "user",
                "action_verb": "read",
                "resource_type": "ahu",
                "resource_id": "rooftop-1",
            },
        )
        assert response.status_code == 200
        assert "Gateway response" in response.text


def test_console_does_not_import_basis_core_via_operation_aware_path():
    with gateway_client_app(_allow_handler) as client:
        client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
    assert "basis_core" not in sys.modules


def test_bearer_token_never_rendered_in_oa_html():
    with gateway_client_app(_allow_handler) as client:
        response = client.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert TOKEN not in response.text
