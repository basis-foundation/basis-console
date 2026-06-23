"""Route tests for gateway-backed simulation (mocked HTTP).

These exercise the alignment with gateway-owned composition: the console submits
a *normalized* request (bare verb + resource_type + local resource_id) and the
gateway composes the canonical action and resource id.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from basis_console.gateway import GatewayClient
from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "super-secret-token-abc123"

# Normalized form: bare verb + resource_type (domain) + LOCAL resource id.
_VALID_FORM = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
    "context": "site=bldg-a",
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


def _allow_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "request_id": "req-1",
            "outcome": "allow",
            "reason": "matched rule ot-operator-rbac",
            "policy_version": "2026.06.0",
            "correlation_id": "corr-success",
        },
        headers={"X-Correlation-ID": "corr-success"},
    )


# ---------------------------------------------------------------------------
# Preview mode still works regardless of gateway configuration
# ---------------------------------------------------------------------------


def test_preview_mode_works_without_gateway(client):
    response = client.post("/simulate", data=dict(_VALID_FORM, mode="preview"))
    assert response.status_code == 200
    assert "Normalized request preview" in response.text
    assert "Gateway response" not in response.text


def test_preview_mode_default_when_mode_absent(client):
    response = client.post("/simulate", data=_VALID_FORM)
    assert response.status_code == 200
    assert "Normalized request preview" in response.text


# ---------------------------------------------------------------------------
# Gateway evaluation availability
# ---------------------------------------------------------------------------


def test_eval_disabled_when_base_url_unset(client):
    response = client.get("/simulate")
    assert response.status_code == 200
    assert "Gateway evaluation is not configured" in response.text
    assert "Evaluate through basis-gateway" not in response.text


def test_eval_requires_token_when_base_url_set_but_no_token():
    with gateway_client_app(None, base_url=GATEWAY_URL, token=None) as client:
        response = client.get("/simulate")
        assert response.status_code == 200
        assert "requires a configured server-side bearer token" in response.text
        assert "Evaluate through basis-gateway" not in response.text


def test_eval_button_shown_when_configured():
    with gateway_client_app(_allow_handler) as client:
        response = client.get("/simulate")
        assert response.status_code == 200
        assert "Evaluate through basis-gateway" in response.text


def test_gateway_mode_requested_but_not_configured_shows_warning(client):
    response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
    assert response.status_code == 200
    assert "Gateway evaluation is not configured" in response.text
    assert "Gateway response" not in response.text


# ---------------------------------------------------------------------------
# Gateway responses are displayed (verbatim, clearly labelled)
# ---------------------------------------------------------------------------


def test_successful_evaluation_displays_allow():
    with gateway_client_app(_allow_handler) as client:
        response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
        assert response.status_code == 200
        assert "Gateway response" in response.text
        assert "allow" in response.text
        assert "matched rule ot-operator-rbac" in response.text
        assert "corr-success" in response.text


def test_gateway_evaluation_sends_normalized_request_not_composed():
    """The body sent to /v1/evaluate is the normalized shape — the gateway composes.

    The console submits a BARE verb plus resource_type and a LOCAL resource_id; it
    must NOT pre-compose the {verb}:{domain} action or the typed resource id.
    """
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data=dict(
                _VALID_FORM,
                action_verb="write",
                resource_type="setpoint",
                resource_id="zone-3",
                mode="gateway",
            ),
        )
        assert response.status_code == 200

    body = seen["body"]
    assert isinstance(body, dict)
    # Normalized: bare verb, resource_type, LOCAL resource id.
    assert body["action"] == "write"
    assert ":" not in body["action"]
    assert body["resource_type"] == "setpoint"
    assert body["resource_id"] == "zone-3"
    assert ":" not in body["resource_id"]
    # The identity boundary still holds: no subject is ever sent.
    assert "subject_id" not in body
    assert "subject_roles" not in body
    assert "subject_type" not in body


def test_gateway_composition_evidence_is_displayed():
    """When the gateway returns composition evidence, the console shows it."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "request_id": "req-1",
                "outcome": "allow",
                "reason": "ok",
                "context": {
                    "basis_gateway.resource_composed": True,
                    "basis_gateway.original_resource_id": "rooftop-1",
                    "basis_gateway.resource_type": "ahu",
                    "basis_gateway.composed_resource_id": "ahu:rooftop-1",
                },
            },
        )

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
        assert response.status_code == 200
        assert "Gateway composition" in response.text
        assert "basis_gateway.composed_resource_id" in response.text
        assert "ahu:rooftop-1" in response.text


def test_denied_evaluation_is_shown_not_hidden():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"request_id": "r", "outcome": "deny", "reason": "role viewer lacks write"},
        )

    with gateway_client_app(handler) as client:
        response = client.post(
            "/simulate",
            data=dict(
                _VALID_FORM,
                action_verb="write",
                resource_type="setpoint",
                resource_id="zone-3",
                mode="gateway",
            ),
        )
        assert response.status_code == 200
        assert "Gateway response" in response.text
        assert "deny" in response.text
        assert "role viewer lacks write" in response.text


def test_unauthorized_evaluation_is_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": "authentication_failed", "message": "Token verification failed"}
        )

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
        assert response.status_code == 200
        assert "authentication_failed" in response.text


def test_validation_error_evaluation_is_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": "validation_failed", "message": "action: bad format"}
        )

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
        assert response.status_code == 200
        assert "validation_failed" in response.text


def test_gateway_unavailable_is_shown():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with gateway_client_app(handler) as client:
        response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
        assert response.status_code == 200
        assert "Gateway response" in response.text
        assert "could not contact gateway" in response.text


def test_invalid_input_does_not_call_gateway():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return _allow_handler(request)

    with gateway_client_app(handler) as client:
        # Missing required fields → invalid; gateway must not be called.
        response = client.post("/simulate", data={"action_verb": "read", "mode": "gateway"})
        assert response.status_code == 200
        assert "Please correct the following" in response.text
        assert calls == []
        assert "Gateway response" not in response.text


# ---------------------------------------------------------------------------
# Token safety + boundary
# ---------------------------------------------------------------------------


def test_bearer_token_never_rendered_in_html():
    with gateway_client_app(_allow_handler) as client:
        assert TOKEN not in client.get("/simulate").text
        response = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
        assert TOKEN not in response.text


def test_console_does_not_import_basis_core():
    with gateway_client_app(_allow_handler) as client:
        client.post("/simulate", data=dict(_VALID_FORM, mode="gateway"))
    assert "basis_core" not in sys.modules


@pytest.mark.parametrize("path", ["/", "/policies", "/simulate", "/audit"])
def test_existing_pages_still_render(client, path):
    assert client.get(path).status_code == 200
