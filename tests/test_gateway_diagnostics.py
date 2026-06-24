"""Tests for Gateway Diagnostics (Phase 9).

Covers the gateway client's diagnostic probes, the redaction helpers, the
diagnostics aggregator, and the ``/gateway`` view across its three states
(reachable / unreachable / not configured). All gateway HTTP is mocked via
``httpx.MockTransport`` — no live gateway is required.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from basis_console.diagnostics import gather_gateway_diagnostics
from basis_console.gateway import GatewayClient
from basis_console.gateway.redaction import is_sensitive_key, redact_headers, redact_json

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"
CORR = "11111111-2222-4333-8444-555555555555"


def _client(handler: Handler, base_url: str | None = GATEWAY_URL) -> GatewayClient:
    return GatewayClient(base_url=base_url, transport=httpx.MockTransport(handler))


def _install_gateway(client, handler: Handler | None, base_url: str | None) -> None:
    """Replace the running app's gateway client with a mock-backed one."""
    transport = httpx.MockTransport(handler) if handler is not None else None
    client.app.state.gateway_client = GatewayClient(base_url=base_url, transport=transport)


def _healthy_handler(request: httpx.Request) -> httpx.Response:
    headers = {"X-Correlation-ID": CORR}
    if request.url.path == "/health":
        return httpx.Response(
            200, json={"status": "ok", "service": "basis-gateway"}, headers=headers
        )
    if request.url.path == "/ready":
        return httpx.Response(
            200,
            json={
                "status": "ready",
                "service": "basis-gateway",
                "components": {
                    "configuration_loaded": True,
                    "evaluator_initialized": True,
                    "policy_loaded": True,
                    "oidc_configured": True,
                    "jwks_available": True,
                },
            },
            headers=headers,
        )
    return httpx.Response(404)


def _degraded_handler(request: httpx.Request) -> httpx.Response:
    headers = {"X-Correlation-ID": CORR}
    if request.url.path == "/health":
        return httpx.Response(
            200, json={"status": "ok", "service": "basis-gateway"}, headers=headers
        )
    # 503 not_ready with a future/unknown component and a reason map.
    return httpx.Response(
        503,
        json={
            "status": "not_ready",
            "service": "basis-gateway",
            "components": {
                "configuration_loaded": True,
                "policy_loaded": False,
                "future_component_xyz": False,
            },
            "reason": "policy_loaded not ready",
            "reasons": {"policy_loaded": "policy file missing"},
            "correlation_id": CORR,
        },
        headers=headers,
    )


def _unreachable_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


# ── Redaction helpers ─────────────────────────────────────────────────────────


def test_is_sensitive_key_matches_credentials():
    for key in ("Authorization", "access_token", "X-Refresh-Token", "client_secret", "PASSWORD"):
        assert is_sensitive_key(key) is True
    for key in ("status", "service", "correlation_id", "policy_version", "components"):
        assert is_sensitive_key(key) is False


def test_redact_headers_redacts_sensitive_values():
    redacted = redact_headers(
        {"Authorization": "Bearer abc.def", "Content-Type": "application/json"}
    )
    assert redacted["authorization"] == "[redacted]"
    assert redacted["content-type"] == "application/json"
    assert "abc.def" not in str(redacted)


def test_redact_json_walks_nested_structures():
    payload = {
        "status": "ready",
        "nested": {"access_token": "supersecret", "ok": True},
        "list": [{"password": "hunter2"}],
    }
    redacted = redact_json(payload)
    assert redacted["status"] == "ready"
    assert redacted["nested"]["access_token"] == "[redacted]"
    assert redacted["nested"]["ok"] is True
    assert redacted["list"][0]["password"] == "[redacted]"
    assert "supersecret" not in str(redacted)
    assert "hunter2" not in str(redacted)


# ── Gateway client diagnostic probes ──────────────────────────────────────────


def test_get_health_captures_status_and_correlation():
    probe = _client(_healthy_handler).get_health()
    assert probe.reached is True
    assert probe.ok is True
    assert probe.http_status == 200
    assert probe.endpoint == "/health"
    assert probe.target_url == f"{GATEWAY_URL}/health"
    assert probe.correlation_id == CORR
    assert probe.response_json == {"status": "ok", "service": "basis-gateway"}
    assert probe.checked_at  # ISO timestamp populated


def test_get_ready_captures_components():
    probe = _client(_healthy_handler).get_ready()
    assert probe.ok is True
    assert probe.response_json is not None
    assert probe.response_json["components"]["policy_loaded"] is True


def test_probe_not_configured_makes_no_request():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json={})

    client = GatewayClient(base_url=None, transport=httpx.MockTransport(handler))
    probe = client.get_health()
    assert probe.not_configured is True
    assert probe.reached is False
    assert probe.target_url is None
    assert calls == []


def test_probe_unreachable_is_captured_not_raised():
    probe = _client(_unreachable_handler).get_health()
    assert probe.reached is False
    assert probe.error is not None
    assert probe.http_status is None


