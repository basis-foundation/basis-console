"""Unit tests for the decision-simulator logic (no HTTP, no gateway)."""

from __future__ import annotations

from basis_console.simulator import build_simulation
from basis_console.vocabulary import (
    ACTION_DOMAINS,
    ACTION_VERBS,
    compose_action,
    matches_action_format,
)

_VALID = {
    "subject_id": "operator-jane",
    "subject_type": "user",
    "action_verb": "read",
    "action_domain": "ahu",
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
        # Action is composed from verb + domain into the {verb}:{domain} form.
        "action": "read:ahu",
        "resource_id": "hvac:zone-a",
        "resource_type": "sensor",
        "context": {"site": "bldg-a", "maintenance_window": "true"},
    }


def test_preview_action_is_composed_not_bare():
    """The preview action must be the composed string, never a bare verb."""
    preview = build_simulation(_VALID).preview
    assert preview is not None
    assert preview["action"] == "read:ahu"
    assert ":" in preview["action"]
    assert matches_action_format(preview["action"])


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
    for field in (
        "subject_id",
        "subject_type",
        "action_verb",
        "action_domain",
        "resource_id",
        "resource_type",
    ):
        assert field in result.field_errors


def test_empty_subject_id_is_required():
    raw = dict(_VALID, subject_id="   ")
    result = build_simulation(raw)
    assert not result.ok
    assert "subject_id" in result.field_errors


def test_invalid_verb_rejected():
    raw = dict(_VALID, action_verb="delete")
    result = build_simulation(raw)
    assert not result.ok
    assert "action_verb" in result.field_errors
    assert any("verb must be one of" in e for e in result.errors)


def test_invalid_domain_rejected():
    raw = dict(_VALID, action_domain="nonsense")
    result = build_simulation(raw)
    assert not result.ok
    assert "action_domain" in result.field_errors
    assert any("domain must be one of" in e for e in result.errors)


def test_missing_verb_or_domain_rejected():
    no_verb = build_simulation(dict(_VALID, action_verb=""))
    assert not no_verb.ok
    assert "action_verb" in no_verb.field_errors

    no_domain = build_simulation(dict(_VALID, action_domain=""))
    assert not no_domain.ok
    assert "action_domain" in no_domain.field_errors


def test_all_verb_domain_combinations_compose_valid_actions():
    for verb in ACTION_VERBS:
        for domain in ACTION_DOMAINS:
            result = build_simulation(dict(_VALID, action_verb=verb, action_domain=domain))
            assert result.ok, (verb, domain)
            assert result.preview is not None
            assert result.preview["action"] == compose_action(verb, domain)
            # Every composed action satisfies basis-core's required format.
            assert matches_action_format(result.preview["action"]), result.preview["action"]


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
    raw = dict(_VALID, action_domain="bogus")
    result = build_simulation(raw)
    assert result.values["subject_id"] == "operator-jane"
    # Verb and domain are echoed verbatim so the form repopulates.
    assert result.values["action_verb"] == "read"
    assert result.values["action_domain"] == "bogus"


def test_composed_action_echoed_when_both_segments_present():
    raw = dict(_VALID, resource_id="")  # fails on resource, not on action
    result = build_simulation(raw)
    assert not result.ok
    # Even on failure, the best-effort composed action is echoed for display.
    assert result.values["action"] == "read:ahu"


def test_input_is_stripped():
    raw = dict(_VALID, subject_id="  operator-jane  ")
    result = build_simulation(raw)
    assert result.ok
    assert result.preview is not None
    assert result.preview["subject_id"] == "operator-jane"
