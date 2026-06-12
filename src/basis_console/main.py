"""FastAPI application entrypoint for basis-console.

Lifespan (Phase 1):
  1. Load and validate configuration.  → marks "configuration_loaded"

The console renders read-only sample data in Phase 1 and does not contact the
gateway, so configuration is the only readiness component. The process always
serves ``/health`` (liveness); ``/ready`` returns 503 until configuration loads.

app.state holds:
  config — ConsoleConfig
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from basis_console.api.routes import router as api_router
from basis_console.config import configure_logging, load_config
from basis_console.readiness import get_readiness_state
from basis_console.ui.views import router as ui_router

log = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "ui" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown for basis-console."""
    state = get_readiness_state()
    try:
        config = load_config()
        configure_logging(config.log_level)
        app.state.config = config
        log.info(
            "basis-console starting service=%s env=%s host=%s port=%s gateway=%s",
            config.service_name,
            config.environment,
            config.host,
            config.port,
            config.gateway_base_url,
        )
        state.mark_ready("configuration_loaded")
        log.info("Configuration loaded; basis-console ready")
    except Exception as exc:  # pragma: no cover - defensive startup guard
        log.error("Startup failed [%s]: %s", type(exc).__name__, exc)
        state.mark_not_ready(reason=str(exc), component="configuration_loaded")
        # Still yield so /health responds; /ready returns 503.

    yield

    state.mark_not_ready(reason="application shutting down")
    log.info("basis-console shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="basis-console",
        description=(
            "Human-facing operational interface for the BASIS ecosystem. "
            "Read-only Phase 1 skeleton. Does not evaluate authorization or "
            "authenticate users."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    # Local static assets — no CDN dependency, works air-gapped.
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(api_router)
    app.include_router(ui_router)
    return app


app = create_app()
