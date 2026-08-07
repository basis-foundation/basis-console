# Operation-Aware Console Integration Plan

**Status:** Planning only. No operation-aware runtime code is introduced by this
document.
**Branch:** `docs/operation-aware-console-integration-plan`
**Baseline commit:** `672c5c4b113fa976242394d86f5454782fcf0829` (`main`, PR #15 —
"feature/console-training-mode" merged)
**Scope:** Defines the contract, boundaries, and phased implementation sequence
for adding operation-aware authorization support to `basis-console`, consuming
`basis-gateway`'s `POST /v1/evaluate/operation-aware`. This document plans; it
does not implement.

---

## 1. Purpose

`basis-gateway` has shipped a complete, feature-gated operation-aware
authorization surface — `POST /v1/evaluate/operation-aware` — backed by
`basis-core`'s public `OperationAwareEnforcementPoint`. The version chain
behind that surface is precise and worth stating exactly, since "operation-
aware shipped in v0.2.0" is imprecise enough to mislead a future dependency
decision:

- `basis-core` **v0.2.0** introduced the operation-aware surface itself
  (`OperationAwareDecisionRequest`, `OperationAwareEnforcementPoint`,
  `OperationAwareDecisionResponse`, `EvaluationTrace`, `AuditEvidence`, and
  the direct `OperationAwareEnforcementPoint(engine=..., bundle=...)`
  constructor).
- `basis-core` **v0.2.1** added `OperationAwareEnforcementPoint.for_bundle
  (bundle)` as the supported public downstream-construction path — an
  additive, backward-compatible correction to the v0.2.0 construction
  surface, per `basis-core`'s `CHANGELOG.md` (`[0.2.1]`, "Added"). The direct
  constructor remains available for internal/advanced use but is not the
  path downstream repositories are meant to use.
- `basis-gateway`'s `pyproject.toml` pins `basis-core>=0.2.1,<0.3.0` — the
  gateway's own operation-aware integration plan (`docs/implementation/
  operation-aware-gateway-integration-plan.md`) confirms it was built against
  `for_bundle()` specifically, not the raw v0.2.0 constructor.

So: the operation-aware *contracts and semantics* originate in `basis-core`
v0.2.0, but the currently-shipped `basis-gateway` integration — and therefore
the surface this plan documents — depends on `basis-core` v0.2.1 for the
supported public construction boundary it actually uses. This plan does not
imply that the complete current gateway integration supports `basis-core`
v0.2.0 as a dependency floor; `>=0.2.1,<0.3.0` is the floor that matters for
anything built against the shipped gateway.

`basis-console` has not yet integrated with any of this. Per
`basis-architecture`'s adoption sequence (kernel → gateway → console →
identity/adapters), the console is next.

This plan establishes, before any code changes:

- the authoritative gateway contract the console will consume (Sections 4–5);
- the console's architectural boundaries, restated against this specific
  surface (Section 3);
- what Operator and Training modes share and how they differ for this flow
  (Sections 7–9);
- how degraded/error states are classified (Section 6);
- how this coexists with the legacy `/v1/evaluate` path (Section 10);
- where this fits into existing pages (Section 11);
- a narrow, incremental PR sequence (Section 12);
- explicit invariants and non-goals (Sections 13–14).

Later PRs implement against this document without rediscovering the contract
or inventing semantics.

---

## 2. Baseline and Repository Findings

### 2.1 Baseline

- Branch: `docs/operation-aware-console-integration-plan`, working tree clean
  at start.
- Starting commit: `672c5c4b113fa976242394d86f5454782fcf0829`.
- Baseline validation (see Section 15 for exact commands/output): 284 tests
  pass, `ruff check` clean, `ruff format --check` clean (50 files), `mypy
  --strict` clean (20 source files).

### 2.2 Current gateway-client architecture

`src/basis_console/gateway/` is the console's single egress point
(`docs/architecture.md`, "Gateway-first integration rule"):

- `client.py` — `GatewayClient`. Never raises into a caller; every failure
  mode becomes a typed result. Three capabilities exist today:
  `check_status()` (`/health` + `/ready` → `GatewayStatusReport`),
  `get_health()` / `get_ready()` (raw, redacted single-probe results →
  `GatewayProbeResult`, used by Gateway Diagnostics), and `evaluate()`
  (`POST /v1/evaluate` → `GatewayEvaluationResult`).
- `models.py` — typed dataclasses for the above, plus the closed
  `GatewayEvaluationStatus` enum and its operator-facing
  `EVALUATION_STATE_EXPLANATIONS` map.
- `redaction.py` — `redact_json` / `redact_headers`, applied to every
  gateway-sourced value before it is stored on a result object.

`evaluate()` sends only `action` / `resource_type` / `resource_id` /
`context` — never a subject — and stores the configured `GATEWAY_BEARER_TOKEN`
privately, never exposed via property, repr, log, or result object
(`config.py`, `client.py`). This identity boundary is the same one the
operation-aware endpoint enforces server-side (Section 4.3) and must be
preserved unchanged for the new path.

### 2.3 Current Decision Simulator structure

`simulator.py` (pure, no I/O) validates operator-supplied form fields against
the provisional `vocabulary.py` bridge and builds two things: a
`SimulationResult.preview` (educational, includes preview-only subject fields)
and a `SimulationResult.gateway_body` (the exact JSON the console would POST —
no subject). `ui/views.py`'s `/simulate` GET/POST handlers own the two
submission modes (`mode=preview` default, `mode=gateway` opt-in) and hold all
gateway-call orchestration; `simulator.py` itself never imports
`basis_console.gateway`. `simulate.html` renders the form, the two modes, and
(when `mode=gateway`) the relayed `GatewayEvaluationResult`.

### 2.4 Current Operator/Training presentation abstraction

`config.py`'s `ConsoleConfig.basis_console_mode` (`operator` default /
`training`) is read once per request in `ui/views.py`'s `_console_mode()` /
`_base_context()`, which sets `console_mode` and `is_training_mode` in every
template context. Templates use `is_training_mode` to conditionally render
*additional* markup (`partials/training_banner.html`,
`partials/training_callout.html`) — never to gate a route, a control, or a
data source. `test_console_mode.py` enforces this with byte-identical
navigation, identical form controls, and identical HTTP status codes across
both modes for every page.

### 2.5 Relevant existing tests

- `test_gateway_evaluate.py` — `GatewayClient.evaluate()` unit tests (mocked
  HTTP transport), covering the prerequisite gates (not-configured,
  token-missing), the identity boundary (no subject sent, token never leaks),
  request-shape variants, and the full HTTP → `GatewayEvaluationStatus`
  mapping.
- `test_simulate_gateway_routes.py` / `test_simulate_routes.py` — route-level
  tests for the two simulator modes.
- `test_console_mode.py` — the Operator/Training behavioral-equivalence suite
  described in 2.4 (navigation parity, control parity, status-code parity,
  sample-label honesty, gateway-diagnostics-state parity).
- `test_gateway_diagnostics.py`, `test_gateway_status.py`,
  `test_gateway_phase14.py` — diagnostics aggregation and connectivity-state
  tests.

No test in the current suite references anything operation-aware; there is no
prior art to reconcile.

### 2.6 Best integration location

See Section 11. Summary: extend the existing Decision Simulator with an
explicit, separately-modeled evaluation-type selection rather than a new page,
and let the existing Gateway Diagnostics view pick up operation-aware
readiness components for free (it already renders arbitrary `/ready`
component keys dynamically — see Section 11.3).

---

## 3. Authoritative Integration Boundary

```text
User
  ↓
