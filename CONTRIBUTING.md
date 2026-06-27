# Contributing to basis-console

Thank you for your interest in contributing. This document explains how to set up
a development environment, what quality gates must pass, and — most importantly —
the architectural boundaries every contribution must respect.

---

## Project Purpose

`basis-console` is part of the BASIS ecosystem, an open-source architecture for
identity-aware authorization in operational technology (OT) environments. The
console is the **human-facing interface layer**.

```
basis-core       evaluates authorization decisions
basis-gateway    authenticates, normalizes identity, composes, and enforces
basis-adapters   normalize protocol-specific operations into BASIS semantics
basis-console    observes, inspects, submits, and explains   ← this repository
```

The governing principle:

> **The console observes and operates the flow; it owns none of it.**

The console renders the authorization model and lets operators work with the
system **through the gateway**. That is the entire job. Everything else belongs
elsewhere in the ecosystem.

## Architectural Guardrails

These are hard boundaries, not preferences. A pull request that crosses any of
them will not be merged, regardless of code quality.

The console must **not**:

- evaluate authorization decisions or run any policy/role/condition logic
- call or import `basis-core` (the repository has no dependency on it)
- authenticate users, manage sessions, verify tokens, or become an identity
  provider (no OIDC/OAuth/SAML/SCIM implementation)
- parse or emit field protocols (BACnet, Modbus, MQTT, OPC UA, …)
- produce, store, or reinterpret canonical audit records, or define an audit
  schema
- own a resource inventory or perform device discovery
- bypass the gateway to reach the kernel directly
- reach the BASIS system through any egress other than the gateway client

The console must:

- reach the BASIS system **only through `basis-gateway`** (the
  `basis_console.gateway` package is the single egress point)
- degrade gracefully when the gateway is unreachable — never fall back to local
  authorization logic or cached decisions
- relay the gateway's response verbatim — never compute or reinterpret an outcome
- derive subject identity for live evaluation from the gateway's verified token,
  never from the form
- clearly label sample/explanatory data so it is never mistaken for live data
- redact credential-shaped fields before display
  (`basis_console.gateway.redaction`)
- keep presentation modes (`BASIS_CONSOLE_MODE`) presentation-only: operator and
  training must present the **same application**. Training mode may only *add*
  educational content — it must never move navigation, hide/add pages, relocate
  buttons, change workflows or routing, or expose functionality the other mode
  lacks. Mode-conditional markup may add explanatory copy, never gate a page,
  control, or behavior.

See [`docs/architecture.md`](docs/architecture.md) for the full set of boundaries
and design invariants.

## Local Setup

Requires Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Make Commands

```bash
make install     # editable install with dev extras
make test        # python -m pytest
make lint        # ruff check .
make format      # ruff format --check .
make typecheck   # mypy src (strict mode)
make check       # lint + format + typecheck + test
make run         # uvicorn dev server (honors HOST / PORT)
```

## Quality Gates

All four must pass before opening a pull request:

```bash
python -m pytest
ruff check .
ruff format --check .
mypy src
```

`make check` runs all four. Note that the type-checking gate is `mypy src`, not
`mypy .`.

## Branch Naming

Use a short, descriptive prefix:

```
feature/<short-description>     new capability or docs
fix/<short-description>         bug fix
docs/<short-description>        documentation-only change
```

Examples from this repository's history: `feature/operator-workspace`,
`feature/gateway-diagnostics`, `feature/resource-explorer`.

## Commit Messages

Follow the existing style: a conventional-commit-flavored summary line,
imperative mood, under ~72 characters.

```
feat: add operator workspace overview
fix: preserve form values on invalid simulator submission
docs: clarify the identity boundary on the simulate page
```

## Pull Request Expectations

- Keep PRs focused — one concern per PR.
- All quality gates pass locally (the PR template has a checklist).
- Tests accompany behavior changes.
- Update docs (`README.md`, `docs/architecture.md`, `CHANGELOG.md`) when the
  surfaces they describe change.
- Confirm the console boundaries are preserved.
- Do not commit generated artifacts (`__pycache__/`, `.venv/`, `.mypy_cache/`,
  `.ruff_cache/`, `.pytest_cache/` — see `.gitignore`).

## Out of Scope for the Console

Do not propose or include:

- authorization evaluation, policy logic, or any `basis-core` call/import
- user authentication, login, session management, or token verification
- an identity-provider implementation (OIDC/OAuth/SAML/SCIM)
- field-protocol parsing or live device communication
- a canonical audit store, audit schema, or persistent decision history
- a resource inventory, device discovery, or topology mapping
- new `basis-gateway` APIs invented by the console, or any gateway-bypass path

If a contribution needs any of these, it belongs in a different BASIS repository
(`basis-core`, `basis-gateway`, `basis-adapters`, or the future `basis-identity`).

## Questions

Open a GitHub issue. For suspected security problems, do **not** open a public
issue — see [SECURITY.md](SECURITY.md).
