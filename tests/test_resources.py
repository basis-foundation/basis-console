"""Tests for the Resource Explorer (Phase 11).

These cover the page's required behavior and, crucially, the boundaries the
console must preserve: it displays resource concepts and authorization targets
and explains gateway request shapes, but never discovers devices, owns resource
inventory, mutates resources, or calls basis-core.
"""

from __future__ import annotations

import html

from basis_console.resources import (
    future_resource_integrations,
    sample_resources,
)

# The adapter families that must all be represented in the catalog.
_REQUIRED_PROTOCOL_FAMILIES = (
    "BACnet",
    "Modbus",
    "OPC UA",
    "MQTT",
    "DNP3",
    "IEC 61850",
    "KNX",
    "Niagara",
    "REST",
)


def _is_html(response) -> bool:
    return response.headers["content-type"].startswith("text/html")


# 1. Resource Explorer page renders.
def test_resources_page_renders(client):
    response = client.get("/resources")
    assert response.status_code == 200
    assert _is_html(response)
    assert "Resource Explorer" in response.text


def test_resources_appears_in_navigation(client):
    # Nav is shared by every page; the new entry must be reachable from each.
    for path in ("/", "/policies", "/simulate", "/audit", "/identity", "/resources", "/gateway"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Resources" in response.text
        assert 'href="/resources"' in response.text


# 2. Sample resource catalog renders.
def test_sample_resource_catalog_renders(client):
    response = client.get("/resources")
    for resource in sample_resources():
        assert resource.display_name in response.text


def test_page_is_labelled_sample(client):
    # The page must never present resources as a live inventory.
    response = client.get("/resources")
    text = response.text.lower()
    assert "sample" in text
    assert "does not discover devices" in text


# 3. All required protocol/source examples render.
def test_all_protocol_families_render(client):
    response = client.get("/resources")
    for family in _REQUIRED_PROTOCOL_FAMILIES:
        assert family in response.text, f"missing protocol family: {family}"


def test_all_protocol_families_present_in_sample_data():
    families = {r.protocol_family for r in sample_resources()}
    for family in _REQUIRED_PROTOCOL_FAMILIES:
        assert family in families, f"sample data missing family: {family}"


def test_adapter_sources_render(client):
    response = client.get("/resources")
    for resource in sample_resources():
        assert resource.adapter_source.name in response.text


# 4. Identifier explanation renders.
def test_identifier_explanation_renders(client):
    response = client.get("/resources")
    text = response.text
    assert "local resource_id" in text
    assert "canonical resource_id" in text
    assert "resource_type" in text
    # The gateway composition flow is shown.
    assert "resource_type + local_resource_id" in text
    assert "canonical_resource_id" in text
    # The direct, already-typed request shape is shown.
    assert '"action": "read:ahu"' in text
    assert '"resource_id": "ahu:rooftop-1"' in text


# 5. Gateway request preview renders.
def test_gateway_request_preview_renders(client):
    response = client.get("/resources")
    assert "Gateway request preview" in response.text
    # Variable-rendered JSON is HTML-escaped by Jinja; unescape before matching.
    text = html.unescape(response.text)
    # The preferred normalized shape (bare verb + resource_type + local id).
    assert '"resource_type": "ahu"' in text
    assert '"resource_id": "rooftop-1"' in text
    assert '"action": "read"' in text


# 6. Canonical resource IDs render.
def test_canonical_resource_ids_render(client):
    response = client.get("/resources")
    for resource in sample_resources():
        assert resource.canonical_resource_id in response.text
        # Canonical id mirrors {resource_type}:{local_resource_id}.
        expected = f"{resource.resource_type}:{resource.local_resource_id}"
        assert resource.canonical_resource_id == expected


# 7. Supported actions render.
def test_supported_actions_render(client):
    response = client.get("/resources")
    for resource in sample_resources():
        for action in resource.supported_actions:
            assert action.verb in response.text
            # The composed {verb}:{type} action is previewed too.
            assert action.canonical_action in response.text
            assert action.canonical_action == f"{action.verb}:{resource.resource_type}"


# 8. Simulator link or guidance renders.
def test_simulator_link_or_guidance_renders(client):
    response = client.get("/resources")
    text = response.text
    assert "Use in evaluation" in text
    # At least one resource deep-links into a real simulator example.
    assert "/simulate?example=" in text
    # And the simulator deep-link targets a coherent, loadable scenario.
    slugs = {r.simulator_example for r in sample_resources() if r.simulator_example}
    assert slugs
    for slug in slugs:
        example_resp = client.get(f"/simulate?example={slug}")
        assert example_resp.status_code == 200


def test_resources_page_does_not_bypass_gateway_or_call_core(client):
    response = client.get("/resources")
    # No form on the page submits anywhere; the only actions are GET links into
    # the existing simulator. There is no direct /v1/evaluate call here.
    assert "<form" not in response.text
    assert "/v1/evaluate" not in response.text


# 9. Raw resource JSON renders safely.
def test_raw_resource_json_renders_safely(client):
    response = client.get("/resources")
    # Raw payloads are rendered inside <pre><code> blocks so any markup is inert
    # (Jinja autoescaping keeps angle brackets as text).
    assert '<pre class="json"><code>' in response.text
    assert "Raw resource" in response.text
    # Source attributes from the sample data round-trip into the rendered payload.
    assert "source_attributes" in response.text


# 10. Sensitive fields are redacted.
def test_sensitive_fields_are_redacted(client):
    response = client.get("/resources")
    text = response.text
    # The sample data deliberately includes credential-shaped attributes; their
    # values must never reach the page.
    assert "SAMPLE-bacnet-bbmd-secret-do-not-use" not in text
    assert "SAMPLE-rest-api-key-do-not-use" not in text
    assert "[redacted]" in text


def test_sensitive_values_absent_from_sample_raw_json():
    # Redaction happens in the model layer too (raw_json is pre-redacted).
    for resource in sample_resources():
        assert "do-not-use" not in resource.raw_json


# 11. Future integration panel is clearly labeled as future/non-live.
def test_future_integration_panel_is_clearly_future(client):
    response = client.get("/resources")
    text = response.text
    assert "Future live resource integrations" in text
    assert "not live" in text.lower()
    for item in future_resource_integrations():
        assert item.name in text


def test_future_panel_lists_expected_sources(client):
    response = client.get("/resources")
    text = response.text
    for fragment in (
        "basis-adapters",
        "basis-gateway",
        "basis-schemas",
        "basis-identity",
        "basis-deploy",
        "CMDB",
    ):
        assert fragment in text


# Boundary: the resources module must never reach the kernel directly.
def test_resources_module_never_imports_basis_core():
    import basis_console.resources as resources_module

    with open(resources_module.__file__, encoding="utf-8") as handle:
        contents = handle.read()
    assert "import basis_core" not in contents
    assert "from basis_core" not in contents


# 12. Existing pages continue to work.
def test_existing_pages_still_work(client):
    for path in ("/", "/policies", "/simulate", "/audit", "/identity", "/gateway"):
        response = client.get(path)
        assert response.status_code == 200


def test_existing_simulate_preview_still_works(client):
    post_resp = client.post(
        "/simulate",
        data={
            "subject_id": "operator-jane",
            "subject_type": "user",
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "context": "",
            "mode": "preview",
        },
    )
    assert post_resp.status_code == 200
    assert "Normalized request preview" in post_resp.text
    assert "read:ahu" in post_resp.text
    assert "ahu:rooftop-1" in post_resp.text
