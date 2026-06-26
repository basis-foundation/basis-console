"""Phase 14 — live gateway integration polish.

Focused tests for the polish added in Phase 14, all with mocked gateway HTTP:
  - probe latency is measured and surfaced;
  - timeouts are distinguished from generic unreachability;
  - the diagnostics aggregator exposes a next step, last-successful timestamps,
    and a connection-state glossary;
  - evaluation outcome explanations are stable and operator-facing;
  - the /gateway and home/workspace views render the new, consistent state info;
  - the simulator surfaces clear error explanations and graceful "not returned"
    handling for a missing correlation id / policy version.

No new gateway endpoints are invented and no live gateway is required.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from basis_console.diagnostics import (
    REDACTION_ASSURANCE_NOTICE,
    connection_state_guide,
    gather_gateway_diagnostics,
)
from basis_console.gateway import GatewayClient
from basis_console.gateway.models import (
    EVALUATION_STATE_EXPLANATIONS,
    GatewayEvaluationResult,
    GatewayEvaluationStatus,
)
from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state

Handler = Callable[[httpx.Request], httpx.Response]

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "super-secret-token-xyz789"
CORR = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _client(handler: Handler, base_url: str | None = GATEWAY_URL) -> GatewayClient:
    return GatewayClient(base_url=base_url, transport=httpx.MockTransport(handler))


def _healthy_handler(request: httpx.Request) -> httpx.Response:
    headers = {"X-Correlation-ID": CORR}
    if request.url.path == "/health":
        return httpx.Response(
            200, json={"status": "ok", "service": "basis-gateway"}, headers=headers
        )
    return httpx.Response(
        200,
        json={"status": "ready", "service": "basis-gateway", "components": {"policy_loaded": True}},
        headers=headers,
    )


def _timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


@contextmanager
def _gateway_app(
    handler: Handler | None, *, base_url: str | None = GATEWAY_URL, token: str | None = TOKEN
) -> Iterator[TestClient]:
    reset_readiness_state()
    app = create_app()
    with TestClient(app) as client:
        transport = httpx.MockTransport(handler) if handler is not None else None
        client.app.state.gateway_client = GatewayClient(
            base_url=base_url, bearer_token=token, transport=transport
        )
        yield client


# ── Latency measurement ───────────────────────────────────────────────────────


def test_probe_records_latency_on_success():
    probe = _client(_healthy_handler).get_health()
    assert probe.latency_ms is not None
    assert probe.latency_ms >= 0.0


def test_diagnostics_surface_latency():
    diagnostics = gather_gateway_diagnostics(_client(_healthy_handler))
    assert diagnostics.health.latency_ms is not None
    assert diagnostics.ready.latency_ms is not None


# ── Timeout distinguished from generic unreachable ────────────────────────────


def test_probe_marks_timeout_distinctly():
    probe = _client(_timeout_handler).get_health()
    assert probe.reached is False
    assert probe.timed_out is True
    assert probe.error is not None
    assert "timeout" in probe.error.lower()
    # Latency is still recorded for a timed-out attempt.
    assert probe.latency_ms is not None


def test_check_status_timeout_detail_mentions_timeout():
    report = _client(_timeout_handler).check_status()
    # Status stays UNREACHABLE (a timeout is a kind of unreachable)...
    assert report.status.value == "unreachable"
    # ...but the detail explains it was specifically a timeout.
    assert "timeout" in (report.detail or "").lower()


def test_evaluate_timeout_is_unavailable_and_flagged():
    result = GatewayClient(
        base_url=GATEWAY_URL,
        bearer_token=TOKEN,
        transport=httpx.MockTransport(_timeout_handler),
    ).evaluate(action="read", resource_type="ahu", resource_id="rooftop-1")
    assert result.status is GatewayEvaluationStatus.UNAVAILABLE
    assert result.timed_out is True
    assert "timeout" in (result.detail or "").lower()


# ── Aggregator: next step, last successful, state glossary ────────────────────


def test_aggregator_exposes_next_step_for_each_state():
    ready = gather_gateway_diagnostics(_client(_healthy_handler))
    assert ready.next_step  # ready state has a next step
    notcfg = gather_gateway_diagnostics(GatewayClient(base_url=None))
    assert "GATEWAY_BASE_URL" in notcfg.next_step
    unreachable = gather_gateway_diagnostics(_client(_timeout_handler))
    assert unreachable.next_step


def test_aggregator_records_last_successful_when_ok():
    diagnostics = gather_gateway_diagnostics(_client(_healthy_handler))
    assert diagnostics.last_successful_health == diagnostics.health.checked_at
    assert diagnostics.last_successful_ready == diagnostics.ready.checked_at


def test_aggregator_last_successful_none_when_unreachable():
    diagnostics = gather_gateway_diagnostics(_client(_timeout_handler))
    assert diagnostics.last_successful_health is None
    assert diagnostics.last_successful_ready is None


def test_connection_state_guide_covers_all_states():
    states = {guide.state for guide in connection_state_guide()}
    assert states == {"not_configured", "unreachable", "error", "reachable", "ready"}
    for guide in connection_state_guide():
        assert guide.meaning and guide.next_step


# ── Evaluation explanations ───────────────────────────────────────────────────


def test_every_evaluation_status_has_an_explanation():
    for status in GatewayEvaluationStatus:
        assert status in EVALUATION_STATE_EXPLANATIONS
        assert EVALUATION_STATE_EXPLANATIONS[status]


def test_evaluation_result_explanation_property():
    denied = GatewayEvaluationResult(status=GatewayEvaluationStatus.DENIED, http_status=403)
    assert "DENY" in denied.explanation
    unauthorized = GatewayEvaluationResult(status=GatewayEvaluationStatus.UNAUTHORIZED)
    assert "token" in unauthorized.explanation.lower()


# ── /gateway view: new fields render ──────────────────────────────────────────


def test_gateway_page_shows_latency_and_next_step():
    with _gateway_app(_healthy_handler) as client:
        text = client.get("/gateway").text
    assert "Response latency" in text
    assert "ms" in text
    assert "Next step" in text


def test_gateway_page_shows_state_glossary_and_redaction_assurance():
    with _gateway_app(_healthy_handler) as client:
        text = client.get("/gateway").text
    assert "What these connection states mean" in text
    assert REDACTION_ASSURANCE_NOTICE[:40] in text


def test_gateway_page_timeout_message():
    with _gateway_app(_timeout_handler) as client:
        text = client.get("/gateway").text
    assert "unreachable" in text
    assert "timeout" in text.lower()


# ── Home/workspace consistency ────────────────────────────────────────────────


def test_home_links_to_diagnostics_with_consistent_state():
    with _gateway_app(_healthy_handler) as client:
        text = client.get("/").text
    assert 'href="/gateway"' in text
    assert 'href="/workspace"' in text
    # The same state label vocabulary is used.
    assert "ready" in text


def test_workspace_shows_next_step():
    with _gateway_app(_healthy_handler) as client:
        text = client.get("/workspace").text
    assert "Next step" in text


# ── Simulator error-state explanations ────────────────────────────────────────

_VALID_FORM = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
    "context": "",
}


def test_simulator_unauthorized_shows_explanation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "authentication_failed", "message": "bad token"})

    with _gateway_app(handler) as client:
        text = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway")).text
    assert "rejected the bearer token" in text


def test_simulator_validation_error_shows_explanation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "validation_failed", "message": "bad action"})

    with _gateway_app(handler) as client:
        text = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway")).text
    assert "rejected the request body" in text


def test_simulator_missing_correlation_id_is_explicit():
    def handler(request: httpx.Request) -> httpx.Response:
        # ALLOW with no correlation id and no policy version returned.
        return httpx.Response(200, json={"outcome": "allow", "reason": "ok"})

    with _gateway_app(handler) as client:
        text = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway")).text
    assert "Correlation ID" in text
    assert "not returned by the gateway" in text


def test_simulator_token_never_leaks_in_error_states():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "authentication_failed"})

    with _gateway_app(handler) as client:
        text = client.post("/simulate", data=dict(_VALID_FORM, mode="gateway")).text
    assert TOKEN not in text


@pytest.mark.parametrize("path", ["/", "/workspace", "/gateway", "/simulate"])
def test_live_pages_still_render(path):
    with _gateway_app(_healthy_handler) as client:
        assert client.get(path).status_code == 200
