"""Static, console-authored educational content for operation-aware Training mode (PR 5).

WHAT THIS MODULE IS
────────────────────
A pure collection of static, typed teaching content — ecosystem-flow
descriptions, a provenance legend, an authorization-vocabulary glossary,
outcome/failure-reason explanations, null/absent-evidence guidance,
context/producer-trust boundary education, identifier education, and
preview-mode education — consumed only by
``partials/operation_aware_training.html`` when Training mode is active.

Every string here is console-authored teaching copy (``ContentSource
.CONSOLE_EXPLANATION`` or ``ContentSource.FUTURE_CAPABILITY`` in
``operation_aware_presentation``'s vocabulary) and is exhaustive over the
closed enums it maps from — never a partial or inferred mapping, and never a
place that "fills in" an unrecognized value with invented text.

WHAT THIS MODULE IS NOT
────────────────────────
This module performs no I/O, makes no gateway or network call, reads no
configuration, decodes no token, imports nothing from ``basis_console.config``,
``basis_console.gateway.client``, ``httpx``, ``fastapi``, or ``jinja2``, and
accepts no console-mode/authorization-shaped input anywhere in its public
surface. It does not alter, wrap, or re-derive any
``OperationAwarePresentation`` value — every mapping here is keyed by the
same closed, already-computed enums that module already exposes
(``OperationAwareOutcome``, ``OperationAwareFailureReason``,
``OperationAwareEvaluationState``, ``OperationAwareEvaluationStatus``,
``OperationAwareDisposition``), so selecting an entry is a lookup by an
already-classified value, never a second, independently-computed decision.

Every field on :data:`TRAINING_CONTENT` is built once, at import time, from
literal data — there is no per-request construction, no argument, and
therefore no way for console mode, request content, or gateway response
content to change what this module returns. The calling template decides,
from the shared ``OperationAwarePresentation`` object it already has, which
of these static entries is relevant to display; this module does not make
that decision either — see ``partials/operation_aware_training.html``, which
performs only key lookups (``dict[value]``) and applicability checks
(``.applicable`` / ``.present``) already established by the presentation
model, never a new comparison against outcome/disposition/failure_reason
literals.
"""

from __future__ import annotations

from dataclasses import dataclass

from basis_console.gateway.operation_aware_models import (
    OperationAwareEvaluationStatus,
    OperationAwareFailureReason,
    OperationAwareOutcome,
)

# ---------------------------------------------------------------------------
# Section 1 — How BASIS processes the request (conceptual flow, not a trace)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EcosystemStage:
    """One conceptual processing stage in the operation-aware request flow.

    ``observable_today`` is ``True`` only when this stage's result actually
    surfaces as a field on the current ``OperationAwareEvaluationResponse``/
    ``OperationAwareEvaluationResult`` (Section 5.1 of the integration plan).
    A conceptual flow entry is never rendered as a completed-stage checkmark;
    it is prose describing what the stage does and whether it is visible.
    """

    key: str
    title: str
    owner: str
    description: str
    observable_today: bool
    observability_note: str


