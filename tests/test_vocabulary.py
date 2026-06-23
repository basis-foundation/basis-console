"""Unit tests for the provisional console-local vocabulary bridge (Phases 6–7)."""

from __future__ import annotations

import re

from basis_console.vocabulary import (
    ACTION_VERBS,
    RESOURCE_TYPES,
    compose_action,
    compose_resource_id,
    is_supported_resource_type,
    is_supported_verb,
    is_typed_identifier,
    matches_action_format,
)


def test_verbs_are_the_established_basis_set():
    # Only verbs already established across BASIS (and accepted by earlier
    # console phases / emitted by basis-adapters). No new verbs introduced.
    assert ACTION_VERBS == ("read", "write", "execute", "browse", "subscribe")


def test_resource_types_are_conservative_starter_set():
    assert set(RESOURCE_TYPES) == {
        "ahu",
        "setpoint",
        "telemetry",
        "device",
        "schedule",
        "command",
    }


def test_compose_action_previews_two_segment_string():
    assert compose_action("read", "ahu") == "read:ahu"
    assert compose_action("write", "setpoint") == "write:setpoint"


def test_compose_resource_id_previews_typed_identifier():
    assert compose_resource_id("ahu", "rooftop-1") == "ahu:rooftop-1"
    assert compose_resource_id("setpoint", "zone-3") == "setpoint:zone-3"


def test_compose_action_output_matches_core_format():
    for verb in ACTION_VERBS:
        for rtype in RESOURCE_TYPES:
            assert matches_action_format(compose_action(verb, rtype))


def test_bare_verb_does_not_match_core_format():
    # A bare verb is NOT a valid kernel action.
    for verb in ACTION_VERBS:
        assert not matches_action_format(verb)


def test_is_typed_identifier_detects_colon():
    assert is_typed_identifier("ahu:rooftop-1")
    assert is_typed_identifier("read:ahu")
    assert not is_typed_identifier("rooftop-1")
    assert not is_typed_identifier("read")


def test_format_mirror_matches_basis_core_regex():
    # This must stay in lock-step with basis-core's DecisionRequest.action regex:
    # two or more colon-separated lowercase segments.
    core_re = re.compile(r"^[a-z][a-z0-9_-]*(:[a-z][a-z0-9_-]*)+$")
    samples = ["read:ahu", "write:hvac:setpoint", "read", "Read:Ahu", "read:", ":ahu", ""]
    for s in samples:
        assert matches_action_format(s) == bool(core_re.match(s)), s


def test_support_helpers():
    assert is_supported_verb("read")
    assert not is_supported_verb("delete")
    assert is_supported_resource_type("ahu")
    assert not is_supported_resource_type("nonsense")
