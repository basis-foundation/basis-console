"""Route tests for the decision simulator (normalized request builder)."""

from __future__ import annotations

from basis_console.gateway.client import GatewayClient

# Normalized form: bare verb + resource_type (domain) + LOCAL resource id.
_VALID_FORM = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
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
    # All allowed verbs are offered.
    for verb in ("read", "write", "execute", "browse", "subscribe"):
        assert verb in response.text
    # Starter resource types / domains are offered too.
    for rtype in ("ahu", "setpoint", "telemetry", "device"):
        assert rtype in response.text


def test_valid_post_renders_normalized_preview(client):
    response = client.post("/simulate", data=_VALID_FORM)
    assert response.status_code == 200
    assert "Normalized request preview" in response.text
    # Submitted values appear on the page.
    assert "operator-jane" in response.text
    assert "rooftop-1" in response.text
    assert "site" in response.text
    # The page shows what the gateway will compose, never a console-composed body.
    assert "read:ahu" in response.text
    assert "ahu:rooftop-1" in response.text


def test_missing_required_fields_show_errors(client):
    response = client.post("/simulate", data={"action_verb": "read"})
    assert response.status_code == 200
    assert "Please correct the following" in response.text
    assert "required" in response.text.lower()
    assert "Normalized request preview" not in response.text


def test_invalid_verb_shows_error(client):
    bad = dict(_VALID_FORM, action_verb="delete")
    response = client.post("/simulate", data=bad)
    assert response.status_code == 200
    assert "verb must be one of" in response.text
    assert "Normalized request preview" not in response.text


def test_invalid_resource_type_shows_error(client):
    bad = dict(_VALID_FORM, resource_type="nonsense")
    response = client.post("/simulate", data=bad)
    assert response.status_code == 200
    assert "Resource type must be one of" in response.text
    assert "Normalized request preview" not in response.text


def test_typed_resource_id_with_type_shows_error(client):
    """A typed resource id alongside a resource type is rejected (dual source)."""
    bad = dict(_VALID_FORM, resource_id="ahu:rooftop-1")
    response = client.post("/simulate", data=bad)
    assert response.status_code == 200
    assert "must be local" in response.text
    assert "Normalized request preview" not in response.text


def test_domain_level_request_is_accepted(client):
    """Omitting the local resource id is a valid domain-level request."""
    ok = dict(_VALID_FORM, resource_id="")
    response = client.post("/simulate", data=ok)
    assert response.status_code == 200
    assert "Normalized request preview" in response.text
    assert "domain-level request" in response.text


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
    # The scenario's normalized values populate the form inputs.
    assert "tech-mike" in response.text
    assert "zone-3" in response.text


def test_sample_scenarios_carry_local_resource_ids(client):
    """No sample scenario pairs a descriptive resource type with a typed id."""
    from basis_console.sample_data import sample_simulator_scenarios

    for scenario in sample_simulator_scenarios():
        # The submitted resource id is local (untyped) so it never drifts from
        # the resource type prefix the gateway composes.
        assert ":" not in scenario["resource_id"], scenario["slug"]
        assert scenario["resource_type"], scenario["slug"]


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
