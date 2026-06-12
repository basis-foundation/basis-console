# basis-console — Architecture Notes (Phase 1)

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
   Phase 1 simulator is a non-functional placeholder; it does not decide
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

## How Phase 1 reflects these boundaries

- **No `basis-core` dependency.** `pyproject.toml` does not depend on
  `basis-core`. The sample data in `sample_data.py` is plain local dicts, not
  imported kernel models. This keeps the "console is not a kernel client"
  invariant true at the dependency level.
- **No gateway calls.** The console does not contact `GATEWAY_BASE_URL` yet. The
  value is configurable from day one so no public URL is ever baked in, but the
  network path is deferred to a later phase.
- **Read-only views.** `/policies` and `/audit` render clearly labelled sample
  data. The `/simulate` form is disabled and submits nowhere.
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

## Endpoints (Phase 1)

| Method | Path        | Type | Purpose                                              |
| ------ | ----------- | ---- | ---------------------------------------------------- |
| GET    | `/health`   | JSON | Liveness probe.                                      |
| GET    | `/ready`    | JSON | Readiness probe (per-component state).               |
| GET    | `/`         | HTML | Status / landing page.                               |
| GET    | `/policies` | HTML | Policy viewer placeholder (sample data, read-only).  |
| GET    | `/simulate` | HTML | Decision simulator placeholder (form, not wired up). |
| GET    | `/audit`    | HTML | Audit viewer placeholder (sample data, read-only).   |
```