ECOSYSTEM_FLOW_STAGES: tuple[EcosystemStage, ...] = (
    EcosystemStage(
        key="submitted_request",
        title="1. Submitted request",
        owner="basis-console",
        description=(
            "The console builds a typed request from the action, resource "
            "type, and resource ID you supplied — nothing else. No subject "
            "and no context are ever part of this request."
        ),
        observable_today=True,
        observability_note=(
            "Directly observable: the exact submitted values are shown above, "
            "tagged submitted input."
        ),
    ),
    EcosystemStage(
        key="gateway_authentication",
        title="2. Gateway authentication",
        owner="basis-gateway",
        description=(
            "The gateway verifies the console's Bearer token before any "
            "request-body logic runs. A request that fails authentication "
            "never reaches evaluation."
        ),
        observable_today=False,
        observability_note=(
            "Not directly observable as a field: the console can only state, "
            "generically, that authentication succeeded when a response (of "
            "any outcome or failure category) comes back rather than an "
            "unauthorized status — it never learns or displays who "
            "authenticated."
        ),
    ),
    EcosystemStage(
        key="producer_trust_classification",
        title="3. Producer trust and field-ownership validation",
        owner="basis-gateway",
        description=(
            "The gateway classifies whether the authenticated caller is a "
            "trusted operation producer (an adapter or identity service) and, "
            "on that basis, decides which request fields the caller may "
            "supply at all. An ordinary console session is not a trusted "
            "producer and has no code path capable of setting a "
            "producer-only field."
        ),
        observable_today=False,
        observability_note=(
            "Not returned by this endpoint today: no field on the response "
            "reveals a live trusted-producer classification for this request."
        ),
    ),
    EcosystemStage(
        key="action_resource_composition",
        title="4. Action and resource composition",
        owner="basis-gateway",
        description=(
            "The gateway composes the canonical kernel action "
            "({verb}:{resource_type}) and, when a local resource ID was "
            "given, the canonical resource identifier ({resource_type}:{id}) "
            "— identically to the legacy /v1/evaluate path."
        ),
        observable_today=False,
        observability_note=(
            "No composition-evidence field exists on this response (unlike "
            "the legacy path's basis_gateway.* evidence): the composed "
            "values are not echoed back separately from the outcome."
        ),
    ),
    EcosystemStage(
        key="policy_bundle_applicability",
        title="5. Policy bundle applicability",
        owner="basis-core",
        description=(
            "The kernel determines whether any loaded policy bundle covers "
            "this request's domain and scope at all before evaluating a "
            "single rule."
        ),
        observable_today=True,
        observability_note=(
            "Observable via bundle_id/bundle_version (preserved whenever a "
            "trustworthy typed bundle exists, including on not_applicable) "
            "and via outcome=not_applicable when no bundle covers the "
            "request."
        ),
    ),
    EcosystemStage(
        key="rule_evaluation_precedence",
        title="6. Rule evaluation and precedence",
        owner="basis-core",
        description=(
            "For an applicable bundle, the kernel evaluates its rules in "
            "governed precedence order to reach allow or deny."
        ),
        observable_today=True,
        observability_note=(
            "Partially observable: reason_code and explanation, when the "
            "kernel populates them, may hint at which rule mattered — but "
            "neither is a documented, closed vocabulary today, and null is a "
            "normal, complete state for both."
        ),
    ),
    EcosystemStage(
        key="kernel_outcome",
        title="7. Kernel outcome",
        owner="basis-core",
        description=(
            "The kernel's authorization result: allow, deny, or "
            "not_applicable — or, if evaluation could not complete, a "
            "governed failure reason instead of an outcome."
        ),
        observable_today=True,
        observability_note="Directly observable via outcome / failure_reason.",
    ),
    EcosystemStage(
        key="enforcement_disposition_http",
        title="8. Enforcement disposition and HTTP classification",
        owner="basis-gateway",
        description=(
            "The gateway surfaces the kernel-computed enforcement "
            "disposition (allow/deny) and classifies the HTTP response. "
            "disposition collapses not_applicable into deny the same way "
            "HTTP status does, but is a labelled field, never gateway-"
            "recomputed from outcome."
        ),
        observable_today=True,
        observability_note="Directly observable via disposition and HTTP status.",
    ),
    EcosystemStage(
        key="correlation_and_evidence",
        title="9. Correlation and evidence",
        owner="basis-gateway",
        description=(
            "The gateway attaches a correlation ID (matching the "
            "X-Correlation-ID header) and, when available, a trace "
            "reference, for connecting this call to related gateway records."
        ),
        observable_today=True,
        observability_note=(
            "Directly observable via request_id / correlation_id / trace_id, "
            "each shown only when the gateway actually returned it."
        ),
    ),
    EcosystemStage(
        key="console_presentation",
        title="10. Console presentation",
        owner="basis-console",
        description=(
            "The console relays every governed fact above verbatim and adds "
            "only the console-authored explanations on this page — it never "
            "reevaluates, recomputes, or reinterprets a kernel or gateway "
            "fact."
        ),
        observable_today=True,
        observability_note="This page is the observable result of this stage.",
    ),
)

IDENTITY_PROCESSING_BOUNDARY_NOTE = (
    "Stages 2 and 3 above are gateway processing stages, not per-request "
    "evidence: this endpoint does not return the authenticated subject or a "
    "live trusted-producer classification, the console does not decode or "
    "introspect the configured Bearer token to derive either one, and no "
    "subject or producer classification is inferred from any other signal."
)

