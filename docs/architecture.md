# basis-console — Architecture Notes (Phases 1–20)

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

> **Superseded by Phase 7.** Phase 6 had the *console* compose the `{verb}:{domain}`
> action string. Phase 7 moves composition to `basis-gateway`: the console now
> submits a bare verb plus a `resource_type` and lets the gateway compose the
> canonical action **and** resource id. See
> "[Phase 7 gateway resource composition alignment](#phase-7-gateway-resource-composition-alignment)".

The simulator replaces the single bare-action input with **structured action
construction**: an operator chooses an **action verb** and an **action domain**.
Through Phase 6 the console composed the final action string (`{verb}:{domain}`,
e.g. `read:ahu`) itself; from Phase 7 it submits the bare verb and the resource
type and the gateway composes. The form surfaces the verb, the domain, a preview
of what the gateway will compose, the normalized request preview, and the
gateway response when evaluated.

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

## Phase 7 gateway resource composition alignment

Phase 7 aligns the console's request builder with `basis-gateway`'s composition
boundary. It does not change any console invariant; it changes only the *shape*
of the request the console hands to the gateway.

### Composition belongs to the gateway

`basis-gateway` is the action/resource composition boundary. It accepts a
normalized request and composes the canonical kernel identifiers:

```
Adapters / console provide normalization inputs.
basis-gateway composes the canonical action and resource_id.
basis-core evaluates the canonical request.
```

Through Phase 6 the console pre-composed the `{verb}:{domain}` action itself and
sent an already-typed `resource_id` next to a separate, merely-descriptive
`resource_type`. That is a dual source of truth: the descriptive `resource_type`
and the `resource_id` prefix can drift. Phase 7 removes the pre-composition. The
console now submits the *normalized* inputs and lets the gateway compose.

### The two valid request shapes

- **Normalized (preferred).** `{"action": "read", "resource_type": "ahu",
  "resource_id": "rooftop-1"}` — a bare verb, the resource type, and a *local*
  (untyped) resource id. The gateway composes `action = read:ahu` and
  `resource_id = ahu:rooftop-1`. Omitting the resource id is a valid
  domain-level request (the gateway composes the action only;
  `resource_id = null`).
- **Direct (fully typed).** `{"action": "read:ahu",
  "resource_id": "ahu:rooftop-1"}` — used only when an operator intentionally
  enters a kernel-compatible request. `resource_type` is omitted and the gateway
  passes the request through unchanged.

The console never sends a `resource_type` alongside an already-typed
`resource_id` — even when the prefix matches — because that reintroduces the
dual source of truth. `basis_console.simulator.build_gateway_request` encodes
this rule and rejects the invalid combination before any call is made.

### `resource_type` is dual-purpose

In a normalized request `resource_type` is not a display label: the gateway uses
the same field to compose both the action domain (`{verb}:{resource_type}`) and
the resource-identifier prefix (`{resource_type}:{local_id}`). The console
therefore carries a single `resource_type` field rather than a separate action
domain and resource type. Whether the action domain and the resource type
*should* be the same concept is a real open question owned by
`basis-architecture` / future `basis-schemas`; the console does not resolve it,
and Phase 7 explicitly does **not** split them or resolve the resource taxonomy.

### Composition evidence display

When the gateway composes identifiers it records evidence under keys prefixed
with `basis_gateway.` (e.g. `basis_gateway.composed_resource_id`). If those keys
appear in the `/v1/evaluate` response, the simulator surfaces them in a small
"Gateway composition" panel. The console only *reads* this evidence for display;
it never sets `basis_gateway.*` keys (the gateway rejects caller-supplied ones).

### Still inside the same boundaries

Phase 7 adds no evaluation, no `basis-core` import, and no new egress. The
console submits a normalized request and relays the gateway's response verbatim.
The provisional `basis_console.vocabulary` bridge remains a console-local mirror
(now exposing `RESOURCE_TYPES` and preview-only `compose_action` /
`compose_resource_id` helpers) and is still **not** the vocabulary authority.

## Phase 8 Identity & Access Explorer

Phase 8 adds an operator-facing **Identity & Access Explorer** (`GET /identity`)
and prepares the console for a future `basis-identity` service. It adds no new
egress, no evaluation, and no `basis-core` import; it changes only what the
console *renders*. The page is render / inspect / explain only.

### What the console does and does not own here

The console renders, inspects, submits (through the gateway), and explains
identity/access context. It must **not** authenticate independently, authorize,
evaluate policy, call `basis-core` directly, become an identity provider, or
implement SAML / OIDC / SCIM / OAuth itself. These are the same invariants as
earlier phases, applied to identity:

- **No independent authentication / token verification.** The claims/token
  preview is explicitly **unverified**. Token verification (signature, issuer,
  audience, expiry) belongs to `basis-gateway`. The console holds no credentials
  and runs no login flow on this page.
- **No subject derivation for live decisions.** The normalized "verified
  subject" and the claim→subject mapping are **illustrative previews**. For live
  evaluation the gateway derives the subject from its verified token; the console
  never derives identity and never sends a subject as identity (the simulator
  linkage preserves the Phase 4 identity boundary).
- **No protocol implementation.** The console may *display* protocol data but
  implements none. Presentation models in `src/basis_console/identity.py` are
  named `IdentityPreview` / `ClaimPreview` / `SubjectPreview` / `AccessPreview`
  (plus `MappingStep` / `FutureIntegration`) and deliberately avoid
  protocol-ownership names like `OidcProvider`, `SamlService`, `ScimEngine`, or
  `OAuthServer`.

### Sample data, no invented endpoints

`basis-gateway` does not yet expose subject/identity diagnostic endpoints, so the
page renders **sample/demo data**, clearly labelled as such, and invents no
gateway endpoints. The presentation models are structured so live gateway /
`basis-identity` data can replace the samples later with minimal template change.

### The future `basis-identity` relationship

A future `basis-identity` repository will own identity lifecycle and federation.
The relationship is one-way and enforced by the gateway:

```
External IdP → basis-identity → basis-gateway → basis-core

basis-console observes and operates the flow; it owns none of it.
```

`basis-identity` will integrate with external IdPs — it will not replace them.
The Identity & Access Explorer documents this relationship and lists the future
integrations (OIDC discovery viewer, OAuth flow explorer, JWT inspector, JWKS
viewer, SAML assertion viewer, SCIM event viewer, access-review workflows) as
**non-live, future** capabilities the console will eventually display, not
implement. Phase 8 does **not** implement `basis-identity`, any identity
protocol, token verification, IdP administration, provisioning, password auth,
MFA, or access-review execution, and modifies neither `basis-gateway` nor
`basis-core`.

## Phase 9 Gateway Diagnostics

Phase 9 adds a **Gateway Diagnostics** view (`GET /gateway`) that makes the
gateway's operational state legible to an operator. It is observability only and
adds no new boundary: it changes what the console *renders*, not what it *does*.

```
basis-console observes, inspects, submits, and explains.
basis-gateway authenticates, composes, enforces, and emits evidence.
basis-core evaluates.
```

### What the diagnostics view does and does not own

- **Observe, don't configure.** The view reads gateway health/readiness; it never
  sets gateway configuration, restarts components, or mutates gateway state.
