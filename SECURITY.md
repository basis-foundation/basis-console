# Security Policy

## Project Status

`basis-console` is an early-stage project and a `v0.1.0` release candidate. It is
a **human-facing operational interface** for the BASIS ecosystem. It is
read-oriented and gateway-first: it observes, inspects, submits requests through
`basis-gateway`, and explains the authorization model. It does **not** evaluate
authorization decisions, authenticate users, own identity, store audit records,
or own resource inventory.

No claims of production readiness are made. This application has not been audited
and should not be exposed on an untrusted network in its current state.

## Supported Versions

Only the latest released version receives security fixes during the pre-`1.0`
period. There is no long-term-support branch yet.

| Version            | Supported          |
| ------------------ | ------------------ |
| `0.1.x` (latest)   | :white_check_mark: |
| `< 0.1.0`          | :x:                |

## Reporting a Vulnerability

Please do **not** report security issues through public GitHub issues.

Use GitHub's private vulnerability reporting on this repository
(**Security** tab → **Report a vulnerability**). If private reporting is not
available, contact the maintainer directly rather than disclosing publicly.

<!-- Maintainer: add a security contact email here when one exists. -->

Please include a description of the issue, steps to reproduce, and an assessment
of impact if you have one. You can expect an acknowledgment within a reasonable
timeframe; as an early-stage project there is no formal SLA yet.

## Security Model

The console's security posture follows directly from its boundaries:

- **The console does not authenticate users.** It has no login, no session
  management, and no credential store. It is not an identity provider and runs no
  OIDC/OAuth/SAML/SCIM flow. Authentication belongs to `basis-gateway` and the
  identity providers it trusts.
- **The console does not evaluate authorization.** It contains no policy logic
  and never imports `basis-core`. It cannot produce an allow/deny decision; it
  only relays the gateway's decision verbatim.
- **The console does not store secrets.** It persists nothing — no database, no
  secret store, no token cache. Configuration is read from environment variables
  at startup.
- **`GATEWAY_BEARER_TOKEN` is server-side configuration only.** When set, it is
  used solely to construct the `Authorization: Bearer <token>` header on the
  gateway's `POST /v1/evaluate` call. It is **never** displayed in the UI, written
  to logs, rendered in any page, or exposed via an object repr. The console does
  no OIDC login and no token refresh; a token is obtained out-of-band.
- **Defensive redaction.** Diagnostics, audit, and resource views run gateway
  payloads and headers through `basis_console.gateway.redaction` before display,
  so credential-shaped fields (`authorization`, `access_token`, `refresh_token`,
  `id_token`, `client_secret`, `password`, `secret`, cookies, bearer tokens, API
  keys) are redacted even if a future gateway change or misbehaving proxy returns
  one.

## Deployment Guidance

- **Do not expose the development server publicly.** `make run` /
  `uvicorn ...` binds to `127.0.0.1` by default. Do not bind the dev server to a
  public interface.
- **Production deployments must sit behind appropriate access controls.** Because
  the console performs no authentication of its own, any deployment reachable by
  more than a trusted operator must be fronted by a reverse proxy or gateway that
  enforces authentication and authorization (for example, an SSO-aware proxy),
  plus TLS termination.
- **Treat `GATEWAY_BEARER_TOKEN` as a secret.** Inject it through your platform's
  secret mechanism (environment from a secrets manager, not a committed file).
  Anyone who can reach a console configured with a token can submit evaluations
  as that token's subject.

## What Counts as a Security Issue Here

Reports are welcome for issues such as:

- **Secret leakage** — any path that displays, logs, or renders
  `GATEWAY_BEARER_TOKEN`, a raw `Authorization` header, or another credential, or
  a gap in the redaction helpers.
- **Boundary violation** — any code path that evaluates authorization locally,
  imports `basis-core`, authenticates a user, or otherwise crosses a documented
  console boundary.
- **Injection / unsafe rendering** — template-injection, XSS, or unsafe handling
  of operator input or gateway responses.
- **Misleading identity surface** — any path that appears to let a user submit an
  arbitrary subject as identity (live evaluation derives the subject from the
  gateway's verified token, never from the form).
- **Dependency vulnerabilities** — issues in development or runtime dependencies.

## Scope Notes

Issues in policy evaluation belong to `basis-core`; issues in authentication,
identity, token verification, or enforcement belong to `basis-gateway`. If you
are unsure which repository an issue belongs to, report it here and it will be
routed.
