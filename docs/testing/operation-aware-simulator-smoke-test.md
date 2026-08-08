# Manual Smoke Test — Operation-Aware Decision Simulator

A human walkthrough of the operation-aware evaluation contract on the Decision
Simulator (`GET`/`POST /simulate`, `evaluation_type=operation_aware`). This
complements — it does not replace — [`docs/smoke-test.md`](../smoke-test.md)
(which covers every page in the legacy/general run modes) and the automated
suite (`python -m pytest`, in particular `tests/test_simulate_operation_aware_routes.py`,
`tests/test_operation_aware_mode_parity.py`, and
`tests/test_gateway_evaluate_operation_aware.py`). Smoke testing is a
reproducibility check for a human reviewer, not a substitute for the
gateway/core contract tests that already cover this surface exhaustively.

## Prerequisites

- A supported Python environment: Python 3.10+, with the project installed
  (`pip install -e ".[dev]"` or `make install`) — see the repository
  [`README.md`](../../README.md) quickstart.
- No internet access is required to run the console itself.
- To exercise the **live** scenarios (7–14 below) you need a reachable
  `basis-gateway` instance with its operation-aware capability enabled
  (`OPERATION_AWARE_ENABLED` on the gateway) and, for scenarios 7–10, a loaded
  policy bundle that can produce `allow`, `deny`, and `not_applicable` for a
  request you control. Scenarios 11–14 do not require a working evaluator —
  they specifically exercise degraded gateway states.
- Required console environment variables for the live scenarios:
  - `GATEWAY_BASE_URL` — base URL of the reachable `basis-gateway` instance.
  - `GATEWAY_BEARER_TOKEN` — a verified bearer token obtained **out-of-band**
    from the gateway's configured OIDC issuer. The console issues no tokens
    and does no OIDC login itself. Do not use a real production token; use a
    disposable/test-environment credential only. **Never** commit a token to
    this file, a commit message, or a screenshot.
  - `BASIS_CONSOLE_MODE` — `operator` (default) or `training`. Scenarios below
    call out where the two modes are expected to differ (Training adds an
    educational panel only) and where they must render identically.
- Confirm the connected gateway actually exposes
  `POST /v1/evaluate/operation-aware` before scenarios 7–14: if it is not
  enabled, the console will honestly show `capability_unavailable` for every
  live submission (scenario 13 covers this case directly) rather than error.

## Local startup

From the repository root, with the dev install active:

```bash
GATEWAY_BASE_URL=http://127.0.0.1:8000 \
GATEWAY_BEARER_TOKEN="<token-obtained-out-of-band>" \
make run
```

This is the same `make run` / `uvicorn basis_console.main:app` command
documented in the [`README.md`](../../README.md) quickstart and
[`docs/smoke-test.md`](../smoke-test.md) — no new command is introduced. Omit
`GATEWAY_BASE_URL`/`GATEWAY_BEARER_TOKEN` for the preview-only scenarios (1–6,
15–17 can be exercised without a token as noted per-scenario).

Navigate to `http://127.0.0.1:8080/simulate`.

## Smoke scenarios

For each scenario, select **Operation-aware — `POST /v1/evaluate/operation-aware`**
under "Evaluation contract" unless noted otherwise.

### 1. Operator-mode page load

With `BASIS_CONSOLE_MODE` unset (or `operator`), load `/simulate`.

**Expect:** the page loads; "Legacy" is selected by default; no training
banner or "What this page teaches" callout appears; the topbar shows a quiet
`operator mode` badge.

### 2. Training-mode page load

Restart with `BASIS_CONSOLE_MODE=training`, load `/simulate`.

**Expect:** the training banner and per-page callout appear; the topbar shows
a highlighted `training mode` badge. Selecting "Operation-aware" does not yet
show the operation-aware training panel (no request has been submitted).

### 3. Legacy preview

Select "Legacy", fill in a subject, action verb, resource type, and resource
ID, and click "Build request preview".

**Expect:** unchanged from pre-existing behavior — a "Normalized request
preview" section, the exact gateway body, and the composition preview. No
gateway call is made.

### 4. Operation-aware preview

Select "Operation-aware", fill in an action verb, resource type, and resource
ID (leave subject/context blank — their fields are disabled), click "Build
request preview".

**Expect:** a "Submitted request" section tagged `submitted input`, a
`preview — not yet evaluated` badge, and a notice stating no call was made to
`basis-gateway`. No outcome, disposition, correlation ID, or trace ID appears
anywhere on the page.

