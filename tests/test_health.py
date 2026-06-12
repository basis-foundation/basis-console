"""Tests for the operational JSON endpoints (/health and /ready)."""

from __future__ import annotations


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_status_ok(client):
    response = client.get("/health")
    assert response.json()["status"] == "ok"


def test_health_service_name(client):
    response = client.get("/health")
    assert response.json()["service"] == "basis-console"


def test_ready_returns_200_after_startup(client):
    # The TestClient context manager runs the lifespan, which loads config and
    # marks configuration_loaded ready.
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["components"]["configuration_loaded"] is True
