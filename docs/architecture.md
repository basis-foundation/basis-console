# basis-console — Architecture Notes (Phases 1–3)

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

### Future live evaluation must go through `basis-gateway`

When live evaluation arrives, the previewed request will be submitted to the
gateway's authenticated evaluation endpoint (`/v1/evaluate`); the gateway
authenticates, normalizes identity, invokes `basis-core`, and assembles the
audit record, and the console renders the returned `DecisionResponse`. The flow
remains strictly one-way:

```
Operator → basis-console → basis-gateway → basis-core
```

The console must never call `/v1/evaluate`-equivalent kernel logic itself,
never import `basis-core`, and never substitute a local result when the gateway
is unreachable.

## How the console reflects these boundaries

- **No `basis-core` dependency.** `pyproject.toml` does not depend on
  `basis-core`. The sample data in `sample_data.py` is plain local dicts, not
  imported kernel models. This keeps the "console is not a kernel client"
  invariant true at the dependency level.
- **Gateway-only egress.** The console's single egress is the gateway client,
  which probes the gateway's `/health` and `/ready` endpoints (Phase 2). It
  never contacts `basis-core` and makes no authorization call to the gateway.
  `GATEWAY_BASE_URL` is configurable so no public URL is ever baked in.
- **Read-only views.** `/policies` and `/audit` render clearly labelled sample
  data. The `/simulate` request builder validates input and renders a
  normalized request preview; it performs no evaluation and makes no gateway
  call (Phase 3).
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

## Endpoints (Phases 1–3)

| Method | Path                 | Type | Purpose                                                       |
| ------ | -------------------- | ---- | ------------------------------------------------------------- |
| GET    | `/health`            | JSON | Liveness probe.                                               |
| GET    | `/ready`             | JSON | Readiness probe; includes gateway connectivity state.        |
| GET    | `/`                  | HTML | Status / landing page with gateway status panel.             |
| GET    | `/policies`          | HTML | Policy viewer placeholder (sample data, read-only).          |
| GET    | `/simulate`          | HTML | Decision-simulator request builder (optional `?example=`).   |
| POST   | `/simulate`          | HTML | Validate input + render normalized request preview (no eval).|
| GET    | `/simulate/examples` | HTML | Sample simulator scenarios (read-only).                      |
| GET    | `/audit`             | HTML | Audit viewer placeholder (sample data, read-only).           |
```
