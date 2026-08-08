# Release Checklist — v0.2.0

This document defines what must be true before a `v0.2.0` release of
`basis-console` is tagged. It is a gate, not a promise of a date.

**Current status: v0.2.0 release candidate.** The read-oriented, gateway-first
console — Home, Operator Workspace, Policy viewer, Decision Simulator (legacy
and operation-aware evaluation contracts), Audit Explorer, Identity & Access
Explorer, Resource Explorer, and Gateway Diagnostics — is feature-complete for
this release. The version in `pyproject.toml` is `0.2.0`. The console performs
no authorization evaluation, no authentication, and has no coupling to
`basis-core`.

> **Release readiness does not mean production readiness.** Tagging `v0.2.0`
> means the console's interaction patterns, boundaries, documentation, and
> quality gates are coherent and stable enough for early adopters to evaluate.
> It does not mean the console has been audited or hardened for live
> operational technology deployment. No production-readiness claims are made
> anywhere in this repository, and the release must not introduce any.

## Quality Gates

- [ ] All tests pass: `python -m pytest`
- [ ] Lint passes: `ruff check .`
- [ ] Format check passes: `ruff format --check .`
- [ ] Type check passes: `mypy src` (strict mode)
- [ ] `make check` runs all four cleanly

## Documentation

- [ ] `README.md` reviewed: quickstart, configuration table, run modes, page map,
      boundaries, and release status reflect the actual code.
- [ ] `docs/architecture.md` describes the console as it exists, including the
      operation-aware Phases 16–20.
- [ ] `docs/releases/v0.2.0.md` reviewed.
- [ ] `CHANGELOG.md` has an accurate, dated `## [0.2.0] - 2026-08-08` section,
      kept distinct from the preserved historical `## [0.1.0]` entry, scoped to
      changes introduced after `v0.1.1`; verify the release date matches the
      actual intended tag date before merging.
- [ ] `CHANGELOG.md`'s `[0.2.0]` comparison link targets
      `v0.1.1...v0.2.0` (the latest prior tag), and the historical `[0.1.0]`
      link reference is unchanged.
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

Follow [`docs/smoke-test.md`](smoke-test.md) and, for the operation-aware
contract specifically,
[`docs/testing/operation-aware-simulator-smoke-test.md`](testing/operation-aware-simulator-smoke-test.md).

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
- [ ] **Operation-aware preview verified** — request-shape preview renders
      without contacting the gateway; legacy-only controls (Subject ID, Subject
      type, Context) are HTML-disabled and server-reject a crafted value.
- [ ] **Operation-aware live scenarios** (require a gateway with
      `OPERATION_AWARE_ENABLED`) — see the dedicated smoke-test guide for the
      full outcome/failure/degraded-state matrix.

## Repository Hygiene

- [ ] No `__pycache__/`, `.venv/`, `.mypy_cache/`, `.ruff_cache/`,
      `.pytest_cache/`, or other generated artifacts are committed
      (`.gitignore` covers them; verify with `git ls-files`).
- [ ] No stray working files or local tooling output in the tree.
- [ ] Built sdist/wheel contain no test caches, virtual environments, secrets,
      `.env` files, or unrelated reference-repository content (verify with
      archive inspection, not just a successful build).

## Claims Discipline

- [ ] No claims that the console evaluates authorization, authenticates users,
      owns identity/audit/inventory, or speaks field protocols.
- [ ] No production-readiness claims.
- [ ] Sample data is labelled as sample everywhere it appears.
- [ ] No credential (`GATEWAY_BEARER_TOKEN`, raw `Authorization` header) is
      displayed, logged, or rendered.
- [ ] Version in `pyproject.toml` (`0.2.0`) matches the tag being prepared, and
      matches `src/basis_console/__init__.py:__version__` and the `uv.lock`
      self-entry.
- [ ] No future capability (trace retrieval, audit-event viewing, identity
      telemetry, arbitrary operation-aware context, caller-asserted subject or
      producer evidence) is described as already available.

## Architectural Integrity

- [ ] No `basis-core` dependency in `pyproject.toml`; no import of `basis-core`.
- [ ] The gateway client is the single egress; no invented gateway endpoint; no
      gateway-bypass path.
- [ ] Live evaluation derives the subject from the gateway token, not the form.
- [ ] The gateway's response is relayed verbatim, never recomputed.
- [ ] Legacy `/v1/evaluate` remains the default and unchanged; operation-aware
      is opt-in per request via `evaluation_type`.

## v0.2.0 Release Checklist

### Completed on the release branch

- [ ] Version set to `0.2.0` in `pyproject.toml`, `src/basis_console/__init__.py`,
      and `uv.lock`.
- [ ] `CHANGELOG.md` `## [0.2.0]` entry prepared.
- [ ] `docs/releases/v0.2.0.md` prepared.
- [ ] Documentation reviewed (`README.md`, `docs/architecture.md`,
      `SECURITY.md`, `docs/release-checklist.md`).
- [ ] Dependency review completed — no unjustified changes.
- [ ] Tests, lint, format, and mypy pass on the release branch.
- [ ] Documentation/link checks pass.
- [ ] Package build (sdist + wheel) passes.
- [ ] Archive contents inspected (wheel and sdist).
- [ ] Clean-environment installation passes; `pip check` clean.
- [ ] Import and application-factory smoke tests pass.
- [ ] Packaged templates/static assets verified present in the wheel.
- [ ] Local (non-gateway-dependent) smoke scenarios pass.

### Required after PR merge

- [ ] Update local `main`.
- [ ] Verify the merge commit.
- [ ] Rerun the final release checks on merged `main`.
- [ ] Create annotated tag `v0.2.0`.
- [ ] Push the tag.
- [ ] Create the GitHub release, using the reviewed `docs/releases/v0.2.0.md`
      as release notes.
- [ ] Verify the release page and that the tag points to the merged release
      commit.
- [ ] Verify no publication workflow failed (none is configured in this
      repository today — see "Release automation" below).
- [ ] Verify post-release installation instructions work against the tagged
      commit.
- [ ] Update any external project status only after the release is visible.

## Release automation

This repository has no tag-triggered CI workflow and no package-publication
automation as of `v0.2.0` (there is no `.github/workflows/` directory). Tagging
and publishing are manual, deliberate steps performed by a maintainer — not
automated by anything in this repository.

## Out of Scope for v0.2.0

Tagging `v0.2.0` explicitly does not require (and must not include): local
policy evaluation, arbitrary operation-aware caller context, caller-asserted
subject or producer identity, authenticated-subject details in the
operation-aware response, embedded evaluation traces, trace retrieval or
visualization, audit-event retrieval or viewing, identity telemetry,
southbound OT execution, a canonical audit store, a resource inventory,
field-protocol parsing, Docker/Kubernetes artifacts, or PyPI publishing
automation. Those are separate decisions for later phases.