# ---------------------------------------------------------------------------
# Section 2 — Provenance legend
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvenanceLegendEntry:
    key: str
    label: str
    description: str


PROVENANCE_LEGEND: tuple[ProvenanceLegendEntry, ...] = (
    ProvenanceLegendEntry(
        key="submitted_input",
        label="Submitted input",
        description=(
            "What the console sent (or would send) to the gateway — action, "
            "resource type, resource ID. Not a gateway confirmation: the "
            "gateway may accept, reject, or default any of these "
            "independently."
        ),
    ),
    ProvenanceLegendEntry(
        key="returned_evidence",
        label="Returned evidence",
        description=(
            "An exact value copied from the gateway's typed response — never "
            "a console interpretation of it, and never a value the console "
            "itself supplied."
        ),
    ),
    ProvenanceLegendEntry(
        key="console_explanation",
        label="Console explanation",
        description=(
            "Educational or diagnostic prose authored by basis-console "
            "itself. Never gateway-authored, never presented as if it were a "
            "returned field's value."
        ),
    ),
    ProvenanceLegendEntry(
        key="future_capability",
        label="Future capability",
        description=(
            "A capability that is not returned or implemented today (the "
            "only current example is an embedded evaluation trace). Never "
            "implied to be live."
        ),
    ),
)

# ---------------------------------------------------------------------------
# Section 3 — Authorization vocabulary glossary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VocabularyEntry:
    term: str
    definition: str


AUTHORIZATION_VOCABULARY: tuple[VocabularyEntry, ...] = (
    VocabularyEntry(
        term="Evaluation status",
        definition=(
            "Whether the kernel's governed evaluation completed or failed "
            "(evaluation_status: completed / failed). Never itself an "
            "authorization decision."
        ),
    ),
    VocabularyEntry(
        term="Kernel outcome",
        definition=(
            "The policy evaluation result — allow, deny, or not_applicable — "
            "present only when evaluation_status is completed."
        ),
    ),
    VocabularyEntry(
        term="Failure reason",
        definition=(
            "Why a governed evaluation failed before producing an outcome — "
            "present only when evaluation_status is failed. Not a policy "
            "denial."
        ),
    ),
    VocabularyEntry(
        term="Enforcement disposition",
        definition=(
            "The gateway-surfaced, kernel-computed fail-open/fail-closed "
            "enforcement result (allow / deny). Collapses not_applicable "
            "into deny the same way HTTP status does, but is a labelled "
            "response field, never gateway-recomputed from outcome."
        ),
    ),
    VocabularyEntry(
        term="HTTP status",
        definition=(
            "The transport-level classification the gateway returned for "
            "this call. Status code alone does not determine whether the "
            "body is a governed result or a generic pre-kernel rejection."
        ),
    ),
    VocabularyEntry(
        term="Client status",
        definition=(
            "How basis-console classifies this call's outcome at the "
            "transport/capability layer — configuration, connectivity, "
            "authentication, request-shape, or contract state, in addition "
            "to the two governed states (evaluation completed / evaluation "
            "failed)."
        ),
    ),
)

VOCABULARY_COLLAPSE_WARNING = (
    "These are separate facts. None of evaluation status, kernel outcome, "
    "failure reason, enforcement disposition, HTTP status, or client status "
    "is a substitute for any other, and this page never collapses them into "
    "a single allowed/denied boolean."
)

# ---------------------------------------------------------------------------
# Section 4 — Outcome-specific teaching
# ---------------------------------------------------------------------------

_OUTCOME_TRAINING_COPY_BY_ENUM: dict[OperationAwareOutcome, str] = {
    OperationAwareOutcome.ALLOW: (
        "The applicable policy bundle completed evaluation, the kernel "
        "outcome was allow, the enforcement disposition was allow, and the "
        "gateway returned a successful enforcement classification. This page "
        "does not claim which specific rule allowed the action unless the "
        "returned reason_code or explanation explicitly says so."
    ),
    OperationAwareOutcome.DENY: (
        "The applicable policy bundle completed evaluation and the kernel "
        "outcome was deny; the enforcement disposition prevents the "
        "operation. The response does not distinguish an explicit deny rule "
        "from a default deny when no allow rule matched, and this page does "
        "not invent that distinction — an opaque reason_code, if present, is "
        "shown exactly as returned, never turned into a stronger claim."
    ),
    OperationAwareOutcome.NOT_APPLICABLE: (
        "The policy bundle did not apply to this request's domain or scope "
        "at all — this is a coverage gap, not a policy evaluating the "
        "request and saying no. The gateway still enforces this fail-closed "
        "(HTTP 403, disposition=deny), but that HTTP classification is an "
        "enforcement fact, not a replacement for the kernel's own outcome. "
        "Bundle identity remains meaningful evidence here and stays visible "
        "when the gateway returns it — the kernel outcome for this result is "
        "never shown as deny."
    ),
}
assert set(_OUTCOME_TRAINING_COPY_BY_ENUM) == set(OperationAwareOutcome), (
    "OUTCOME_TRAINING_COPY must be exhaustive over OperationAwareOutcome"
)

