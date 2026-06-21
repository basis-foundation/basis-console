"""Route tests for the Phase 3 decision simulator."""

from __future__ import annotations

from basis_console.gateway.client import GatewayClient

_VALID_FORM = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action": "read",
    "resource_id": "hvac:zone-a",
    "resource_type": "sensor",
    "context": "site=bldg-a",
}


def test_simulate_get_renders_form(client):
    response = client.get("/simulate")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # The decision-request fields are present.
    for field in ("subject", "resource", "action"):
        assert field in response.text.lower()
    # The no-evaluation boundary is stated.
    assert "does not evaluate decisions" in response.text
    # All allowed actions are offered.
    for action in ("read", "write", "execute", "browse", "subscribe"):
        assert action in response.text


def test_valid_post_renders_normalized_preview(client):
    response = client.post("/simulate", data=_VALID_FORM)
    assert response.status_code == 200
    assert "Normalized request preview" in response.text
    # Submitted values appear inside the JSON preview.
    assert "operator-jane" in response.text
    assert "hvac:zone-a" in response.text
    assert "site" in response.text


def test_missing_required_fields_show_errors(client):
    response = client.post("/simulate", data={"action": "read"})
    assert response.status_code == 200
    assert "Please correct the following" in response.text
    assert "required" in response.text.lower()
    # No preview is rendered for invalid input.
    assert "Normalized request preview" not in response.text


def test_invalid_action_shows_error(client):
    bad = dict(_VALID_FORM, action="delete")
    response = client.post("/simulate", data=bad)
    assert response.status_code == 200
    assert "must be one of" in response.text
    assert "Normalized request preview" not in response.text


def test_unsafe_identifier_shows_error(client):
    bad = dict(_VALID_FORM, resource_id="bad value; rm -rf")
    response = client.post("/simulate", data=bad)
    assert response.status_code == 200
    assert "simple safe string" in response.text
    assert "Normalized request preview" not in response.text


def test_examples_page_renders(client):
    response = client.get("/simulate/examples")
    assert response.status_code == 200
    assert "Sample Scenarios" in response.text
    assert "Building operator reads AHU temperature" in response.text
    assert "Technician writes HVAC setpoint" in response.text
    assert "Vendor attempts access to a restricted device" in response.text


def test_example_loads_into_form(client):
    response = client.get("/simulate?example=technician-write-setpoint")
    assert response.status_code == 200
    assert "Loaded sample scenario" in response.text
    # The scenario's values populate the form inputs.
    assert "tech-mike" in response.text
    assert "hvac:zone-3:setpoint" in response.text


def test_unknown_example_renders_empty_form(client):
    response = client.get("/simulate?example=does-not-exist")
    assert response.status_code == 200
    assert "Loaded sample scenario" not in response.text


def test_simulation_makes_no_gateway_call(client, monkeypatch):
    """Building a preview must never contact basis-gateway."""

    def boom(self, *args, **kwargs):
        raise AssertionError("gateway must not be contacted during simulation")

    monkeypatch.setattr(GatewayClient, "check_status", boom)

    response = client.post("/simulate", data=_VALID_FORM)
    assert response.status_code == 200
    assert "Normalized request preview" in response.text

    # The GET form must not contact the gateway either.
    assert client.get("/simulate").status_code == 200
    assert client.get("/simulate/examples").status_code == 200
