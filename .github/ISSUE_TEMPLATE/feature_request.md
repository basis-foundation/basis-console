---
name: Feature request
about: Propose a new capability or improvement for the console
title: ""
labels: enhancement
assignees: ""
---

## What Are You Proposing

<!-- A new view, an improvement to an existing page, better explanation/copy,
     or a new way to display data the gateway already provides. -->

## Scope Check (console boundaries)

The console observes, inspects, submits through the gateway, and explains. It
owns none of the authorization system. Requests that involve any of the
following belong in a different BASIS repository, **not** the console:

- authorization evaluation, policy logic, or calling/importing `basis-core`
- user authentication, login, sessions, token verification, or identity-provider
  logic (OIDC/OAuth/SAML/SCIM)
- a canonical audit store, audit schema, or persistent decision history
- a resource inventory, device discovery, or topology mapping
- field-protocol parsing or live device communication
- inventing a `basis-gateway` endpoint or any gateway-bypass path

- [ ] I've confirmed this request is within the console's (observe / inspect /
      submit-through-gateway / explain) scope

## How It Should Behave

<!-- Which route(s)? What does the operator see? What live vs. sample data is
     involved? Does it need a gateway endpoint that exists today? -->

## Why It Matters

<!-- Use case, who benefits, what it makes legible or easier to operate. -->