# String-keyed for direct Jinja lookup (``PresentationContentItem.value`` is
# already a plain ``str``, e.g. "allow" — see ``operation_aware_presentation``).
# A lookup by the already-classified value is not a second decision; it is a
# key-into-a-static-mapping operation over a value the presentation model
# already computed.
OUTCOME_TRAINING_COPY: dict[str, str] = {
    outcome.value: text for outcome, text in _OUTCOME_TRAINING_COPY_BY_ENUM.items()
}

GOVERNED_FAILURE_INTRO = (
    "The evaluator failed to produce a valid policy outcome — no allow, "
    "deny, or not_applicable exists for this call. This is not a policy "
    "denial: the returned failure_reason is authoritative, and this page "
    "does not add a remediation claim the contract does not support."
)

_FAILURE_REASON_TRAINING_COPY_BY_ENUM: dict[OperationAwareFailureReason, str] = {
    OperationAwareFailureReason.INVALID_REQUEST: (
        "Request category. The submitted request did not satisfy the "
        "evaluator's shape contract before evaluation could begin — a "
        "structural problem with this specific call, not a bundle or "
        "internal-state problem."
    ),
    OperationAwareFailureReason.UNSUPPORTED_SCHEMA_VERSION: (
        "Request category. The evaluator does not support this request's "
        "schema version — a version mismatch for this specific call, not a "
        "policy decision."
    ),
    OperationAwareFailureReason.INVALID_POLICY_BUNDLE: (
        "Bundle category. The gateway's configured policy dependency is not "
        "in the state its own startup check certified — a dependency-"
        "integrity problem discovered after startup, independent of this "
        "specific request's content."
    ),
    OperationAwareFailureReason.POLICY_VALIDATION_FAILURE: (
        "Validation category. The loaded policy bundle failed validation at "
        "evaluation time — again a dependency-integrity problem with the "
        "bundle itself, not a decision about this request."
    ),
    OperationAwareFailureReason.CONDITION_EVALUATION_ERROR: (
        "Condition category. A policy condition could not be evaluated for "
        "this specific request — a per-request evaluation-time failure, "
        "distinct from a bundle-level problem."
    ),
    OperationAwareFailureReason.INTERNAL_EVALUATION_ERROR: (
        "Internal-evaluation category. The evaluator failed unexpectedly "
        "while processing this request — an evaluation-time failure with no "
        "more specific governed cause available."
    ),
}
assert set(_FAILURE_REASON_TRAINING_COPY_BY_ENUM) == set(OperationAwareFailureReason), (
    "FAILURE_REASON_TRAINING_COPY must be exhaustive over OperationAwareFailureReason"
)

# String-keyed for direct Jinja lookup — see OUTCOME_TRAINING_COPY above for
# why a string-keyed lookup is not a second decision.
FAILURE_REASON_TRAINING_COPY: dict[str, str] = {
    reason.value: text for reason, text in _FAILURE_REASON_TRAINING_COPY_BY_ENUM.items()
}

GENERIC_FAILURE_INTRO = (
    "No trusted governed decision is available for this call. The failure "
    "occurred in configuration, connectivity, authentication, request "
    "validation, capability availability, response parsing, or another "
    "gateway/client boundary — before or instead of a governed evaluation "
    "result. This page does not present a kernel outcome, a disposition, or "
    "a policy bundle identity for this result, and does not claim exactly "
    "how far the request progressed beyond what the client status itself "
    "proves."
)

