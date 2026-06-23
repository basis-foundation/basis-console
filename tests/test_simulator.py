"""Unit tests for the decision-simulator logic (no HTTP, no gateway).

Covers both the form-driven normalized request builder (``build_simulation``)
and the lower-level gateway request-shape builder (``build_gateway_request``)
that encodes the console's half of the gateway composition contract.
"""

from __future__ import annotations

from basis_console.simulator import build_gateway_request, build_simulation
from basis_console.vocabulary import (
    ACTION_VERBS,
    RESOURCE_TYPES,
    compose_action,
    compose_resource_id,
    matches_action_format,
)

# A valid normalized form: bare verb + resource_type (domain) + LOCAL resource id.
_VALID = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "read",
    "resource_type": "ahu",
    "resource_id": "rooftop-1",
    "context": "site=bldg-a\nmaintenance_window=true",
}


# ---------------------------------------------------------------------------
# build_simulation — normalized form path
# ---------------------------------------------------------------------------


def test_valid_input_builds_normalized_preview():
    result = build_simulation(_VALID)
    assert result.ok
    assert result.errors == []
    # Preview shows the bare verb + resource_type + LOCAL id (gateway composes).
    assert result.preview == {
        "subject_id": "operator-jane",
        "subject_type": "user",
        "action": "read",
        "resource_type": "ahu",
        "resource_id": "rooftop-1",
        "context": {"site": "bldg-a", "maintenance_window": "true"},
    }


def test_gateway_body_is_normalized_and_subjectless():
    """The body submitted to the gateway carries the bare verb + type + local id."""
    result = build_simulation(_VALID)
    assert result.ok
    assert result.gateway_body == {
        "action": "read",
        "resource_type": "ahu",
        "resource_id": "rooftop-1",
        "context": {"site": "bldg-a", "maintenance_window": "true"},
    }
    # Identity boundary: no subject is ever part of the submitted body.
    assert "subject_id" not in result.gateway_body
    assert "subject_type" not in result.gateway_body
    # The console submits a BARE verb; it does not pre-compose the action.
    assert result.gateway_body["action"] == "read"
    assert ":" not in result.gateway_body["action"]


def test_composition_preview_mirrors_gateway():
    result = build_simulation(_VALID)
    assert result.composition == {
        "action": "read:ahu",
        "resource_id": "ahu:rooftop-1",
    }


def test_domain_level_request_omits_resource_id():
    """resource_id is optional; omitting it is a valid domain-level request."""
    result = build_simulation(dict(_VALID, resource_id=""))
    assert result.ok
    assert result.gateway_body == {
        "action": "read",
        "resource_type": "ahu",
        "context": {"site": "bldg-a", "maintenance_window": "true"},
    }
    assert "resource_id" not in result.gateway_body
    # Composition preview reflects the action only; no composed resource id.
    assert result.composition == {"action": "read:ahu", "resource_id": None}


def test_typed_resource_id_with_resource_type_is_rejected():
    """An already-typed resource id plus a resource type is a dual source of truth."""
    result = build_simulation(dict(_VALID, resource_id="ahu:rooftop-1"))
    assert not result.ok
    assert result.gateway_body is None
    assert "resource_id" in result.field_errors
    assert any("local" in e.lower() for e in result.errors)


def test_missing_required_fields_fail():
    result = build_simulation({})
    assert not result.ok
    assert result.preview is None
    assert result.gateway_body is None
    for field_name in ("subject_id", "subject_type", "action_verb", "resource_type"):
        assert field_name in result.field_errors
    # resource_id is OPTIONAL — its absence is not an error.
    assert "resource_id" not in result.field_errors


def test_invalid_verb_rejected():
    result = build_simulation(dict(_VALID, action_verb="delete"))
    assert not result.ok
    assert "action_verb" in result.field_errors
    assert any("verb must be one of" in e for e in result.errors)


def test_invalid_resource_type_rejected():
    result = build_simulation(dict(_VALID, resource_type="nonsense"))
    assert not result.ok
    assert "resource_type" in result.field_errors
    assert any("Resource type must be one of" in e for e in result.errors)


def test_all_verb_type_combinations_build_valid_requests():
    for verb in ACTION_VERBS:
        for rtype in RESOURCE_TYPES:
            result = build_simulation(dict(_VALID, action_verb=verb, resource_type=rtype))
            assert result.ok, (verb, rtype)
            assert result.gateway_body is not None
            assert result.gateway_body["action"] == verb
            assert result.gateway_body["resource_type"] == rtype
            # The composition the gateway will perform is structurally valid.
            assert result.composition is not None
            assert result.composition["action"] == compose_action(verb, rtype)
            assert matches_action_format(result.composition["action"])
            assert result.composition["resource_id"] == compose_resource_id(rtype, "rooftop-1")


