# Changelog

All notable changes to `basis-console` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-08-08

`v0.2.0` brings **operation-aware authorization** into the Decision Simulator
through `basis-gateway`, alongside the console's existing legacy-evaluation
workflow (`POST /v1/evaluate`, unchanged and still the default), and closes
out a release-readiness hardening pass over that capability.

This release also restores alignment among package metadata, this changelog,
and the Git tag after the `v0.1.x` tags did not consistently update all
three — see the "Notes" section below.

### Added

- **Operation-aware evaluation contract** — a second, explicit evaluation
  contract on the Decision Simulator (`evaluation_type=operation_aware`),
  selectable alongside the legacy contract. Submits only action / resource
  type / resource ID (no subject, no context) to `basis-gateway`'s
  `POST /v1/evaluate/operation-aware`.
- **Typed operation-aware gateway client** — strict, shape-driven parsing that
  distinguishes a governed evaluation result from a generic/client error.
- **Governed and generic response handling** — evaluation status, kernel
  outcome (`allow` / `deny` / `not_applicable`), governed failure reason,
  gateway disposition, HTTP status, and console client status are kept
  distinct throughout, never collapsed into one another.
- **Correlation-ID integrity checking** between the submitted request and the
  gateway's response.
- **Shared operation-aware presentation model** with explicit provenance
  classification on every displayed fact (submitted input / returned
  evidence / console explanation / future capability).
- **Legacy/operation-aware simulator selection** — one shared Decision
  Simulator workflow, with an explicit per-request evaluation-contract
  choice, preview mode (no gateway call), and live gateway submission.
- **Operator/Training runtime parity** — both presentation modes render the
  identical operation-aware workflow and result.
- **Training-mode educational enrichment** — a dedicated panel (ecosystem
  flow, provenance legend, vocabulary glossary, and an explanation of the
  actual result) alongside the shared result; explanatory markup only, never
  a behavior change.
- **Release and test documentation**: `docs/releases/v0.2.0.md` and
  `docs/testing/operation-aware-simulator-smoke-test.md`.

### Security

- **Strict typed response parsing** for the operation-aware gateway contract —
  a governed result and a generic/client error are mutually exclusive, closed
  shapes; a response that matches neither is surfaced as `contract_invalid`
  rather than guessed at or partially rendered.
- **Correlation-ID integrity check** — when the gateway echoes a correlation ID
  that does not match the one the console sent, the mismatch is treated as a
  contract violation and surfaced as a diagnostic, never silently accepted.
- **Redacted diagnostics** — the raw response body and headers shown for a
  generic/client failure or a contract-invalid result run through
  `basis_console.gateway.redaction` first, so `Authorization`, cookies, and
  other credential-shaped fields never render even in diagnostic output.
- **HTML-escaping of gateway-returned and submitted-input values** — fields the
  console does not validate against a closed vocabulary (reason codes,
  evaluator explanations, generic error text) rely on Jinja's default
  autoescaping; this is now covered by dedicated tests asserting a crafted
  `<script>` payload renders inert.
- **Legacy-only fields disabled and server-rejected in operation-aware mode** —
  Subject ID, Subject type, and Context are HTML-`disabled` (not just
  CSS-hidden) when the operation-aware contract is selected, and a crafted
  non-empty value submitted directly (bypassing the browser) is rejected
  server-side before a request is built or a gateway call is made.
- **No bearer-token display or subject inference** — `GATEWAY_BEARER_TOKEN` is
  never displayed, logged, or rendered; live evaluation derives the subject
  from the gateway's verified token, and the console never asserts or infers a
  subject for the operation-aware contract, which has no field for one.

### Notes

- **Not production-ready.** A `v0.2.0` release means the console's interaction
  patterns, boundaries, documentation, and quality gates are coherent enough for
  early adopters to evaluate. It has not been audited or hardened for deployment
  in live operational technology environments.
- **Compatibility.** The legacy `/v1/evaluate` contract is unchanged and remains
  the default; no request field, response contract, or evaluation behavior
  changed for existing legacy usage. No migration is required to adopt `v0.2.0`.
- **Version alignment.** `v0.1.0` and `v0.1.1` were tagged without a
  corresponding `pyproject.toml`/`__init__.py` version bump or a versioned
  changelog entry — all prior work accumulated under a single
  `[0.1.0] - Unreleased` heading (preserved below) regardless of which tag it
  shipped in. `v0.2.0` is the first release where the package version, this
  changelog, and the Git tag agree; it does not reopen or invalidate the
  `v0.1.0`/`v0.1.1` tags themselves.
- The provisional `basis_console.vocabulary` bridge is a console-local mirror, not
  the vocabulary authority; it is expected to be replaced by a future
  `basis-schemas` package.

## [0.1.0] - Unreleased

