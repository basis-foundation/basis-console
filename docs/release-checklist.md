# Release Checklist — v0.1.0

This document defines what must be true before a `v0.1.0` release of
`basis-console` is tagged. It is a gate, not a promise of a date.

**Current status: v0.1.0 release candidate.** The read-oriented, gateway-first
console — Home, Operator Workspace, Policy viewer, Decision Simulator, Audit
Explorer, Identity & Access Explorer, Resource Explorer, and Gateway Diagnostics —
is feature-complete for this release. The version in `pyproject.toml` is `0.1.0`.
The console performs no authorization evaluation, no authentication, and has no
coupling to `basis-core`.

> **Release readiness does not mean production readiness.** Tagging `v0.1.0` means
> the console's interaction patterns, boundaries, documentation, and quality gates
> are coherent and stable enough for early adopters to evaluate. It does not mean
> the console has been audited or hardened for live operational technology
> deployment. No production-readiness claims are made anywhere in this repository,
> and the release must not introduce any.

## Quality Gates

- [ ] All tests pass: `python -m pytest`
- [ ] Lint passes: `ruff check .`
- [ ] Format check passes: `ruff format --check .`
- [ ] Type check passes: `mypy src` (strict mode)
- [ ] `make check` runs all four cleanly

## Documentation

- [ ] `README.md` reviewed: quickstart, configuration table, run modes, page map,
      boundaries, and release status reflect the actual code.
- [ ] `docs/architecture.md` describes the console as it exists.
- [ ] `docs/releases/v0.1.0.md` reviewed.
- [ ] `CHANGELOG.md` has an accurate `## [0.1.0] - Unreleased` section.
- [ ] `SECURITY.md` reviewed: supported versions, reporting, console-does-not-
      authenticate / does-not-store-secrets, `GATEWAY_BEARER_TOKEN` is server-side
      only, do-not-expose-dev-server-publicly, production access-control guidance.
- [ ] `CONTRIBUTING.md` reviewed: setup, make commands, branch/PR expectations,
      boundaries, out-of-scope list.
- [ ] `LICENSE` reviewed and present (Apache-2.0); `pyproject.toml` license
      metadata matches.

## Screenshots

- [ ] Screenshots reviewed (README "Screenshots" section) — the section contains
      the actual `docs/images/*.png` captures (no placeholders); image paths are
      relative and resolve; no stale/misleading images.

## Smoke Tests

Follow [`docs/smoke-test.md`](smoke-test.md).

- [ ] Browser smoke test: every page renders without error.
- [ ] **Sample-only mode verified** — started with no `GATEWAY_BASE_URL`; Home
      shows `not_configured`; Workspace, Policies, Simulate, Audit, Identity,
      Resources, and Gateway pages all load.
- [ ] **`GATEWAY_BASE_URL` mode verified** — Gateway Diagnostics shows
      configured/reachable (or an honest unreachable state); Home and Workspace
      reflect gateway state.
- [ ] **Gateway smoke test** — `basis-gateway` `GET /health` and `GET /ready`
      return 200 and the console surfaces them.
- [ ] **`GATEWAY_BEARER_TOKEN` behavior documented** — when the token is absent,
      the simulator stays preview-only and says so; when present, gateway-backed
      evaluation is offered. (No token issuance is invented.)

## Repository Hygiene

- [ ] No `__pycache__/`, `.venv/`, `.mypy_cache/`, `.ruff_cache/`,
      `.pytest_cache/`, or other generated artifacts are committed
      (`.gitignore` covers them; verify with `git ls-files`).
- [ ] No stray working files or local tooling output in the tree.

## Claims Discipline

- [ ] No claims that the console evaluates authorization, authenticates users,
      owns identity/audit/inventory, or speaks field protocols.
- [ ] No production-readiness claims.
- [ ] Sample data is labelled as sample everywhere it appears.
- [ ] No credential (`GATEWAY_BEARER_TOKEN`, raw `Authorization` header) is
      displayed, logged, or rendered.
- [ ] Version in `pyproject.toml` (`0.1.0`) matches the tag being prepared.

## Architectural Integrity

- [ ] No `basis-core` dependency in `pyproject.toml`; no import of `basis-core`.
- [ ] The gateway client is the single egress; no invented gateway endpoint; no
      gateway-bypass path.
- [ ] Live evaluation derives the subject from the gateway token, not the form.
- [ ] The gateway's response is relayed verbatim, never recomputed.

## v0.1.0 Release Candidate Checklist

The remaining steps between this release candidate and a tag:

- [ ] Final pass of the four quality gates on `main` at the candidate commit.
- [ ] Confirm `git ls-files` shows no generated artifacts or stray files.
- [ ] Confirm the version in `pyproject.toml` (`0.1.0`) matches the tag to be
      created.
- [ ] Tag the release (separate, deliberate step — not automated by anything in
      this repository).

## Out of Scope for v0.1.0

Tagging `v0.1.0` explicitly does not require (and must not include): authorization
evaluation, a `basis-core` client, user authentication or an identity-provider
implementation, a canonical audit store, a resource inventory, field-protocol
parsing, Docker/Kubernetes artifacts, or PyPI publishing automation. Those are
separate decisions for later phases.