def test_client_redacts_response_headers_and_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "ok", "access_token": "leaked-token"},
            headers={"X-Correlation-ID": CORR, "Set-Cookie": "session=abc"},
        )

    probe = _client(handler).get_health()
    assert probe.response_json is not None
    assert probe.response_json["access_token"] == "[redacted]"
    assert probe.headers.get("set-cookie") == "[redacted]"
    assert "leaked-token" not in str(probe.response_json)
    assert "session=abc" not in str(probe.headers)


# ── Diagnostics aggregator ────────────────────────────────────────────────────


def test_aggregator_reports_ready_state():
    diagnostics = gather_gateway_diagnostics(_client(_healthy_handler))
    assert diagnostics.connection_state == "ready"
    assert diagnostics.overall_ready is True
    names = [c.name for c in diagnostics.components]
    assert "policy_loaded" in names
    assert diagnostics.policy.exposed is True


def test_aggregator_renders_unknown_components_and_reasons():
    diagnostics = gather_gateway_diagnostics(_client(_degraded_handler))
    names = {c.name for c in diagnostics.components}
    assert "future_component_xyz" in names  # arbitrary keys handled
    policy_loaded = next(c for c in diagnostics.components if c.name == "policy_loaded")
    assert policy_loaded.ready is False
    assert policy_loaded.reason == "policy file missing"
    assert diagnostics.overall_ready is False


def test_aggregator_not_configured_state():
    diagnostics = gather_gateway_diagnostics(GatewayClient(base_url=None))
    assert diagnostics.connection_state == "not_configured"
    assert diagnostics.overall_ready is None
    assert diagnostics.components == ()


def test_aggregator_unreachable_state():
    diagnostics = gather_gateway_diagnostics(_client(_unreachable_handler))
    assert diagnostics.connection_state == "unreachable"
    assert diagnostics.overall_ready is None


# ── /gateway view integration ─────────────────────────────────────────────────


def test_gateway_page_renders(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Gateway Diagnostics" in response.text


def test_gateway_page_in_navigation(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    for path in ("/", "/simulate", "/identity", "/gateway"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert 'href="/gateway"' in resp.text


def test_gateway_not_configured_state(client):
    _install_gateway(client, handler=None, base_url=None)
    response = client.get("/gateway")
    assert response.status_code == 200
    assert "not_configured" in response.text
    assert "GATEWAY_BASE_URL" in response.text


def test_gateway_unreachable_state(client):
    _install_gateway(client, _unreachable_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert response.status_code == 200
    assert "unreachable" in response.text
    assert "could not be contacted" in response.text
    # Honesty invariant carried over: no local-authorization fallback implied.
    assert "never falls back to local authorization" in response.text


def test_gateway_health_renders_when_reachable(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert "GET /health" in response.text
    assert f"{GATEWAY_URL}/health" in response.text
    assert "basis-gateway" in response.text


def test_gateway_readiness_renders_when_reachable(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert "GET /ready" in response.text
    assert "Components" in response.text


def test_gateway_readiness_components_render_dynamically(client):
    _install_gateway(client, _degraded_handler, GATEWAY_URL)
    response = client.get("/gateway")
    # Arbitrary component keys and their reasons must render.
    assert "future_component_xyz" in response.text
    assert "policy file missing" in response.text


def test_gateway_correlation_id_displayed(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert CORR in response.text
    assert "Correlation IDs" in response.text


def test_gateway_policy_capability_not_exposed_message(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    response = client.get("/gateway")
    # policy_version is not exposed by /health or /ready — say so, don't invent it.
    assert "does not expose policy name/version" in response.text


def test_gateway_raw_response_renders_safely(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert "Raw responses" in response.text
    assert '<pre class="json"><code>' in response.text


def test_gateway_sensitive_data_is_redacted_in_page(client):
    def leaky_handler(request: httpx.Request) -> httpx.Response:
        headers = {"X-Correlation-ID": CORR, "Authorization": "Bearer leaked.jwt.value"}
        if request.url.path == "/health":
            return httpx.Response(
                200, json={"status": "ok", "service": "basis-gateway"}, headers=headers
            )
        return httpx.Response(
            200,
            json={"status": "ready", "service": "basis-gateway", "access_token": "leaked-secret"},
            headers=headers,
        )

    _install_gateway(client, leaky_handler, GATEWAY_URL)
    response = client.get("/gateway")
    assert response.status_code == 200
    assert "leaked.jwt.value" not in response.text
    assert "leaked-secret" not in response.text
    assert "[redacted]" in response.text


def test_network_error_does_not_crash_gateway_page(client):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("socket exploded", request=request)

    _install_gateway(client, boom, GATEWAY_URL)
    response = client.get("/gateway")
    assert response.status_code == 200


# ── Existing pages still work ─────────────────────────────────────────────────


def test_existing_simulator_and_identity_pages_still_work(client):
    _install_gateway(client, _healthy_handler, GATEWAY_URL)
    sim = client.get("/simulate")
    assert sim.status_code == 200
    assert "does not evaluate decisions" in sim.text

    ident = client.get("/identity")
    assert ident.status_code == 200
    assert "Identity &amp; Access Explorer" in ident.text