### 5. Legacy-only controls disabled in operation-aware mode

With "Operation-aware" selected (server-rendered, i.e. reload the page or
submit with `evaluation_type=operation_aware`), inspect the Subject ID,
Subject type, and Context fields with your browser's dev tools / accessibility
inspector.

**Expect:** all three controls carry the HTML `disabled` attribute (not merely
a CSS class) and are visually de-emphasized. With JavaScript disabled entirely
(browser setting or dev-tools "Disable JavaScript"), reload the page with
`evaluation_type=operation_aware` already selected and confirm the fields are
still disabled — this is server-rendered, not a script-driven effect.

### 6. Crafted legacy-only field rejection

Using your browser's dev tools, re-enable one of the disabled fields (e.g.
Context) and submit a non-empty value with "Operation-aware" selected — or use
curl/httpie to POST directly:

```bash
curl -s -X POST http://127.0.0.1:8080/simulate \
  --data-urlencode "evaluation_type=operation_aware" \
  --data-urlencode "mode=preview" \
  --data-urlencode "action_verb=read" \
  --data-urlencode "resource_type=ahu" \
  --data-urlencode "context=maintenance_window=true" | grep -i "does not accept"
```

**Expect:** the response shows "Operation-aware evaluation does not accept a
context value." (or the subject-ID/subject-type equivalent), no "Submitted
request" section, and — if you also pointed this at a live gateway with
`mode=gateway` — no HTTP call was made to the gateway at all (verify via the
gateway's own access log if available).

### 7. Operation-aware live `ALLOW`

Requires a live gateway with a policy bundle that allows your test
action/resource. Select "Operation-aware", fill in the fields, click
"Evaluate through basis-gateway".

**Expect:** "Evaluation result" section with client status
`evaluation completed`, kernel outcome `allow` (styled distinctly), gateway
disposition `allow`, HTTP status `200`, and — when the bundle returns them —
bundle ID/version, reason code, and evaluator explanation, each tagged
`returned evidence`. No fabricated field appears.

### 8. Operation-aware live `DENY`

Same as above with a request your test bundle denies.

**Expect:** kernel outcome `deny`, gateway disposition `deny`, HTTP status
`403`. Bundle identity remains visible if the gateway returns it.

### 9. Operation-aware live `NOT_APPLICABLE`

Submit a request outside any loaded bundle's domain/scope.

**Expect:** kernel outcome `not_applicable`, distinctly styled from `deny`
(different CSS class, different text) even though the gateway disposition is
still `deny` and HTTP status is `403`. The page shows the console-authored
note distinguishing "no bundle applied" from "a bundle evaluated and said
no," and bundle identity remains visible if returned.

### 10. Governed evaluation failure

Trigger a governed failure (e.g. temporarily point at a gateway with an
intentionally invalid policy bundle configuration, or use a request shape the
evaluator's contract rejects, if your test environment supports staging one).
If you cannot reproduce a live governed failure, use the automated coverage in
`tests/test_gateway_evaluate_operation_aware.py` and
`tests/test_simulate_operation_aware_routes.py` (`test_governed_failure_*`) as
the substitute for this scenario, and note that substitution in your review.

**Expect:** no "Kernel outcome" or "Gateway disposition allow/deny" row (the
evaluation never completed); a "Failure reason" row with the exact
governed value (e.g. `invalid_request`) plus a one-line console-authored
explanation that it is not a policy decision.

### 11. Unauthorized / token failure

Restart the console with an intentionally wrong `GATEWAY_BEARER_TOKEN` (or
temporarily unset it while `GATEWAY_BASE_URL` stays set), submit a live
operation-aware evaluation.

**Expect (wrong token):** client status `unauthorized`; no governed fields.
**Expect (no token):** the page states gateway evaluation requires a
configured server-side bearer token and does not offer the "Evaluate through
basis-gateway" button at all.

### 12. Gateway unavailable or timeout

Stop the gateway (or point `GATEWAY_BASE_URL` at an unreachable host), submit
a live evaluation.

**Expect:** client status `unavailable`, a "could not contact gateway" or
timeout-specific note, no governed fields, HTTP status not shown (no response
was received).

### 13. Capability unavailable

Point at a running gateway that does **not** have `OPERATION_AWARE_ENABLED`
set (the legacy `/v1/evaluate` endpoint still works), submit a live
operation-aware evaluation.

**Expect:** client status `capability_unavailable`, a note that this is a
deployment capability gap, not a validation error or a denial. No governed
fields.

### 14. Contract-invalid or malformed-response behavior, where safely reproducible

This requires a gateway (or a local stand-in / proxy) that can be made to
return a body violating the documented contract (e.g. a 403 with no governed
body, or a completed evaluation missing `outcome`). If you cannot safely
stage this against a real gateway, rely on the exhaustive automated coverage
in `tests/test_gateway_evaluate_operation_aware.py` (the
`test_..._is_contract_invalid` and `test_..._is_invalid` tests) instead, and
note the substitution.

**Expect:** client status `contract_invalid`, a redacted diagnostic section
(not evaluator evidence), no governed fields fabricated to paper over the
mismatch.

### 15. Redacted diagnostics

For any generic/client failure or contract-invalid result (scenarios
11–14), expand "Redacted diagnostic response".

**Expect:** the raw response body and selected headers are shown, clearly
labelled "Diagnostic material only... never evaluator evidence." Any
`Authorization`, cookie, or token-like header/field shows `[redacted]`
instead of a real value.

### 16. No secret material in rendered output

Across every scenario above, view the page source (not just the rendered
DOM) and search for your configured `GATEWAY_BEARER_TOKEN` value.

**Expect:** the token never appears anywhere in the HTML, in any `<pre>`
block, in any HTML comment, or in server logs printed to the console's
terminal.

### 17. Operator/Training evidence parity

Repeat scenario 7 (or any live scenario) once with `BASIS_CONSOLE_MODE=operator`
and once with `BASIS_CONSOLE_MODE=training`, using the identical form
submission both times.

**Expect:** identical evaluation-type controls, identical enabled/disabled
control state, identical returned evidence (outcome, disposition, bundle,
reason code, explanation, correlation/trace IDs), and identical diagnostics.
Training mode additionally renders one extra section ("Learn: how this
operation-aware evaluation works") below the shared result — everything above
that section is byte-for-byte the same content (formatting differences from
the training banner elsewhere on the page aside).

## Expected observations summary

For each scenario, a reviewer should be able to state, without guessing:

- the kernel **outcome** (`allow` / `deny` / `not_applicable` / not
  applicable because evaluation failed or no governed response exists);
- the gateway **disposition** (`allow` / `deny` / not applicable), kept
  visually and textually distinct from outcome;
- the **HTTP status** and **client status**, distinct from both of the above;
- whether **bundle identity** and **evidence** (reason code, explanation,
  correlation ID, trace ID) are present, absent-but-valid, or not applicable;
- the **provenance label** (`submitted input` / `returned evidence` /
  `console explanation` / `future capability`) on every displayed fact;
- whether **Training-only education** appears, and that it never changes the
  request, gateway call, or result above it;
- that **no field was fabricated** — an absent value is shown as absent
  ("not provided" / "not returned"), never invented or defaulted silently.

## Limitations

- The console does not evaluate policy locally under any circumstance shown
  above; every outcome above came from a live `basis-gateway` call or is
  explicitly labelled as a preview that was never evaluated.
- The console does not expose arbitrary operation-aware context — there is no
  control for it, and a crafted non-empty value is rejected server-side
  regardless of what the browser renders.
- The console does not return the authenticated subject — live evaluation
  derives identity entirely from the configured bearer token, and no subject
  is shown anywhere on this page for operation-aware evaluation.
- The console does not return a live trusted-producer classification for the
  current request; Training mode's "producer trust" content is architectural
  education, not per-request evidence.
- No embedded evaluation trace is available today — the endpoint's contract
  currently always returns `evaluation_trace` as null/absent, and the page
  labels this a "future capability," never a live one.
- No trace-retrieval endpoint or audit-event viewer exists in this console
  today; the "Evidence and correlation" section shows only what the
  operation-aware response itself returns.
- This smoke test is a reproducibility check for a human reviewer. It does
  not replace the automated gateway/core contract tests
  (`tests/test_gateway_evaluate_operation_aware.py`), the presentation-model
  tests (`tests/test_operation_aware_presentation.py`), the mode-parity tests
  (`tests/test_operation_aware_mode_parity.py`), or the architecture-boundary
  tests (`tests/test_no_basis_core_boundary.py`,
  `tests/test_operation_aware_route_boundary.py`,
  `tests/test_operation_aware_presentation_boundary.py`,
  `tests/test_operation_aware_training_boundary.py`) — run
  `python -m pytest` for the authoritative, reproducible check.