basis-console
  ↓
basis-gateway
  ↓
basis-core
```

The console consumes `POST /v1/evaluate/operation-aware` through the existing
gateway-client boundary (`basis_console.gateway.GatewayClient`), extended with
a new method — never through a new dependency or a parallel client.

Restated for this specific surface, the console must never:

- import `basis-core`, or any `basis_core.*` symbol, directly;
- construct `OperationAwareEnforcementPoint` or call
  `OperationAwareEnforcementPoint.for_bundle()` — the existence of this public
  factory in `basis-core`'s public API proves the kernel surface is stable, it
  does **not** make it a console integration point;
- evaluate authorization locally, in preview or any other mode;
- load operation-aware policy bundles;
- reinterpret `outcome`, `evaluation_status`, `failure_reason`, or
  `disposition` — these are relayed verbatim, exactly as
  `GatewayEvaluationResult` already does for the legacy path;
- produce evaluator evidence (`AuditEvidence`, `TraceRuleEvidence`, or any
  operation-aware trace/audit artifact) — the console displays what the
  gateway returns; it never assembles evidence of its own;
- bypass `basis-gateway`;
- create a parallel operation-aware contract (its own request/response model
  independent of the gateway's documented shape).

The gateway's HTTP contract — `docs/operation-aware-endpoint.md` in
`basis-gateway`, as it exists on `main` at commit `81f72a8` — is authoritative
for console implementation. Where this plan and that document ever disagree in
a later PR, the gateway document governs and this plan must be updated, not
worked around.

---

## 4. Authoritative Request Contract

Source: `basis-gateway/docs/operation-aware-endpoint.md`, "Request shape."
`OperationAwareEvaluateRequest` uses `extra="forbid"` — any field not listed
below is rejected with `400`, never silently accepted or dropped.

### 4.1 Caller-allowed fields (any authenticated caller)

| Field | Required | User-editable in console | Validation | Operator mode | Training mode |
|---|---|---|---|---|---|
| `request_id` | No | **Not exposed in the initial milestone.** Optional per the gateway contract, but the console's existing `/v1/evaluate` integration already omits it (Section 2.2) and inventing a new console-generated identifier adds surface area with no operator benefit — the gateway defaults it to the generated `correlation_id` when absent. Revisit only if an operator need surfaces. | N/A while unexposed | Not shown | May explain that an omitted `request_id` defaults to `correlation_id` |
| `action` | **Yes** | Yes — same verb/`resource_type` composition UI the legacy simulator already uses (Section 10) | Non-empty; bare verb requires `resource_type`; composite action + `resource_type` together is rejected (`400`, "invalid double composition") | Shown, editable | Explained: gateway composes `{verb}:{resource_type}` identically to legacy `/v1/evaluate` |
| `resource_type` | No (required for a bare-verb `action`) | Yes | Must pair correctly with `action`/`resource_id` per Section 4.4 grammar | Shown, editable | Explained |
| `resource_id` | No | Yes | Local (untyped) id requires `resource_type`; typed id + `resource_type` together is rejected (`400`) | Shown, editable | Explained |
| `context` | No — **empty-only on this endpoint** | **No.** Never exposed as an editable field. | A non-empty `context` is rejected (`400`) — the public `OperationAwareDecisionRequest` has no free-form context field to map it onto. Defaults to `{}`. | Not shown as an input | Explains *why* it is absent (Section 4.5) — never shown as a control a user could fill in |

### 4.2 Trusted-producer-only fields — excluded from the initial console form

`operation_intent`, `location`, `device`, `protocol_context`,
`safety_context`, `environment_context`, `risk_context`,
`identity_evidence_reference`, `adapter_evidence_reference`.

| Field | Source | User-editable | Shown in Operator mode | Explained in Training mode |
|---|---|---|---|---|
| all nine above | Trusted operation producer only (`OPERATION_PRODUCER_SUBJECT_IDS`, matched against the gateway-verified `subject_id`) | **No, for any milestone this plan covers** | No | Yes — as a glossary/architecture explanation of what these fields are and why an ordinary console session cannot supply them |

The console's `GATEWAY_BEARER_TOKEN` identifies a human operator or an
operator-controlled service account — not `basis-adapters` or
`basis-identity`, the components this trust classification exists for. Even in
a deployment where an operator *could* configure the console's token as a
trusted producer, the console must not expose input controls for
producer-only fields: doing so would let the console originate operational
evidence (device identity, protocol context, safety context) it has no way to
attest to, which is exactly the invented-evidence failure mode Section 13
forbids. If a future, explicitly-scoped PR wants to let an operator preview
what a *trusted producer's* request would look like, that is a distinct,
clearly-labelled educational preview — not a live producer-context submission
path — and is out of scope here (Section 14).

### 4.3 Gateway-owned fields — never sent

`subject_id`, `subject_roles`, `subject_attrs`, `identity_source`,
`authority_mode`, `evaluation_time`, `correlation_id`, `evaluation_status`,
`outcome`, `failure_reason`, `disposition`, `bundle_id`, `bundle_version`,
`is_trusted_operation_producer`/`producer_trust_classification`,
`expected_policy_version`.

None of these are ever constructed or sent by the console, for the same
reason `evaluate()` never sends a subject today (Section 2.2): the gateway
derives or computes every one of them, and `extra="forbid"` rejects them with
`400` if supplied. `expected_policy_version` in particular is not accepted at
all in this rollout — the console must not build a UI control for it.

### 4.4 Action/resource grammar

Identical to `POST /v1/evaluate` — the console's existing `vocabulary.py` /
`simulator.py` composition-preview logic (Section 2.3) needs no new grammar,
only a new submission target. Composite action + `resource_type` together,
and typed `resource_id` + `resource_type` together, are both rejected
(`400`) — `simulator.build_gateway_request` already encodes and rejects both
combinations for the legacy path; PR2 reuses that logic rather than
duplicating it.

### 4.5 Why `context` is excluded

The gateway rejects a non-empty operation-aware `context` with `400` — there
is no field on the public `OperationAwareDecisionRequest` for caller-supplied
free-form context to land on. Exposing an editable `context` textarea (as the
legacy simulator does) would present operators with a control the gateway is
guaranteed to reject for any non-trivial input. Training mode may explain this
as an architecture point: unlike the legacy path, operation-aware context is
owned by trusted producers (Section 4.2), not the calling operator, and
silently discarding caller-supplied context would be unsafe — better to
reject it visibly than accept-and-ignore it.

---

## 5. Authoritative Response Contract

Source: `basis-gateway/docs/operation-aware-endpoint.md`, "Response shape,"
"Semantic outcome matrix." Fields with a `null`/absent value are omitted from
the JSON body (`exclude_none=True`); the console's typed model must treat
"absent" and "explicitly null" as the same case, not fabricate a distinction
the gateway does not make.

### 5.1 Field inventory

| Field | Contract owner | Meaning | Nullable | Closed vocabulary | Operator mode | Training mode | Redaction |
|---|---|---|---|---|---|---|---|
| `request_id` | Gateway (echoes kernel) | Always present | No | — | Shown | Shown | Safe to display |
| `correlation_id` | Gateway | Matches `X-Correlation-ID` header | Usually present, may be absent | — | Shown | Shown | Safe to display |
| `evaluation_status` | Kernel, relayed verbatim | `completed` or `failed` | No | Closed, 2 values | Shown | Shown, explained | Safe to display |
| `outcome` | Kernel, relayed verbatim | `allow` / `deny` / `not_applicable` | Present iff `evaluation_status=completed` | Closed, 3 values | Shown as the primary result | Shown, with the ALLOW/DENY/NOT_APPLICABLE distinction explained (Section 8) | Safe to display |
| `failure_reason` | Kernel, relayed verbatim | One of 6 governed values | Present iff `evaluation_status=failed` | Closed, 6 values | Shown as the primary result when present | Shown, each value explained | Safe to display |
| `bundle_id` | Kernel, relayed verbatim | Evaluated bundle identity | Null/absent only when no trustworthy typed bundle exists (Section 8.4) | — | Shown | Shown | Safe to display |
| `bundle_version` | Kernel, relayed verbatim | Evaluated bundle version | Same as `bundle_id` | — | Shown | Shown | Safe to display |
| `trace_id` | Gateway-generated | Per-evaluation-call reference | Absent when not available | — | Shown when present | Shown when present, explained as a reference (no embedded trace is fetched — Section 5.2) | Safe to display |
| `reason_code` | Kernel, relayed verbatim, never gateway-synthesized | Stable machine-readable reason | Absent when the kernel populated none | Open (not yet a closed vocabulary — Section 5.3) | Shown verbatim when present | Shown verbatim, with a glossary-style explanation if the console recognizes the code, and the raw string regardless | Safe to display |
| `explanation` | Kernel, relayed verbatim, never gateway-synthesized | Safe human-readable rendering | **Null is valid and expected** (Section 5.4) | — | Shown when present; "No additional evaluator explanation was provided." when null | Same, plus explicit note that null is a normal, complete contract state | Safe to display; must never be console-authored prose presented as this field's value |
| `disposition` | Kernel-computed, never gateway-recomputed | `allow` / `deny` | Always present | Closed, 2 values | Shown, labelled distinctly from `outcome` (Section 8.3) | Shown, with the outcome-vs-disposition distinction explained | Safe to display |
| `evaluation_trace` | Gateway, embeds kernel trace when requested | Full trace object | **Always `null` today** — this endpoint's own call site never requests trace embedding | — | Not shown (nothing to show) | Labelled explicitly as "not returned by this endpoint today," not hidden silently | N/A while always null |

### 5.2 What is *not* on this response

The operation-aware response carries no `basis_gateway.*` composition-evidence
keys the way the legacy `/v1/evaluate` response sometimes does (Section 10.3).
The legacy mechanism piggybacks on the `context` field to echo composition
evidence back to the caller; the operation-aware `context` field is
empty-only (Section 4.5), so there is no field for that evidence to ride on.
**PR2 must not assume operation-aware composition evidence appears anywhere
in the response** — it should build the typed model strictly from the fields
in Section 5.1, verified against a real gateway response or a canonical
`basis-schemas` fixture (Section 5.5), not by analogy to the legacy path.

### 5.3 `reason_code` is not yet closed

Per `basis-architecture`'s trace/audit-evidence document (Section 12), reason
codes are a *governed compatibility surface* but the vocabulary is not
finalized. The console must render `reason_code` as an opaque string in
Operator mode and may add human-readable glossary text in Training mode only
for values it can point to a `basis-schemas`-published or
`basis-architecture`-documented meaning for (the illustrative examples in that
document — `ALLOW_RULE_MATCHED`, `DENY_RULE_MATCHED`,
`NO_ALLOW_RULE_MATCHED`, etc. — are explicitly *not* a final vocabulary). An
unrecognized code must render as-is with no invented gloss.

### 5.4 Null `explanation` is a first-class contract state

Per `basis-architecture`'s evidence-provenance clarification (Section 2),
`basis-core` does not synthesize aggregate explanation prose — null is the
correct, complete value whenever no governed stage supplied one, not a
placeholder or a defect. The console:

- may display a restrained, clearly console-authored message such as "No
  additional evaluator explanation was provided" when `explanation` is null;
- must not treat null as malformed;
- must not generate a reason to fill the field;
- must not infer a policy explanation from `reason_code`, `outcome`, or
  anything else and present it as if it were the `explanation` field's value.

The same rule applies to any other optional/nullable field in Section 5.1 —
`bundle_id`/`bundle_version` absence, `trace_id` absence, `reason_code`
absence are all valid, expected states, never console-inferred.

### 5.5 Building the typed model against real shapes

PR2's response model and fixtures must be derived from the real gateway
response documented in `operation-aware-endpoint.md`'s worked examples
(Section 6 below) and, where available, from `basis-schemas`'
`operation-aware-decision-response` contract and the
`examples/operation-aware/compatibility/` canonical vectors — never from
assumption or from the legacy `GatewayEvaluationResult` shape by analogy.

---

## 6. HTTP Classification and Degraded/Error States

This is the state table `GatewayEvaluationStatus` already models for the
legacy path (Section 2.2), extended for the operation-aware endpoint's wider
and more precisely governed failure space. **A key implementation nuance the
legacy model does not have to handle:** HTTP status code alone does not
determine response body shape on this endpoint. `400`, `503`, and `500` can
each carry *either* a governed `OperationAwareEvaluateResponse` body
(`evaluation_status=failed`, with a `failure_reason`) *or* a generic
`ErrorResponse` body (`error`/`message`/`correlation_id`) for a pre-kernel
rejection. PR2's parser must distinguish these by inspecting the body for an
`evaluation_status` key, not by status code.

| State | What the console knows | What it must not infer | Operator wording | Training-mode treatment | Raw response safe to show? |
|---|---|---|---|---|---|
| Gateway not configured (`GATEWAY_BASE_URL` unset) | No call attempted | Nothing about the gateway's operation-aware capability | "No gateway configured." | Same explanation as legacy `NOT_CONFIGURED` | N/A |
| No bearer token configured | No call attempted | Nothing | "No bearer token configured; live evaluation disabled." | Same as legacy `TOKEN_MISSING` | N/A |
| Feature disabled (`OPERATION_AWARE_ENABLED` unset/false) | The route is not registered on this gateway instance; the `404` is framework-generated (Starlette/FastAPI's default not-found handling), **not** an `OperationAwareEvaluateResponse` or a governed gateway `ErrorResponse` | Must not be shown as a "denied" or "validation error" outcome; it means the capability does not exist on this deployment | "Operation-aware evaluation is not enabled on this gateway (404)." | Explain the feature gate exists and this deployment has not turned it on | Yes, subject to normal redaction — the framework may return a generic body (e.g. `{"detail": "Not Found"}`); whatever body is present must pass through the same `redact_json` path as any other response before display, the same as every other row in this table |
| Evaluator unavailable (route registered, startup incomplete/failed) | `503`, `ErrorResponse` body `{"error": "evaluator_unavailable", ...}` | Not a policy decision of any kind | "The gateway's operation-aware evaluator is not ready." | Explain this is a startup/readiness condition, link conceptually to Gateway Diagnostics (Section 11.3) | Yes |
| Authentication failure | `401` before request-body logic runs | No outcome was computed | Same wording pattern as legacy `UNAUTHORIZED` | Same | Yes |
| Missing bearer token entirely | `401` | Same as above | Same | Same | Yes |
| Request validation failure (bad shape, e.g. bare verb with no `resource_type`) | `400`, `ErrorResponse` body | Not a policy denial | "The request was rejected before evaluation (validation)." | Explain the specific grammar rule violated when identifiable | Yes |
| Caller-context rejected (non-empty `context`, or a producer-only field from an unclassified caller) | `400`, `ErrorResponse` body naming the offending field(s) | Not a policy denial; not evidence the operator "isn't allowed" to do the operation itself | "The request included a field the console does not submit and the gateway rejects from this caller." (Should not be reachable through the console's own UI at all, per Section 4 — this is a defensive case, not a normal user path.) | Explain the producer-trust boundary (Section 4.2) | Yes |
| Governed evaluation failure: `invalid_request` / `unsupported_schema_version` | `400`, `OperationAwareEvaluateResponse` body, `evaluation_status=failed` | Not a policy denial | "Evaluation could not proceed: invalid request." / "...unsupported schema version." | Explain this is a shape/version problem, distinct from a policy outcome (evaluation-semantics §14) | Yes |
| Governed evaluation failure: `invalid_policy_bundle` / `policy_validation_failure` | `503`, `OperationAwareEvaluateResponse` body | Not a policy denial; is a dependency-integrity anomaly, not an ordinary request problem | "The gateway's policy dependency is not in the state its startup check certified." | Explain this indicates a bundle problem discovered post-startup-preflight | Yes |
| Governed evaluation failure: `condition_evaluation_error` / `internal_evaluation_error` | `500`, `OperationAwareEvaluateResponse` body | Not a policy denial | "Evaluation failed unexpectedly." | Explain per-request evaluation-time failure, distinct from a bundle-level problem | Yes |
| Unexpected exception crossing the evaluator boundary | `500`, `ErrorResponse` body (ungoverned) | Not a policy denial | Generic gateway-error wording, matching legacy `GATEWAY_ERROR` | Same | Yes |
| Kernel `ALLOW` | `200`, `outcome=allow` | — | Primary result: allowed | Full flow walkthrough available | Yes |
| Kernel `DENY` | `403`, `outcome=deny` | Not the same condition as `NOT_APPLICABLE` even though HTTP status matches | Primary result: denied, **outcome shown as `deny`** | Explain deny precedence / default deny distinction (Section 8) | Yes |
| Kernel `NOT_APPLICABLE` | `403`, `outcome=not_applicable` | **Must never be relabelled `deny` anywhere in the UI**, even though the gateway's enforcement disposition collapses it with deny at the HTTP layer | Primary result shown as **"not applicable"**, not "denied" — with the HTTP 403 explained as the gateway's fail-closed enforcement choice, not the kernel's answer | Full explanation of the `NOT_APPLICABLE` vs `DENY` distinction (Section 8.2), including that bundle identity is still shown (Section 8.4) | Yes |
| Malformed/contract-invalid gateway response (e.g. unparseable JSON, unexpected shape) | Parsing failed | Nothing about outcome | "The gateway's response could not be read as expected." | Same, plus a note that this indicates a version/contract mismatch worth reporting | Only the raw bytes/text if safe (no partial trust in a partially-parsed structure) |
| Timeout / connection failure | No response received | Nothing | Same pattern as legacy `UNAVAILABLE`/timeout wording | Same | N/A |

Every row above must never be rendered as a bare "denied" in Operator mode —
this repeats the task's explicit instruction and Section 13's invariant, and
is the single most important row-by-row discipline for PR4 (shared simulator
integration, Section 12) to enforce in review, since PR4 is where this
rendering first ships for both modes simultaneously.

---

## 7. Operator and Training Modes for This Flow

Restating the existing invariant (`docs/architecture.md`, "Same application in
both modes," and `test_console_mode.py`) against this specific flow: Operator
and Training modes must use the identical gateway client method, request
model, endpoint, response model, validation, error handling, outcome
classification, evidence, and redaction. Mode selection must never change
what is submitted, which endpoint is called, how the response is parsed, how
outcomes are classified, whether an operation is allowed, or whether evidence
is considered valid. PR4 (Section 12) is required to ship this parity from
day one — the shared behavior and an initial parity check land together, so
there is no interval in which Operator and Training modes diverge for this
flow. PR6 then formalizes and expands that check into a dedicated
`test_operation_aware_mode_parity.py`-style suite, extending
`test_console_mode.py`'s existing navigation/control/status-code parity
pattern to cover every degraded state from Section 6 as well.

### 7.1 Operator mode

Concise, operational, action-oriented. Prioritizes, per Section 5.1's field
inventory: requested operation, target resource, gateway disposition, kernel
outcome, concise `reason_code`/`explanation` when present, bundle ID/version,
correlation ID, `trace_id` when present, readiness/dependency problems
(linked to Gateway Diagnostics), and a clear next action. Avoids
architectural tutorials, full raw trace-by-default (there is no trace to show
today — Section 5.1), and vocabulary explanations. A concise UI must remain
semantically accurate — in particular it must never collapse `NOT_APPLICABLE`
into "denied" merely to save space (Section 6).

**Correction — no authenticated-subject summary or live producer
classification is displayed.** `OperationAwareEvaluateResponse` (Section 5.1)
does not return the authenticated subject or the caller's trusted-producer
classification; no other supported gateway endpoint returns them to the
console today either. Accordingly:

- `basis-console` must not decode, parse, or introspect `GATEWAY_BEARER_TOKEN`
  to derive a subject — doing so would be exactly the kind of independent
  identity inference Section 3 and `basis-architecture/docs/architecture/
  basis-console.md`'s "no independent authentication" invariant forbid, and
  it would present console-computed data as if it were returned evidence.
- `basis-console` must not infer the authenticated subject from any other
  signal (configuration, prior requests, etc.).
- `basis-console` may state, generically, that the gateway authenticated the
  request when the request reaches evaluation (i.e., when a response — of any
  outcome or failure category — comes back rather than a `401`). This is a
  true statement derivable from the HTTP exchange itself, not a claim about
  *who* authenticated.
- `basis-console` must not display *who* authenticated unless and until a
  supported gateway response or endpoint actually returns that information.
  No such field exists on this endpoint today (Section 5.1 is the complete
  field inventory).
- `basis-console` must not claim a specific, live trusted-producer
  classification for the current request unless the gateway response itself
  returns one. It does not today.
- Where identity or producer detail would be useful but is not available,
  the console must label its absence as **console explanation** or **future
  capability** (Section 7.2's three-way tagging) — never render it as if it
  were **returned evidence**.

Operator mode's field list above is corrected accordingly: it does not
include an authenticated-subject summary or a live trusted-producer
classification, because the response contract does not supply either. If a
future, separately-governed gateway contract adds such a field, this plan's
Section 5.1 table must be updated first, and only then may Operator mode
display it.

### 7.2 Training mode

Educational presentation over the same real behavior, walking the flow the
task specifies:

```text
Authenticated identity
  ↓
