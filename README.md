# basis-console

`basis-console` is a human-facing operational interface for the BASIS ecosystem. It gives operators read-only visibility into policy state, authorization decisions, and audit activity, and it establishes the interaction patterns that later phases will connect to live data through `basis-gateway`.

This repository is at **Phase 12**: the read-only skeleton, the gateway connection-status display, the **decision-simulator request builder**, an optional **gateway-backed simulation** path, structured action construction, alignment with gateway-owned action/resource composition, an operator-facing **Identity & Access Explorer**, a **Gateway Diagnostics** view, an **Audit Explorer**, a **Resource Explorer** that makes visible how OT/platform resources become normalized authorization targets, and (new in Phase 12) an **Operator Workspace / Overview** that brings these areas together into a single orientation landing page organized around operational questions. The simulator always supports preview mode (validate input, render the normalized request shape, no gateway call). When a gateway base URL and a server-side Bearer token are configured, it can additionally submit the request to `basis-gateway`'s `POST /v1/evaluate` and display the gateway's decision verbatim. The console **never evaluates decisions itself**, never imports `basis-core`, and never reinterprets the gateway's response — it relays it. Subject identity for live evaluation comes from the gateway's verified token, never from the form.

As of Phase 7 the console submits an **adapter/console-normalized** request — a bare action verb, a `resource_type`, and a *local* `resource_id` — and **`basis-gateway` composes** the canonical kernel action (`read:ahu`) and the typed resource id (`ahu:rooftop-1`). The console no longer pre-composes those canonical strings (see [Phase 7](#phase-7-gateway-resource-composition-alignment) below). The verb/resource-type lists live in a small, explicitly **provisional** console-local vocabulary bridge (`basis_console.vocabulary`) that the console is **not** the authority for — the authoritative home is a future `basis-schemas` package (see [Future `basis-schemas` extraction](#future-basis-schemas-extraction)).

```
basis-console is a human-facing operational interface.
It does not evaluate authorization decisions.
It does not authenticate users yet.
It does not replace basis-gateway or basis-core.
```

---

## What basis-console is

- A human-facing **interface layer** that makes the authorization system understandable and operable.
- A **read-only** window (in Phase 1) onto policy state, decision outcomes, and audit records.
- A deployable **operational web application** — not a public marketing site — designed to run in cloud, on-prem, and air-gapped environments.

## What basis-console is not

The console renders information and (in later phases) submits requests through enforced boundaries. It never becomes the system behind the interface. Specifically, the console does **not**:

- evaluate authorization decisions — that belongs to `basis-core`;
- authenticate users or manage sessions — that belongs to `basis-gateway` and the identity providers it trusts;
- normalize or speak field protocols (BACnet, Modbus, MQTT, …) — that belongs to `basis-adapters`;
- produce, supplement, or reinterpret audit records — those are produced by `basis-core` and `basis-gateway`;
- bypass the gateway to reach the kernel directly in production deployments.

See [`docs/architecture.md`](docs/architecture.md) for the full set of boundaries and design invariants the console must preserve.

---

## Scope by phase

**Phase 1 (skeleton):**

- **Health / status page** (`GET /`) and a JSON liveness probe (`GET /health`).
- **Readiness probe** (`GET /ready`) reporting per-component state.
- **Policy viewer** (`GET /policies`) — read-only placeholder backed by local sample data.
- **Decision simulator** (`GET /simulate`) — a placeholder form establishing the subject / resource / action pattern. It is intentionally not wired to the gateway.
- **Audit viewer** (`GET /audit`) — read-only placeholder backed by local sample data.
- Configuration, readiness tracking, server-rendered UI, and a test/lint/typecheck toolchain.

**Phase 2 (gateway status):**

- A **gateway client abstraction** (`basis_console.gateway`) that probes the gateway's `/health` and `/ready` endpoints over HTTP and returns a typed status report. It never raises a network error into the UI.
- A **configurable gateway base URL and timeout** (`GATEWAY_BASE_URL`, `GATEWAY_TIMEOUT_SECONDS`).
- A **gateway status panel** on the homepage showing the connection state (`not_configured` / `reachable` / `ready` / `unreachable` / `error`) and the configured base URL.
- **`/ready` extended** with `gateway_configured` and `gateway_reachable` components plus a `gateway` status object.

### How Phase 2 uses the gateway

The console probes only the gateway's operational endpoints to determine connectivity:

- If `GATEWAY_BASE_URL` is **unset**, the status is `not_configured`, the console runs in sample-only mode, and no gateway call is made. The console still starts and `/ready` stays ready.
- If it is **set and the gateway is reachable**, the console reports `reachable` (gateway answered `/health`) or `ready` (gateway also answered `/ready`), and the UI shows the base URL and state.
- If it is **set but the gateway is unreachable**, the console reports `unreachable`, the UI shows a clear warning, and the console does **not** fall back to local authorization behavior. Placeholder pages remain read-only / sample-only.

An unreachable or unconfigured gateway does **not** make the console itself unready in Phase 2 — gateway connectivity is reported additively so the console does not flap when the gateway is down. No network call happens at startup, so the console starts cleanly offline / air-gapped; connectivity is probed on demand when `/ready` or the homepage is rendered.

### Still placeholder / sample-only

Policy, simulator, and audit pages still render **local sample data only**. The console consumes no live gateway policy, decision, or audit APIs yet (the gateway does not expose console-facing variants of these), and it never evaluates decisions locally.

### Why the console does not call `basis-core` directly

In the production interaction model the console reaches the authorization system **only through `basis-gateway`**. The gateway authenticates the request, normalizes identity, invokes the kernel when evaluation is needed, and assembles the audit record. A console that talked to `basis-core` directly would bypass authentication, enforcement, and audit assembly — so this repository has no dependency on `basis-core` and the gateway package never imports it.

**Phase 3 (decision simulator):**

- A functional **request builder** at `GET /simulate` where an operator enters a subject identifier and type, an action, a resource identifier and type, and optional `key=value` context.
- `POST /simulate` validates and sanitizes the input and renders a **normalized request preview** as formatted JSON, alongside an explanation of every field.
- A **`GET /simulate/examples`** page and three loadable, clearly-marked sample scenarios (operator reads AHU temperature; technician writes HVAC setpoint; vendor attempts access to a restricted device).

#### The simulator does not evaluate decisions

This is the core boundary of Phase 3. Submitting the form **does not call `basis-gateway`** and produces **no allow/deny outcome**. The console validates input, builds a preview object, and renders it — nothing more. The accepted actions (`read`, `write`, `execute`, `browse`, `subscribe`) are the normalized verbs `basis-adapters` already emits; the preview uses `basis-core` `DecisionRequest` field names (`subject_id`, `action`, `resource_id`, `context`) so a later swap is small, but enforcement-path fields the gateway/kernel populate (`request_id`, `timestamp`, resolved `subject_roles`) are deliberately not fabricated.

#### Validation rules (preview mode)

- subject identifier, subject type, action verb, action domain, resource identifier, and resource type are required; context is optional;
- the action verb must be one of `read`, `write`, `execute`, `browse`, `subscribe`, and the action domain one of the provisional starter domains (`ahu`, `setpoint`, `telemetry`, `device`, `schedule`, `command`) — see Phase 6 below;
- the composed action string (`{verb}:{domain}`) must match `basis-core`'s action format;
- identifiers must be simple safe strings (letters, digits, and `. _ - : /`); types must be simple slugs;
- context is one `key=value` per line; malformed, oversized, or duplicate entries are rejected;
- invalid submissions re-render the form with user-friendly errors and the submitted values preserved.

> Note: through Phase 5 the action was a single **bare verb** (`read`); Phase 6 replaces that with structured verb + domain composition so the simulator no longer produces gateway-invalid actions. See **Phase 6** below.

**Phase 4 (gateway-backed simulation — this phase):**

The simulator gains an optional second mode that submits the request to the gateway. Preview mode is unchanged and always available.

- **Gateway-evaluation mode** (`POST /simulate` with `mode=gateway`) submits `action` / `resource_id` / `context` to `basis-gateway`'s `POST /v1/evaluate` and renders the gateway's response in a clearly labelled "Gateway response" section: the decision (`allow` / `deny` / `not_applicable`), HTTP status, reason, policy version, correlation ID, and the raw JSON in a collapsible block.
- **Available only when configured** — both `GATEWAY_BASE_URL` and `GATEWAY_BEARER_TOKEN` must be set (the gateway requires a verified Bearer token). When the base URL is unset the page shows _"Gateway evaluation is not configured…"_; when the token is missing it shows _"Gateway evaluation requires a configured server-side bearer token."_
- **The console still does not evaluate decisions.** It relays the gateway's response verbatim and never reinterprets it, never computes an outcome, and never imports `basis-core`.

##### Identity boundary (important)

The gateway verified the Bearer token derives subject identity **exclusively** from that token and **rejects** any caller-supplied `subject_id` / `subject_roles` (HTTP 400). The console therefore sends **only** `action` / `resource_id` / `context` to `/v1/evaluate` — never a subject. The form's subject fields are **preview/educational only**; the page states plainly that live evaluation's subject is the token's, not the form's. This avoids any misleading path that would appear to let a user impersonate an arbitrary subject.

##### Token handling

`GATEWAY_BEARER_TOKEN` is an optional, server-side, operator-configured token for local/dev/operator-controlled environments. It is **never displayed in the UI, never logged, and never rendered in any page** — it is used only as the `Authorization: Bearer <token>` header on the `/v1/evaluate` call. The console does **no** OIDC login, no token refresh, and no browser-session token storage; it is not an identity provider. Obtain a token out-of-band from the gateway's configured OIDC issuer.

##### How a gateway response is classified

The client maps the gateway's documented HTTP contract to a typed result, distinguishing: success (200 ALLOW), denied (403 DENY/NOT_APPLICABLE — surfaced, never hidden), unauthorized (401), validation error (400), unavailable (503 or a network failure), and gateway error (500/other). Network and HTTP errors never raise into the UI.

> Note: the gateway validates the action against `basis-core`'s `{verb}:{domain}[:{object}]` naming convention. Through Phase 5 the simulator submitted a bare verb (e.g. `read`), which returned a gateway `validation_failed` (400). **Phase 6 resolves this** by composing a `{verb}:{domain}` action string, so normal simulator-generated requests now satisfy the gateway's action contract. See **Phase 6** below and `docs/architecture.md`.

**Phase 6 (action vocabulary contract and schema preparation — this phase):**

Phase 6 makes the simulator construct **gateway-compatible action strings** in a transparent, spec-driven way, and documents the vocabulary contract that should eventually move into a dedicated `basis-schemas` package.

> **Superseded by [Phase 7](#phase-7-gateway-resource-composition-alignment).** Phase 6 had the *console* compose the `{verb}:{domain}` action. Phase 7 moves composition to `basis-gateway`: the console submits a bare verb plus a `resource_type` and the gateway composes the canonical action **and** resource id.

- **Why it exists.** During Phase 4/5 gateway-backed simulation, the simulator's bare verbs (`read`) failed `basis-core`'s `DecisionRequest.action` validation, which requires the `{verb}:{domain}[:{object}]` form (two or more colon-separated lowercase segments). Every gateway-backed simulation of a simulator-generated request therefore returned HTTP 400. This is the action-vocabulary mismatch Phase 6 addressed.
- **Structured action construction.** The single bare-action input is replaced with an **action verb** and a **resource type / action domain**. Through Phase 6 the console composed them into a final action string itself (e.g. `read:ahu`); from Phase 7 it submits the bare verb and the resource type and the gateway composes. The form shows the verb, the resource type, a preview of what the gateway will compose, the normalized request preview, and — when evaluated — the gateway response.
- **Provisional vocabulary bridge.** `src/basis_console/vocabulary.py` defines the supported verbs (`read`, `write`, `execute`, `browse`, `subscribe`), a small set of starter domains (`ahu`, `setpoint`, `telemetry`, `device`, `schedule`, `command`), a composition helper, and a structural validator mirroring `basis-core`'s action regex. It is **explicitly a temporary, console-local mirror** and is documented as such in code; it is **not** the canonical vocabulary authority and introduces no new verbs.
- **The console is not the vocabulary authority.** The console may help users construct valid action strings, but the authoritative source of the action vocabulary is `basis-architecture/docs/architecture/action-vocabulary.md` today and should become `basis-schemas` in the future.

##### Future `basis-schemas` extraction

The Phase 6 vocabulary bridge is a stopgap. A dedicated **`basis-schemas`** package should eventually own the cross-component contracts that are currently mirrored, re-derived, or implied across repositories:

- the **action vocabulary** (verbs, domains, naming structure, reserved prefixes);
- the **request/response schemas** (e.g. `DecisionRequest` / `DecisionResponse`, the gateway's `EvaluateRequest` / `EvaluateResponse`);
- the **audit/event schemas**;
- the **cross-component compatibility contracts** that keep adapters, the gateway, the kernel, and the console in agreement.

When `basis-schemas` (or an equivalent shared contract package) exists, `basis_console.vocabulary` should be deleted and the simulator should consume the shared definitions instead of a local copy.

**Phase 7 (gateway resource composition alignment — this phase):**

Phase 7 aligns the console's request builder with `basis-gateway`'s composition boundary. The gateway now composes **both** the canonical action and the canonical resource identifier from a normalized request, so the console stops pre-composing them and submits the normalized inputs instead:

```
Adapters / console provide normalization inputs.
Gateway composes the canonical action and resource_id.
Core evaluates the canonical request.
```

- **The console submits normalized requests; the gateway composes.** The simulator collects a bare **action verb**, a **resource type / action domain**, and a **local resource ID**, and submits `{"action": "read", "resource_type": "ahu", "resource_id": "rooftop-1"}`. The gateway composes `action = read:ahu` and `resource_id = ahu:rooftop-1`. The console previews what the gateway will compose but no longer builds those canonical strings itself.
- **`resource_type` is not merely descriptive.** It is an input the gateway uses to compose **both** the action (`{verb}:{resource_type}`) and the resource id (`{resource_type}:{local_id}`). The console therefore carries a single `resource_type` field instead of a separate action domain and a descriptive resource type that could drift apart.
- **Two valid shapes; no dual source of truth.** The preferred **normalized** shape sends a bare verb + `resource_type` + *local* `resource_id`. The **direct** shape — used only when an operator intentionally enters a fully typed kernel-compatible request — sends `{"action": "read:ahu", "resource_id": "ahu:rooftop-1"}` with **no** `resource_type`. The console refuses to send a `resource_type` alongside an already-typed `resource_id` (even when the prefix matches), because that is a dual source of truth that can drift. A `resource_type` with **no** `resource_id` is valid — it is a domain-level request (the gateway composes the action only, `resource_id = null`).
- **Composition evidence.** When the gateway returns composition evidence (`basis_gateway.resource_composed`, `basis_gateway.original_resource_id`, `basis_gateway.resource_type`, `basis_gateway.composed_resource_id`), the simulator surfaces it in a small "Gateway composition" panel. The console only reads this evidence; it never sets it.
- **The console still does not evaluate or call `basis-core`.** Phase 7 changes only how the request is shaped before it reaches the gateway; the boundaries are unchanged.

Explicitly **out of scope** (later phases): OIDC login, user sessions, token refresh, browser-stored tokens, live policy / audit / decision viewers, adapter integration, deployment tooling (Docker, Kubernetes), metrics, multi-user sessions, and RBAC. Phase 7 also does **not** create `basis-schemas`, resolve the resource taxonomy, or split the action domain from the resource type.

**Phase 8 (Identity & Access Explorer foundation — this phase):**

Phase 8 adds an operator-facing **Identity & Access Explorer** at `GET /identity` and prepares the console to work cleanly with a future `basis-identity` service. It is a console *feature area*, not a protocol implementation. The page renders, inspects, and explains identity/access context — it does **not** authenticate, authorize, evaluate policy, verify tokens, or call `basis-core`, and it implements no OIDC/OAuth/SAML/SCIM/JWKS.

- **Verified subject.** Displays a normalized BASIS subject (`subject_id`, `subject_type`, `roles`, `groups`, `issuer`) — shown as clearly-labelled **sample** data, since the console does not derive or verify identity.
- **Claims / token preview.** A read-only viewer of a (nested) OIDC-style claim set with issuer/audience/expiration, marked **unverified**. The console performs no token verification — that belongs to the gateway.
- **Subject normalization preview.** Shows how claims become a BASIS subject (`OIDC claims → gateway subject mapper → BASIS Subject`) with role/group mapping tables. Illustrative; the gateway owns the real mapping.
- **Access decision linkage.** A "Use this subject in evaluation" link into the existing simulator. The subject is **never** sent as identity — live evaluation derives the subject from the gateway's verified token; the link only previews how a request would be shaped.
- **Future `basis-identity` integration panel.** A clearly-labelled, **non-live** list of upcoming capabilities (OIDC discovery viewer, OAuth flow explorer, JWT inspector, JWKS viewer, SAML assertion viewer, SCIM event viewer, access review workflows). These are future integrations the console will *display*, never implement.

Console-owned presentation models live in `src/basis_console/identity.py` (`IdentityPreview`, `ClaimPreview`, `SubjectPreview`, `AccessPreview`, plus supporting `MappingStep` / `FutureIntegration`). They are deliberately named `*Preview` and avoid protocol-ownership names (`OidcProvider`, `SamlService`, `ScimEngine`, `OAuthServer`): the console can display protocol data, but it must not implement the protocols. **All data on this page is sample/demo data** — no live gateway or identity APIs are consumed, and no gateway endpoints were invented. The structure lets live gateway/`basis-identity` data replace the samples later.

The intended relationship the page documents:

```
External IdP → basis-identity → basis-gateway → basis-core

basis-console observes and operates the flow; it owns none of it.
```

`basis-identity` (a future repository) will own identity lifecycle and federation; it will integrate with external IdPs, not replace them. Phase 8 explicitly does **not** implement `basis-identity`, OIDC/OAuth/SAML/SCIM, token verification, IdP administration, user provisioning, password auth, MFA, or access-review execution; it does not modify `basis-gateway` or `basis-core` or create `basis-schemas`.

**Phase 9 (Gateway Diagnostics — this phase):**

Phase 9 adds a **Gateway Diagnostics** view at `GET /gateway` that makes `basis-gateway`'s operational state understandable to an operator. It continues the direction of the Identity & Access Explorer: the console **observes, inspects, and explains**; the gateway **authenticates, composes, enforces, and emits evidence**; the kernel **evaluates**. The view does **not** configure the gateway, authenticate users, evaluate policy, call `basis-core`, or bypass the gateway.

It probes only the gateway's **real** operational endpoints (`GET /health`, `GET /ready`) through the existing gateway client — it invents no endpoints and fabricates no data. The page is useful in three states:

- **Configured and reachable** — shows live health, readiness, readiness components, capability, and correlation IDs.
- **Configured but unreachable** — shows a clear connection error and never falls back to local authorization behavior.
- **Not configured** — explains that `GATEWAY_BASE_URL` must be set.

UI panels:

1. **Connection summary** — gateway base URL, connection state, health/readiness HTTP status, and last-checked time.
2. **Health** — the result of `GET /health` (status, service, target URL), or an error when unreachable.
3. **Readiness** — the result of `GET /ready`, including per-component status **rendered dynamically** (arbitrary component keys are shown safely, since gateway readiness may evolve) with reasons for not-ready components.
4. **Evaluation & policy capability** — evaluation/policy-related readiness components (`evaluator_initialized`, `policy_loaded`, `oidc_configured`, `jwks_available`) when reported. The gateway does **not** expose `policy_version`/`policy_name` on `/health` or `/ready` (only on evaluation responses), so the panel says so rather than inventing a policy endpoint.
5. **Correlation IDs** — the `X-Correlation-ID` returned on the health and readiness responses. The evaluation correlation ID is surfaced on the Simulate page; the console never fabricates correlation IDs.
6. **Raw responses** — the raw, **redacted** payloads and selected headers for health/readiness, for learning and debugging.

**Security:** sensitive headers and fields (`authorization`, `access_token`, `refresh_token`, `id_token`, `client_secret`, `password`, `secret`, cookies, bearer tokens, API keys) are **redacted defensively** before any value is stored on a result object or rendered — see `basis_console.gateway.redaction`. The console never displays the configured Bearer token and never sends it to `/health` or `/ready`.

The gateway client gains two diagnostic probes, `get_health()` and `get_ready()`, that capture HTTP status, response JSON, selected headers, correlation ID, the request target URL, a `checked_at` timestamp, and any transport error — each returning a presentation-friendly `GatewayProbeResult` and never raising into a route. `basis_console.diagnostics` aggregates these into the view model. No method calls a non-existent gateway endpoint.

**Future identity diagnostics** (OIDC discovery, JWKS, JWT inspection) will integrate through the future `basis-identity` service, not through console-owned protocol logic. Phase 9 does **not** add packet capture, proxy/traffic sniffing, deployment tooling, policy editing, an audit/resource explorer, authentication, or any identity protocol, and modifies neither `basis-gateway` nor `basis-core`.

**Phase 10 (Audit Explorer — this phase):**

Phase 10 turns the placeholder audit viewer into an **Audit Explorer** at `GET /audit` that makes authorization decisions and gateway evidence understandable. It answers: who attempted what, was it allowed or denied, which action/resource was involved, what gateway evidence was recorded, and what correlation ID connects the request. This is **operational visibility**, not an audit storage system. The console **displays audit evidence** produced by `basis-core` and `basis-gateway`; it does **not** authenticate, authorize, evaluate, store canonical audit records, own audit semantics, define an audit schema, replace SIEM/log infrastructure, or call `basis-core`.

`basis-gateway` does not yet expose an audit-history endpoint, so the Audit Explorer is **sample-backed and evaluation-result-aware**, and is honest about what is live versus sample: the recent-events list is clearly-labelled demo data with obviously-sample correlation IDs, and the page links to the Simulate page where **live** decision + composition evidence + correlation IDs are produced today. No audit endpoint is invented; no database or persistent history is added.

UI panels:

1. **Audit overview** — states plainly that the console displays evidence and does not produce canonical records.
2. **Recent authorization events** — a table of decision events (timestamp, outcome, subject, action, resource, policy, correlation ID, source).
3. **Event detail** (inline, expandable) — Decision, Subject, Action, Resource, Policy, Gateway Evidence, Correlation, and the Raw Event.
4. **Gateway evidence** — the real reserved `basis_gateway.*` composition-evidence keys (`action_composed`, `original_action`, `composed_action`, `resource_type`, `resource_composed`, `original_resource_id`, `composed_resource_id`) when present; a clear "no composition evidence" state for direct/already-typed requests.
5. **Correlation IDs** — shown per event and explained: a correlation ID connects request → gateway response → audit evidence → operator troubleshooting. The console never fabricates correlation IDs.
6. **Evaluation-result integration** — a path from the Audit Explorer to the Simulator (and a link back from the simulator's gateway response) so live decision evidence is reachable, plus a static explanation of how a future gateway audit-history endpoint will populate the page.
7. **Future live audit integrations** — a clearly-labelled, non-live list: `basis-gateway` audit-history endpoint, `basis-core` audit event schema, `basis-schemas` audit contracts, `basis-identity` lifecycle events, and external SIEM/log pipelines.

Console-owned presentation models live in `src/basis_console/audit.py` (`AuditEventPreview`, `AuditDecisionPreview`, `AuditEvidencePreview`, plus `FutureAuditIntegration`). They are named `*Preview` and avoid canonical-ownership names (`AuditEvent`, `CanonicalAuditRecord`, `GatewayAuditStore`): canonical audit types belong to `basis-core` / `basis-gateway` / `basis-schemas`. **Security:** raw event payloads are run through the shared `basis_console.gateway.redaction` helpers before display, so sensitive fields (`authorization`, `access_token`, `refresh_token`, `id_token`, `client_secret`, `password`, `secret`, cookies, bearer tokens, API keys) are redacted — bearer tokens and raw `Authorization` headers are never displayed.

Phase 10 explicitly does **not** add audit storage, persistent history, a database, SIEM integration, a canonical audit schema, policy editing, or a resource explorer, and modifies neither `basis-gateway` nor `basis-core`.

**Phase 11 (Resource Explorer foundation — this phase):**

Phase 11 adds a read-only **Resource Explorer** at `GET /resources` that makes visible what BASIS reasons about — resources, actions, resource identifiers, adapter sources, and gateway request shapes — so operators and contributors can see how OT/platform resources become normalized authorization targets. This is **operational visibility**, not device discovery, inventory management, topology mapping, or live protocol integration. The console **displays resource concepts and authorization targets**; it does **not** discover devices, connect to OT protocols, call adapters directly, mutate resources, edit policies, call `basis-core`, or own a resource inventory.

`basis-adapters` does not yet expose a live resource-inventory service and `basis-gateway` does not yet expose a resource-catalog endpoint, so the Resource Explorer is **sample-backed** and clearly labels its data as illustrative/non-live. No adapter or gateway resource API is invented.

UI areas:

1. **Resource overview** — states plainly that the console displays resource concepts and authorization targets and does not discover devices or own inventory.
2. **Identifier explanation** — the difference between `local resource_id`, `resource_type`, and the gateway-composed `canonical resource_id`, with the composition flow and the direct typed request shape (`{"action": "read:ahu", "resource_id": "ahu:rooftop-1"}`).
3. **Resource catalog** — a table of sample normalized resources spanning every current adapter family (BACnet, Modbus, OPC UA, MQTT, DNP3, IEC 61850, KNX, Niagara) plus REST, with display name, type, local/canonical identifiers, protocol family, adapter source, and supported actions.
4. **Resource detail** (inline, expandable) — Resource, Identifier, Adapter Source, Supported Actions, Gateway Request Preview, and the redacted Raw Resource.
5. **Gateway request preview** — the preferred normalized shape (bare verb + `resource_type` + local `resource_id`) and the canonical action/resource id the gateway composes from it.
6. **Use in evaluation** — a link/guidance into the existing simulator (deep-linking a matching sample scenario where one exists, otherwise guiding the operator); it never bypasses the gateway.
7. **Future live resource integrations** — a clearly-labelled, non-live list: `basis-adapters` resource outputs, a `basis-gateway` resource catalog, `basis-schemas` resource contracts, `basis-identity` subject/resource mapping, `basis-deploy` site inventory, and external CMDB/OT inventory.

Console-owned presentation models live in `src/basis_console/resources.py` (`ResourcePreview`, `ResourceIdentifierPreview`, `ResourceActionPreview`, `AdapterSourcePreview`, plus `GatewayRequestPreview` and `FutureResourceIntegration`). They are named `*Preview` and avoid canonical-ownership names (`Resource`, `CanonicalResource`, `DeviceInventory`, `ResourceStore`): canonical resource contracts belong to a future `basis-schemas`. **Security:** raw resource payloads are run through the shared `basis_console.gateway.redaction` helpers before display, so sensitive fields (`authorization`, `access_token`, `refresh_token`, `id_token`, `client_secret`, `password`, `secret`, cookies, bearer tokens, API keys) are redacted.

Phase 11 explicitly does **not** add device discovery, resource inventory storage, topology mapping, CRUD/mutation, policy authoring, live adapter integrations, `basis-schemas`, or deployment tooling, and modifies none of `basis-adapters`, `basis-gateway`, or `basis-core`.

**Phase 12 (Operator Workspace / Overview — this phase):**

Phase 12 adds a read-only **Operator Workspace / Overview** at `GET /workspace` that brings the existing console areas — Identity & Access, Resources, Decision Simulator, Gateway Diagnostics, and Audit Explorer — together into a single operational landing page. It organizes those areas around operational *questions* (Who is the subject? What resource is targeted? Can this action be performed? Is the enforcement boundary healthy? What evidence was recorded?) rather than repository names, and presents the BASIS operational model (Identity → Resource → Gateway → Decision → Audit) with each stage linked to the area that makes it inspectable. The simple homepage at `GET /` stays the landing page and now links prominently to the workspace.

This is an **orientation/workspace foundation**, not a new backend integration. The Operator Workspace **organizes existing console views**; it does **not** add backend authority, does **not** change `basis-gateway`, `basis-core`, or `basis-adapters` behavior, and does **not** make sample data live. The only live datum it surfaces is the gateway connection/readiness state, reused from the existing **Gateway Diagnostics** aggregator (`basis_console.diagnostics`) — no new diagnostics logic is added and `basis-core` is never called.

UI areas:

1. **Workspace header** — states the purpose: identity, resources, gateway state, authorization simulation, and audit evidence in a single operational view, and that the page summarizes and links existing capabilities rather than adding new ones.
2. **Operational flow summary** — the BASIS model `Identity → Resource → Gateway → Decision → Audit`, each stage mapped to `/identity`, `/resources`, `/gateway`, `/simulate`, `/audit`.
3. **Capability cards** — one card per area (Identity & Access, Resources, Decision Simulator, Gateway Diagnostics, Audit Explorer) with purpose, the question it helps answer, a link, and a live/sample status.
4. **Operational questions panel** — the operator questions above, each linked to the relevant page.
5. **System readiness snapshot** — an honest gateway connection/readiness summary reused from Gateway Diagnostics; shows configured/unconfigured/unreachable state honestly and links to `/gateway` for the full view.
6. **Current data maturity panel** — distinguishes **live/configurable** (gateway health/readiness, gateway-backed evaluations), **sample/explanatory** (identity previews, resource catalog, audit history), and **future** (`basis-identity`, live resource catalog, live audit history).
7. **Recommended operator path** — Check Gateway → Inspect Identity → Inspect Resources → Run Evaluation → Review Audit Evidence, each step linked to its page.

Console-owned presentation models live in `src/basis_console/workspace.py` (`WorkspaceCard`, `OperationalQuestion`, `DataMaturityItem`, `OperatorPathStep`, plus `FlowStep`). They are named for what the console *shows* and deliberately avoid names that would imply backend authority (`SystemState`, `CanonicalWorkspace`, `OperationalControlPlane`).

Phase 12 explicitly does **not** add a live resource catalog, live audit history, identity protocol flows, policy editing, user provisioning, device discovery, topology mapping, persistent storage, or any `basis-core` call, and modifies none of `basis-core`, `basis-gateway`, or `basis-adapters`. It does not redesign the UI or replace existing pages.

---

## Relationship to the ecosystem

The console preserves BASIS layering. Operator actions flow through the console to the gateway, and the gateway enforces the appropriate boundary before reaching the kernel:

```
Operator → basis-console → basis-gateway → basis-core
```

**Relationship to `basis-gateway`.** The gateway is the console's primary operational dependency. Everything the console surfaces — policy state, decision history, audit records, system status — it obtains through gateway APIs. The console must degrade gracefully when the gateway is unreachable and must never fall back to local authorization logic or cached decisions. (Phase 2 contacts only the gateway's `/health` and `/ready` endpoints to report connectivity; live policy/audit/decision data remains future work.)

**Relationship to `basis-core`.** In the production interaction model the console has **no direct dependency** on `basis-core`. It does not import kernel libraries or invoke kernel evaluation. Kernel-derived information reaches the console only through the gateway. (Accordingly, this repository does not depend on the `basis-core` package.)

---

## Local setup

**Requirements:** Python 3.10+. No internet access, cloud account, or external service is required to run the console.

```bash
# from the repository root
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### Run

```bash
uvicorn basis_console.main:app --host 127.0.0.1 --port 8080
# or: make run         (honors HOST / PORT environment variables)
```

Then open <http://127.0.0.1:8080/>. The status page should report `Status: running`.

### Configuration

All configuration comes from environment variables with safe local defaults. Nothing is hardcoded to a public URL or SaaS endpoint.

| Variable                  | Default         | Purpose                                                        |
| ------------------------- | --------------- | -------------------------------------------------------------- |
| `HOST`                    | `127.0.0.1`     | Bind address. Set `0.0.0.0` (or a specific interface) behind a reverse proxy. |
| `PORT`                    | `8080`          | Bind port.                                                     |
| `LOG_LEVEL`               | `INFO`          | One of DEBUG, INFO, WARNING, ERROR, CRITICAL.                  |
| `ENVIRONMENT`             | `local`         | One of local, development, staging, production.                |
| `GATEWAY_BASE_URL`        | _(unset)_       | Base URL of the basis-gateway. Optional — when unset, gateway status is `not_configured` and the console runs sample-only. No public URL is baked in. |
| `GATEWAY_TIMEOUT_SECONDS` | `2.0`           | Timeout for gateway `/health`, `/ready`, and `/v1/evaluate` calls. Must be > 0. |
| `GATEWAY_BEARER_TOKEN`    | _(unset)_       | Optional server-side Bearer token enabling gateway-backed simulation. Sent only as `Authorization: Bearer <token>` to `/v1/evaluate`; never displayed, logged, or rendered. For local/dev/operator-controlled use — the console does no OIDC login or token refresh. |
| `SERVICE_NAME`            | `basis-console` | Service name reported by health/readiness.                     |

The console is designed to sit behind a reverse proxy (Nginx, Caddy, or a cloud load balancer) and serves all static assets locally so it works in air-gapped deployments. Container, systemd, and Kubernetes packaging are deliberately deferred to a later phase; nothing here precludes them.

---

## Development commands

```bash
python -m pytest        # run the test suite
ruff check .            # lint
ruff format --check .   # formatting check
mypy src                # static type checking
```

A `Makefile` wraps these:

```bash
make test
make lint
make format
make typecheck
make check     # lint + format + typecheck + test
```

---

## Repository structure

```
basis-console/
  src/basis_console/
    __init__.py
    main.py            # FastAPI app factory + lifespan
    config.py          # environment-driven configuration
    readiness.py       # readiness state tracker
    sample_data.py     # read-only SAMPLE data for placeholder views + scenarios
    simulator.py       # decision-simulator validation + preview builder (Phases 3 + 6)
    identity.py        # Identity & Access Explorer presentation models + SAMPLE data (Phase 8)
    diagnostics.py     # Gateway Diagnostics aggregator / presentation model (Phase 9)
    audit.py           # Audit Explorer presentation models + SAMPLE events (Phase 10)
    resources.py       # Resource Explorer presentation models + SAMPLE resources (Phase 11)
    workspace.py       # Operator Workspace presentation models + orientation content (Phase 12)
    vocabulary.py      # provisional console-local action vocabulary bridge (Phase 6)
    gateway/           # gateway client abstraction (Phases 2 + 4 + 9)
      client.py        #   httpx /health + /ready probes, /v1/evaluate, diagnostic probes
      models.py        #   GatewayStatus + GatewayEvaluationStatus/Result + GatewayProbeResult
      redaction.py     #   defensive redaction of sensitive headers/fields (Phase 9)
    api/routes.py      # /health, /ready (JSON, incl. gateway state)
    ui/views.py        # /, /workspace, /policies, /simulate (GET+POST), /audit, /identity, /resources, /gateway (HTML)
    ui/templates/      # Jinja2 templates (incl. workspace + simulate + examples + identity + gateway + audit + resources)
    ui/static/         # locally served CSS (no CDN)
  tests/               # health, routes, config, gateway, simulator, eval tests
  docs/architecture.md # console boundaries and phase notes
  pyproject.toml
  Makefile
  README.md
```
