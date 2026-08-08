"""Operator/Training mode-parity tests for the operation-aware simulator flow (PR 4).

Extends ``test_console_mode.py``'s existing parity pattern (byte-identical
controls/status codes, same navigation) to the new operation-aware evaluation
selector, request, and result rendering — the integration plan requires this
parity to ship in the same PR that introduces the shared behavior (no window
where Operator and Training modes diverge for this flow).

Full degraded-state parity coverage (every row of the endpoint's HTTP
classification table) is PR 6 scope; this file proves the invariant holds for
the representative set PR 4 must cover: the selector itself, a preview
submission, and one live outcome from each of the three governed/ungoverned
categories (allow, not_applicable, governed failure, generic failure).
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

_OA_FORM = {
    "evaluation_type": "operation_aware",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
}

ALLOW_BODY = {
    "request_id": "req-allow",
    "correlation_id": "corr-allow",
    "evaluation_status": "completed",
    "outcome": "allow",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "disposition": "allow",
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

GOVERNED_FAILURE_BODY = {
    "request_id": "req-f",
    "correlation_id": "corr-f",
    "evaluation_status": "failed",
    "failure_reason": "invalid_request",
    "disposition": "deny",
}


@contextmanager
def _mode_client(monkeypatch, mode: str | None, handler=None) -> Iterator[TestClient]:
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


def _json_handler(status: int, payload: dict[str, object], **headers: str):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=headers or None)

    return handler


# ---------------------------------------------------------------------------
# Same controls in both modes
# ---------------------------------------------------------------------------


def test_both_modes_show_same_evaluation_type_choices(monkeypatch):
    with (
        _mode_client(monkeypatch, None) as operator,
        _mode_client(monkeypatch, "training") as training,
    ):
        op = operator.get("/simulate").text
        tr = training.get("/simulate").text
        for control in (
            'name="evaluation_type" value="legacy"',
            'name="evaluation_type" value="operation_aware"',
            'id="evaluation_type_legacy"',
            'id="evaluation_type_operation_aware"',
        ):
            assert control in op, control
            assert control in tr, control


def test_both_modes_hide_same_context_control_for_operation_aware(monkeypatch):
    with (
        _mode_client(monkeypatch, None) as operator,
        _mode_client(monkeypatch, "training") as training,
    ):
        op = operator.post("/simulate", data={**_OA_FORM, "mode": "preview"}).text
        tr = training.post("/simulate", data={**_OA_FORM, "mode": "preview"}).text
        for body in (op, tr):
            assert 'id="legacy-only-context"' in body
            assert 'class="is-hidden"' in body.split('id="legacy-only-context"')[1][:60]


def test_both_modes_disable_same_legacy_only_controls_for_operation_aware(monkeypatch):
    """Operator and Training modes must produce the same disabled/enabled state."""
    with (
        _mode_client(monkeypatch, None) as operator,
        _mode_client(monkeypatch, "training") as training,
    ):
        op = operator.post("/simulate", data={**_OA_FORM, "mode": "preview"}).text
        tr = training.post("/simulate", data={**_OA_FORM, "mode": "preview"}).text
        for body in (op, tr):
            for fieldset_id in ("legacy-only-fields", "legacy-only-context"):
                snippet = body.split(f'id="{fieldset_id}"')[1][:120]
                assert "disabled" in snippet

    with (
        _mode_client(monkeypatch, None) as operator,
        _mode_client(monkeypatch, "training") as training,
    ):
        op = operator.get("/simulate").text
        tr = training.get("/simulate").text
        for body in (op, tr):
            for fieldset_id in ("legacy-only-fields", "legacy-only-context"):
                snippet = body.split(f'id="{fieldset_id}"')[1][:120]
                assert "disabled" not in snippet


# ---------------------------------------------------------------------------
# Same request built, same client call, same route status
# ---------------------------------------------------------------------------


def test_both_modes_submit_same_operation_aware_request(monkeypatch):
    seen: dict[str, list[object]] = {"operator": [], "training": []}

    def make_handler(bucket: str):
        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            seen[bucket].append(_json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json=ALLOW_BODY, headers={"X-Correlation-ID": "corr-allow"})

        return handler

    with _mode_client(monkeypatch, None, make_handler("operator")) as operator:
        r = operator.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert r.status_code == 200
    with _mode_client(monkeypatch, "training", make_handler("training")) as training:
        r = training.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
        assert r.status_code == 200

    assert (
        seen["operator"]
        == seen["training"]
        == [{"action": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}]
    )


@pytest.mark.parametrize(
    "body,http_status",
    [
        (ALLOW_BODY, 200),
        (NOT_APPLICABLE_BODY, 403),
        (GOVERNED_FAILURE_BODY, 400),
    ],
)
def test_both_modes_render_same_returned_evidence(monkeypatch, body, http_status):
    handler = _json_handler(http_status, body)
    with _mode_client(monkeypatch, None, handler) as operator:
        op = operator.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
    with _mode_client(monkeypatch, "training", handler) as training:
        tr = training.post("/simulate", data={**_OA_FORM, "mode": "gateway"})

    assert op.status_code == tr.status_code == 200

    # Same governed facts rendered in both modes (allowing for the training
    # banner / callout markup that surrounds — never replaces — them).
    for key_fragment in (str(http_status), body.get("outcome") or body.get("failure_reason") or ""):
        if key_fragment:
            assert key_fragment in op.text
            assert key_fragment in tr.text


def test_both_modes_same_route_status_for_client_failure(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _mode_client(monkeypatch, None, handler) as operator:
        op = operator.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
    with _mode_client(monkeypatch, "training", handler) as training:
        tr = training.post("/simulate", data={**_OA_FORM, "mode": "gateway"})

    assert op.status_code == tr.status_code == 200
    assert "could not contact gateway" in op.text
    assert "could not contact gateway" in tr.text


def test_both_modes_same_validation_behavior(monkeypatch):
    with (
        _mode_client(monkeypatch, None) as operator,
        _mode_client(monkeypatch, "training") as training,
    ):
        op = operator.post("/simulate", data={**_OA_FORM, "context": "a=b"})
        tr = training.post("/simulate", data={**_OA_FORM, "context": "a=b"})
        assert op.status_code == tr.status_code == 200
        assert "does not accept a context value" in op.text
        assert "does not accept a context value" in tr.text


def test_neither_mode_changes_authorization_behavior(monkeypatch):
    """The same DENY result renders as DENY (never ALLOW) in both modes."""
    deny_body = {
        "request_id": "req-deny",
        "correlation_id": "corr-deny",
        "evaluation_status": "completed",
        "outcome": "deny",
        "bundle_id": "site-a-bundle",
        "bundle_version": "1.0.0",
        "disposition": "deny",
    }
    handler = _json_handler(403, deny_body)
    with _mode_client(monkeypatch, None, handler) as operator:
        op = operator.post("/simulate", data={**_OA_FORM, "mode": "gateway"})
    with _mode_client(monkeypatch, "training", handler) as training:
        tr = training.post("/simulate", data={**_OA_FORM, "mode": "gateway"})

    for body in (op.text, tr.text):
        assert "deny" in body
        assert "outcome allow" not in body.lower()


# ---------------------------------------------------------------------------
# Submitted-input HTML-escaping parity (PR 6 correction)
# ---------------------------------------------------------------------------
#
# Mirrors test_simulate_operation_aware_routes.py's
# test_malicious_resource_id_rejected_and_escaped_when_echoed_back_to_form —
# the representative submitted-input escaping case (resource_id is the only
# one of the three fields that is ever echoed back into the page at all;
# action_verb/resource_type are closed-vocabulary <select> controls that are
# never reflected, escaped or not — see that file's own tests for both
# fields). This proves the escaping behavior, the validation outcome, and
# the zero-gateway-call behavior are identical in both presentation modes,
# and that Training mode adds no additional unescaped content around it.

_XSS_PAYLOAD = "<script>alert(1)</script>"
_XSS_ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_both_modes_escape_malicious_submitted_resource_id_identically(monkeypatch):
    calls: dict[str, list[str]] = {"operator": [], "training": []}

    def make_handler(bucket: str):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            calls[bucket].append(request.url.path)
            return httpx.Response(200, json=ALLOW_BODY)

        return handler

    with _mode_client(monkeypatch, None, make_handler("operator")) as operator:
        op = operator.post(
            "/simulate",
            data={**_OA_FORM, "mode": "gateway", "resource_id": _XSS_PAYLOAD},
        )
    with _mode_client(monkeypatch, "training", make_handler("training")) as training:
        tr = training.post(
            "/simulate",
            data={**_OA_FORM, "mode": "gateway", "resource_id": _XSS_PAYLOAD},
        )

    # Same route status in both modes.
    assert op.status_code == tr.status_code == 200

    for label, response in (("operator", op), ("training", tr)):
        # Same validation outcome.
        assert "simple safe string" in response.text
        # Same escaping: raw payload absent, escaped form present in the
        # echoed form value, in both modes.
        assert _XSS_PAYLOAD not in response.text, label
        snippet = response.text[response.text.find('id="resource_id"') :][:200]
        assert f'value="{_XSS_ESCAPED}"' in snippet, label
        # No fabricated evaluation/evidence in either mode. Checked as the
        # exact <dt>/<dd> markup the live result section uses (not just the
        # bare phrase "Kernel outcome") because Training mode's always-on
        # ecosystem-flow table legitimately mentions "7. Kernel outcome" as
        # static educational prose regardless of validation state — that is
        # not a fabricated evaluation result and must not be confused with
        # one.
        assert "Evaluation result</h3>" not in response.text, label
        assert "<dt>Kernel outcome</dt>" not in response.text, label
        assert "<dt>Gateway disposition</dt>" not in response.text, label

    # Same (zero) number of gateway calls in both modes — validation failed
    # before either mode's route code could reach GatewayClient.
    assert calls["operator"] == calls["training"] == []

    # Training mode's only permitted difference is additional
    # console-authored educational markup elsewhere on the page — it must
    # not introduce any *additional* reflection of the submitted value.
    assert tr.text.count(_XSS_PAYLOAD) == op.text.count(_XSS_PAYLOAD) == 0
    assert tr.text.count(_XSS_ESCAPED) == op.text.count(_XSS_ESCAPED) == 1


def test_training_mode_may_add_banner_without_changing_oa_workflow(monkeypatch):
    with _mode_client(monkeypatch, "training") as training:
        response = training.post("/simulate", data={**_OA_FORM, "mode": "preview"})
        assert response.status_code == 200
        assert "Training mode is enabled" in response.text
        # The shared workflow content is still present alongside the banner.
        assert "Submitted request" in response.text
