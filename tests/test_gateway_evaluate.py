"""Unit tests for GatewayClient.evaluate() (mocked HTTP — no live gateway)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from basis_console.gateway import GatewayClient, GatewayEvaluationStatus

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "secret-token-value-do-not-leak"


def _client(handler: Handler, *, base_url: str | None = GATEWAY_URL, token: str | None = TOKEN):
    transport = httpx.MockTransport(handler)
    return GatewayClient(base_url=base_url, bearer_token=token, transport=transport)


def _allow_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "request_id": "req-1",
            "outcome": "allow",
            "reason": "matched rule ot-operator-rbac",
            "policy_version": "2026.06.0",
            "correlation_id": "corr-1",
        },
        headers={"X-Correlation-ID": "corr-1"},
    )


# ---------------------------------------------------------------------------
# Prerequisites: no call without base URL / token
# ---------------------------------------------------------------------------


def test_not_configured_returns_not_configured():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    client = GatewayClient(
        base_url=None, bearer_token=TOKEN, transport=httpx.MockTransport(handler)
    )
    result = client.evaluate(action="read", resource_id="hvac:zone-a")

    assert result.status is GatewayEvaluationStatus.NOT_CONFIGURED
    assert result.called_gateway is False
    assert calls == []


def test_missing_token_returns_token_missing():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    client = GatewayClient(
        base_url=GATEWAY_URL, bearer_token=None, transport=httpx.MockTransport(handler)
    )
    result = client.evaluate(action="read")

    assert result.status is GatewayEvaluationStatus.TOKEN_MISSING
    assert result.called_gateway is False
    assert calls == []


# ---------------------------------------------------------------------------
# Request shape + identity boundary
# ---------------------------------------------------------------------------


def test_sends_bearer_token_and_no_subject():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return _allow_response(request)

    _client(handler).evaluate(
        action="read",
        resource_id="hvac:zone-a",
        context={"site": "bldg-a"},
    )

    assert seen["path"] == "/v1/evaluate"
    assert seen["auth"] == f"Bearer {TOKEN}"
    body = seen["body"]
    assert body == {"action": "read", "resource_id": "hvac:zone-a", "context": {"site": "bldg-a"}}
    # Identity boundary: the console must never send subject fields.
    assert "subject_id" not in body
    assert "subject_roles" not in body
    assert "subject_type" not in body


def test_omits_optional_fields_when_absent():
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _allow_response(request)

    _client(handler).evaluate(action="read")
    assert seen["body"] == {"action": "read"}


def test_sends_normalized_request_with_resource_type():
    """The normalized shape carries a bare verb + resource_type + local id."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _allow_response(request)

    _client(handler).evaluate(action="read", resource_type="ahu", resource_id="rooftop-1")

    body = seen["body"]
    assert body == {"action": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}
    # The console submits the bare verb; the gateway composes the typed action/id.
    assert ":" not in body["action"]
    assert ":" not in body["resource_id"]


def test_direct_typed_request_omits_resource_type():
    """A fully-typed (direct) request sends no resource_type."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _allow_response(request)

    _client(handler).evaluate(action="read:ahu", resource_id="ahu:rooftop-1")
    assert seen["body"] == {"action": "read:ahu", "resource_id": "ahu:rooftop-1"}
    assert "resource_type" not in seen["body"]


# ---------------------------------------------------------------------------
# Response classification
# ---------------------------------------------------------------------------


def test_allow_maps_to_success():
    result = _client(_allow_response).evaluate(action="read", resource_id="hvac:zone-a")
    assert result.status is GatewayEvaluationStatus.SUCCESS
    assert result.http_status == 200
    assert result.outcome == "allow"
    assert result.reason == "matched rule ot-operator-rbac"
    assert result.policy_version == "2026.06.0"
    assert result.correlation_id == "corr-1"
    assert result.response_json is not None


def test_deny_403_maps_to_denied_and_is_not_hidden():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"request_id": "r", "outcome": "deny", "reason": "role viewer lacks write"},
        )

    result = _client(handler).evaluate(action="write", resource_id="hvac:zone-a")
    assert result.status is GatewayEvaluationStatus.DENIED
    assert result.http_status == 403
    assert result.outcome == "deny"
    assert result.reason == "role viewer lacks write"


def test_not_applicable_403_maps_to_denied():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"request_id": "r", "outcome": "not_applicable", "reason": "no policy"}
        )

    result = _client(handler).evaluate(action="read")
    assert result.status is GatewayEvaluationStatus.DENIED
    assert result.outcome == "not_applicable"


def test_401_maps_to_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": "authentication_failed", "message": "Token verification failed"}
        )

    result = _client(handler).evaluate(action="read")
    assert result.status is GatewayEvaluationStatus.UNAUTHORIZED
    assert result.error_code == "authentication_failed"
    assert result.error_message == "Token verification failed"


def test_400_maps_to_validation_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": "validation_failed", "message": "action: bad format"}
        )

    result = _client(handler).evaluate(action="read")
    assert result.status is GatewayEvaluationStatus.VALIDATION_ERROR
    assert result.error_code == "validation_failed"


def test_503_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "evaluator_unavailable"})

    result = _client(handler).evaluate(action="read")
    assert result.status is GatewayEvaluationStatus.UNAVAILABLE
    assert result.http_status == 503


def test_500_maps_to_gateway_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal_error"})

    result = _client(handler).evaluate(action="read")
    assert result.status is GatewayEvaluationStatus.GATEWAY_ERROR


def test_network_failure_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    result = _client(handler).evaluate(action="read")
    assert result.status is GatewayEvaluationStatus.UNAVAILABLE
    assert result.http_status is None
    assert result.detail is not None


def test_token_never_appears_on_result():
    """No field of the result object should ever contain the bearer token."""
    result = _client(_allow_response).evaluate(action="read")
    for value in vars(result).values():
        assert TOKEN not in str(value)