- **No authentication / authorization / evaluation.** Invariants #1–#2 hold: the
  diagnostics path runs no policy logic, makes no decision, and imports no
  `basis-core`. It does not authenticate users; the configured Bearer token is
  never displayed and is never sent to `/health` or `/ready`.
- **No gateway bypass, no invented endpoints.** The view probes only the
  gateway's **real** operational endpoints (`/health`, `/ready`) through the
  single gateway-client egress (invariant #5). The client gains `get_health()`
  and `get_ready()` probes; it adds **no** method that calls a non-existent
  endpoint. Where the gateway does not expose a datum (e.g. `policy_version` is
  returned only on `/v1/evaluate`, not on `/health` / `/ready`), the UI states
  that plainly instead of fabricating it.

### Probe result model and redaction

`GatewayClient.get_health()` / `get_ready()` each return a typed
`GatewayProbeResult` capturing the request target URL, `checked_at` timestamp,
HTTP status, parsed response JSON, selected response headers, the
`X-Correlation-ID`, and any transport error — and, like the Phase 2/4 methods,
never raise into a route. `basis_console.diagnostics.gather_gateway_diagnostics`
aggregates the two probes into the view model, deriving the connection state,
the dynamically-rendered readiness components (arbitrary keys are shown safely so
the console does not depend on a fixed component set), the evaluation/policy
capability view, and the correlation-ID entries.

Sensitive values are **redacted defensively** by
`basis_console.gateway.redaction` before they are ever stored on a result object
or rendered — header names and JSON keys containing `authorization`,
`access_token`, `refresh_token`, `id_token`, `client_secret`, `password`,
`secret`, `cookie`, `bearer`, or `api_key` have their values replaced. This is
display hygiene layered on top of the fact that the console sends no credentials
to the probed endpoints; it ensures a future gateway change or a misbehaving
proxy cannot leak a secret through the raw-response viewer.

### Three operational states

The view is designed to be useful whether the gateway is reachable or not:

- **configured + reachable** → live health/readiness data, components, capability,
  and correlation IDs;
- **configured + unreachable** → a clear connection error; the console surfaces no
  live state and never substitutes local authorization behavior;
- **not configured** → an explanation that `GATEWAY_BASE_URL` must be set.

### Future identity diagnostics

Identity-oriented diagnostics (OIDC discovery, JWKS, JWT inspection) are **not**
part of this view and will integrate through the future `basis-identity` service,
not through console-owned protocol logic. The console will *display* such data
later; it will never implement the protocols (see the Phase 8 Identity & Access
Explorer). Phase 9 deliberately excludes packet capture, proxy/traffic
inspection, an audit/resource explorer, policy editing, deployment tooling, and
any modification to `basis-gateway` or `basis-core`.

## Phase 10 Audit Explorer

Phase 10 turns the placeholder audit viewer into an **Audit Explorer**
(`GET /audit`) that makes authorization decisions and gateway evidence
understandable. It is observability only and introduces no new boundary.

```
basis-console observes, inspects, submits, and explains.
basis-core and basis-gateway produce and own audit semantics/records.
```

### What the Audit Explorer does and does not own

- **Displays evidence; does not store it.** The view renders audit *evidence*
  (decision, subject, action, resource, policy, gateway composition evidence,
  correlation). It is **not** an audit store, defines **no** audit schema, and
  does **not** replace SIEM/log infrastructure. Canonical audit records belong to
  `basis-core` and `basis-gateway`.
- **No evaluation, no `basis-core`.** Invariants #1 and #5 hold: the page makes no
  decision, runs no policy logic, and imports no `basis-core`. Outcomes shown are
  relayed sample/evaluation evidence, never computed by the console.
- **No invented endpoint, honest about live vs sample.** `basis-gateway` does not
  yet expose an audit-history endpoint, so the recent-events list is clearly
  labelled **sample** data with obviously-sample correlation IDs. The console does
  not invent a gateway audit endpoint and adds no database or persistent history.
  Live decision + composition evidence is reachable today via the Simulate page,
  which the Audit Explorer links to (and which links back).

### Presentation models and naming

Console-owned models live in `basis_console.audit`: `AuditEventPreview`,
`AuditDecisionPreview`, `AuditEvidencePreview`, and `FutureAuditIntegration`.
They are named `*Preview` and deliberately avoid canonical-ownership names
(`AuditEvent`, `CanonicalAuditRecord`, `GatewayAuditStore`) — the console is not
the authority for the audit contract. The gateway evidence panel uses the **real**
reserved `basis_gateway.*` keys (`action_composed`, `original_action`,
`composed_action`, `resource_type`, `resource_composed`, `original_resource_id`,
`composed_resource_id`) so the displayed evidence matches what the gateway
actually records; the console only reads these keys and never sets them.

### Redaction

Raw event payloads are passed through `basis_console.gateway.redaction`
(`redact_json`) before display, so credential-shaped fields (`authorization`,
`access_token`, `refresh_token`, `id_token`, `client_secret`, `password`,
`secret`, cookies, bearer tokens, API keys) are redacted defensively. The sample
data includes a credential-shaped field specifically to exercise this path; a
bearer token or raw `Authorization` header is never rendered.

### Future live audit sources

Live audit history will eventually be sourced and governed elsewhere — a
`basis-gateway` audit-history endpoint, the `basis-core` audit event schema,
`basis-schemas` audit contracts, `basis-identity` lifecycle events, and optionally
an external SIEM/log pipeline. The Audit Explorer lists these as **future,
non-live** integrations. Phase 10 implements none of them and adds no audit
storage, persistent history, canonical schema, SIEM integration, policy editing,
or resource explorer, and modifies neither `basis-gateway` nor `basis-core`.

## Phase 11 Resource Explorer

Phase 11 adds a read-only **Resource Explorer** (`GET /resources`) that makes
visible what BASIS reasons about — resources, actions, resource identifiers,
adapter sources, and gateway request shapes — so operators and contributors can
see how OT/platform resources become normalized authorization targets. It is
operational visibility only and introduces no new boundary.

```
basis-console displays resource concepts and authorization targets.
It does not discover devices or own resource inventory.
Adapters normalize. Gateway composes and catalogs. Console displays.
```

### What the Resource Explorer does and does not own

- **Displays concepts; does not own inventory.** The view renders sample
  normalized resources (display name, type, local/canonical identifier, adapter
  source, supported actions, gateway request shape, raw payload). It is **not** a
  resource inventory, device-discovery service, or topology map, and it does
  **not** mutate resources or perform CRUD.
- **No protocol contact, no adapter calls.** The console does not connect to OT
  protocols, build protocol stacks, or call adapters directly. Adapter sources are
  *labelled*, not invoked.
- **No evaluation, no `basis-core`.** Invariants #1 and #5 hold: the page makes no
  decision, runs no policy logic, and imports no `basis-core`. The "Use in
  evaluation" affordance only links/guides into the existing simulator and never
  bypasses the gateway.
- **No invented endpoint.** `basis-adapters` does not yet expose a live
  resource-inventory service and `basis-gateway` does not yet expose a
  resource-catalog endpoint, so the catalog is clearly labelled **sample** data.
  The console invents neither API.

### Identifiers and composition

The page explains the difference between the `local resource_id` (meaningful in an
adapter's source system), the `resource_type`, and the **gateway-composed**
`canonical resource_id` (`{type}:{local}`). Canonical identifiers and the example
gateway request shapes are produced as a **preview mirror** of the gateway's
composition via `basis_console.vocabulary` (`compose_action`,
`compose_resource_id`); the gateway remains the composition authority. The page
also shows the direct, already-typed request shape and does not resolve the
broader action-domain vs. resource-type question (owned by `basis-architecture` /
future `basis-schemas`).

### Presentation models and naming

Console-owned models live in `basis_console.resources`: `ResourcePreview`,
`ResourceIdentifierPreview`, `ResourceActionPreview`, `AdapterSourcePreview`,
`GatewayRequestPreview`, and `FutureResourceIntegration`. They are named
`*Preview` and deliberately avoid canonical-ownership names (`Resource`,
`CanonicalResource`, `DeviceInventory`, `ResourceStore`) — canonical resource
contracts belong to a future `basis-schemas`. The sample set spans every current
adapter family (BACnet, Modbus, OPC UA, MQTT, DNP3, IEC 61850, KNX, Niagara) plus
REST.

### Redaction

Raw resource payloads are passed through `basis_console.gateway.redaction`
(`redact_json`) before display, so credential-shaped fields (`authorization`,
`access_token`, `refresh_token`, `id_token`, `client_secret`, `password`,
`secret`, cookies, bearer tokens, API keys) are redacted defensively. The sample
data includes credential-shaped attributes specifically to exercise this path.

### Future live resource sources

Live resource data will eventually be sourced and governed elsewhere —
`basis-adapters` resource outputs, a `basis-gateway` resource catalog,
`basis-schemas` resource contracts, `basis-identity` subject/resource mapping,
`basis-deploy` site inventory, and optionally an external CMDB/OT inventory. The
Resource Explorer lists these as **future, non-live** integrations. Phase 11
implements none of them and adds no device discovery, inventory storage, topology
mapping, CRUD/mutation, policy authoring, `basis-schemas`, or deployment tooling,
and modifies none of `basis-adapters`, `basis-gateway`, or `basis-core`.

## Phase 12 Operator Workspace / Overview

Phase 12 adds a read-only **Operator Workspace / Overview** (`GET /workspace`)
that brings the existing console areas together into a single orientation landing
page. It is a **workspace/orientation** phase, not a new backend integration: it
organizes existing views rather than adding new responsibilities. The simple
homepage at `/` remains the landing page and links prominently to `/workspace`.

The workspace presents the BASIS operational model — `Identity → Resource →
Gateway → Decision → Audit` — with each stage mapped to an existing console area
(`/identity`, `/resources`, `/gateway`, `/simulate`, `/audit`), and reframes the
console around operational *questions* (Who is the subject? What resource is
targeted? Can this action be performed? Is the enforcement boundary healthy? What
evidence was recorded?) rather than repository names.

### What the workspace does and does not own

The Operator Workspace **organizes** existing console capability. It adds **no**
backend authority: it does not authenticate, authorize, evaluate, own identity
protocols, own audit semantics, own resource inventory, or call `basis-core`. It
does not change `basis-gateway`, `basis-core`, or `basis-adapters` behavior, and
it does not make any sample data live. It does not redesign the UI or replace
existing pages — every page continues to work unchanged.

### Reused diagnostics, no duplicated logic

The only live datum on the workspace is the gateway connection/readiness
snapshot, obtained by reusing the existing Gateway Diagnostics aggregator
(`gather_gateway_diagnostics` in `basis_console.diagnostics`). No new diagnostics
logic, endpoints, or data are invented; when the gateway is unconfigured or
unreachable the snapshot says so honestly and links to `/gateway` for the full
view.

### Data maturity, stated honestly

A data-maturity panel distinguishes **live/configurable** (gateway
health/readiness, gateway-backed evaluations) from **sample/explanatory**
(identity previews, resource catalog, audit history) from **future**
(`basis-identity`, live resource catalog, live audit history). This preserves the
auditability invariant: the workspace never presents sample data as live.

### Presentation models and naming

Console-owned presentation models live in `src/basis_console/workspace.py`
(`WorkspaceCard`, `OperationalQuestion`, `DataMaturityItem`, `OperatorPathStep`,
and `FlowStep`). They are named for what the console *shows* and deliberately
avoid names that would imply backend authority (`SystemState`,
`CanonicalWorkspace`, `OperationalControlPlane`). The module imports no
`basis-core`.

## Phase 14 live gateway integration polish

Phase 14 polishes the *existing* live gateway integration without changing any
boundary. It adds no new gateway endpoint, no new console page, no authentication,
and no `basis-core` import; it changes only what the console **derives from and
displays of** the same `/health`, `/ready`, and `/v1/evaluate` responses it already
used.

### What it adds (display only)

- **Latency and timeout visibility.** Each diagnostic probe records its round-trip
  `latency_ms`, and a timeout is captured distinctly (`timed_out`) from a generic
  unreachable cause. The gateway client times the call locally; it invents no
  gateway-provided latency datum.
- **Consistent connection state.** The five-state vocabulary
  (`not_configured` / `unreachable` / `error` / `reachable` / `ready`) is described
  once in `basis_console.diagnostics.connection_state_guide()` and surfaced on the
  home page, the Operator Workspace, and Gateway Diagnostics, each with the same
  label and a matching `next_step`. The diagnostics aggregator also records the
  `last_successful_health` / `last_successful_ready` timestamps (the probe's
  `checked_at` when the probe returned 200).
- **Evaluation outcome explanations.** Each `GatewayEvaluationStatus` has a stable,
  operator-facing explanation (`EVALUATION_STATE_EXPLANATIONS`, surfaced via
  `GatewayEvaluationResult.explanation`) so an unauthorized / validation /
  unavailable / timeout / denied outcome reads clearly. A missing correlation id or
  policy version is shown as "not returned by the gateway" rather than hidden.

### Boundaries preserved

The console still **observes, inspects, submits through the gateway, and explains**.
It does not evaluate, authenticate, store audit, own inventory, or call
`basis-core`. Latency is a local measurement, not a claim about gateway internals;
the explanations describe the gateway's own response and never reinterpret an
ALLOW/DENY decision. Sample/identity/resource/policy/audit pages remain clearly
labelled sample data — Phase 14 turns no sample view into fake live data.

### Gateway contract gaps (follow-ups for basis-gateway, not console)

These remain true after Phase 14 and are **not** worked around in the console:

- no console-facing policy, audit-history, identity-diagnostic, or resource-catalog
  endpoints exist, so those pages stay sample-labelled;
- `/health` and `/ready` expose no policy name/version (only `/v1/evaluate` does);
- there is no gateway-minted dev token, so `GATEWAY_BEARER_TOKEN` is supplied
  out-of-band.

If a missing capability is needed, it is filed against `basis-gateway`; the console
does not implement it.

## Phase 15 presentation modes (operator / training)

Phase 15 adds two **presentation modes** selected by `BASIS_CONSOLE_MODE`
(`operator`, the default, and `training`). This is a UX/copy concern only. It
adds no backend authority, no new page, no endpoint, no authentication, no
evaluation, and no `basis-core` import; it changes only how existing pages are
explained. The mode names the **audience** of the interface, not a deployment
environment.

### Same application in both modes (invariant)

Operator mode and training mode must always present the **same application**.
Training mode may only **add** educational content; it must never change the
application itself. Concretely, switching modes must **not**:

- move, add, or remove navigation;
- hide, add, or reorder pages or routes;
- relocate, add, or remove buttons or controls;
- change any workflow, form behavior, or submission path;
- change routing or URLs;
- expose any functionality that the other mode lacks.

The only permitted difference is **educational presentation**: in training mode a
top-level banner, per-page "What this page teaches" callouts, and a standard BASIS
architecture explanation are *added*, and the purely-pedagogical trailing
explainer panels are shown (they are hidden in the cleaner operator default).
Every route, nav link, control, and behavior is otherwise identical. This is an
intentional architectural rule for future contributors: new mode-conditional
markup may only add explanatory copy, never gate a page, control, or behavior.

### Honesty preserved in both modes

Mode is never an excuse to mislead. Sample/live/future labels, redaction notices,
and short boundary statements remain in **both** modes; operator mode is concise,
not dishonest. Training mode adds explanation without making any sample view look
live.

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

## Endpoints (Phases 1–12)

| Method | Path                 | Type | Purpose                                                       |
| ------ | -------------------- | ---- | ------------------------------------------------------------- |
| GET    | `/health`            | JSON | Liveness probe.                                               |
| GET    | `/ready`             | JSON | Readiness probe; includes gateway connectivity state.        |
| GET    | `/`                  | HTML | Status / landing page with gateway status panel; links to the workspace. |
| GET    | `/workspace`         | HTML | Operator Workspace / Overview — orientation across all areas (read-only). |
| GET    | `/policies`          | HTML | Policy viewer placeholder (sample data, read-only).          |
| GET    | `/simulate`          | HTML | Decision-simulator request builder (optional `?example=`).   |
| POST   | `/simulate`          | HTML | Two independent axes: submission (`mode=preview` validates + renders a request-shape preview; `mode=gateway` submits live) and evaluation contract (`evaluation_type=legacy`, default, targets `/v1/evaluate`; `evaluation_type=operation_aware` targets `/v1/evaluate/operation-aware` via the shared presentation model — Phase 18). |
| GET    | `/simulate/examples` | HTML | Sample simulator scenarios (read-only).                      |
| GET    | `/audit`             | HTML | Audit Explorer — decision events + gateway evidence (sample data, read-only). |
| GET    | `/identity`          | HTML | Identity & Access Explorer (sample data, read-only).        |
| GET    | `/resources`         | HTML | Resource Explorer — sample resources, identifiers, request shapes (read-only). |
| GET    | `/gateway`           | HTML | Gateway Diagnostics — live gateway health/readiness (read-only). |
```

## Phase 16 operation-aware contract and gateway-client layer

Phase 16 adds a second, structurally separate gateway-client capability:
`GatewayClient.evaluate_operation_aware()`, which submits to
`basis-gateway`'s `POST /v1/evaluate/operation-aware` and relays the kernel's
governed operation-aware result verbatim. **This phase adds an internal
client capability only** — no route, template, navigation entry, simulator
control, or other user-visible surface calls it. Operator mode and Training
mode are both completely unaffected; neither exposes operation-aware
evaluation yet. The console still calls only the gateway, never
`basis-core` directly — this phase adds no `basis-core` import and no
`basis-core` dependency (see the new `tests/test_no_basis_core_boundary.py`,
the first mechanical enforcement of that invariant in this repository). The
legacy `POST /v1/evaluate` client (`evaluate()`, Phase 4) is untouched and
remains fully supported; the two paths share only the `GatewayClient` class,
`redact_headers`/`redact_json`, and the console's configured
`GATEWAY_BASE_URL`/`GATEWAY_BEARER_TOKEN` — no request, response, or result
model is shared or interchangeable between them.

### New module: `gateway/operation_aware_models.py`

Kept as a sibling of `gateway/models.py`, not an extension of it, so the
legacy and operation-aware contracts can never be intertwined or cast into
one another (the operation-aware console integration plan's §10.2/§16
"Module Organization" — Option B). It defines:

- `OperationAwareEvaluationRequest` — the complete, closed set of fields an
  ordinary console session may send (`action`, `resource_type`,
  `resource_id`, `request_id`). There is no field for a subject, for
  arbitrary `context`, or for any of the nine trusted-producer-only fields
  (`operation_intent`, `location`, `device`, `protocol_context`,
  `safety_context`, `environment_context`, `risk_context`,
  `identity_evidence_reference`, `adapter_evidence_reference`) — the type
  surface makes them impossible to set, not merely unvalidated. Frozen, so a
  caller-held request object can never be mutated.
- Closed-vocabulary enums matching the gateway's own closed fields exactly:
  `OperationAwareEvaluationState` (`completed`/`failed`),
  `OperationAwareOutcome` (`allow`/`deny`/`not_applicable`),
  `OperationAwareFailureReason` (the six governed failure reasons), and
  `OperationAwareDisposition` (`allow`/`deny`). `reason_code` stays a plain
  `str | None` — the gateway contract documents it as not yet a closed
  vocabulary.
- `OperationAwareEvaluationResponse` — the fully-parsed, contract-valid
  governed response body. Deliberately has no `evaluation_trace` field: the
  endpoint's current contract returns that field only as `null`/absent, so
  there is nothing typed to carry; a response asserting a non-null trace is
  treated as a contract violation, not modeled as a loosely-typed trace
  viewer.
- `OperationAwareEvaluationStatus` — the client-level classification of a
  call (`NOT_CONFIGURED`, `TOKEN_MISSING`, `UNAUTHORIZED`,
  `CAPABILITY_UNAVAILABLE`, `REQUEST_REJECTED`, `EVALUATOR_UNAVAILABLE`,
  `EVALUATION_COMPLETED`, `EVALUATION_FAILED`, `CONTRACT_INVALID`,
  `UNAVAILABLE`, `GATEWAY_ERROR`). This is a different axis from the
  kernel's own `evaluation_status` field: kernel `DENY` and
  `NOT_APPLICABLE` are both `EVALUATION_COMPLETED` at this level — they are
  already distinguished precisely by the parsed `response.outcome`, so the
  status enum does not duplicate that distinction.
- `OperationAwareEvaluationResult` — the typed result wrapper, structurally
  distinct from the legacy `GatewayEvaluationResult` (no shared fields, no
  casting between them). Carries the redacted raw body and redacted response
  headers alongside the typed `response`, for later raw-display use.

### Strict, shape-driven response parsing

Per the endpoint contract, HTTP status code alone does not determine response
body shape: `400`, `403`, `500`, and `503` can each carry either a governed
`OperationAwareEvaluateResponse` body or a generic, ungoverned
`ErrorResponse`/framework body. `GatewayClient._interpret_operation_aware`
distinguishes the two by inspecting the body for an `evaluation_status` key,
never by status code — a governed body is parsed and trusted regardless of
which status carried it (including a governed failure on `400`/`503`/`500`),
and a body that looks governed but violates a documented invariant (missing
required field, unknown closed-vocabulary value, contradictory
outcome/failure-reason/disposition combination, a non-null trace) is
classified `CONTRACT_INVALID` rather than partially trusted. An HTTP `403`
carrying no governed body is also `CONTRACT_INVALID` — this endpoint's
contract always returns a governed body on `403`. Every other HTTP status is
classified generically (`400`→`REQUEST_REJECTED`, `401`→`UNAUTHORIZED`,
`404`→`CAPABILITY_UNAVAILABLE`, `503`→`EVALUATOR_UNAVAILABLE`,
`500`→`GATEWAY_ERROR`, anything else→`GATEWAY_ERROR`), matching the
`_interpret_evaluation` precedent already established for the legacy path.

### Boundaries preserved

The console still calls the gateway, never the kernel; relays governed
results without reevaluating or reinterpreting them; and fabricates no
evidence, explanation, reason code, or trace the gateway did not return. Null
`explanation`/absent `reason_code`/absent `bundle_id`/`bundle_version` are
preserved as first-class valid states, never synthesized. `NOT_APPLICABLE` is
never relabelled `deny`, even though both share HTTP `403` and
`disposition=deny` on this endpoint. Redaction reuses the existing
`redact_headers`/`redact_json` helpers unchanged — no new redaction path was
introduced. The configured Bearer token is never present in any request body,
result field, or `repr`.

### What Phase 16 does not do

No route, no template, no navigation entry, no simulator control, no
Operator-mode or Training-mode rendering, no presentation/view model, no
evaluation-type selector, and no live-gateway integration test. Operation-aware
evaluation remains entirely unreachable from the console's UI until a later
phase builds the shared presentation model and wires it into `/simulate` —
see `docs/implementation/operation-aware-console-integration-plan.md`, PRs
3–6, for that sequence.

## Phase 17 operation-aware presentation model

Phase 17 (integration-plan PR 3) adds one new module,
`operation_aware_presentation.py`, containing a shared, mode-independent
presentation model consumed identically by both Operator and Training modes
once a later phase wires it into `/simulate`. **This phase adds a pure,
unit-tested transformation only** — no route, template, navigation entry, or
simulator control calls it yet; Operator mode and Training mode remain
completely unaffected. The module performs no gateway call and no I/O of any
kind: `build_operation_aware_presentation(request, result)` consumes PR 2's
already-typed, already-redacted `OperationAwareEvaluationRequest` /
`OperationAwareEvaluationResult` and returns one frozen
`OperationAwarePresentation` object.

### New module: `operation_aware_presentation.py`

Kept as a flat, top-level module — consistent with the repository's existing
presentation-oriented modules (`workspace.py`, `diagnostics.py`,
`simulator.py`) — rather than introducing a new `presentation` package for a
single module. It defines:

- `ContentSource` — the closed provenance vocabulary the integration plan's
  §9 requires be encoded directly rather than left as an informal template
  convention. Four values, not three: implementation surfaced a distinction
  the plan's §9 table did not separate out — the exact values the console
  *submitted* in its request are not gateway evidence, even though both are
  equally exact and equally never console-invented. Collapsing them would let
  a submitted `resource_id` or `action` be presented as if the gateway had
  confirmed or returned it, when the gateway may in fact reject it, ignore
  it, or (for `request_id`) silently default it. The four values:
  `SUBMITTED_INPUT` (an exact value from the typed request — used only for
  `RequestSummarySection`'s four fields), `RETURNED_EVIDENCE` (an exact value
  from the typed gateway result), `CONSOLE_EXPLANATION`
  (`basis-console`-authored prose, including `OperationAwareEvaluationResult
  .detail`, which is itself documented as a console-side note), and
  `FUTURE_CAPABILITY` (used only for the not-yet-returned embedded
  `evaluation_trace`).
- `PresentationContentItem` — a frozen, narrowly-typed content unit (`key`,
  `label`, `value`, `source`, `applicable`, `present`, `description`)
  replacing what could otherwise have been an unbounded dict. `applicable`
  and `present` together distinguish three states a template must render
  differently: the concept doesn't exist in this evaluation state at all
  (`applicable=False`), it exists and was validly returned as null/absent
  (`applicable=True, present=False`), or a real value is available
  (`applicable=True, present=True`).
- Five typed sections — `RequestSummarySection`, `EvaluationResultSection`,
  `PolicyBundleSection`, `EvidenceSection`, `TransportSection` — plus
  `RedactedDiagnostics` (already-redacted diagnostic material for
  generic/contract-invalid results, retained without reinterpretation) and
  the top-level `OperationAwarePresentation` that groups them, alongside a
  small tuple of `identity_processing_notes`.
- `build_operation_aware_presentation(request, result)` — the single pure
  builder. Raises `PresentationBuildError` only when `result.status` and
  `result.response`'s presence disagree with
  `OperationAwareEvaluationResult`'s own documented invariant — a condition
  a real gateway-client result can never produce, so this is a contract-drift
  guard, not a data case to render.

### Semantic preservation

`ALLOW`/`DENY`/`NOT_APPLICABLE` are read from `response.outcome` and rendered
as three distinct values, never collapsed into one. `NOT_APPLICABLE` is never
relabelled `deny`: its `PolicyBundleSection.applicability_note` (tagged
`CONSOLE_EXPLANATION`) explains the fail-closed HTTP/disposition behavior
without altering the preserved `outcome` value, and bundle identity remains
visible exactly as on `ALLOW`/`DENY`. A governed evaluation failure
(`evaluation_status=failed`) leaves `outcome` `applicable=False` and is never
displayed as a policy decision — verified for every one of the six governed
failure reasons, including on HTTP `400`/`503`/`500`, and distinguished by
test from the corresponding *generic* pre-kernel rejection on the same HTTP
status (`REQUEST_REJECTED`/`EVALUATOR_UNAVAILABLE`/`GATEWAY_ERROR`), which
carries no governed fields at all. Null `explanation`, absent `reason_code`,
and absent `bundle_id`/`bundle_version`/`trace_id`/`correlation_id` are all
preserved as first-class `applicable=True, present=False` states — never
synthesized, never treated as malformed.

### Boundaries preserved

No `basis-core` import (covered by the existing repository-wide
`test_no_basis_core_boundary.py` sweep, which now also covers this file, plus
a file-scoped reassertion in the new `test_operation_aware_presentation_boundary.py`).
No gateway HTTP call — the module never imports `GatewayClient` or `httpx`.
No subject or producer-trust inference — the model has no subject field
anywhere, and its one identity-related note (`identity_processing_notes`,
shown only when a governed response exists) is tagged `CONSOLE_EXPLANATION`
and states plainly that it describes a gateway processing stage, not a
per-request result. No console-mode dependency: the builder takes exactly
`(request, result)`, no presentation dataclass has a mode-shaped field, and
the module imports nothing from `basis_console.config`.

### What Phase 17 does not do

No route, no template, no navigation entry, no simulator control, no
Operator-mode or Training-mode rendering decision, no evaluation-type
selector, and no live-gateway integration test. Operation-aware evaluation
remains entirely unreachable from the console's UI until PR 4 wires this
model into `/simulate` — see
`docs/implementation/operation-aware-console-integration-plan.md`, PRs 4–6,
for that sequence.

## Phase 18 shared operation-aware simulator integration

Phase 18 (integration-plan PR 4) wires PR 2's gateway-client layer and PR 3's
presentation model into the existing Decision Simulator (`/simulate`),
completing the first end-to-end operation-aware evaluation path reachable
from the console's UI. It adds no new route, no second `GatewayClient`, and
no second `/simulate` implementation — the existing GET/POST handlers gain
one new, explicit axis alongside the existing preview/gateway submission
axis, and the same code path renders identically in Operator and Training
modes from this phase onward. **This phase does not add Training-mode
educational enrichment** — that remains PR 5 scope; every Operator/Training
difference here is limited to the pre-existing training banner/callout
mechanism, never to the operation-aware controls, request, gateway call, or
result content.

### Two independent axes

The simulator now has two independent selections, never conflated:

- **Submission behavior** (unchanged): `mode=preview` (default) / `mode=gateway`.
- **Evaluation contract** (new): `evaluation_type=legacy` (default,
  absent-compatible) / `evaluation_type=operation_aware`, added as
  `simulator.EvaluationType`, a closed `str` `Enum` consistent with the
  repository's existing operation-aware enum style
  (`operation_aware_models.py`). `simulator.parse_evaluation_type()` treats an
  absent or blank field as legacy (so every link, bookmark, and test that
  predates this field is unaffected) and a present-but-unrecognized value as
  an explicit validation failure — never a silent fallback and never a
  gateway call.

### Operation-aware request building (`simulator.py`)

`simulator.build_operation_aware_simulation()` is a new, pure, I/O-free
sibling of `build_simulation()` that builds a typed
`OperationAwareEvaluationRequest`. It reuses — rather than reimplements — the
legacy path's action-verb/resource-type vocabulary and
`build_gateway_request()`'s composition grammar (Section 4.4 of the
integration plan: the two endpoints' grammar is identical), and reads only
`action_verb` / `resource_type` / `resource_id` from the submitted form. A
non-empty value for any field in the explicit, known
`OPERATION_AWARE_LEGACY_ONLY_FIELDS` allowlist (`context`, `subject_id`,
`subject_type` — never a rule that rejects arbitrary/unknown POST keys) is
rejected unconditionally and checked first, independent of whatever the
browser form renders, disables, or a dev-tools edit re-enables — the
operation-aware endpoint has no field for caller-supplied context (Section
4.5) or for a caller-supplied subject (the gateway derives identity
exclusively from the verified Bearer token), so this is enforced
server-side regardless of client behavior, with every offending field
reported (not just the first). No caller-supplied `request_id`, subject
field, or trusted-producer-only field (`location`,
`device`, `protocol_context`, `safety_context`, `environment_context`,
`risk_context`, `operation_intent`, `identity_evidence_reference`,
`adapter_evidence_reference`) is ever read from the form or settable on the
built request — the typed request model has no field for any of them, so an
unrestricted form dictionary cannot smuggle one through.

This module now imports the frozen `OperationAwareEvaluationRequest`
dataclass from `basis_console.gateway.operation_aware_models` — still no I/O
capability and no network code, only the typed model needed to build the
value `simulator.py` returns.

### Route integration (`ui/views.py`)

`POST /simulate` parses `evaluation_type` once and branches:

- **Legacy** (`evaluation_type=legacy` or absent): the existing Phase 4/6
  code path, byte-for-byte unchanged.
- **Operation-aware, preview**: validates and builds the typed request via
  `build_operation_aware_simulation()`, then renders it as a request-shape
  preview only. No `GatewayClient` call is made, and no
  `OperationAwareEvaluationResult` — real or fabricated — is ever
  constructed for a preview.
- **Operation-aware, gateway**: calls
  `GatewayClient.evaluate_operation_aware()` exactly once with the built
  request, passes the request and the returned typed result straight into
  `build_operation_aware_presentation()` unchanged, and renders the returned
  `OperationAwarePresentation`. The route never parses raw gateway JSON,
  never imports `httpx`, and never reconstructs outcome/disposition/failure
  semantics itself — those decisions live in `operation_aware_presentation.py`
  and are consumed here only through its already-built content items.

An invalid `evaluation_type` value is rejected before either builder runs:
no gateway call, no local evaluation, whatever was submitted is echoed back
so the form can be corrected.

### Template integration (`simulate.html`)

The existing `/simulate` form gains an explicit, always-visible
`evaluation_type` radio selection above the shared action/resource controls.
Design decision: rather than a second page or a fully separate form, the
legacy-only subject/context controls are wrapped in server-rendered
`<fieldset>` containers (`#legacy-only-fields`, `#legacy-only-context`, not
plain `<div>`s) whose visibility **and enabled state** are both driven by the
currently-rendered `evaluation_type`. When operation-aware is selected, the
server renders each fieldset `disabled` (which, per the HTML `<fieldset
disabled>` semantics, disables every descendant control in one step — a
disabled control is never included in a submitted form's data, unlike a
merely CSS-hidden one) as well as visually hidden (`class="is-hidden"`); when
legacy is selected, neither attribute is rendered and the controls are fully
enabled. A small progressive-enhancement script toggles both `classList` and
each fieldset's `.disabled` property together immediately on radio change,
for a same-page feel without a reload, and without ever clearing a user's
already-typed legacy values. **Correctness never depends on the browser or
the script**: `simulator.build_operation_aware_simulation()` unconditionally
rejects a non-empty value for any of `simulator.OPERATION_AWARE_LEGACY_ONLY_FIELDS`
(`context`, `subject_id`, `subject_type` — an explicit known-field allowlist,
never a rule that rejects arbitrary unknown POST keys) regardless of what the
DOM shows, disables, or a browser dev-tools edit re-enables — this is the
actual enforcement boundary, and a crafted non-empty value for any of the
three is rejected with the established console validation response (no
gateway call, no request built, no identity inferred) on both preview and
gateway submissions. The legacy "Normalized request preview" and "Gateway
evaluation" sections are now gated to `evaluation_type == "legacy"`; a new,
parallel "Operation-aware evaluation" section renders only for
`evaluation_type == "operation_aware"`, reusing the existing `.gateway-eval`/
`.gw-response`/`.kv`/`.badge`/`.tag`/`.outcome` styling (one new rule,
`.outcome.not_applicable`, keeps that outcome visually distinct from `deny`).

### Minimal, semantically accurate rendering

The operation-aware section renders, strictly from `OperationAwarePresentation`,
without reevaluating or recomputing any of it:

- **Submitted request** — action / resource type / resource ID, explicitly
  tagged `submitted input` and, in preview mode, labelled "preview — not yet
  evaluated." Never labelled as returned evidence.
- **Evaluation result** (gateway mode only) — client status, HTTP status,
  kernel evaluation status, kernel outcome, gateway disposition, failure
  reason (plus its one-line console-authored note), reason code, and
  evaluator explanation (or, when null, the console-authored "No additional
  evaluator explanation was provided." note) — each rendered only when
  `PresentationContentItem.applicable`, and distinguished from a real value
  by `.present` rather than by blank space.
- **Policy bundle** — bundle ID/version, preserved on `NOT_APPLICABLE` and on
  a governed failure exactly as on `ALLOW`/`DENY`, plus the
  `NOT_APPLICABLE`-only applicability note explaining the fail-closed HTTP
  behavior without ever relabelling the outcome itself.
- **Evidence and correlation** — request ID (returned), correlation ID,
  trace ID, and the `evaluation_trace` future-capability row (labelled
  `future capability`, never implying a trace exists today).
- **Transport/diagnostics** — client-level status explanation, error
  code/message, console diagnostic note, and — only when no governed
  response exists — the already-redacted raw diagnostic body/headers,
  explicitly labelled as diagnostic material, never evaluator evidence.

Provenance is made visible through text, not color alone: `submitted input`
and `returned evidence` tags reuse the existing `.tag` badge style, and every
console-authored line is prefixed "Console note:" in the rendered HTML — so
the four-category distinction from PR 3 survives into the rendered page
without a new legend beyond the section's own two introductory notices.

### Mode independence

Operator and Training modes call the identical route function, build the
identical `OperationAwareEvaluationRequest`, call
`GatewayClient.evaluate_operation_aware()` the same single time, and render
the identical `OperationAwarePresentation` — nothing in `views.py` or
`simulator.py` branches on `console_mode`/`is_training_mode` for this flow.
`tests/test_operation_aware_mode_parity.py` extends `test_console_mode.py`'s
existing parity discipline to prove this for the selector controls, the
submitted request body, and one live outcome from each response category
(allow, not_applicable, governed failure, generic/transport failure).

### Legacy compatibility

Every existing simulator behavior is unchanged: the default GET, a POST
without an `evaluation_type` field, legacy preview, legacy gateway
evaluation, and legacy response rendering all behave exactly as before Phase
18, verified by the full pre-existing test suite passing unmodified alongside
the new tests.

### What Phase 18 does not do

No Training-mode educational enrichment beyond the pre-existing banner/callout
mechanism (PR 5), no caller-editable `request_id`, no arbitrary
operation-aware context, no trusted-producer-only field exposure, no trace
viewer, no audit-event viewer, no policy editing, no schema/gateway/adapter
changes, and no change to legacy `/v1/evaluate` behavior or its default
status.

## Phase 19 operation-aware Training-mode educational enrichment

Phase 19 (integration-plan PR 5) adds Training-only educational content
around the operation-aware Decision Simulator flow Phase 18 already shipped
for both modes. **This phase adds explanatory markup only** — no control,
form field, request construction, validation rule, gateway call, endpoint
selection, response parsing, presentation-model field, authorization
behavior, returned evidence, or page status code changes. Operator mode is
byte-for-byte unaffected: the new markup is never rendered outside Training
mode, and the shared route, request, gateway-client call, and
`OperationAwarePresentation` object Phase 18 built remain exactly as before.

### New module: `operation_aware_training.py`

A flat, top-level module of static, console-authored teaching content —
consistent with `operation_aware_presentation.py`'s own precedent of one
focused module per concern rather than a `presentation`/`training` package.
Everything in it is literal data built once at import time:

- Ten `EcosystemStage` entries walking the conceptual operation-aware flow
  (submitted request → gateway authentication → producer trust/field-ownership
  validation → action/resource composition → policy-bundle applicability →
  rule evaluation and precedence → kernel outcome → enforcement
  disposition/HTTP classification → correlation and evidence → console
  presentation), each tagged with its owning component and whether its result
  is actually observable on the current gateway response — explicitly false
  for authenticated-subject and live producer-trust classification, per the
  integration plan's §7.1 correction.
- A four-entry `PROVENANCE_LEGEND` restating `ContentSource`'s vocabulary in
  prose, and a six-entry `AUTHORIZATION_VOCABULARY` glossary (evaluation
  status, kernel outcome, failure reason, enforcement disposition, HTTP
  status, client status) with an explicit "never collapse these" warning.
- `OUTCOME_TRAINING_COPY` and `FAILURE_REASON_TRAINING_COPY` — string-keyed
  (by the same `.value` strings `PresentationContentItem` already carries)
  dictionaries built from an enum-keyed private mapping asserted exhaustive
  over `OperationAwareOutcome`/`OperationAwareFailureReason` at import time,
  so a future enum addition fails loudly rather than rendering silently
  incomplete copy. `GOVERNED_FAILURE_INTRO`/`GENERIC_FAILURE_INTRO` cover the
  two remaining Section-4 categories (governed failure, generic/client
  failure), and `GOVERNED_CLIENT_STATUS_VALUES`/`GENERIC_CLIENT_STATUS_VALUES`
  partition `OperationAwareEvaluationStatus` exhaustively by construction.
- Null/absent-evidence guidance (explanation, `reason_code`, bundle identity,
  `trace_id`), context/producer-trust boundary points, correlation/trace/
  audit-evidence identifier education, and preview-mode education points —
  each a plain string or string tuple, never a function.
- `TRAINING_CONTENT` — one frozen `OperationAwareTrainingContent` aggregate
  gathering all of the above, attached to the simulator's template context
  unconditionally (`ui/views.py`) exactly like `is_training_mode` itself; only
  the template's own Training-mode gate decides whether any of it renders.

The module declares no functions at all (enforced by
`tests/test_operation_aware_training_boundary.py`): every "selection" of
which static entry applies to the current result is a dictionary lookup or an
`.applicable`/`.present` check performed in the template against a value
`operation_aware_presentation.build_operation_aware_presentation()` already
computed — never a second, independently-computed decision. It imports
nothing from `basis_console.config`, `basis_console.gateway.client`,
`httpx`, `fastapi`, or `jinja2`, matches `operation_aware_presentation.py`'s
own "no I/O, no mode argument" discipline, and is never given a request,
response, or console-mode value to act on.

### New partial: `partials/operation_aware_training.html`

Included only from `simulate.html`'s existing `evaluation_type ==
"operation_aware"` branch, immediately before that section's closing tag, so
it shares the surrounding context (`oa_presentation`, `oa_preview_only`,
`oa_request_summary`) without any new context-passing mechanism. Reuses the
existing `.training-callout` container class and the repository's established
`<details>`/`<summary>`/`table.grid`/`dl.kv` conventions rather than
introducing new visual patterns; the only new CSS is spacing rules for the
added subsections (`.oa-training-section`), added to the existing
`style.css`, not a redesign.

Renders, only when `is_training_mode`:

- the ten-stage ecosystem-flow table plus the identity/producer processing
  boundary note (Required Section 1);
- the provenance legend (Required Section 2);
- the authorization vocabulary glossary (Required Section 3);
- preview-only education when `oa_preview_only` is set, and otherwise
  (`oa_presentation` present) exactly one of the ALLOW / DENY / NOT_APPLICABLE
  / governed-failure / generic-failure explanations, selected by a lookup
  keyed on `kernel_evaluation_status`/`outcome`/`failure_reason`'s
  already-computed `.value` — never a re-derived decision (Required Section
  4, enforced by `test_partial_does_not_reconstruct_outcome_disposition_or_failure_reason_logic`);
- only the null/absent-evidence guidance sentences relevant to the actual
  result, never all four at once (Required Section 5);
- the context/producer-trust boundary explanation, shown unconditionally
  whenever the operation-aware section renders in Training mode, since it is
  architectural education rather than per-request evidence (Required Section
  6);
- correlation/trace/evaluation-trace/audit-evidence identifier education,
  shown alongside a live result (Required Section 7).

### Security and evidence discipline

No bearer token, `Authorization` header, or gateway configuration value is
ever referenced by the partial or the content module (enforced by
`test_partial_never_references_tokens_or_configuration`). No new gateway
call, gateway-client method, or route is introduced — the route still calls
`GatewayClient.evaluate_operation_aware()` exactly once per submission
(`test_views_module_calls_evaluate_operation_aware_exactly_once`), and only
one `POST /simulate` route exists. No console explanation is ever labelled
`returned evidence`, and no returned evidence is altered, embellished, or
overwritten for teaching purposes — every new sentence is visually and
semantically tagged `console explanation` (or `future capability` for the
evaluation-trace row), reusing the exact vocabulary Phase 17 already
established.

### Training-mode parity

`tests/test_operation_aware_training_rendering.py` and the existing
`tests/test_operation_aware_mode_parity.py` together prove that enabling
Training mode changes markup only: the same form controls, enabled/disabled
control state, submitted request, `GatewayClient` call, typed result,
`OperationAwarePresentation` object, returned evidence, validation outcome,
and route status are produced in both modes — Operator mode simply never
renders the additional `<section class="oa-training-content">` block.

### What Phase 19 does not do

No new evaluation-type selector, submission-mode selector, request field,
context behavior, form validation change, route, gateway-client method,
response-parsing change, or presentation-model field. No trace retrieval, no
trace viewer, no audit-event viewer, no subject or producer-trust inference,
no AI-generated explanation, and no change to Operator-mode rendering, legacy
`/v1/evaluate` behavior, or any degraded-state HTTP classification. Full
degraded-state parity coverage, further diagnostics refinement, documentation
polish, and release readiness remain PR 6 scope.

## Phase 20 operation-aware integration hardening and release readiness

Phase 20 (integration-plan PR 6) closes the operation-aware Decision Simulator
milestone Phases 16–19 built. It is a hardening and verification pass, not a
feature-expansion PR: it adds no operation-aware control, request field,
endpoint, policy feature, identity capability, or gateway behavior. Its job
was to verify the already-integrated system end to end, close any
demonstrated gaps in that verification, and document the milestone as
complete for its approved scope.

### Baseline verified, not assumed

Before any change, the branch (`chore/operation-aware-integration-hardening`,
starting commit `31fbaed4`), a clean working tree, and the canonical quality
gates were confirmed rather than taken on faith: `python -m pytest` (601
passed), `ruff check .` (clean), `ruff format --check .` (65 files already
formatted), and `mypy src` (strict; success across 23 source files, after
routing mypy's SQLite cache away from a FUSE-mounted sandbox directory that
does not support the cache's write mode — a sandbox-environment detail, not a
repository defect).

### Gap analysis and what PR 6 actually changed

Phases 16–19 already delivered thorough, independently-verified coverage of
nearly every hardening area this PR was scoped to check: the full
`OperationAwareEvaluationStatus` vocabulary is exercised at the route level
(not just the presentation-model level), every governed outcome and failure
reason has dedicated route tests, correlation-ID reconciliation and
contract-invalid handling are covered exhaustively in
`tests/test_gateway_evaluate_operation_aware.py`, disabled-state (not just
CSS-hidden) form behavior is asserted directly, and Operator/Training parity
already has a dedicated test module. Re-auditing against every hardening area
in the PR 6 task turned up a small number of genuine, narrow gaps rather than
a broad rewrite:

- **No test proved HTML-escaping of gateway-returned, console-unvalidated
  values** (`reason_code`, `explanation`, a generic error's `error`/`message`,
  and the redacted diagnostic body) — a real security-relevant coverage gap,
  since these fields (unlike `action`/`resource_type`/`resource_id`, which are
  drawn from a closed vocabulary or a restrictive regex before a request is
  ever built) are opaque strings the console does not validate. Jinja's
  default autoescaping (no `|safe` is used anywhere in these templates)
  already renders them inert; the gap was in *proving* it, not in the
  behavior itself. Closed with five new tests in
  `tests/test_simulate_operation_aware_routes.py` using a representative
  `<script>alert(1)</script>` payload, asserting the raw payload is absent
  from the rendered page and the entity-escaped form is present.
- **Long opaque tokens (reason codes, correlation/trace IDs, diagnostic text)
  had no wrap rule** in the `.kv` grid or `.mono`/`code` styles, so a single
  long unbroken token could overflow the fixed-width label column on a narrow
  viewport instead of wrapping. Closed with a narrow `overflow-wrap: anywhere`
  addition to those two rules in `style.css` — no layout redesign.
- **`README.md` stated the operation-aware integration plan was still
  "planning" with "no operation-aware runtime code... implemented yet"** —
  true when that document was written, false since Phase 16, and actively
  misleading in a release-readiness review. Corrected to describe the
  document as the plan that scoped the (now-implemented) feature, pointing at
  this file's Phase 16–20 notes. The adjacent "single egress point" bullet
  was also missing `/v1/evaluate/operation-aware` from its endpoint list;
  added.
- **No manual smoke-test guide covered the operation-aware contract
  specifically** — `docs/smoke-test.md` predates Phase 16 and only exercises
  the legacy contract. Added
  `docs/testing/operation-aware-simulator-smoke-test.md` (17 scenarios:
  mode/page loads, preview, disabled-control verification, crafted-field
  rejection, the full live outcome/failure/degraded-state matrix, redacted
  diagnostics, secret-absence, and Operator/Training parity), linked from
  `docs/smoke-test.md` and this README.
- **`CHANGELOG.md`'s `[0.1.0] - Unreleased` section never mentioned the
  operation-aware capability** despite four prior shipped phases — a
  release-readiness gate (`docs/release-checklist.md`) this repository already
  holds itself to. Added one `### Added` entry summarizing the capability.

Everything else audited against the PR 6 task's ten hardening areas was
already correctly implemented and already covered by an existing, focused
test — extending that coverage further would have been the "inflate test
counts with redundant assertions" anti-pattern the task explicitly warns
against, so it was left as-is and is itemized as verified-not-changed in the
PR's completion report rather than re-tested here.

### Internal invariant failures remain unconverted

`operation_aware_presentation.PresentationBuildError` (raised only when
`OperationAwareEvaluationResult.status`/`.response` presence disagree — a
contract drift between this module and `gateway.operation_aware_models`, not
a data condition a real gateway response can produce) is deliberately left
unhandled by `ui/views.py`. No broad `except Exception` was added around
`build_operation_aware_presentation()` to "keep the page alive": doing so
would risk converting a programming defect into a fabricated `DENY`,
`NOT_APPLICABLE`, or evaluator-failure result, which the PR 6 task explicitly
forbids. A real invariant violation still surfaces as an unhandled exception
(a 500 from the ASGI stack), which is the correct, honest failure mode for a
condition that should never occur — distinct from every genuine degraded
state above, all of which render safely through the existing typed result
model.

### What Phase 20 does not do

No new operation-aware endpoint, request field, context support,
producer-field support, subject-field support, identity decoding, token
handling, policy evaluation, trace retrieval, trace viewer, audit-event
retrieval or viewer, diagnostics aggregation from external systems, or
`basis-core`/gateway/schema/adapter change. Legacy `/v1/evaluate` remains the
default and is unchanged. Operator and Training modes continue to share the
one runtime path Phase 18 established; Training mode continues to add
explanation only. Identity telemetry, trace retrieval, an audit-event viewer,
and broader operator investigation workflows remain genuine future work,
tracked separately from this milestone.

**The `basis-console` operation-aware integration milestone (integration-plan
PRs 1–6 / architecture Phases 16–20) is complete for its approved scope, and
ships in `v0.2.0`** (see [`docs/releases/v0.2.0.md`](releases/v0.2.0.md)).
Phases 1–15 shipped earlier, under the `v0.1.0`/`v0.1.1` tags.
