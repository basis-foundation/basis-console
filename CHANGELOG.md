# Changelog

All notable changes to `basis-console` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

First release candidate of the human-facing operational interface for the BASIS
ecosystem. The console is read-oriented and gateway-first: it observes, inspects,
submits requests through `basis-gateway`, and explains the authorization model.
It does not evaluate authorization, authenticate users, own identity, store audit
records, or own resource inventory.

### Added

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
  `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, and GitHub
  issue/PR templates.

### Notes

- **Not production-ready.** A `v0.1.0` release means the console's interaction
  patterns, boundaries, documentation, and quality gates are coherent enough for
  early adopters to evaluate. It has not been audited or hardened for deployment
  in live operational technology environments.
- The provisional `basis_console.vocabulary` bridge is a console-local mirror, not
  the vocabulary authority; it is expected to be replaced by a future
  `basis-schemas` package.

[0.1.0]: https://github.com/basis-foundation/basis-console/releases/tag/v0.1.0