First release candidate of the human-facing operational interface for the BASIS
ecosystem. The console is read-oriented and gateway-first: it observes, inspects,
submits requests through `basis-gateway`, and explains the authorization model.
It does not evaluate authorization, authenticate users, own identity, store audit
records, or own resource inventory.

### Added

- **Presentation modes (`BASIS_CONSOLE_MODE`)** — two UX-only modes selected by
  configuration, defaulting to `operator`. The mode names the *audience* of the
  interface, not a deployment environment. `operator` is professional and concise
  (clean, operator-focused screenshots/demos); `training` adds a visible
  top-level training banner, per-page "What this page teaches" callouts, and a
  standard BASIS architecture explanation (console observes/inspects/submits/
  explains, gateway enforces, core evaluates, adapters normalize, identity is the
  future `basis-identity` service, deploy/demo/topology are future layers). Both
  modes present the **same application** (same pages, navigation, controls,
  routing, and workflows) and keep sample/live/future labels honest; training
  mode only adds educational content. An invalid mode fails startup cleanly. This
  is a presentation/copy change only — no new backend authority, endpoints,
  evaluation, authentication, layout change, or behavior change.
- **Operator Workspace / Overview** (`GET /workspace`) — a single orientation
  landing page organizing the console around operational questions (Who is the
  subject? What resource is targeted? Can this action be performed? Is the
  enforcement boundary healthy? What evidence was recorded?), with the BASIS
  operational model `Identity → Resource → Gateway → Decision → Audit`.
- **Home / status page** (`GET /`) — console liveness and gateway connection
  state, linking prominently to the workspace.
- **Policy viewer** (`GET /policies`) — read-only, sample data.
- **Decision Simulator** (`GET`/`POST /simulate`, `GET /simulate/examples`) — a
  request builder that validates input and renders the normalized request shape
  (preview mode), and — when a gateway base URL and server-side bearer token are
  configured — optionally submits to `basis-gateway`'s `POST /v1/evaluate` and
  displays the gateway's decision verbatim (gateway-evaluation mode). The console
  never evaluates locally and never sends a subject as identity.
- **Audit Explorer** (`GET /audit`) — decision events and gateway composition
  evidence with correlation IDs; sample data, with a path to live evaluation
  evidence on the Simulate page.
- **Identity & Access Explorer** (`GET /identity`) — normalized subject,
  unverified claim/token preview, and claim→subject mapping; sample data.
- **Resource Explorer** (`GET /resources`) — sample normalized resources across
  every current adapter family, with local/canonical identifiers, supported
  actions, and gateway request shapes.
- **Gateway Diagnostics** (`GET /gateway`) — live gateway health/readiness probed
  through the single gateway client, with dynamically rendered readiness
  components and correlation IDs.
- **Readiness and liveness probes** (`GET /health`, `GET /ready`), the latter
  reporting gateway connectivity state additively.
- **Sample-only mode** — runs with no gateway configured; every data-bearing page
  is clearly labelled as sample/explanatory.
- **Optional gateway integration** — `GATEWAY_BASE_URL` enables live
  health/readiness; `GATEWAY_BEARER_TOKEN` additionally enables gateway-backed
  evaluation. Both are optional, server-side configuration.
- **Defensive redaction** of credential-shaped fields/headers before display
  (`basis_console.gateway.redaction`).
- **Live gateway integration polish** — Gateway Diagnostics shows per-probe
  response latency, last-successful timestamps, a connection-state glossary, and a
  concrete next step; the connection state is labelled consistently across the home
  page, the workspace, and diagnostics; timeouts are distinguished from other
  unreachable causes; and the Decision Simulator explains each evaluation outcome
  category and states plainly when the gateway returns no correlation ID or policy
  version. Display only — no new endpoints, pages, or evaluation behavior.
- **Explicit architectural boundaries** documented throughout: the console does
  not evaluate, authenticate, own identity/audit/inventory, parse protocols, or
  call `basis-core`, and reaches the system only through the gateway.
- Release and contributor documentation: `README.md`, `docs/architecture.md`,
  `docs/releases/v0.1.0.md`, `docs/release-checklist.md`, `docs/smoke-test.md`,
  `docs/testing/operation-aware-simulator-smoke-test.md`, `SECURITY.md`,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, and GitHub issue/PR
  templates.

### Notes

- **Not production-ready.** A `v0.1.0` release means the console's interaction
  patterns, boundaries, documentation, and quality gates are coherent enough for
  early adopters to evaluate. It has not been audited or hardened for deployment
  in live operational technology environments.
- The provisional `basis_console.vocabulary` bridge is a console-local mirror, not
  the vocabulary authority; it is expected to be replaced by a future
  `basis-schemas` package.

[0.1.0]: https://github.com/basis-foundation/basis-console/releases/tag/v0.1.0
[0.2.0]: https://github.com/basis-foundation/basis-console/compare/v0.1.1...v0.2.0
