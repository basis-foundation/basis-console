# basis-console

`basis-console` is a human-facing operational interface for the BASIS ecosystem. It gives operators read-only visibility into policy state, authorization decisions, and audit activity, and it establishes the interaction patterns that later phases will connect to live data through `basis-gateway`.

This repository is at **Phase 2**: the read-only skeleton plus a gateway client abstraction and a gateway connection-status display. The console can now report whether `basis-gateway` is configured, reachable, and ready — but it still does not consume live policy, audit, or decision APIs, and it never evaluates authorization itself.

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

**Phase 2 (gateway status — this phase):**

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

Explicitly **out of scope** (later phases): authentication / OIDC login, user sessions, token storage, calling `/v1/evaluate`, live policy / audit / decision integration, adapter integration, deployment tooling (Docker, Kubernetes), metrics, multi-user sessions, and RBAC.

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
| `GATEWAY_TIMEOUT_SECONDS` | `2.0`           | Timeout for gateway `/health` and `/ready` probes. Must be > 0. |
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
    sample_data.py     # read-only SAMPLE data for placeholder views
    gateway/           # gateway client abstraction (Phase 2)
      client.py        #   httpx-based /health + /ready probe
      models.py        #   GatewayStatus enum + typed status report
    api/routes.py      # /health, /ready (JSON, incl. gateway state)
    ui/views.py        # /, /policies, /simulate, /audit (HTML)
    ui/templates/      # Jinja2 templates
    ui/static/         # locally served CSS (no CDN)
  tests/               # health, routes, config, and gateway tests
  docs/architecture.md # console boundaries and Phase 1 notes
  pyproject.toml
  Makefile
  README.md
```
