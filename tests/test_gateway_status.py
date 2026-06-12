"""Integration tests: gateway status in /ready and the homepage UI.

All gateway HTTP is mocked via httpx.MockTransport injected into the app's
gateway client. No live gateway is required.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from basis_console.gateway import GatewayClient

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"


def _install_gateway(client, handler: Handler | None, base_url: str | None) -> None:
    """Replace the running app's gateway client with a mock-backed one."""
    transport = httpx.MockTransport(handler) if handler is not None else None
    client.app.state.gateway_client = GatewayClient(base_url=base_url, transport=transport)


def _ready_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/ready":
        return httpx.Response(200, json={"status": "ready"})
    return httpx.Response(200, json={"status": "ok"})


def _unreachable_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


# ── /ready integration ──────────────────────────────────────────────────────


def test_ready_not_configured_still_ready(client):
    # Default fixture config has no GATEWAY_BASE_URL set.
    _install_gateway(client, handler=None, base_url=None)
    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["components"]["gateway_configured"] is False
    assert body["components"]["gateway_reachable"] is False
    assert body["gateway"]["status"] == "not_configured"


def test_ready_includes_gateway_reachable_when_ready(client):
    _install_gateway(client, _ready_handler, GATEWAY_URL)
    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    # Console stays ready regardless; gateway reported additively.
    assert body["status"] == "ready"
    assert body["components"]["gateway_configured"] is True
    assert body["components"]["gateway_reachable"] is True
    assert body["gateway"]["status"] == "ready"
    assert body["gateway"]["base_url"] == GATEWAY_URL


def test_ready_when_gateway_unreachable_console_still_ready(client):
    _install_gateway(client, _unreachable_handler, GATEWAY_URL)
    response = client.get("/ready")

    # Unreachable gateway must NOT make the console unready in Phase 2.
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["components"]["gateway_configured"] is True
    assert body["components"]["gateway_reachable"] is False
    assert body["gateway"]["status"] == "unreachable"


# ── Homepage UI integration ─────────────────────────────────────────────────


def test_homepage_shows_not_configured(client):
    _install_gateway(client, handler=None, base_url=None)
    response = client.get("/")

    assert response.status_code == 200
    assert "not_configured" in response.text
    assert "Gateway integration is not configured" in response.text


def test_homepage_shows_ready_and_url(client):
    _install_gateway(client, _ready_handler, GATEWAY_URL)
    response = client.get("/")

    assert response.status_code == 200
    assert GATEWAY_URL in response.text
    assert "reachable and reports ready" in response.text


def test_homepage_shows_unreachable_warning(client):
    _install_gateway(client, _unreachable_handler, GATEWAY_URL)
    response = client.get("/")

    assert response.status_code == 200
    assert "could not be contacted" in response.text
    # The honesty invariant: no local-authorization fallback is implied.
    assert "will not fall back to local authorization" in response.text


def test_network_error_does_not_crash_homepage(client):
    # A handler raising a generic transport error must surface as a status,
    # never a 500 from the UI route.
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("socket exploded", request=request)

    _install_gateway(client, boom, GATEWAY_URL)
    response = client.get("/")
    assert response.status_code == 200


def test_network_error_does_not_crash_ready(client):
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("socket exploded", request=request)

    _install_gateway(client, boom, GATEWAY_URL)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["components"]["gateway_reachable"] is False
