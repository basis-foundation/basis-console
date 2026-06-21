"""Unit tests for the decision-simulator logic (no HTTP, no gateway)."""

from __future__ import annotations

from basis_console.simulator import (
    ALLOWED_ACTIONS,
    build_simulation,
)

_VALID = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action": "read",
    "resource_id": "hvac:zone-a",
    "resource_type": "sensor",
    "context": "site=bldg-a\nmaintenance_window=true",
}


def test_valid_input_builds_preview():
    result = build_simulation(_VALID)
    assert result.ok
    assert result.errors == []
    assert result.preview == {
        "subject_id": "operator-jane",
        "subject_type": "user",
        "action": "read",
        "resource_id": "hvac:zone-a",
        "resource_type": "sensor",
        "context": {"site": "bldg-a", "maintenance_window": "true"},
    }


def test_preview_uses_decision_request_field_names():
    preview = build_simulation(_VALID).preview
    assert preview is not None
    # Mirrors basis-core DecisionRequest field names so the later swap is small.
    for key in ("subject_id", "action", "resource_id", "context"):
        assert key in preview


def test_missing_required_fields_fail():
    result = build_simulation({})
    assert not result.ok
    assert result.preview is None
    # Each required field reports an error.
    for field in ("subject_id", "subject_type", "action", "resource_id", "resource_type"):
        assert field in result.field_errors


def test_empty_subject_id_is_required():
    raw = dict(_VALID, subject_id="   ")
    result = build_simulation(raw)
    assert not result.ok
    assert "subject_id" in result.field_errors


def test_invalid_action_rejected():
    raw = dict(_VALID, action="delete")
    result = build_simulation(raw)
    assert not result.ok
    assert "action" in result.field_errors
    assert any("must be one of" in e for e in result.errors)


def test_all_allowed_actions_accepted():
    for action in ALLOWED_ACTIONS:
        result = build_simulation(dict(_VALID, action=action))
        assert result.ok, action


def test_unsafe_identifier_rejected():
    raw = dict(_VALID, resource_id="hvac zone-a; drop")
    result = build_simulation(raw)
    assert not result.ok
    assert "resource_id" in result.field_errors


def test_unsafe_subject_type_rejected():
    raw = dict(_VALID, subject_type="user/admin")
    result = build_simulation(raw)
    assert not result.ok
    assert "subject_type" in result.field_errors


def test_context_is_optional():
    raw = dict(_VALID, context="")
    result = build_simulation(raw)
    assert result.ok
    assert result.preview is not None
    assert result.preview["context"] == {}


def test_malformed_context_line_rejected():
    raw = dict(_VALID, context="not-a-pair")
    result = build_simulation(raw)
    assert not result.ok
    assert any("key=value" in e for e in result.errors)


def test_duplicate_context_key_rejected():
    raw = dict(_VALID, context="site=a\nsite=b")
    result = build_simulation(raw)
    assert not result.ok
    assert any("Duplicate" in e for e in result.errors)


def test_values_echoed_back_on_failure():
    raw = dict(_VALID, action="bogus")
    result = build_simulation(raw)
    assert result.values["subject_id"] == "operator-jane"
    assert result.values["action"] == "bogus"


def test_input_is_stripped():
    raw = dict(_VALID, subject_id="  operator-jane  ")
    result = build_simulation(raw)
    assert result.ok
    assert result.preview is not None
    assert result.preview["subject_id"] == "operator-jane"
