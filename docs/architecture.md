# basis-console — Architecture Notes (Phases 1–6)

This document records the architectural position of `basis-console` and the
boundaries this implementation must preserve. It summarizes and defers to the
authoritative ecosystem document,
[`basis-architecture/docs/architecture/basis-console.md`](https://example.invalid/basis-architecture),
which defines the console's responsibilities and design invariants for the
whole ecosystem. Where this repository and that document differ, the ecosystem
document governs.

## Position in the ecosystem

The console is the human-facing interface layer. It renders information the
authorization system already has and (in later phases) submits requests through
channels the authorization system already enforces. It does not own the logic
behind the interface.

```
Operator
  ↓
basis-console        ← this repository (interface layer)
  ↓
basis-gateway        ← authentication, enforcement, audit assembly
  ↓
basis-core           ← deterministic authorization kernel
```

The dependency direction is strict and one-way. The console depends on the
gateway; the gateway depends on the kernel. The console never reaches the kernel
directly in production.

## What the console owns

The console owns the **interface**: navigation, rendering, and operator-facing
presentation of policy state, decision outcomes, and audit records, plus the
interaction patterns (such as the decision-simulation form) operators use to
work with the system through the gateway.

## What the console must never own

These are invariants, not preferences. Phase 1 honors them by construction.

1. **No authorization evaluation.** The console contains no policy logic, role
   checks, or condition evaluation. Authorization belongs to `basis-core`. The
   simulator builds a normalized request preview; it does not decide
   anything.
2. **No independent authentication.** The console does not issue credentials,
   validate tokens, or manage sessions. Authentication belongs to
   `basis-gateway` and the identity providers it trusts. Phase 1 adds no auth.
3. **No protocol semantics.** The console parses and emits no field protocols
   (BACnet, Modbus, MQTT, OPC UA, …). That belongs to `basis-adapters`.
4. **No audit authorship.** The console displays audit records; it does not
   produce, supplement, or reinterpret them. Audit authority resides in
   `basis-core` and `basis-gateway`.
5. **No gateway bypass.** In production the console interacts with the system
   only through gateway-authenticated APIs. Direct console-to-kernel access is
   permitted only in explicitly documented local-development tooling — Phase 1
   does neither; it renders local sample data.
6. **The console is optional.** BASIS must function correctly without the
   console. Enforcement correctness, audit completeness, and authorization
   semantics must not depend on the console's presence.

## Gateway-first integration rule

The console reaches the BASIS authorization system **only through
`basis-gateway`**. This is invariant #4 ("no gateway bypass") and #5
("no kernel client") made concrete:

- The console never imports `basis-core` and never opens a connection to the
  kernel. The `basis_console.gateway` package is the single egress point, and it
  talks exclusively to the gateway's HTTP surface.
- Whatever the console eventually displays — policy state, decision history,
  audit records — it must obtain from gateway-provided endpoints. It does not
  hold an independent copy or an alternate path to that data.
- When the gateway is unreachable, the console reports the outage and surfaces
  nothing live. It must never substitute local authorization logic or cached
  decisions for live gateway data.

## Phase 2 gateway status scope

Phase 2 implements the *connectivity* slice of gateway integration and nothing
more:

- A gateway client (`basis_console.gateway.client.GatewayClient`) probes the
  gateway's operational endpoints, `/health` and `/ready`, using `httpx` with a
  configurable timeout (`GATEWAY_TIMEOUT_SECONDS`).
- The probe result is a typed `GatewayStatusReport` with a `GatewayStatus` of
  `not_configured`, `reachable`, `ready`, `unreachable`, or `error`. The client
  turns every network failure into one of these states and never raises into a
  UI route or the readiness probe.
- `GATEWAY_BASE_URL` is optional. Unset → `not_configured` and no network call.
  The console starts cleanly offline; connectivity is probed on demand (when
  `/ready` or the homepage renders), not at startup, so air-gapped deployments
  are unaffected.
- `/ready` reports `gateway_configured` and `gateway_reachable` additively. An
  unreachable or unconfigured gateway does **not** make the console unready in
  Phase 2 — a required-gateway mode is intentionally deferred until there is a
  clear need and a config flag to model it.

### Explicitly future work

Phase 2 does **not** read policy, audit, or decision data, and does **not** call
`/v1/evaluate`. The gateway does not yet expose console-facing policy/audit
query APIs; inventing them in the console would violate the gateway-first
boundary. Those endpoints, and the live policy/audit/simulator views that
consume them, are a later phase. Until then the policy and audit pages remain
read-only sample data, and (as of Phase 3) the simulator builds a request
preview but performs no evaluation.

## Phase 3 decision-simulator boundary

Phase 3 turns the simulator from a disabled placeholder into a functional
*request builder*. It is deliberately constrained to stay inside the same
invariants:

- **The console previews requests; it does not decide.** `POST /simulate`
  validates and sanitizes operator input and renders a normalized request
  *shape* as JSON. It produces no `DecisionOutcome`, applies no policy, checks
  no role, and evaluates no condition. Invariant #1 ("no authorization
  evaluation") holds: there is no decision logic anywhere in the console.
- **No gateway call, no kernel import.** Building a preview is a pure, local,
  in-memory transformation (`basis_console.simulator.build_simulation`). The
  simulator path never touches `basis_console.gateway`, never opens a network
  connection, and adds no dependency on `basis-core`. This keeps the console
  startable offline / air-gapped and preserves the gateway-first boundary.
- **No invented semantics.** The five accepted actions
  (`read`, `write`, `execute`, `browse`, `subscribe`) are the normalized verbs
  `basis-adapters` already emits; the preview reuses `basis-core`
  `DecisionRequest` field names. The console references this vocabulary rather
  than defining its own. Enforcement-path fields the gateway/kernel populate
  (`request_id`, `timestamp`, resolved `subject_roles`) are intentionally not
  fabricated, so the preview never masquerades as a completed request.

### Why the console previews requests but does not decide

The interface layer's job is to make the authorization model legible and to
help operators construct well-formed requests — not to answer them. Answering a
request requires authenticated identity, policy state, and audit assembly, all
of which live behind the gateway. A console that produced its own allow/deny
result would be a second, unaudited decision path that could disagree with the
real one. Previewing the request shape gives operators the educational value of
the simulator with none of that risk.

### Live evaluation goes through `basis-gateway` (Phase 4)

Phase 4 implements the optional live-evaluation path. The previewed request is
submitted to the gateway's authenticated `/v1/evaluate` endpoint; the gateway
authenticates the caller, derives identity from the verified token, invokes
`basis-core`, and assembles the audit record, and the console renders the
returned decision. The flow remains strictly one-way:

```
Operator → basis-console → basis-gateway → basis-core
```

The console never calls kernel logic itself, never imports `basis-core`, and
never substitutes a local result when the gateway is unreachable.

## Phase 4 gateway-backed simulation

Phase 4 adds an *optional* second simulator mode. Preview mode is unchanged and
always available; gateway-evaluation mode submits the request to the gateway and
displays the gateway's response. The boundaries:

- **The console relays the gateway's decision; it does not make or reinterpret
  it.** `GatewayClient.evaluate()` POSTs to `/v1/evaluate` and classifies the
  HTTP response into a typed `GatewayEvaluationResult`
  (success / denied / unauthorized / validation-error / unavailable /
  gateway-error). Classifying an HTTP status for display is not deciding: the
  console never computes an outcome and surfaces the gateway's `outcome`/`reason`
  verbatim. A 403 DENY/NOT_APPLICABLE is shown, never hidden.
- **No kernel import, errors never raised into the UI.** The client still never
  imports `basis-core`; every network/HTTP failure becomes a result status, so
  routes render safely. No retries are performed.
- **Gateway owns authentication and enforcement.** `/v1/evaluate` requires a
  verified `Authorization: Bearer` token. The console holds an optional
  server-side `GATEWAY_BEARER_TOKEN` and sends it only as that header; it does
  no OIDC login, no token refresh, and no browser-session storage. The console
  is not an identity provider. Live evaluation is enabled only when both a base
  URL and a token are configured; otherwise the page shows a clear configuration
  warning and stays preview-only.

### Identity boundary

The gateway derives subject identity **exclusively** from the verified Bearer
token and **rejects** caller-supplied `subject_id` / `subject_roles` (HTTP 400,
enforced by `EvaluateRequest`). Therefore the console sends **only**
`action` / `resource_id` / `context` to `/v1/evaluate` — never a subject. The
simulator's subject fields remain **preview/educational only**, and the UI
states that live evaluation's subject is the token's, not the form's. The
console deliberately exposes no subject-override, so there is no path that could
appear to let a user impersonate an arbitrary subject.

### Token handling

`GATEWAY_BEARER_TOKEN` is stored privately on the `GatewayClient`, never exposed
via a property, repr, log line, result object, or rendered page. It is used
solely to construct the `Authorization` header. The startup log reports only
whether evaluation is enabled, never the token value.

### Architectural concerns discovered

- **Action vocabulary mismatch.** *(Resolved in Phase 6 — see "Phase 6 action
  vocabulary contract" below.)* The Phase 3–5 simulator accepted the five
  normalized verbs (`read` / `write` / `execute` / `browse` / `subscribe`) as a
  *bare* action, but `basis-core`'s `DecisionRequest.action` requires the
  `{verb}:{domain}[:{object}]` form (e.g. `read:sensor:telemetry`). A bare verb
  sent to `/v1/evaluate` therefore returned a gateway `validation_failed` (400),
  which the console displayed correctly. Phase 6 aligns the simulator with the
  gateway's action naming by composing a `{verb}:{domain}` string, so the
  success path is reachable with operator-entered actions — without the console
  inventing or owning vocabulary semantics it should not own.
- **No gateway-minted dev token.** `basis-gateway` verifies tokens against a
  real OIDC issuer (JWKS); it provides no built-in dev/static token. Operators
  must obtain a token out-of-band. The console correctly treats the token as
  externally supplied configuration.

## Phase 6 action vocabulary contract

Phase 6 addresses the **action vocabulary mismatch** recorded above. It does not
create `basis-schemas`; its goal is narrower: make `basis-console` construct
gateway-compatible action strings transparently, and document the vocabulary
contract that should eventually move into `basis-schemas`.

### The mismatch (found in Phase 4/5)

`basis-core` enforces that every `DecisionRequest.action` matches
`{verb}:{domain}[:{object}]` — concretely, two or more colon-separated lowercase
segments (`basis_core.decisions.models._ACTION_RE`). The governance rules for
this naming live in
`basis-architecture/docs/architecture/action-vocabulary.md`. The Phase 3–5
simulator submitted a single bare verb (`read`) as the action, so every
gateway-backed simulation of a simulator-generated request returned HTTP 400
`validation_failed`. The console was the only component emitting bare verbs;
adapters already emit fully-qualified actions.

### What Phase 6 changes

The simulator replaces the single bare-action input with **structured action
construction**: an operator chooses an **action verb** and an **action domain**,
and the console composes the final action string (`{verb}:{domain}`, e.g.
`read:ahu`). The form surfaces the verb, the domain, the composed string, the
normalized request preview, and the gateway response when evaluated. Both preview
mode and gateway-evaluation mode use the composed string, so the simulator no
longer produces a bare action for gateway evaluation.

### The temporary local vocabulary bridge

`src/basis_console/vocabulary.py` is a **provisional, console-local mirror**: a
short verb list (`read` / `write` / `execute` / `browse` / `subscribe`), a small
starter-domain list (`ahu`, `setpoint`, `telemetry`, `device`, `schedule`,
`command`), a `compose_action` helper, and a structural validator that mirrors
`basis-core`'s action regex so a malformed composition is rejected before it
could reach the gateway. The module documents in its own docstring that it is a
temporary bridge, introduces no new verbs, and is **not** the canonical
vocabulary authority.

This respects the core architectural constraint: **the console may help users
construct valid action strings, but it must not become the authority for the
action vocabulary.** The authoritative home is
`basis-architecture/docs/architecture/action-vocabulary.md` today, and should
become `basis-schemas` in the future.

### Open architectural question (verb-set divergence)

The verb set mirrored here (`read` / `write` / `execute` / `browse` /
`subscribe`) matches what `basis-adapters` normalizes to and what earlier console
phases accepted. The governance document
(`basis-architecture/docs/architecture/action-vocabulary.md`) currently lists a
partially different controlled set — it uses `command` and `configure` (and
reserves `audit` / `enroll` / `revoke`) rather than `execute` / `browse`. The
enforced `basis-core` regex constrains only the *shape* (≥2 lowercase segments),
not the verb set, so both lists pass validation, but the divergence between the
adapter-normalized verbs and the governance verb list is a real cross-component
question. Phase 6 deliberately does **not** resolve it: reconciling the
authoritative verb set is a vocabulary-authority decision the console does not
own, and is exactly the kind of contract `basis-schemas` should settle.

## Future `basis-schemas` extraction

The Phase 6 vocabulary bridge is a stopgap. A dedicated **`basis-schemas`**
package should eventually own the shared contracts that are presently mirrored or
re-derived across repositories, so that no single component (least of all the
console) is the de-facto authority:

- the **action vocabulary** — verbs, domains, the `{verb}:{domain}[:{object}]`
  structure, reserved prefixes/namespaces, and stability/deprecation rules;
- the **request/response schemas** — `DecisionRequest` / `DecisionResponse` and
  the gateway's `EvaluateRequest` / `EvaluateResponse`;
- the **audit/event schemas** — the audit record shape and its action-vocabulary
  version field;
- the **cross-component compatibility contracts** that keep adapters, the
  gateway, the kernel, and the console mutually consistent over time.

When `basis-schemas` (or an equivalent shared contract package) lands,
`basis_console.vocabulary` should be deleted and the simulator should import the
shared definitions instead of maintaining a local copy. Until then, this
document and `basis_console.vocabulary` record the assumptions the console is
making and mark them explicitly as provisional.

## How the console reflects these boundaries

- **No `basis-core` dependency.** `pyproject.toml` does not depend on
  `basis-core`. The sample data in `sample_data.py` is plain local dicts, not
  imported kernel models. This keeps the "console is not a kernel client"
  invariant true at the dependency level.
- **Gateway-only egress.** The console's single egress is the gateway client,
  which probes `/health` and `/ready` (Phase 2) and, when explicitly configured,
  submits to `/v1/evaluate` (Phase 4). It never contacts `basis-core` and never
  evaluates locally. `GATEWAY_BASE_URL` is configurable so no public URL is ever
  baked in.
- **Read-only views.** `/policies` and `/audit` render clearly labelled sample
  data. The `/simulate` request builder validates input and renders a normalized
  request preview with no gateway call; in gateway-evaluation mode it forwards
  the request to `/v1/evaluate` and relays the gateway's decision verbatim
  without reinterpreting it (Phases 3–4).
- **Sample-data labelling.** Every data-bearing page carries a notice making
  clear the content is illustrative and that live data will come from the
  gateway. This preserves the auditability invariant: the console never presents
  placeholder data as authoritative system state.

## Deployment philosophy (preserved, not yet implemented)

The console is a deployable operational web application intended to run in
cloud, on-prem, and air-gapped environments. Phase 1 implements no deployment
tooling but preserves the constraints that make later packaging
straightforward:

- configurable bind host and port (`HOST`, `PORT`);
- configurable gateway base URL (`GATEWAY_BASE_URL`);
- static assets served locally — no CDN or web-font dependency;
- no mandatory internet access, no required SaaS services, no hardcoded cloud
  dependencies or public URLs;
- compatible with reverse proxies (Nginx, Caddy, cloud load balancers);
- suitable for future Docker, systemd/on-prem, and Kubernetes packaging.

Deployment topology must never alter authorization behavior. Because the console
performs no evaluation, where and how it is deployed cannot change what the
system evaluates or enforces.

## Graceful degradation (forward-looking)

When gateway integration arrives, an unreachable gateway must mean the console
cannot surface live state — never that it falls back to local authorization
logic or cached decisions as a substitute. The Phase 1 readiness model
(`readiness.py`) is structured to add components such as `gateway_reachable`
later without changing the contract.

## Endpoints (Phases 1–6)

| Method | Path                 | Type | Purpose                                                       |
| ------ | -------------------- | ---- | ------------------------------------------------------------- |
| GET    | `/health`            | JSON | Liveness probe.                                               |
| GET    | `/ready`             | JSON | Readiness probe; includes gateway connectivity state.        |
| GET    | `/`                  | HTML | Status / landing page with gateway status panel.             |
| GET    | `/policies`          | HTML | Policy viewer placeholder (sample data, read-only).          |
| GET    | `/simulate`          | HTML | Decision-simulator request builder (optional `?example=`).   |
| POST   | `/simulate`          | HTML | Preview mode: validate + render request shape. Gateway mode (`mode=gateway`): forward to gateway `/v1/evaluate` and display the response.|
| GET    | `/simulate/examples` | HTML | Sample simulator scenarios (read-only).                      |
| GET    | `/audit`             | HTML | Audit viewer placeholder (sample data, read-only).           |
```
