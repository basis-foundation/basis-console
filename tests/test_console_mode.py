"""Tests for the operator/training presentation modes (BASIS_CONSOLE_MODE).

These verify the UX-only mode separation: operator is the default and stays
clean; training adds a banner and educational callouts. Neither mode changes
runtime behavior, both present the same application (same pages/navigation), and
both keep sample data honestly labelled.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state

ALL_PAGES = [
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

TRAINING_BANNER = "Training mode is enabled"
PAGE_TEACHES = "What this page teaches"


def _client(monkeypatch, mode: str | None) -> TestClient:
    if mode is None:
        monkeypatch.delenv("BASIS_CONSOLE_MODE", raising=False)
    else:
        monkeypatch.setenv("BASIS_CONSOLE_MODE", mode)
    reset_readiness_state()
    return TestClient(create_app(), raise_server_exceptions=True)


@pytest.fixture()
def operator_client(monkeypatch) -> Iterator[TestClient]:
    with _client(monkeypatch, None) as c:
        yield c


@pytest.fixture()
def training_client(monkeypatch) -> Iterator[TestClient]:
    with _client(monkeypatch, "training") as c:
        yield c


# ── Default / operator mode ─────────────────────────────────────────────────


@pytest.mark.parametrize("path", ALL_PAGES)
def test_all_pages_render_in_operator_mode(operator_client, path):
    assert operator_client.get(path).status_code == 200


def test_operator_mode_has_no_training_banner(operator_client):
    # The default (operator) mode must not show the training banner anywhere.
    for path in ALL_PAGES:
        assert TRAINING_BANNER not in operator_client.get(path).text


def test_operator_mode_hides_page_teaches_callouts(operator_client):
    for path in ALL_PAGES:
        assert PAGE_TEACHES not in operator_client.get(path).text


def test_operator_mode_shows_operator_badge(operator_client):
    body = operator_client.get("/").text
    assert "mode-operator" in body
    assert "operator mode" in body


# ── Training mode ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ALL_PAGES)
def test_all_pages_render_in_training_mode(training_client, path):
    assert training_client.get(path).status_code == 200


def test_training_mode_shows_banner_on_every_page(training_client):
    for path in ALL_PAGES:
        assert TRAINING_BANNER in training_client.get(path).text


def test_training_mode_shows_page_teaches_callout(training_client):
    # At least one training-only "What this page teaches" callout appears.
    assert PAGE_TEACHES in training_client.get("/audit").text


def test_training_mode_includes_architecture_explanation(training_client):
    body = training_client.get("/").text
    # The standard ecosystem responsibilities are explained in training mode.
    for component in ("basis-gateway", "basis-core", "basis-adapters", "basis-identity"):
        assert component in body


def test_training_mode_shows_training_badge(training_client):
    assert "mode-training" in training_client.get("/").text


# ── Same application in both modes (layout parity) ──────────────────────────


def _nav_links(html: str) -> list[str]:
    """Extract the navigation links (label + href) from the topbar."""
    nav_match = re.search(r'<nav class="nav">(.*?)</nav>', html, re.DOTALL)
    assert nav_match, "navigation block not found"
    return re.findall(r'href="([^"]+)"[^>]*>([^<]+)</a>', nav_match.group(1))


@pytest.mark.parametrize("path", ALL_PAGES)
def test_navigation_identical_across_modes(operator_client, training_client, path):
    # Training mode must not move, add, hide, or reorder navigation — both modes
    # present the same application, so the nav (links + order) is byte-identical.
    assert _nav_links(operator_client.get(path).text) == _nav_links(training_client.get(path).text)


def test_same_pages_available_in_both_modes(operator_client, training_client):
    # Training mode hides/adds no pages: every route resolves identically.
    for path in ALL_PAGES:
        assert operator_client.get(path).status_code == training_client.get(path).status_code == 200


def test_training_only_adds_content_not_controls(operator_client, training_client):
    # The simulator's action controls (submit buttons, verb/resource selects) are
    # identical across modes — training adds copy, never controls/workflows.
    op = operator_client.get("/simulate").text
    tr = training_client.get("/simulate").text
    for control in (
        'name="mode" value="preview"',
        'id="action_verb"',
        'id="resource_type"',
        'action="/simulate"',
    ):
        assert control in op
        assert control in tr


# ── Honesty + behavior parity across modes ──────────────────────────────────


def test_both_modes_label_sample_data(operator_client, training_client):
    # Sample data stays clearly labelled in BOTH modes — training never makes
    # sample data look live, and operator never drops the sample labels.
    for client in (operator_client, training_client):
        assert "sample" in client.get("/policies").text.lower()
        assert "sample" in client.get("/audit").text.lower()
        assert "sample" in client.get("/resources").text.lower()


def test_both_modes_keep_future_labels(operator_client, training_client):
    for client in (operator_client, training_client):
        assert "not live" in client.get("/identity").text


def test_gateway_diagnostics_behavior_unchanged_in_both_modes(operator_client, training_client):
    # The gateway page still reports the same (not-configured) state regardless
    # of presentation mode — mode is copy-only and changes no behavior.
    for client in (operator_client, training_client):
        assert client.get("/gateway").status_code == 200
        assert "not_configured" in client.get("/gateway").text


def test_simulator_still_builds_preview_in_training_mode(training_client):
    # Existing simulator behavior is intact under training mode.
    response = training_client.post(
        "/simulate",
        data={
            "subject_id": "operator-jane",
            "subject_type": "user",
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "context": "site=bldg-a",
            "mode": "preview",
        },
    )
    assert response.status_code == 200
    assert "Normalized request preview" in response.text
    # The gateway-owned composition is still previewed, unchanged by mode.
    assert "read:ahu" in response.text
    assert "ahu:rooftop-1" in response.text
