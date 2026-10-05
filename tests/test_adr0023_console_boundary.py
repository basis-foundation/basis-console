"""Regression tests for the ADR-0023 console boundary.

Accepted ADR-0023 (and ``basis-console.md`` Design Invariants 11-15) says the
console administers BASIS and is not an OT control path. Simulator evaluation
uses the gateway's direct, non-producer path, so its result cannot support
dispatch: ``ALLOW`` is not ``DISPATCHED``. The console has no path to producer
intake, the authorization-to-execution binding, or a protocol executor.

Every test here encodes an ADR-0023 architectural invariant, not the
console's current feature inventory. ADR-0023 lets the console grow as a BASIS
administrative interface, including new gateway-mediated administrative APIs
and administrative mutation routes. These tests must keep passing when such a
conforming capability is added. They fail only on the prohibited categories:
simulator traffic that leaves the direct evaluation path, a dependency on the
kernel, the producer runtime, or an OT protocol client, or execution state in
an authorization result. No test here restricts route names, method names, or
the words they use.

The tests check behavior where possible. They do not invent execution
endpoint names in order to show those endpoints go uncalled. The exclusion of
subject, context, and producer-only fields from operation-aware requests is
covered by ``test_gateway_evaluate_operation_aware.py`` and is not repeated.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from basis_console.gateway import GatewayClient
from basis_console.gateway.models import GatewayEvaluationResult, GatewayEvaluationStatus
from basis_console.gateway.operation_aware_models import (
    OperationAwareEvaluationResponse,
    OperationAwareEvaluationResult,
    OperationAwareEvaluationState,
    OperationAwareEvaluationStatus,
)
from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state
from basis_console.ui.views import SIMULATOR_NON_DISPATCH_NOTICE

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "basis_console"

GATEWAY_URL = "http://gateway.test:8000"
TOKEN = "super-secret-token-abc123"

# The gateway's direct, non-producer evaluation endpoints (ADR-0020
# Decision 6). The simulator submits only here. This set scopes simulator
# traffic; it does not limit which administrative gateway APIs the console
# may use elsewhere.
DIRECT_EVALUATION_ENDPOINTS = {"/v1/evaluate", "/v1/evaluate/operation-aware"}

# BASIS packages whose import would put kernel evaluation or the
# operation-producer runtime inside the console. These are the real package
# names. basis_adapters is deliberately absent: the architecture forbids the
# console from performing protocol behavior (covered by the protocol-client
# check below), not from referencing an adapter-owned type or shared contract.
FORBIDDEN_BASIS_PACKAGES = {"basis_core", "basis_producer"}

# Widely used OT protocol client libraries. Importing any of them would give
# the console direct device or protocol control.
FORBIDDEN_PROTOCOL_LIBRARIES = {
    "BAC0",
    "bacpypes",
    "bacpypes3",
    "pymodbus",
    "pyModbusTCP",
    "paho",
    "asyncua",
    "opcua",
    "pydnp3",
}

HTML_PAGES = [
    "/",
    "/workspace",
    "/policies",
    "/simulate",
    "/simulate/examples",
    "/audit",
    "/identity",
    "/resources",
    "/gateway",
]

LEGACY_FORM = {
    "evaluation_type": "legacy",
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "write",
    "resource_type": "setpoint",
    "resource_id": "zone-3",
    "context": "maintenance_window=true",
}

OA_FORM = {
    "evaluation_type": "operation_aware",
    "action_verb": "write",
    "resource_type": "setpoint",
    "resource_id": "zone-3",
}

LEGACY_ALLOW_BODY = {
    "request_id": "req-legacy",
    "outcome": "allow",
    "reason": "matched rule",
    "policy_version": "2026.06.0",
    "correlation_id": "corr-legacy",
}

OA_ALLOW_BODY = {
    "request_id": "req-oa",
    "correlation_id": "corr-oa",
    "evaluation_status": "completed",
    "outcome": "allow",
    "bundle_id": "site-a-bundle",
    "bundle_version": "1.0.0",
    "disposition": "allow",
}

ESCAPED_NOTICE = str(escape(SIMULATOR_NON_DISPATCH_NOTICE))

_EXECUTION_VOCABULARY = re.compile(r"dispatch|execut|actuat|command", re.IGNORECASE)


class RecordingGateway:
    """Mock gateway that records every request and answers with ALLOW."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if request.url.path == "/v1/evaluate":
            return httpx.Response(200, json=LEGACY_ALLOW_BODY)
        if request.url.path == "/v1/evaluate/operation-aware":
            return httpx.Response(200, json=OA_ALLOW_BODY)
        return httpx.Response(200, json={"status": "ok"})

    def bodies_for(self, path: str) -> list[dict[str, object] | None]:
        return [body for _, p, body in self.calls if p == path]


@contextmanager
def _client(
    monkeypatch: pytest.MonkeyPatch, mode: str, gateway: RecordingGateway
) -> Iterator[TestClient]:
    monkeypatch.setenv("BASIS_CONSOLE_MODE", mode)
    reset_readiness_state()
    app = create_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        client.app.state.gateway_client = GatewayClient(
            base_url=GATEWAY_URL, bearer_token=TOKEN, transport=httpx.MockTransport(gateway)
        )
        yield client


