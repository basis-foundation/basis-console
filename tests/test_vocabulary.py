"""Unit tests for the provisional console-local action vocabulary (Phase 6)."""

from __future__ import annotations

import re

from basis_console.vocabulary import (
    ACTION_DOMAINS,
    ACTION_VERBS,
    compose_action,
    is_supported_domain,
    is_supported_verb,
    matches_action_format,
)


def test_verbs_are_the_established_basis_set():
    # Only verbs already established across BASIS (and accepted by earlier
    # console phases / emitted by basis-adapters). No new verbs introduced.
    assert ACTION_VERBS == ("read", "write", "execute", "browse", "subscribe")


def test_domains_are_conservative_starter_set():
    assert set(ACTION_DOMAINS) == {
        "ahu",
        "setpoint",
        "telemetry",
        "device",
        "schedule",
        "command",
    }


def test_compose_action_builds_two_segment_string():
    assert compose_action("read", "ahu") == "read:ahu"
    assert compose_action("write", "setpoint") == "write:setpoint"


def test_compose_action_output_matches_core_format():
    for verb in ACTION_VERBS:
        for domain in ACTION_DOMAINS:
            assert matches_action_format(compose_action(verb, domain))


def test_bare_verb_does_not_match_core_format():
    # The whole point of Phase 6: a bare verb is NOT a valid action.
    for verb in ACTION_VERBS:
        assert not matches_action_format(verb)


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
    assert is_supported_domain("ahu")
    assert not is_supported_domain("nonsense")
