# Manual Smoke Test

A quick, repeatable manual check that `basis-console` runs and that every page
renders in each supported mode. This is a human walkthrough, not an automated
suite — the automated suite is `python -m pytest`.

Pages to verify in every mode:

```
/            /workspace   /policies   /simulate
/audit       /identity    /resources  /gateway
```

Probes: `GET /health` (liveness) and `GET /ready` (readiness).

---

## 1. Sample-only mode (no gateway)

Start the console with **no** `GATEWAY_BASE_URL`:

```bash
# from the repository root, with the dev install active
make run
# or: uvicorn basis_console.main:app --host 127.0.0.1 --port 8080
```

Then verify:

- [ ] `GET /health` returns `200`.
- [ ] `GET /ready` returns `200` (the console is ready even with no gateway).
- [ ] **Home** (`/`) loads and the gateway status shows **`not_configured`**.
- [ ] **Workspace** (`/workspace`) loads; the readiness snapshot honestly shows
      the gateway is not configured and links to `/gateway`.
- [ ] **Policies** (`/policies`) loads with the sample-data notice.
- [ ] **Simulate** (`/simulate`) loads. Submitting a valid form renders a
      normalized request preview. The page states that gateway evaluation is not
      configured.
- [ ] **Audit** (`/audit`) loads with sample events and the sample-data notice.
- [ ] **Identity** (`/identity`) loads with the sample subject/claims notice.
- [ ] **Resources** (`/resources`) loads with the sample catalog notice.
- [ ] **Gateway** (`/gateway`) loads and explains that `GATEWAY_BASE_URL` must be
      set.

## 2. Gateway mode (`GATEWAY_BASE_URL` set)

First confirm a local `basis-gateway` is up:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health   # expect 200
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/ready    # expect 200
```

Then start the console pointed at it:

```bash
GATEWAY_BASE_URL=http://127.0.0.1:8000 make run
```

Verify:

- [ ] **Gateway Diagnostics** (`/gateway`) shows the gateway as configured and
      reachable/ready, with health, readiness components, and correlation IDs.
- [ ] **Home** (`/`) reflects the gateway connection state (`reachable` / `ready`).
- [ ] **Workspace** (`/workspace`) readiness snapshot reflects the live gateway
      state.
- [ ] If the gateway is then stopped, the console shows an honest **unreachable**
      state and does **not** fall back to any local authorization behavior.
- [ ] All other pages from section 1 still load.

## 3. Live evaluation mode (`GATEWAY_BEARER_TOKEN` required)

Live evaluation requires a verified bearer token, because the gateway derives the
subject identity from it and rejects unauthenticated `/v1/evaluate` calls. The
console does **no** OIDC login and **no** token issuance — obtain a token
out-of-band from the gateway's configured OIDC issuer.

```bash
GATEWAY_BASE_URL=http://127.0.0.1:8000 \
GATEWAY_BEARER_TOKEN="<token-obtained-out-of-band>" \
make run
```

Verify:

- [ ] **Without** a token (section 2 setup): the Simulate page stays preview-only
      and states that gateway evaluation requires a configured server-side bearer
      token.
- [ ] **With** a token: the Simulate page offers gateway-evaluation mode.
      Submitting with `mode=gateway` displays the gateway's decision verbatim
      (outcome, HTTP status, reason, policy version, correlation ID, raw JSON) and,
      when present, the gateway composition evidence.
- [ ] The token is never displayed, logged, or rendered anywhere in the UI.
- [ ] The form's subject fields are labelled preview-only; live evaluation sends
      no subject (identity comes from the token).

> If no token is available in your environment, sections 1 and 2 are sufficient
> to confirm the console runs and degrades honestly; section 3's first checkbox
> (the disabled-without-token behavior) can still be verified.
