"""Unit tests for the pure operation-aware Training-mode content module (PR 5).

Mirrors ``test_operation_aware_presentation.py``'s discipline: no HTTP
mocking, no route/template involvement — this file tests only the static
data module in isolation.
"""

from __future__ import annotations

import dataclasses

import pytest

from basis_console.gateway.operation_aware_models import (
    OperationAwareEvaluationStatus,
    OperationAwareFailureReason,
    OperationAwareOutcome,
)
from basis_console.operation_aware_training import (
    AUTHORIZATION_VOCABULARY,
    ECOSYSTEM_FLOW_STAGES,
    FAILURE_REASON_TRAINING_COPY,
    GENERIC_CLIENT_STATUS_VALUES,
    GOVERNED_CLIENT_STATUS_VALUES,
    OUTCOME_TRAINING_COPY,
    PROVENANCE_LEGEND,
    TRAINING_CONTENT,
)


def test_outcome_copy_is_exhaustive_over_outcome_enum():
    assert set(OUTCOME_TRAINING_COPY) == {o.value for o in OperationAwareOutcome}


def test_failure_reason_copy_is_exhaustive_over_failure_reason_enum():
    assert set(FAILURE_REASON_TRAINING_COPY) == {r.value for r in OperationAwareFailureReason}


def test_every_outcome_and_failure_reason_entry_is_non_empty_text():
    for text in OUTCOME_TRAINING_COPY.values():
        assert isinstance(text, str) and text.strip()
    for text in FAILURE_REASON_TRAINING_COPY.values():
        assert isinstance(text, str) and text.strip()


def test_governed_and_generic_status_values_partition_the_status_enum():
    all_values = {s.value for s in OperationAwareEvaluationStatus}
    governed = set(GOVERNED_CLIENT_STATUS_VALUES)
    generic = set(GENERIC_CLIENT_STATUS_VALUES)
    assert governed | generic == all_values
    assert governed & generic == set()
    assert governed == {"evaluation_completed", "evaluation_failed"}
    # Defensive: every non-governed status is classified generic (Section 4's
    # "generic/client failure" category is exhaustive by construction).
    assert generic == all_values - governed


def test_ecosystem_flow_has_ten_ordered_stages():
    assert len(ECOSYSTEM_FLOW_STAGES) == 10
    keys = [stage.key for stage in ECOSYSTEM_FLOW_STAGES]
    assert keys[0] == "submitted_request"
    assert keys[-1] == "console_presentation"
    assert len(set(keys)) == 10  # no duplicate stage keys


def test_ecosystem_stages_never_claim_identity_or_producer_are_observable():
    for stage in ECOSYSTEM_FLOW_STAGES:
        if stage.key in ("gateway_authentication", "producer_trust_classification"):
            assert stage.observable_today is False


def test_provenance_legend_has_exactly_the_four_categories():
    keys = {entry.key for entry in PROVENANCE_LEGEND}
    assert keys == {
        "submitted_input",
        "returned_evidence",
        "console_explanation",
        "future_capability",
    }


def test_vocabulary_covers_the_six_required_terms():
    terms = {entry.term for entry in AUTHORIZATION_VOCABULARY}
    assert terms == {
        "Evaluation status",
        "Kernel outcome",
        "Failure reason",
        "Enforcement disposition",
        "HTTP status",
        "Client status",
    }


def test_training_content_aggregate_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        TRAINING_CONTENT.governed_failure_intro = "mutated"  # type: ignore[misc]


def test_ecosystem_stage_entries_are_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        ECOSYSTEM_FLOW_STAGES[0].title = "mutated"  # type: ignore[misc]


def test_not_applicable_copy_never_uses_the_word_deny_as_the_outcome():
    """The NOT_APPLICABLE explanation may mention 'deny' only when describing
    disposition/HTTP enforcement — it must never state the *outcome* is deny.
    """
    text = OUTCOME_TRAINING_COPY[OperationAwareOutcome.NOT_APPLICABLE.value]
    assert "never shown as deny" in text or "not_applicable" in text
    assert "outcome was deny" not in text


def test_deny_copy_does_not_invent_explicit_vs_default_distinction():
    text = OUTCOME_TRAINING_COPY[OperationAwareOutcome.DENY.value]
    assert "does not distinguish" in text


def test_governed_failure_copy_states_it_is_not_a_policy_denial():
    assert "not a policy denial" in TRAINING_CONTENT.governed_failure_intro
    # Per-reason copy stays in request/bundle/validation/condition/internal
    # category language and never independently asserts a policy denial.
    for text in FAILURE_REASON_TRAINING_COPY.values():
        assert "denial" not in text.lower()


def test_generic_failure_copy_never_invents_a_kernel_outcome():
    text = TRAINING_CONTENT.generic_failure_intro
    assert "does not present a kernel outcome" in text
