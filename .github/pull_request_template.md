# Pull Request

## Summary

<!-- What does this PR change, and why? One concern per PR. -->

## Type of Change

<!-- e.g. feature, fix, docs, UI copy, test-only -->

## Quality Gates

- [ ] `python -m pytest` passes
- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] `mypy src` passes

## Architectural Integrity

The console observes, inspects, submits (through the gateway), and explains. It
owns none of the authorization system. Confirm this PR does not cross any
boundary:

- [ ] No authorization evaluation / policy / role / condition logic added
- [ ] No direct `basis-core` call or import added (the repo has no `basis-core`
      dependency)
- [ ] No local authentication, login, session, or token verification added; no
      identity-provider logic (OIDC/OAuth/SAML/SCIM)
- [ ] No owned audit store, audit schema, or persistent decision history added
- [ ] No owned resource inventory, device discovery, or topology mapping added
- [ ] No field-protocol parsing or live device communication added
- [ ] Integration stays **gateway-first**: the gateway client is the only egress,
      no gateway endpoint is invented, and there is no gateway-bypass path
- [ ] The gateway's response is relayed verbatim (never recomputed or
      reinterpreted); live evaluation derives the subject from the gateway token,
      not the form
- [ ] Sample/explanatory data stays clearly labelled and is not presented as live
- [ ] No credential is displayed, logged, or rendered; redaction preserved

## Documentation

- [ ] Docs updated if behavior, configuration, or boundaries changed
      (`README.md`, `docs/architecture.md`, `CHANGELOG.md`) — or N/A

## Notes for Reviewer

<!-- Anything that needs extra attention, trade-offs made, follow-ups deferred. -->
