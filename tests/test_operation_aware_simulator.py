"""Unit tests for the operation-aware simulator request builder (PR 4).

Pure, no HTTP, no route involvement — mirrors ``test_simulator.py``'s style for
the legacy builder. Covers ``EvaluationType``/``parse_evaluation_type`` and
``build_operation_aware_simulation``.
"""

from __future__ import annotations

from basis_console.gateway.operation_aware_models import OperationAwareEvaluationRequest
from basis_console.simulator import (
    DEFAULT_EVALUATION_TYPE,
    OPERATION_AWARE_CONTEXT_REJECTED_MESSAGE,
    OPERATION_AWARE_LEGACY_ONLY_FIELDS,
    OPERATION_AWARE_SUBJECT_ID_REJECTED_MESSAGE,
    OPERATION_AWARE_SUBJECT_TYPE_REJECTED_MESSAGE,
    EvaluationType,
    build_operation_aware_simulation,
    parse_evaluation_type,
)

# ---------------------------------------------------------------------------
# parse_evaluation_type
# ---------------------------------------------------------------------------


def test_default_evaluation_type_is_legacy():
    assert DEFAULT_EVALUATION_TYPE is EvaluationType.LEGACY


def test_parse_none_defaults_to_legacy():
    assert parse_evaluation_type(None) is EvaluationType.LEGACY


def test_parse_empty_string_defaults_to_legacy():
    assert parse_evaluation_type("") is EvaluationType.LEGACY
    assert parse_evaluation_type("   ") is EvaluationType.LEGACY


def test_parse_explicit_legacy():
    assert parse_evaluation_type("legacy") is EvaluationType.LEGACY


def test_parse_explicit_operation_aware():
    assert parse_evaluation_type("operation_aware") is EvaluationType.OPERATION_AWARE


def test_parse_is_case_and_whitespace_tolerant():
    assert parse_evaluation_type(" Operation_Aware ") is EvaluationType.OPERATION_AWARE
    assert parse_evaluation_type("LEGACY") is EvaluationType.LEGACY


def test_parse_invalid_value_returns_none():
    assert parse_evaluation_type("bogus") is None
    assert parse_evaluation_type("operation-aware") is None  # hyphen, not underscore
    assert parse_evaluation_type("gateway") is None  # a `mode` value, not an evaluation_type


# ---------------------------------------------------------------------------
# build_operation_aware_simulation — happy path
# ---------------------------------------------------------------------------


def test_valid_normalized_request_builds_typed_request():
    result = build_operation_aware_simulation(
        {"action_verb": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}
    )
    assert result.ok
    assert isinstance(result.request, OperationAwareEvaluationRequest)
    assert result.request.action == "read"
    assert result.request.resource_type == "ahu"
    assert result.request.resource_id == "rooftop-1"
    # Never exposed in this milestone.
    assert result.request.request_id is None


def test_domain_level_request_omits_resource_id():
    result = build_operation_aware_simulation({"action_verb": "read", "resource_type": "ahu"})
    assert result.ok
    assert result.request is not None
    assert result.request.resource_id is None


def test_values_echo_stripped_submitted_fields():
    result = build_operation_aware_simulation(
        {"action_verb": " read ", "resource_type": " ahu ", "resource_id": " rooftop-1 "}
    )
    assert result.values == {
        "action_verb": "read",
        "resource_type": "ahu",
        "resource_id": "rooftop-1",
    }


# ---------------------------------------------------------------------------
# build_operation_aware_simulation — request integrity (no forbidden fields)
# ---------------------------------------------------------------------------


def test_built_request_has_no_subject_or_context_fields():
    """The typed request model has no field capable of carrying these at all.

    Type-level guarantee, checked against a clean (no crafted legacy-only
    fields) submission — a submission that *does* carry a crafted subject_id/
    subject_type/context is rejected outright before a request is built at
    all (see the "legacy-only field rejection" tests below).
    """
    result = build_operation_aware_simulation(
        {"action_verb": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}
    )
    assert result.ok
    request = result.request
    assert request is not None
    field_names = set(vars(request))
    assert "subject_id" not in field_names
    assert "subject_roles" not in field_names
    assert "context" not in field_names
    assert not hasattr(request, "subject_id")
    assert not hasattr(request, "context")


def test_unrestricted_form_dict_cannot_smuggle_producer_only_fields():
    """A crafted form dict with producer-only-shaped keys is simply ignored.

    The builder only ever reads action_verb/resource_type/resource_id/context
    by name — arbitrary extra keys (as a trusted-producer-only field would
    arrive on a hand-crafted POST) are never inspected or forwarded.
    """
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "location": "site-a",
            "device": "plc-1",
            "protocol_context": "bacnet",
            "operation_intent": "maintenance",
            "identity_evidence_reference": "evidence-1",
            "expected_policy_version": "9.9.9",
        }
    )
    assert result.ok
    request = result.request
    assert request is not None
    assert request.action == "read"
    assert request.resource_type == "ahu"
    for forbidden in (
        "location",
        "device",
        "protocol_context",
        "operation_intent",
        "identity_evidence_reference",
        "expected_policy_version",
    ):
        assert not hasattr(request, forbidden)


# ---------------------------------------------------------------------------
# build_operation_aware_simulation — context rejection
# ---------------------------------------------------------------------------


def test_nonempty_context_is_rejected():
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "context": "maintenance_window=true",
        }
    )
    assert not result.ok
    assert result.request is None
    assert OPERATION_AWARE_CONTEXT_REJECTED_MESSAGE in result.errors
    assert result.field_errors.get("context") == OPERATION_AWARE_CONTEXT_REJECTED_MESSAGE


