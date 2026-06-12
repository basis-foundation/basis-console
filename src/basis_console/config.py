"""Configuration loading and validation for basis-console.

All configuration is sourced from environment variables with safe local-dev
defaults. The console is designed to run anywhere — cloud, on-prem, or
air-gapped — so every value that could tie it to a specific deployment is
configurable and nothing is hardcoded to a public URL or SaaS endpoint.

Phase 1 deployment constraints honored here:
  - configurable bind host and port (HOST / PORT)
  - configurable gateway base URL (GATEWAY_BASE_URL) — not contacted yet
  - no mandatory internet access, no required SaaS services
  - no hardcoded cloud dependencies or public URLs
"""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class ConsoleConfig(BaseSettings):  # type: ignore[misc]
    """Runtime configuration for basis-console.

    Loaded from environment variables at startup. Defaults are safe for local
    development and do not assume any cloud or internet dependency.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=False,
        populate_by_name=True,
    )

    service_name: str = Field(default="basis-console")

    # Bind address. Defaults to loopback so a fresh checkout does not expose the
    # console on all interfaces by accident. Operators set HOST=0.0.0.0 (or a
    # specific interface) when fronting the console with a reverse proxy.
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8080, alias="PORT", ge=1, le=65535)

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: Literal["local", "development", "staging", "production"] = Field(
        default="local", alias="ENVIRONMENT"
    )

    # Base URL of the basis-gateway this console will eventually talk to. It is
    # NOT contacted in Phase 1 — the console renders sample data only — but the
    # value is configurable from day one so no public URL is ever baked in.
    gateway_base_url: str = Field(default="http://localhost:8000", alias="GATEWAY_BASE_URL")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        upper = v.upper()
        if upper not in _VALID_LOG_LEVELS:
            raise ValueError(
                f"Invalid LOG_LEVEL {v!r}. Must be one of: {', '.join(sorted(_VALID_LOG_LEVELS))}"
            )
        return upper


def load_config() -> ConsoleConfig:
    """Load and validate console configuration from environment variables."""
    return ConsoleConfig()


def configure_logging(log_level: str) -> None:
    """Configure root logging at the specified level."""
    numeric = getattr(logging, log_level, logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