# ---------------------------------------------------------------------------
# ADR-0023 invariant: no path into the governed OT chain
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["operator", "training"])
def test_simulator_submissions_stay_on_direct_evaluation_path(monkeypatch, mode):
    """Simulator traffic goes only to direct-path evaluation endpoints.

    Scoped to the simulator: other console pages may use other conforming
    administrative gateway APIs. Each contract must hit its own endpoint, so
    the check cannot pass vacuously.
    """
    for form, endpoint in (
        (LEGACY_FORM, "/v1/evaluate"),
        (OA_FORM, "/v1/evaluate/operation-aware"),
    ):
        gateway = RecordingGateway()
        with _client(monkeypatch, mode, gateway) as client:
            response = client.post("/simulate", data=dict(form, mode="gateway"))
            assert response.status_code == 200
        posted = {path for method, path, _ in gateway.calls if method == "POST"}
        assert posted == {endpoint}
        assert posted <= DIRECT_EVALUATION_ENDPOINTS


def test_preview_submissions_make_no_gateway_evaluation_call(monkeypatch):
    gateway = RecordingGateway()
    with _client(monkeypatch, "operator", gateway) as client:
        for form in (LEGACY_FORM, OA_FORM):
            client.post("/simulate", data=dict(form, mode="preview"))
    assert not [call for call in gateway.calls if call[0] == "POST"]


def _imported_top_level_packages() -> set[str]:
    names: set[str] = set()
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def test_console_imports_no_kernel_producer_or_protocol_client_code():
    imported = _imported_top_level_packages()
    assert "httpx" in imported, "import scan found nothing; it would pass vacuously"
    assert not imported & FORBIDDEN_BASIS_PACKAGES
    assert not imported & FORBIDDEN_PROTOCOL_LIBRARIES


# ---------------------------------------------------------------------------
# ALLOW is an authorization result, never an execution state
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "enum_type",
    [GatewayEvaluationStatus, OperationAwareEvaluationStatus, OperationAwareEvaluationState],
)
def test_result_status_enums_have_no_dispatch_or_execution_state(enum_type):
    for member in enum_type:
        assert not _EXECUTION_VOCABULARY.search(member.value), member
        assert not _EXECUTION_VOCABULARY.search(member.name), member


@pytest.mark.parametrize(
    "result_type",
    [GatewayEvaluationResult, OperationAwareEvaluationResult, OperationAwareEvaluationResponse],
)
def test_result_models_carry_no_dispatch_or_execution_field(result_type):
    for field in dataclasses.fields(result_type):
        assert not _EXECUTION_VOCABULARY.search(field.name), field.name


def test_allow_from_gateway_is_relayed_as_an_authorization_outcome():
    """A 200 ALLOW maps to an evaluation status, not to anything executed."""
    gateway = RecordingGateway()
    client = GatewayClient(
        base_url=GATEWAY_URL, bearer_token=TOKEN, transport=httpx.MockTransport(gateway)
    )
    result = client.evaluate(action="write", resource_type="setpoint", resource_id="zone-3")
    assert result.status is GatewayEvaluationStatus.SUCCESS
    assert result.outcome == "allow"


# ---------------------------------------------------------------------------
# Rendering: the non-dispatch notice, in both modes and both contracts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["operator", "training"])
@pytest.mark.parametrize("form", [LEGACY_FORM, OA_FORM], ids=["legacy", "operation_aware"])
def test_allow_result_renders_with_non_dispatch_notice(monkeypatch, mode, form):
    gateway = RecordingGateway()
    with _client(monkeypatch, mode, gateway) as client:
        response = client.post("/simulate", data=dict(form, mode="gateway"))
    assert response.status_code == 200
    assert 'class="outcome allow"' in response.text
    assert ESCAPED_NOTICE in response.text


@pytest.mark.parametrize("form", [LEGACY_FORM, OA_FORM], ids=["legacy", "operation_aware"])
def test_non_dispatch_notice_shown_before_any_evaluation(monkeypatch, form):
    gateway = RecordingGateway()
    with _client(monkeypatch, "operator", gateway) as client:
        response = client.post("/simulate", data=dict(form, mode="preview"))
    assert ESCAPED_NOTICE in response.text


@pytest.mark.parametrize("mode", ["operator", "training"])
def test_every_page_states_console_does_not_operate_ot_equipment(monkeypatch, mode):
    gateway = RecordingGateway()
    with _client(monkeypatch, mode, gateway) as client:
        for path in HTML_PAGES:
            assert "does not operate OT equipment" in client.get(path).text, path


# ---------------------------------------------------------------------------
# Presentation modes do not change request semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("form", "endpoint"),
    [(LEGACY_FORM, "/v1/evaluate"), (OA_FORM, "/v1/evaluate/operation-aware")],
    ids=["legacy", "operation_aware"],
)
def test_operator_and_training_submit_identical_evaluation_requests(monkeypatch, form, endpoint):
    bodies = {}
    for mode in ("operator", "training"):
        gateway = RecordingGateway()
        with _client(monkeypatch, mode, gateway) as client:
            client.post("/simulate", data=dict(form, mode="gateway"))
        bodies[mode] = gateway.bodies_for(endpoint)
        assert len(bodies[mode]) == 1
    assert bodies["operator"] == bodies["training"]
