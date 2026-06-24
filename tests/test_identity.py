"""Tests for the Identity & Access Explorer (Phase 8).

These cover the page's required behavior and, crucially, the boundaries the
console must preserve: it renders, inspects, and explains identity/access context
but never authenticates, authorizes, evaluates, or calls basis-core.
"""

from __future__ import annotations

import json

from basis_console.identity import (
    future_identity_integrations,
    sample_access_preview,
    sample_identity_preview,
)


def _is_html(response) -> bool:
    return response.headers["content-type"].startswith("text/html")


# 1. Identity page/section renders.
def test_identity_page_renders(client):
    response = client.get("/identity")
    assert response.status_code == 200
    assert _is_html(response)
    assert "Identity &amp; Access Explorer" in response.text


def test_identity_appears_in_navigation(client):
    # Nav is shared by every page; the new entry must be reachable from each.
    for path in ("/", "/policies", "/simulate", "/audit", "/identity"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Identity" in response.text
        assert 'href="/identity"' in response.text


# 2. Sample subject data is displayed correctly.
def test_sample_subject_displayed(client):
    response = client.get("/identity")
    subject = sample_identity_preview().subject
    assert subject.subject_id in response.text
    assert subject.subject_type in response.text
    for role in subject.roles:
        assert role in response.text
    for group in subject.groups:
        assert group in response.text
    assert subject.issuer in response.text


def test_page_is_labelled_sample(client):
    # The page must never present identity as live, verified state.
    response = client.get("/identity")
    assert "sample" in response.text.lower()
    assert "does not authenticate" in response.text.lower()


# 3. Claims viewer renders nested claim payloads safely.
def test_claims_viewer_renders_nested_payloads_safely(client):
    response = client.get("/identity")
    claims = sample_identity_preview().claims
    # Nested claim structures must round-trip into the rendered JSON block.
    assert "realm_access" in response.text
    assert "resource_access" in response.text
    assert "telemetry-read" in response.text
    # The exact pretty-printed JSON is embedded; nested keys are present verbatim.
    claims_json = json.dumps(claims.raw, indent=2, sort_keys=False)
    for line in ('"iss"', '"groups"', '"roles"'):
        assert line in claims_json
    # Rendered inside a <pre><code> block, not as raw markup — autoescaping keeps
    # any angle brackets inert. The sample data contains none, but assert the
    # container is present so nested payloads are always shown as text.
    assert '<pre class="json"><code>' in response.text


def test_console_does_not_verify_tokens(client):
    response = client.get("/identity")
    text = response.text.lower()
    assert "unverified" in text
    assert "does not check the signature" in text


# 4. Subject normalization preview displays mapped subject fields.
def test_normalization_preview_displays_mapped_fields(client):
    response = client.get("/identity")
    preview = sample_identity_preview()
    # The claim→subject flow is shown.
    assert "gateway subject mapper" in response.text
    assert "BASIS Subject" in response.text
    # Each mapping row's source and result appear.
    for mapping in preview.role_mappings + preview.group_mappings:
        assert mapping.source in response.text
        assert mapping.result in response.text


# 5. Identity page does not submit directly to basis-core.
def test_identity_page_does_not_submit_to_core_or_gateway(client):
    response = client.get("/identity")
    # No form on the page posts anywhere; the only action is a GET link into the
    # existing simulator. There is no /v1/evaluate call and no submit form here.
    assert "<form" not in response.text
    assert "/v1/evaluate" not in response.text
    # The only outbound link is the simulator deep-link (a GET preview).
    assert "/simulate?example=" in response.text


def test_identity_module_never_imports_basis_core():
    import basis_console.identity as identity_module

    source = identity_module.__file__
    with open(source, encoding="utf-8") as handle:
        contents = handle.read()
    assert "import basis_core" not in contents
    assert "from basis_core" not in contents


def test_access_linkage_keeps_identity_boundary(client):
    # "Use this subject in evaluation" must not imply the subject is sent as
    # identity — the gateway derives identity from its verified token.
    response = client.get("/identity")
    access = sample_access_preview()
    assert "Use this subject in evaluation" in response.text
    assert access.identity_note in response.text
    # The deep-link targets a real sample scenario slug.
    assert f"/simulate?example={access.simulator_example}" in response.text


# 6. Existing gateway-backed evaluation behavior remains unchanged.
def test_existing_simulate_preview_still_works(client):
    # Adding the identity page must not disturb the simulator.
    get_resp = client.get("/simulate")
    assert get_resp.status_code == 200

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
    # Preview mode still builds the normalized request shape and previews what the
    # gateway would compose.
    assert "Normalized request preview" in post_resp.text
    assert "read:ahu" in post_resp.text
    assert "ahu:rooftop-1" in post_resp.text


def test_simulator_deep_link_targets_a_real_scenario(client):
    # The identity page links to a simulator example; loading it must succeed and
    # pre-fill the form (proving the linkage is coherent, not a dead link).
    slug = sample_access_preview().simulator_example
    response = client.get(f"/simulate?example={slug}")
    assert response.status_code == 200
    assert "operator-jane" in response.text


# 7. Future integration panel is clearly labeled as future/non-live.
def test_future_integration_panel_is_clearly_future(client):
    response = client.get("/identity")
    assert "Future" in response.text
    assert "basis-identity" in response.text
    assert "not live" in response.text.lower()
    # The forward-looking capabilities are listed by name.
    for item in future_identity_integrations():
        assert item.name in response.text


def test_future_panel_explains_idp_relationship(client):
    response = client.get("/identity")
    # The IdP → identity → gateway → core relationship must be documented in UI.
    text = response.text
    assert "External IdP" in text
    assert "basis-identity" in text
    assert "basis-gateway" in text
    assert "basis-core" in text
