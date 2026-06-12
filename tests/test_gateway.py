"""Unit tests for the gateway client (mocked HTTP — no live gateway required)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from basis_console.gateway import GatewayClient, GatewayStatus

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"


def _client(handler: Handler, base_url: str | None = GATEWAY_URL) -> GatewayClient:
    return GatewayClient(base_url=base_url, transport=httpx.MockTransport(handler))


def test_not_configured_makes_no_request():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        calls.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    # base_url None → not configured; transport must never be touched.
    client = GatewayClient(base_url=None, transport=httpx.MockTransport(handler))
    report = client.check_status()

    assert report.status is GatewayStatus.NOT_CONFIGURED
    assert report.configured is False
    assert report.base_url is None
    assert calls == []


def test_health_ok_and_ready_ok_is_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "service": "basis-gateway"})
        if request.url.path == "/ready":
            return httpx.Response(200, json={"status": "ready", "service": "basis-gateway"})
        return httpx.Response(404)

    report = _client(handler).check_status()

    assert report.status is GatewayStatus.READY
    assert report.configured is True
    assert report.reachable is True
    assert report.ready is True
    assert report.base_url == GATEWAY_URL


def test_health_ok_but_ready_503_is_reachable_not_ready():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(503, json={"status": "not_ready"})

    report = _client(handler).check_status()

    assert report.status is GatewayStatus.REACHABLE
    assert report.reachable is True
    assert report.ready is False


def test_ready_probe_error_still_reachable():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise httpx.ConnectError("ready boom", request=request)

    report = _client(handler).check_status()

    assert report.status is GatewayStatus.REACHABLE
    assert report.reachable is True
    assert report.ready is False


def test_unreachable_when_health_connection_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    report = _client(handler).check_status()

    assert report.status is GatewayStatus.UNREACHABLE
    assert report.configured is True
    assert report.reachable is False
    assert report.detail is not None


def test_timeout_is_treated_as_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    report = _client(handler).check_status()

    assert report.status is GatewayStatus.UNREACHABLE


def test_health_non_200_is_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    report = _client(handler).check_status()

    assert report.status is GatewayStatus.ERROR
    assert report.reachable is False
    assert "500" in (report.detail or "")


@pytest.mark.parametrize("trailing", ["", "/", "///"])
def test_base_url_trailing_slashes_normalized(trailing):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"status": "ok"})

    client = GatewayClient(
        base_url=GATEWAY_URL + trailing,
        transport=httpx.MockTransport(handler),
    )
    report = client.check_status()

    assert report.base_url == GATEWAY_URL
    # No doubled slashes in the requested URL.
    assert f"{GATEWAY_URL}/health" in seen