# Client-level statuses for which a governed response exists — the two
# categories Section 4's ALLOW/DENY/NOT_APPLICABLE/governed-failure teaching
# applies to. Every other status (of the exhaustive
# ``OperationAwareEvaluationStatus`` enum) is a generic/client failure
# (Section 4's final category) by construction, not by a partial mapping.
# String-valued (not enum members) so tests and templates can compare
# directly against ``PresentationContentItem.value`` without an enum import.
GOVERNED_CLIENT_STATUS_VALUES: tuple[str, ...] = (
    OperationAwareEvaluationStatus.EVALUATION_COMPLETED.value,
    OperationAwareEvaluationStatus.EVALUATION_FAILED.value,
)
GENERIC_CLIENT_STATUS_VALUES: tuple[str, ...] = tuple(
    status.value
    for status in OperationAwareEvaluationStatus
    if status.value not in GOVERNED_CLIENT_STATUS_VALUES
)

# ---------------------------------------------------------------------------
# Section 5 — Null and absent evidence
# ---------------------------------------------------------------------------

NULL_EXPLANATION_GUIDANCE = (
    "A null evaluator explanation is a normal, complete contract state — "
    "the kernel does not fabricate aggregate prose when no governed stage "
    "supplied one. The console-authored placeholder note shown in that case "
    "is not the returned evaluator explanation and is never presented as "
    "such."
)

ABSENT_REASON_CODE_GUIDANCE = (
    "No reason code was returned for this result. The console does not "
    "generate one — reason_code is populated only by the kernel, and its "
    "absence is a valid, expected state, not an error."
)

ABSENT_BUNDLE_IDENTITY_GUIDANCE = (
    "A trustworthy typed policy bundle identity was not available in this "
    "response state. The console does not substitute a configured or "
    "expected bundle identity in its place — absence here is shown as "
    "absence, never inferred."
)

ABSENT_TRACE_ID_GUIDANCE = (
    "No trace reference was returned for this call. The console does not "
    "generate one — trace_id, when present, is a gateway-generated value, "
    "never a console fabrication."
)

# ---------------------------------------------------------------------------
# Section 6 — Context and producer trust
# ---------------------------------------------------------------------------

CONTEXT_AND_PRODUCER_TRUST_POINTS: tuple[str, ...] = (
    "The gateway owns every authentication-derived fact about this call — "
    "basis-console never authenticates users and never derives an "
    "identity of its own.",
    "An ordinary caller cannot assert their own subject identity to this "
    "endpoint: the gateway derives it exclusively from the verified Bearer "
    "token, never from anything the console submits.",
    "Trusted-producer fields (operation intent, location, device, protocol "
    "context, safety context, environment context, risk context, and "
    "identity/adapter evidence references) represent governed operational "
    "evidence that only a trusted operation producer — an adapter or "
    "identity service — may supply.",
    "basis-console is an operator-facing console, not an adapter or a "
    "trusted operation producer, so it never exposes editable controls for "
    "any of those nine fields.",
    "Arbitrary caller-supplied context is not silently accepted or "
    "discarded: the operation-aware endpoint has no field for caller-"
    "supplied context at all, and the console has no control that could "
    "submit one. A crafted non-empty value for a legacy-only or "
    "producer-only field is rejected on the server exactly as it is in "
    "Operator mode.",
    "This boundary prevents basis-console from ever fabricating device, "
    "protocol, safety, or identity evidence it has no way to attest to.",
    "None of this is per-request evidence about the current call — it is "
    "architectural education about why the form looks the way it does.",
)

# ---------------------------------------------------------------------------
# Section 7 — Correlation and evidence identifiers
# ---------------------------------------------------------------------------

REQUEST_ID_EDUCATION = (
    "The operation-aware identifier for this request, when returned. It is "
    "not always console-generated — when no caller-supplied value is given, "
    "the gateway defaults it to the generated correlation ID."
)

CORRELATION_ID_EDUCATION = (
    "The gateway's correlation identifier connecting this HTTP call to "
    "related gateway records, reconciled against the X-Correlation-ID "
    "response header before display. This page performs no new "
    "reconciliation of its own beyond what the typed result already "
    "carries."
)

TRACE_ID_EDUCATION = (
    "A per-call trace reference returned when available. It is not "
    "interchangeable with the correlation ID — the two identify different "
    "things and are never merged into one value here."
)

