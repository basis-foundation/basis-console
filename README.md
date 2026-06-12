# basis-console

`basis-console` is a human-facing operational interface for the BASIS ecosystem. It gives operators read-only visibility into policy state, authorization decisions, and audit activity, and it establishes the interaction patterns that later phases will connect to live data through `basis-gateway`.

This repository is at **Phase 1**: a small, runnable, read-only console skeleton. It renders sample data and establishes the project structure, configuration, and architectural boundaries. It does not yet integrate with the gateway.

```
basis-console is a human-facing operational interface.
It does not evaluate authorization decisions.
It does not authenticate users in Phase 1.
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

## Phase 1 scope

Implemented in this phase:

- **Health / status page** (`GET /`) and a JSON liveness probe (`GET /health`).
- **Readiness probe** (`GET /ready`) reporting per-component state.
- **Policy viewer** (`GET /policies`) — read-only placeholder backed by local sample data.
- **Decision simulator** (`GET /simulate`) — a placeholder form establishing the subject / resource / action pattern. It is intentionally not wired to the gateway.
- **Audit viewer** (`GET /audit`) — read-only placeholder backed by local sample data.
- Configuration, readiness tracking, server-rendered UI, and a test/lint/typecheck toolchain.

Explicitly **out of scope** for Phase 1 (later phases): authentication / OIDC login, user management, policy editing or saving, direct `basis-core` evaluation, gateway integration, adapter integration, deployment tooling (Docker, Kubernetes), metrics, multi-user sessions, and RBAC.

---

## Relationship to the ecosystem

The console preserves BASIS layering. Operator actions flow through the console to the gateway, and the gateway enforces the appropriate boundary before reaching the kernel:

```
Operator → basis-console → basis-gateway → basis-core
```

**Relationship to `basis-gateway`.** The gateway is the console's primary operational dependency. Everything the console surfaces — policy state, decision history, audit records, system status — it obtains through gateway APIs. The console must degrade gracefully when the gateway is unreachable and must never fall back to local authorization logic or cached decisions. (Phase 1 does not contact the gateway; it renders sample data only.)

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

| Variable           | Default                  | Purpose                                                        |
| ------------------ | ------------------------ | -------------------------------------------------------------- |
| `HOST`             | `127.0.0.1`              | Bind address. Set `0.0.0.0` (or a specific interface) behind a reverse proxy. |
| `PORT`             | `8080`                   | Bind port.                                                     |
| `LOG_LEVEL`        | `INFO`                   | One of DEBUG, INFO, WARNING, ERROR, CRITICAL.                  |
| `ENVIRONMENT`      | `local`                  | One of local, development, staging, production.                |
| `GATEWAY_BASE_URL` | `http://localhost:8000`  | Base URL of the gateway the console will use in a later phase. Not contacted in Phase 1. |
| `SERVICE_NAME`     | `basis-console`          | Service name reported by health/readiness.                     |

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
    sample_data.py     # read-only SAMPLE data for Phase 1 views
    api/routes.py      # /health, /ready (JSON)
    ui/views.py        # /, /policies, /simulate, /audit (HTML)
    ui/templates/      # Jinja2 templates
    ui/static/         # locally served CSS (no CDN)
  tests/               # health, route-render, and config tests
  docs/architecture.md # console boundaries and Phase 1 notes
  pyproject.toml
  Makefile
  README.md
```