def test_whitespace_only_context_is_accepted_as_empty():
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "context": "   \n  ",
        }
    )
    assert result.ok


def test_missing_context_key_is_fine():
    result = build_operation_aware_simulation({"action_verb": "read", "resource_type": "ahu"})
    assert result.ok


def test_context_rejection_checked_before_other_validation():
    """Even with other invalid fields, the context error is still reported."""
    result = build_operation_aware_simulation({"context": "a=b"})
    assert not result.ok
    assert result.errors == [OPERATION_AWARE_CONTEXT_REJECTED_MESSAGE]


def test_known_legacy_only_field_allowlist_is_exactly_these_three():
    assert set(OPERATION_AWARE_LEGACY_ONLY_FIELDS) == {"context", "subject_id", "subject_type"}


# ---------------------------------------------------------------------------
# build_operation_aware_simulation — legacy-only subject field rejection
# (targeted correction: a browser-hidden control is not a rejected control;
# the server must reject a crafted non-empty subject_id/subject_type too,
# the same as context, and never build a request or infer identity from it.)
# ---------------------------------------------------------------------------


def test_nonempty_subject_id_is_rejected():
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "subject_id": "operator-jane",
        }
    )
    assert not result.ok
    assert result.request is None
    assert OPERATION_AWARE_SUBJECT_ID_REJECTED_MESSAGE in result.errors
    assert result.field_errors.get("subject_id") == OPERATION_AWARE_SUBJECT_ID_REJECTED_MESSAGE


def test_nonempty_subject_type_is_rejected():
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "subject_type": "user",
        }
    )
    assert not result.ok
    assert result.request is None
    assert OPERATION_AWARE_SUBJECT_TYPE_REJECTED_MESSAGE in result.errors
    assert result.field_errors.get("subject_type") == OPERATION_AWARE_SUBJECT_TYPE_REJECTED_MESSAGE


def test_whitespace_only_subject_fields_are_accepted_as_empty():
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "subject_id": "   ",
            "subject_type": "\t",
        }
    )
    assert result.ok


def test_missing_subject_fields_is_fine():
    result = build_operation_aware_simulation({"action_verb": "read", "resource_type": "ahu"})
    assert result.ok


def test_all_crafted_legacy_only_fields_reported_together():
    """Every offending legacy-only field is reported, not just the first."""
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "context": "a=b",
            "subject_id": "operator-jane",
            "subject_type": "user",
        }
    )
    assert not result.ok
    assert result.request is None
    assert set(result.errors) == {
        OPERATION_AWARE_CONTEXT_REJECTED_MESSAGE,
        OPERATION_AWARE_SUBJECT_ID_REJECTED_MESSAGE,
        OPERATION_AWARE_SUBJECT_TYPE_REJECTED_MESSAGE,
    }
    assert set(result.field_errors) == {"context", "subject_id", "subject_type"}


def test_legacy_field_rejection_does_not_infer_identity():
    """A rejected subject_id never leaks into the (absent) built request."""
    result = build_operation_aware_simulation(
        {"action_verb": "read", "resource_type": "ahu", "subject_id": "operator-jane"}
    )
    assert result.request is None


def test_unrelated_form_fields_are_never_rejected():
    """Only the explicit known legacy-only fields are checked — not every POST key."""
    result = build_operation_aware_simulation(
        {
            "action_verb": "read",
            "resource_type": "ahu",
            "resource_id": "rooftop-1",
            "mode": "gateway",
            "evaluation_type": "operation_aware",
            "csrf_token": "abc123",
        }
    )
    assert result.ok


# ---------------------------------------------------------------------------
# build_operation_aware_simulation — validation / grammar reuse
# ---------------------------------------------------------------------------


def test_missing_action_verb_is_rejected():
    result = build_operation_aware_simulation({"resource_type": "ahu"})
    assert not result.ok
    assert "action_verb" in result.field_errors
    assert result.request is None


def test_unsupported_action_verb_is_rejected():
    result = build_operation_aware_simulation({"action_verb": "delete", "resource_type": "ahu"})
    assert not result.ok
    assert "must be one of" in result.field_errors["action_verb"]


def test_missing_resource_type_is_rejected():
    result = build_operation_aware_simulation({"action_verb": "read"})
    assert not result.ok
    assert "resource_type" in result.field_errors


def test_unsupported_resource_type_is_rejected():
    result = build_operation_aware_simulation({"action_verb": "read", "resource_type": "nonsense"})
    assert not result.ok
    assert "must be one of" in result.field_errors["resource_type"]


def test_typed_resource_id_with_resource_type_is_rejected():
    """Dual source of truth — identical grammar to the legacy path."""
    result = build_operation_aware_simulation(
        {"action_verb": "read", "resource_type": "ahu", "resource_id": "ahu:rooftop-1"}
    )
    assert not result.ok
    assert result.request is None


def test_unsafe_resource_id_is_rejected():
    result = build_operation_aware_simulation(
        {"action_verb": "read", "resource_type": "ahu", "resource_id": "bad value; rm -rf"}
    )
    assert not result.ok


def test_resource_id_too_long_is_rejected():
    result = build_operation_aware_simulation(
        {"action_verb": "read", "resource_type": "ahu", "resource_id": "x" * 200}
    )
    assert not result.ok
    assert "too long" in result.field_errors["resource_id"]