Trusted producer classification
  ↓
Request ownership validation
  ↓
Action composition
  ↓
Resource composition
  ↓
Policy bundle applicability
  ↓
Rule evaluation and precedence
  ↓
Kernel outcome
  ↓
Gateway enforcement disposition
  ↓
Evidence and correlation
```

**This diagram describes gateway/kernel *processing stages*, not fields the
console observes in the response.** Every step corresponds to a real
boundary already documented elsewhere in this plan (Section 4.2 for producer
classification, Section 4.4 for composition, Section 8 for
applicability/outcome/disposition), and Training mode is free to explain that
each stage exists and what it does *conceptually* — but only the stages whose
outcome actually surfaces on the response (kernel outcome, gateway
disposition, bundle applicability, evidence/correlation IDs — Section 5.1)
may be rendered as **returned evidence** for a specific, real evaluation.
"Authenticated identity," "Trusted producer classification," and "Request
ownership validation" are processing stages the console can describe in the
abstract (**console explanation**) but must never illustrate with a live,
per-request value the response does not actually carry (Section 7.1's
correction). Training mode must label each piece of displayed content as one
of three categories, matching the console's existing "sample vs live vs
future" honesty discipline (`workspace.py`'s `DataMaturityItem`, Section
11.2):

- **Returned evidence** — exact data received from the gateway;
- **Console explanation** — educational copy authored by `basis-console`;
- **Future capability** — something not currently returned or implemented
  (e.g. embedded `evaluation_trace`, Section 5.1).

Training mode must never fabricate evidence, invent missing provenance,
convert a null `explanation` into generated prose, claim educational text
came from the gateway, simulate an outcome in a live workflow, expose raw
token material, weaken redaction, call a different endpoint than Operator
mode, or introduce a separate training-only authorization path. The governing
invariant, restated from the task and Section 13: **training mode educates
about the result; it does not alter, complete, or reinterpret the result.**

---

## 8. Outcome Semantics the Console Must Preserve

Distilled from `basis-architecture`'s evaluation-semantics and
evidence-provenance documents (both inspected in full for this plan) into
console-actionable rules.

### 8.1 Four distinct categories

`ALLOW`, `DENY`, `NOT_APPLICABLE`, and evaluation failure are never collapsed
into two ("worked" / "didn't work") anywhere in the UI, in either mode:

- **`ALLOW`** — an applicable bundle evaluated the request and authorized it.
- **`DENY`** — an applicable bundle evaluated the request and denied it (via
  an explicit deny rule, or via default deny when no allow rule matched —
  Section 8.2 covers why the console does not need to distinguish those two
  sub-causes itself).
- **`NOT_APPLICABLE`** — the bundle did not apply to the requested operation
  at all. **Not** equivalent to a kernel denial, even though the gateway's
  enforcement disposition ultimately prevents the operation the same way a
  deny would (Section 8.3).
- **Evaluation failure** (`evaluation_status=failed`) — the evaluator could
  not produce a valid authorization result. Not a policy decision of any
  kind; never shown alongside `outcome` (the two are mutually exclusive per
  the response contract's own invariant, Section 5.1).

### 8.2 Why `NOT_APPLICABLE` gets its own label, always

Per evaluation-semantics §5: `DENY` means "policy was evaluated and did not
grant access" (remediation: change policy); `NOT_APPLICABLE` means "no policy
bundle covers this request's domain/site/scope at all" (remediation: close a
coverage gap). These are different operational signals with different
remediations. The console must never present them identically. This applies
even though, per the semantic outcome matrix (Section 6), both produce HTTP
`403` — the HTTP status is a gateway enforcement fact, not the kernel's
answer, and the console reads `outcome`, not `http_status`, to decide what to
display as the primary result.

### 8.3 Kernel outcome vs. gateway disposition vs. HTTP classification

Three distinct facts, all present on or derivable from the response, and the
console must keep them visually and textually distinct:

1. **Kernel outcome** (`outcome`: `allow`/`deny`/`not_applicable`, or absent
   on failure) — what `basis-core` decided.
2. **Gateway disposition** (`disposition`: `allow`/`deny`) — the gateway's own
   enforcement fact, kernel-computed but gateway-surfaced; collapses
   `not_applicable` into `deny` the same way the HTTP layer does, but is a
   labelled field on the response, not an inferred one.
3. **HTTP classification** (the actual status code + which body shape
   accompanied it, Section 6) — the transport-layer fact the console's
   `GatewayClient` method translates into a typed status.

The console must never describe all three with one word ("denied") in a
context where the distinction matters (i.e., anywhere `outcome` is
`not_applicable` or `evaluation_status` is `failed`).

### 8.4 Bundle identity on `NOT_APPLICABLE`

Per the evidence-provenance clarification (Section 4 of that document,
summarized in this plan's Section 5.1): `bundle_id`/`bundle_version` are
preserved whenever a trustworthy typed bundle exists — including on
`NOT_APPLICABLE` and on a typed semantic policy-validation failure. Only a
structural bundle-parsing failure, or a failure reached before a typed bundle
can be trusted at all, permits `null`. The console must not hide bundle
identity merely because the outcome was `not_applicable`; both modes should
display policy bundle ID, version, applicability/outcome, and gateway
disposition together as one unit (per the task's explicit instruction), never
omitting the bundle fields when the response carries them.

---

## 9. Gateway-Owned vs. Console-Owned Content

| Category | Examples | Ownership |
|---|---|---|
| Relayed by kernel through gateway | `outcome`, `evaluation_status`, `failure_reason`, `bundle_id`, `bundle_version`, `reason_code`, `explanation`, `disposition` | Kernel-authoritative; gateway passes through unmodified (per `operation-aware-endpoint.md`: "copied verbatim... none is recomputed, reinterpreted, or gateway-synthesized") |
| Composed/classified by gateway | `correlation_id` (gateway-generated), `trace_id` (gateway-generated reference), HTTP status code, `request_id` default when omitted | Gateway-owned |
| Presentation-only, console-authored | "No additional evaluator explanation was provided," reason-code glossary text, the ALLOW/DENY/NOT_APPLICABLE explainer copy, the operational-flow diagram in Section 7.2, any "next step" wording | Console-owned; must be visually/structurally distinguishable from returned evidence per Section 7.2's three-category labelling |

This table is the concrete implementation of the task's "gateway-owned
additions" requirement and must be encoded directly in PR3's presentation
model (e.g. a `source: Literal["returned_evidence", "console_explanation",
"future_capability"]` tag on each renderable item), not left as an informal
convention for template authors to remember.

**Correction (post-PR3 implementation):** the table above only enumerates
response-side ownership and does not cover the request-summary values the
console itself submits. PR3's implementation surfaced that a fourth,
distinct category is required: `submitted_input`, for the exact
console-submitted `action`/`resource_type`/`resource_id`/`request_id`
values. These are never `returned_evidence` — the gateway may accept,
reject, or (for `request_id`) silently default any of them, so presenting a
submitted value as if it were a gateway confirmation would misattribute its
provenance. The shipped vocabulary is therefore
`Literal["submitted_input", "returned_evidence", "console_explanation",
"future_capability"]`; this document's illustrative three-value `Literal`
above should be read as superseded by that four-value set.

---

## 10. Legacy Evaluation Compatibility

The console currently supports `POST /v1/evaluate` end-to-end (Section 2.2–
2.3). This plan treats legacy evaluation as existing supported behavior and
operation-aware evaluation as an **additive** capability, per the task's
default framing — nothing here proposes deprecating or migrating away from
the legacy path.

### 10.1 How users select or understand the evaluation mode

The Decision Simulator gains an explicit, labelled evaluation-type selection
(e.g. a `mode` — reusing and extending the existing `preview`/`gateway` query
concept, or a clearly distinct new selector; the exact UI is a PR4 decision,
not fixed here) distinguishing "Legacy (`/v1/evaluate`)" from
"Operation-aware (`/v1/evaluate/operation-aware`)." The selection must be
visible on the page, not inferred from which fields happen to be filled in —
an operator should always be able to tell, before submitting, which contract
and endpoint a submission will use.

### 10.2 How request/response models remain distinct

New Pydantic/dataclass models are added alongside, not merged with, the
existing ones: e.g. `OperationAwareEvaluationResult` /
`OperationAwareEvaluationStatus` sitting next to `GatewayEvaluationResult` /
`GatewayEvaluationStatus` in `gateway/models.py` (or a new
`gateway/operation_aware_models.py` module if that keeps the file legible —
a PR2 implementation detail). No field is shared by casting or duck-typing
between the two; the operation-aware model is built from Section 5's field
inventory only.

### 10.3 How tests prevent field leakage between the contracts

PR2's unit tests must assert, mirroring `test_gateway_evaluate.py`'s existing
discipline: the operation-aware request body never contains `context` unless
empty/absent, never contains a subject field, and never contains any of the
nine producer-only fields (Section 4.2) regardless of form input (the console
must not even have a code path capable of setting them, but a defensive test
belongs here too, matching the "no path that could appear to let a user
impersonate an arbitrary subject" reasoning already applied to the legacy
identity boundary). A second test class should assert the operation-aware
response parser never reads or displays a `basis_gateway.*` composition-
evidence key (Section 5.2), preventing an accidental copy-paste of the legacy
`composition_evidence` property's approach.

### 10.4 Documentation labelling

`docs/architecture.md` gains a new "Phase N operation-aware integration"
section (once PR2 lands) following the existing per-phase pattern; the README
page-map table gains no new row until PR4 actually changes routing.
Both legacy and operation-aware paths are documented as current, supported,
additive capabilities — neither is marked deprecated. Migration is out of
scope (Section 14).

---

## 11. Existing Page Integration

### 11.1 Decision Simulator

**Recommendation: extend the existing simulator with an explicit evaluation-
type selection, not a dedicated new page and not a silent parameter.** This is
the smallest design that preserves clarity: it reuses the existing action/
resource-type composition UI (Section 4.4), the existing preview-vs-gateway
distinction, and the existing page's navigation slot, while keeping the two
request/response contracts structurally separate (Section 10.2–10.3). A fully
separate page would duplicate the composition form for no boundary benefit; a
silently-inferred mode (e.g. "operation-aware if certain fields are present")
would violate the "visible before submission" requirement in Section 10.1.
This plan does not design the exact markup/routing split (single `/simulate`
route branching on a form field vs. a `/simulate?type=operation-aware` query
parameter vs. sub-routes) — that is a PR4 decision (Section 12) informed by
whatever keeps `simulate.html` legible once both contracts render side by
side; PR5 then adds education on top without touching that structure.

### 11.2 Operator Workspace

The existing `Identity → Resource → Gateway → Decision → Audit` flow
(`workspace.py`) already links `/simulate` as the "Decision" stage
(`OperationalQuestion(question="Can this action be performed?", ...,
path="/simulate")`). No new workspace stage is needed; once the simulator
supports operation-aware evaluation, the existing Decision card's `purpose`
copy and the `data_maturity()` list gain an entry noting operation-aware
evaluation as an additional live capability alongside legacy evaluation —
a copy change, not a structural one.

### 11.3 Gateway Diagnostics

**Concrete finding: this already works without any code change for basic
visibility.** `diagnostics.py`'s `_extract_components()` renders *every*
key in the `/ready` response's `components` object dynamically and sorted
(Section 2.4 of `docs/architecture.md`: "arbitrary keys are shown safely").
`basis-gateway`'s four operation-aware readiness components
(`operation_aware_mode_enabled`, `operation_aware_bundle_loaded`,
`operation_aware_evaluator_initialized`,
`operation_aware_policy_semantically_valid` — `basis-gateway/docs/
readiness.md`) will appear on `/gateway` automatically the moment a live
gateway with `OPERATION_AWARE_ENABLED=true` is configured, with zero console
changes. PR6 (Section 12) may add a small, purely-presentational grouping for
these four components — mirroring the existing `_POLICY_CAPABILITY_COMPONENTS`
pattern (`_build_policy_capability`) — so an operator can see "operation-aware
capability" as a labelled unit rather than four scattered rows, but this is a
legibility improvement, not new functionality, and can ship independently of
the simulator work.

### 11.4 Training content placement

Training-mode explanations for this flow belong in the same places existing
training content lives: `partials/training_callout.html`-style per-page "What
this page teaches" callouts on `/simulate` (extended for the new mode), plus
the standard architecture explanation on `/` and `/workspace` gaining a
one-line mention of operation-aware evaluation once it exists. No new
standalone "learn operation-aware authorization" page is proposed — that
would duplicate the callout mechanism the console already has and is
explicitly a non-goal (Section 14) for this milestone.

---

## 12. Proposed Implementation Sequence

Adjusted only in framing (not scope) from the task's suggested sequence, to
reflect the findings above.

**PR 2 — Contract models and gateway client**
Typed operation-aware request/response models (Section 5, kept structurally
separate per Section 10.2); a new `GatewayClient` method (e.g.
`evaluate_operation_aware()`) built from Section 4's request contract; strict
body-shape parsing per Section 6's "status code does not determine body
shape" nuance; redaction reuse (existing `redact_json`/`redact_headers`);
fixtures derived from `operation-aware-endpoint.md`'s worked examples and, if
available in this checkout, `basis-schemas` canonical vectors; focused unit
tests mirroring `test_gateway_evaluate.py`'s structure plus the leakage tests
from Section 10.3. No UI changes.

**PR 3 — Shared operation-aware presentation model**
One shared presentation/view model consumed by both modes; the three-way
`returned_evidence` / `console_explanation` / `future_capability` tagging
from Section 9; outcome/disposition/HTTP-classification display separation
per Section 8.3; no duplicate evaluation paths. No route changes yet — this
can be developed and unit-tested against PR2's fixtures before any template
work.

**PR 4 — Shared simulator integration**
Adds the operation-aware evaluation-type selector from Section 10.1; shared
form/request handling built on PR2's models; shared gateway invocation via
PR2's `evaluate_operation_aware()`; minimal, semantically accurate result
rendering (the ALLOW/DENY/NOT_APPLICABLE/failure distinctions of Section 8
and the ownership separation of Section 9, rendered plainly — not yet
elaborated with Training-mode explanatory copy). The same controls, routes,
gateway call, response model, and status behavior are available in both
Operator and Training modes from the moment this PR lands — there is no
window in which the two modes diverge, because nothing mode-specific is
introduced yet. This PR does **not** add extensive Training-mode education;
it establishes the shared, mode-neutral behavior Section 7's parity
invariant requires, so that PR5's education has real shared behavior to sit
on top of rather than the reverse. Includes an initial parity check (both
modes render identically for the new flow) as part of this PR's own tests,
matching Section 7's requirement that no operation-aware behavior can be
mode-specific even transiently between PR4 and PR5.

**PR 5 — Training-mode educational enrichment**
Adds operation-aware architecture callouts (Section 7.2's flow diagram);
field-ownership labels (Section 9); explanations of ALLOW, DENY,
NOT_APPLICABLE, and evaluation failure (Section 8); explanation of kernel
outcome versus gateway disposition (Section 8.3); explanation of null
evidence (Section 5.4); explanation of the producer-trust and caller-context
boundaries (Sections 4.2, 4.5). Adds **explanatory markup only** — no
control, route, gateway call, data source, or runtime behavior may be added,
removed, or changed based on console mode. Every addition in this PR must be
achievable by rendering additional, clearly-labelled copy around the exact
shared behavior PR4 already shipped; if a proposed change in this PR would
require touching Operator mode's rendering path to keep the two in sync,
that is a signal the change belongs in PR4, not here.

**PR 6 — Integration hardening**
Degraded-state coverage for every row in Section 6; a
`test_operation_aware_mode_parity`-style suite that extends
`test_console_mode.py`'s pattern and formalizes/expands the parity checks PR4
introduced into full coverage (navigation, controls, status codes, and now
outcome rendering) across every degraded and success state; the optional
Gateway Diagnostics grouping from Section 11.3; documentation
(`docs/architecture.md` phase entry, README page-map update if routing
changed); a live-gateway smoke-test note in `docs/smoke-test.md`; release
preparation.

This plan does not require combining PRs or altering this order, but PR3 and
PR2 could in principle proceed with meaningful overlap (model-first, then
client) if a future implementer finds that more convenient — the sequencing
constraint that matters is "contract and shared model before any template,"
and, as of this correction, "shared Operator/Training behavior (PR4) before
Training-only education (PR5)" — not the exact PR boundary between 2 and 3.

---

## 13. Required Architectural Invariants

1. The console calls the gateway, never the kernel.
2. The console relays; it does not reevaluate.
3. The console explains; it does not invent evidence.
4. Operator and Training modes use the same runtime behavior.
5. Training mode may add education but may not add authority.
6. Null evidence remains null.
7. `NOT_APPLICABLE` is not `DENY`.
8. Evaluation failure is not a policy decision.
9. Kernel outcome and gateway disposition remain distinguishable.
10. Bundle identity is preserved on `NOT_APPLICABLE`.
11. Caller-owned context is not silently accepted or discarded — the console
    never exposes a control for a field the gateway is guaranteed to reject.
12. Gateway-owned fields remain visibly gateway-owned (Section 9's tagging).
13. Published schema contracts are not assumed to equal runtime gateway audit
    models (Section 11.3's finding does not extend to inventing an audit-event
    viewer — see Section 14).
14. Live, sample, educational, and future content remain clearly labelled.
15. Redaction applies equally in both modes.

---

## 14. Non-Goals

Excluded from this plan and from every PR in Section 12 unless a future,
separately-scoped plan revisits them:

- operation-aware UI implementation in this PR (this PR is docs-only);
- Python model implementation;
- gateway-client changes;
- new routes;
- new templates;
- new navigation;
- direct `basis-core` integration;
- policy loading;
- policy editing;
- policy-bundle authoring;
- protocol adapter integration;
- southbound operation execution;
- arbitrary context submission;
- audit-event storage;
- **gateway audit-event visualization** — `basis-gateway`'s runtime
  `GatewayAuditEvent` (`audit-model.md` §10.1: a small, gateway-owned record —
  `event_type`, `request_id`, `evaluation_status`, `outcome`,
  `failure_reason`, `audit_evidence_id`, `enforcement_action`) is confirmed,
  by direct inspection of both documents, to be **explicitly narrower** than
  the published `basis-schemas` `gateway-audit-event.yaml` contract (which
  additionally specifies a stable event identifier, a closed event type
  vocabulary, an emission timestamp, and other fields per that contract's own
  purpose statement). The console must not assume these are field-for-field
  equivalent, must not build a generic audit model by copying the schema
  YAML, and must not imply it can retrieve gateway audit events — no such
  console-facing endpoint exists today. This remains a separately-gated
  follow-up, contingent on a real gateway endpoint or a stable runtime fixture
  appearing first;
- identity-provider administration;
- authentication/login implementation;
- token acquisition or refresh;
- metrics and tracing;
- topology;
- deployment tooling;
- `basis-demo`;
- AI-generated explanations;
- autonomous recommendations;
- changes to existing authorization behavior;
- migration of the legacy `/v1/evaluate` path (Section 10 treats it as
  permanently additive within this plan's scope, not deprecated).

---

## 15. Validation

Baseline (before any file changes), all run via the repository's canonical
commands (`Makefile` targets, using a project-local virtualenv with
`pip install -e ".[dev]"`):

```text
$ git branch --show-current
docs/operation-aware-console-integration-plan

