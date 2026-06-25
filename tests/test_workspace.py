"""Tests for the Operator Workspace / Overview (Phase 12).

The workspace is an orientation layer: it organizes the existing console areas
into a single landing page and adds no backend authority. These tests verify the
page renders, links to every existing area, organizes content around operational
questions, distinguishes data maturity tiers, and introduces no basis-core
dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import basis_console


def _is_html(response) -> bool:
    return response.headers["content-type"].startswith("text/html")


def test_workspace_page_renders(client):
    response = client.get("/workspace")
    assert response.status_code == 200
    assert _is_html(response)
    assert "Operator Workspace" in response.text


def test_navigation_includes_workspace(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Workspace" in response.text
    assert "/workspace" in response.text


def test_homepage_links_to_workspace_prominently(client):
    response = client.get("/")
    assert 'href="/workspace"' in response.text


def test_operational_flow_summary_renders(client):
    response = client.get("/workspace")
    text = response.text
    assert "Operational flow" in text
    # The BASIS operational model, in order.
    for stage in ("Identity", "Resource", "Gateway", "Decision", "Audit"):
        assert stage in text


def test_capability_cards_render_and_link(client):
    response = client.get("/workspace")
    text = response.text
    for title in (
        "Identity &amp; Access",
        "Resources",
        "Decision Simulator",
        "Gateway Diagnostics",
        "Audit Explorer",
    ):
        assert title in text
    # Each capability card links to its existing page.
    for path in ("/identity", "/resources", "/simulate", "/gateway", "/audit"):
        assert f'href="{path}"' in text


def test_operational_questions_render(client):
    response = client.get("/workspace")
    text = response.text
    assert "Operational questions" in text
    for question in (
        "Who is the subject?",
        "What resource is targeted?",
        "Can this action be performed?",
        "Is the enforcement boundary healthy?",
        "What evidence was recorded?",
    ):
        assert question in text


def test_data_maturity_panel_distinguishes_tiers(client):
    response = client.get("/workspace")
    text = response.text
    assert "Live / configurable" in text
    assert "Sample / explanatory" in text
    assert "Future" in text
    # Representative items for each tier.
    assert "Gateway health / readiness" in text
    assert "Identity previews" in text
    assert "basis-identity integration" in text


def test_recommended_operator_path_renders(client):
    response = client.get("/workspace")
    text = response.text
    assert "Recommended operator path" in text
    for step in (
        "Check Gateway",
        "Inspect Identity",
        "Inspect Resources",
        "Run Evaluation",
        "Review Audit Evidence",
    ):
        assert step in text


def test_gateway_readiness_snapshot_renders(client):
    response = client.get("/workspace")
    text = response.text
    assert "System readiness snapshot" in text
    # Reuses the diagnostics connection state; not configured in the test env.
    assert "not_configured" in text
    # Links to the full diagnostics view rather than duplicating it.
    assert "Gateway Diagnostics" in text


def test_workspace_states_no_backend_authority(client):
    response = client.get("/workspace")
    # Collapse whitespace: the boundary copy wraps across template lines.
    text = " ".join(response.text.split())
    assert "does not add backend authority" in text
    assert "does not make sample data live" in text


@pytest.mark.parametrize("path", ["/identity", "/resources", "/simulate", "/gateway", "/audit"])
def test_existing_pages_still_work(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert _is_html(response)


def test_existing_pages_share_workspace_navigation(client):
    for path in ("/", "/identity", "/resources", "/simulate", "/gateway", "/audit"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Workspace" in response.text


def test_workspace_module_does_not_import_basis_core():
    """The workspace presentation module must not depend on basis-core."""
    source = Path(basis_console.__file__).parent / "workspace.py"
    text = source.read_text(encoding="utf-8")
    assert "import basis_core" not in text
    assert "from basis_core" not in text
