"""Tests that the read-only HTML pages render."""

from __future__ import annotations

import pytest


def _is_html(response) -> bool:
    return response.headers["content-type"].startswith("text/html")


def test_homepage_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert _is_html(response)
    assert "BASIS Console" in response.text
    assert "running" in response.text


def test_policies_page_renders(client):
    response = client.get("/policies")
    assert response.status_code == 200
    assert _is_html(response)
    assert "Policy visibility will appear here" in response.text
    # Sample policy data is surfaced read-only.
    assert "ot-operator-rbac" in response.text


def test_simulate_page_renders(client):
    response = client.get("/simulate")
    assert response.status_code == 200
    assert _is_html(response)
    # The three decision-request fields establish the UI pattern.
    for field in ("subject", "resource", "action"):
        assert field in response.text.lower()


def test_audit_page_renders(client):
    response = client.get("/audit")
    assert response.status_code == 200
    assert _is_html(response)
    assert "Audit events will appear here" in response.text
    assert "evidence, not enforcement" in response.text


def test_static_css_served_locally(client):
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


@pytest.mark.parametrize("path", ["/", "/policies", "/simulate", "/audit"])
def test_pages_share_navigation(client, path):
    response = client.get(path)
    assert response.status_code == 200
    for label in ("Policies", "Simulate", "Audit"):
        assert label in response.text