$ git status
On branch docs/operation-aware-console-integration-plan
nothing to commit, working tree clean

$ git rev-parse HEAD
672c5c4b113fa976242394d86f5454782fcf0829

$ python -m pytest -q
284 passed, 1 warning in 0.83s

$ ruff check .
All checks passed!

$ ruff format --check .
50 files already formatted

$ mypy src
Success: no issues found in 20 source files
```

Post-change validation (after adding this document; no application code
touched):

```text
$ python -m pytest -q
284 passed, 1 warning in 0.83s

$ ruff check .
All checks passed!

$ ruff format --check .
50 files already formatted

$ mypy src
Success: no issues found in 20 source files
```

No documentation-link-checking tool is configured in this repository
(`Makefile`'s `check` target is `lint format typecheck test`; no `mdlint`,
`linkcheck`, or equivalent is present). Cross-references in this document use
repository-relative paths consistent with `docs/architecture.md`'s existing
convention and were verified by direct `Read`/`Glob` inspection of every
target file during research for this plan, not by an automated tool.

No architecture-boundary test (e.g. an AST-based "no basis-core import" check,
as exists in `basis-identity`) is present in this repository today; the
"no `basis-core` dependency" invariant is currently enforced only by
`pyproject.toml`'s dependency list (Section 2.6 of `docs/architecture.md`) and
code review. Adding such a test is not proposed by this plan (not requested by
the task and not necessary to unblock PR2), but a future PR could consider
one alongside PR2's new gateway-client method, given `basis-identity`'s
precedent.

---

## 16. Open Questions

Only questions that genuinely require a decision before PR2 begins; contract
questions already answered by the current gateway/architecture/schemas
documentation are omitted.

1. **Exact console-side status-enum shape for PR2.** Section 6 establishes
   the state space; whether it is modeled as one flat closed enum (mirroring
   `GatewayEvaluationStatus`) or as a status plus a separate governed-vs-
   ungoverned-failure flag is an implementation choice PR2 should make and
   document, not one this plan needs to pre-decide — either satisfies every
   invariant in Section 13.
2. **UI mechanism for evaluation-type selection (Section 10.1).** A form
   toggle vs. a query parameter vs. sub-routes are each compatible with every
   invariant this plan states; the choice affects `simulate.html`'s
   structure, which is a PR4 concern (Section 12), not an architectural one.
3. **Whether to reuse `simulator.py`'s existing verb/`resource_type`
   vocabulary (`vocabulary.py`) unchanged for the operation-aware path, or
   introduce a second, separately-versioned mirror.** The action/resource
   grammar is identical between the two endpoints (Section 4.4), so reuse
   appears correct, but this is worth an explicit PR2 decision recorded in
   that PR's own description rather than assumed here, since `vocabulary.py`
   is already documented as a provisional bridge slated for eventual deletion
   in favor of `basis-schemas`.

None of these block starting PR2; each has a reasonable default (flat enum;
form toggle; reuse) that satisfies every invariant in Section 13 and can be
revised in review without touching this plan's contract or boundary sections.

---

## 17. Final Recommendation

This plan is ready for implementation. **Recommended scope for PR 2:**
typed operation-aware request/response models in
`basis_console.gateway.models` (or a sibling module — implementer's choice
per Open Question 3's spirit), a new `GatewayClient.evaluate_operation_aware()`
method built strictly from Section 4's request contract and Section 6's
status-classification table, and a focused unit-test suite mirroring
`test_gateway_evaluate.py` plus the field-leakage tests from Section 10.3 —
with zero route, template, or navigation changes. This keeps PR2 exactly as
narrow as PR1 (this plan) was, and gives PR3 a fully-tested contract layer to
build the shared presentation model against.

---

## Related Documents

- [`docs/architecture.md`](../architecture.md) — this repository's phase-by-
  phase architecture record; the natural home for a future "operation-aware
  integration" phase entry once PR2 lands.
- `basis-gateway/docs/operation-aware-endpoint.md` — the authoritative HTTP
  contract this plan is built against.
- `basis-gateway/docs/readiness.md` — operation-aware readiness components
  (Section 11.3).
- `basis-gateway/docs/audit-model.md` — the runtime `GatewayAuditEvent` vs.
  published-schema contrast (Section 14).
- `basis-architecture/docs/architecture/basis-console.md` — the ecosystem-
  level console responsibilities document this plan's Section 3 restates
  against the operation-aware surface specifically.
- `basis-architecture/docs/architecture/operation-aware-evaluation-semantics.md`
  — outcome semantics (Section 8).
- `basis-architecture/docs/architecture/operation-aware-trace-audit-evidence.md`
  — evidence model, redaction, console/training-mode use (Sections 7.2, 9).
- `basis-architecture/docs/architecture/operation-aware-evidence-provenance-semantics.md`
  — null-explanation and bundle-identity provenance (Sections 5.4, 8.4).
- `basis-schemas/docs/operation-aware-decision-response.md` — response
  contract detail supporting Section 5.
- `basis-schemas/docs/gateway-audit-event.md` — schema-side audit-event shape
  contrasted with the runtime shape in Section 14.