EVALUATION_TRACE_EDUCATION = (
    "An embedded evaluation trace is not returned by this endpoint today. "
    "This page does not claim a trace was retrieved, that the console can "
    "currently fetch one, that a trace viewer exists, or that a trace was "
    "generated locally."
)

AUDIT_EVIDENCE_EDUCATION = (
    "No audit-evidence identifier or audit-event display is shown here. "
    "The gateway's runtime audit-event shape is not assumed to match the "
    "published schema contract, and no supported audit retrieval endpoint "
    "exists for this console today."
)

# ---------------------------------------------------------------------------
# Preview-mode education
# ---------------------------------------------------------------------------

PREVIEW_EDUCATION_POINTS: tuple[str, ...] = (
    "The values shown above are submitted input — what the console would "
    "send, not a gateway confirmation of anything.",
    "This request has not been sent to basis-gateway.",
    "No authentication has occurred through this preview.",
    "No policy bundle has been evaluated.",
    "No outcome or enforcement disposition exists for this preview.",
    "No correlation ID or trace ID exists for this preview.",
    "This preview does not simulate authorization in any way — it shows a request shape only.",
)

# ---------------------------------------------------------------------------
# Aggregate, single import surface for the template layer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OperationAwareTrainingContent:
    """All static Training-mode educational content for the operation-aware flow.

    A single frozen aggregate, built once at import time from literal data
    only. ``partials/operation_aware_training.html`` reads fields from this
    object and from the shared ``OperationAwarePresentation`` object it is
    given — it never receives a console-mode argument, a request, or a
    response, and never constructs a second copy of this content.
    """

    ecosystem_stages: tuple[EcosystemStage, ...]
    identity_processing_boundary_note: str
    provenance_legend: tuple[ProvenanceLegendEntry, ...]
    vocabulary: tuple[VocabularyEntry, ...]
    vocabulary_collapse_warning: str
    outcome_copy: dict[str, str]
    governed_failure_intro: str
    failure_reason_copy: dict[str, str]
    generic_failure_intro: str
    governed_client_status_values: tuple[str, ...]
    generic_client_status_values: tuple[str, ...]
    null_explanation_guidance: str
    absent_reason_code_guidance: str
    absent_bundle_identity_guidance: str
    absent_trace_id_guidance: str
    context_and_producer_trust_points: tuple[str, ...]
    request_id_education: str
    correlation_id_education: str
    trace_id_education: str
    evaluation_trace_education: str
    audit_evidence_education: str
    preview_education_points: tuple[str, ...]


TRAINING_CONTENT = OperationAwareTrainingContent(
    ecosystem_stages=ECOSYSTEM_FLOW_STAGES,
    identity_processing_boundary_note=IDENTITY_PROCESSING_BOUNDARY_NOTE,
    provenance_legend=PROVENANCE_LEGEND,
    vocabulary=AUTHORIZATION_VOCABULARY,
    vocabulary_collapse_warning=VOCABULARY_COLLAPSE_WARNING,
    outcome_copy=OUTCOME_TRAINING_COPY,
    governed_failure_intro=GOVERNED_FAILURE_INTRO,
    failure_reason_copy=FAILURE_REASON_TRAINING_COPY,
    generic_failure_intro=GENERIC_FAILURE_INTRO,
    governed_client_status_values=GOVERNED_CLIENT_STATUS_VALUES,
    generic_client_status_values=GENERIC_CLIENT_STATUS_VALUES,
    null_explanation_guidance=NULL_EXPLANATION_GUIDANCE,
    absent_reason_code_guidance=ABSENT_REASON_CODE_GUIDANCE,
    absent_bundle_identity_guidance=ABSENT_BUNDLE_IDENTITY_GUIDANCE,
    absent_trace_id_guidance=ABSENT_TRACE_ID_GUIDANCE,
    context_and_producer_trust_points=CONTEXT_AND_PRODUCER_TRUST_POINTS,
    request_id_education=REQUEST_ID_EDUCATION,
    correlation_id_education=CORRELATION_ID_EDUCATION,
    trace_id_education=TRACE_ID_EDUCATION,
    evaluation_trace_education=EVALUATION_TRACE_EDUCATION,
    audit_evidence_education=AUDIT_EVIDENCE_EDUCATION,
    preview_education_points=PREVIEW_EDUCATION_POINTS,
)
