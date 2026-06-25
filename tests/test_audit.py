"""Tests for the Audit Explorer (Phase 10).

These cover the page's required behavior and the boundaries the console must
preserve: it renders and explains audit *evidence* but never produces, stores, or
owns canonical audit records, and never calls basis-core.
"""

from __future__ import annotations

from basis_console.audit import (
    future_audit_integrations,
    sample_audit_events,
)


def _is_html(response) -> bool:
    return response.headers["content-type"].startswith("text/html")


# 1. Audit Explorer page renders.
def test_audit_page_renders(client):
    response = client.get("/audit")
    assert response.status_code == 200
    assert _is_html(response)
    assert "Audit Explorer" in response.text


def test_audit_overview_states_console_does_not_own_records(client):
    response = client.get("/audit")
    text = response.text.lower()
    assert "does not produce canonical audit records" in text
    assert "does not" in text and "store" in text


# 2. Recent authorization events render.
def test_recent_events_render(client):
    response = client.get("/audit")
    events = sample_audit_events()
    assert events  # sanity
    for event in events:
        assert event.subject_id in response.text
        assert event.action in response.text
        assert event.resource_id in response.text


# 3. ALLOW and DENY outcomes render distinctly.
def test_allow_and_deny_render_distinctly(client):
    response = client.get("/audit")
    # The sample set has both outcomes; both outcome classes must appear.
    assert "read:ahu" in response.text  # the ALLOW event
    assert "write:setpoint" in response.text  # a DENY event
    assert 'class="outcome allow"' in response.text
    assert 'class="outcome deny"' in response.text


# 4. Event detail sections render.
def test_event_detail_sections_render(client):
    response = client.get("/audit")
    for heading in ("Decision", "Subject", "Action", "Resource", "Policy", "Correlation"):
        assert heading in response.text
    assert "Gateway evidence" in response.text
    assert "Raw event" in response.text


# 5. Gateway evidence fields render.
def test_gateway_evidence_fields_render(client):
    response = client.get("/audit")
    for key in (
        "basis_gateway.action_composed",
        "basis_gateway.original_action",
        "basis_gateway.composed_action",
        "basis_gateway.resource_composed",
        "basis_gateway.original_resource_id",
        "basis_gateway.composed_resource_id",
        "basis_gateway.resource_type",
    ):
        assert key in response.text


def test_direct_request_shows_no_evidence_state(client):
    # A direct (already-typed) request records no composition evidence; the page
    # must say so rather than fabricate evidence.
    response = client.get("/audit")
    assert "No gateway composition evidence" in response.text


# 6. Correlation IDs render.
def test_correlation_ids_render(client):
    response = client.get("/audit")
    for event in sample_audit_events():
        assert event.correlation_id in response.text
    assert "correlation id" in response.text.lower()


# 7. Raw event JSON renders safely.
def test_raw_event_json_renders_safely(client):
    response = client.get("/audit")
    assert "Raw event" in response.text
    assert '<pre class="json"><code>' in response.text
    # The event_id appears inside the rendered raw payload block.
    assert "evt-sample-0001" in response.text


# 8. Sensitive fields are redacted.
def test_sensitive_fields_redacted(client):
    response = client.get("/audit")
    # The sample raw payload defensively includes a credential-shaped field.
    assert "Bearer SAMPLE.do-not-use.value" not in response.text
    assert "SAMPLE.do-not-use.value" not in response.text
    assert "[redacted]" in response.text


def test_sample_event_raw_json_is_redacted_at_source():
    # Redaction happens when the event is built, not only in the template.
    event = sample_audit_events()[0]
    assert "do-not-use" not in event.raw_json
    assert "[redacted]" in event.raw_json


# 9. Future integration panel is clearly labeled as future/non-live.
def test_future_integration_panel_clearly_future(client):
    response = client.get("/audit")
    assert "Future live audit integrations" in response.text
    assert "not live" in response.text.lower()
    for item in future_audit_integrations():
        assert item.name in response.text
    # Names that imply the future, not current, ownership.
    assert "basis-gateway audit history endpoint" in response.text
    assert "SIEM" in response.text


def test_audit_data_labelled_sample(client):
    response = client.get("/audit")
    assert "sample" in response.text.lower()


def test_audit_links_to_simulator_for_live_evidence(client):
    response = client.get("/audit")
    assert 'href="/simulate"' in response.text


# 10. Existing simulator, identity, and gateway diagnostics pages still work.
def test_existing_pages_still_work(client):
    sim = client.get("/simulate")
    assert sim.status_code == 200
    assert "does not evaluate decisions" in sim.text

    ident = client.get("/identity")
    assert ident.status_code == 200
    assert "Identity &amp; Access Explorer" in ident.text

    gw = client.get("/gateway")
    assert gw.status_code == 200
    assert "Gateway Diagnostics" in gw.text


def test_audit_in_navigation(client):
    for path in ("/", "/simulate", "/identity", "/gateway", "/audit"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert 'href="/audit"' in resp.text