def test_unsafe_identifier_rejected():
    result = build_simulation(dict(_VALID, resource_id="rooftop 1; drop"))
    assert not result.ok
    assert "resource_id" in result.field_errors


def test_unsafe_subject_type_rejected():
    result = build_simulation(dict(_VALID, subject_type="user/admin"))
    assert not result.ok
    assert "subject_type" in result.field_errors


def test_context_is_optional():
    result = build_simulation(dict(_VALID, context=""))
    assert result.ok
    assert result.preview is not None
    assert result.preview["context"] == {}
    # An empty context is omitted from the submitted body.
    assert "context" not in (result.gateway_body or {})


def test_malformed_context_line_rejected():
    result = build_simulation(dict(_VALID, context="not-a-pair"))
    assert not result.ok
    assert any("key=value" in e for e in result.errors)


def test_duplicate_context_key_rejected():
    result = build_simulation(dict(_VALID, context="site=a\nsite=b"))
    assert not result.ok
    assert any("Duplicate" in e for e in result.errors)


def test_values_echoed_back_on_failure():
    result = build_simulation(dict(_VALID, resource_type="bogus"))
    assert result.values["subject_id"] == "operator-jane"
    assert result.values["action_verb"] == "read"
    assert result.values["resource_type"] == "bogus"


def test_composition_preview_echoed_when_segments_present():
    # Fails on subject, but verb + resource_type + local id are still echoed.
    result = build_simulation(dict(_VALID, subject_id=""))
    assert not result.ok
    assert result.values["composed_action"] == "read:ahu"
    assert result.values["composed_resource_id"] == "ahu:rooftop-1"


def test_input_is_stripped():
    result = build_simulation(dict(_VALID, subject_id="  operator-jane  "))
    assert result.ok
    assert result.preview is not None
    assert result.preview["subject_id"] == "operator-jane"


# ---------------------------------------------------------------------------
# build_gateway_request — the gateway request-shape contract
# ---------------------------------------------------------------------------


def test_request_normalized_shape():
    """Preferred shape: bare verb + resource_type + local id."""
    result = build_gateway_request(action="read", resource_type="ahu", resource_id="rooftop-1")
    assert result.ok
    assert result.payload == {
        "action": "read",
        "resource_type": "ahu",
        "resource_id": "rooftop-1",
    }


def test_request_direct_typed_shape_excludes_resource_type():
    """Direct shape: fully-typed action + typed resource id, no resource_type."""
    result = build_gateway_request(action="read:ahu", resource_id="ahu:rooftop-1")
    assert result.ok
    assert result.payload == {"action": "read:ahu", "resource_id": "ahu:rooftop-1"}
    assert "resource_type" not in result.payload


def test_request_domain_level_includes_type_omits_resource_id():
    """Domain-level: verb + resource_type, no resource_id. Remains valid."""
    result = build_gateway_request(action="read", resource_type="ahu", resource_id="")
    assert result.ok
    assert result.payload == {"action": "read", "resource_type": "ahu"}
    assert "resource_id" not in result.payload


def test_request_invalid_mixed_typed_id_and_type():
    """resource_type + already-typed resource id (matching prefix) is rejected."""
    result = build_gateway_request(action="read", resource_type="ahu", resource_id="ahu:rooftop-1")
    assert not result.ok
    assert result.payload is None
    assert any("local" in e.lower() for e in result.errors)


def test_request_invalid_drift_typed_id_and_type():
    """resource_type + already-typed resource id (drifting prefix) is rejected."""
    result = build_gateway_request(
        action="read", resource_type="sensor", resource_id="ahu:rooftop-1"
    )
    assert not result.ok
    assert result.payload is None
    assert any("local" in e.lower() for e in result.errors)


def test_request_composite_action_with_resource_type_rejected():
    """A composite action alongside a resource_type is ambiguous and rejected."""
    result = build_gateway_request(action="read:ahu", resource_type="ahu", resource_id="rooftop-1")
    assert not result.ok
    assert result.payload is None


def test_request_local_id_without_resource_type_rejected():
    """A local resource id needs a resource_type for the gateway to compose it."""
    result = build_gateway_request(action="read:ahu", resource_id="rooftop-1")
    assert not result.ok
    assert result.payload is None


def test_request_bare_action_without_resource_type_rejected():
    """A bare verb with no resource_type gives the gateway no domain to compose."""
    result = build_gateway_request(action="read")
    assert not result.ok
    assert result.payload is None


def test_request_context_included_when_present():
    result = build_gateway_request(
        action="read", resource_type="ahu", resource_id="rooftop-1", context={"site": "a"}
    )
    assert result.ok
    assert result.payload is not None
    assert result.payload["context"] == {"site": "a"}


def test_request_never_includes_subject():
    result = build_gateway_request(action="read", resource_type="ahu", resource_id="rooftop-1")
    assert result.payload is not None
    assert "subject_id" not in result.payload
    assert "subject_roles" not in result.payload
