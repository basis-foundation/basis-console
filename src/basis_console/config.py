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
_VALID_CONSOLE_MODES = {"operator", "training"}


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

    # Presentation mode. This is a UX/copy concern only — it changes how pages are
    # rendered and explained, never runtime behavior, architectural boundaries,
    # APIs, or capabilities.
    #
    #   operator (default) — professional, concise, operator-focused. Minimal
    #     educational banners; suitable for clean, operator-focused demos and
    #     screenshots.
    #   training            — educational. Adds a visible training banner, page
    #     "what this page teaches" callouts, and architecture explanations.
    #
    # The mode names the *audience* of the interface, not a deployment
    # environment. Both modes present the same application (same pages,
    # navigation, and workflows); training mode only adds explanatory copy and
    # is explicitly NOT a substitute for the operator view. Both keep
    # sample/live/future labels honest.
    basis_console_mode: Literal["operator", "training"] = Field(
        default="operator", alias="BASIS_CONSOLE_MODE"
    )

    # Base URL of the basis-gateway. Optional: when unset, the console reports
    # gateway status as "not_configured" and runs in sample-only mode. No public
    # URL is ever baked in — operators point this at their own gateway.
    gateway_base_url: str | None = Field(default=None, alias="GATEWAY_BASE_URL")

    # Timeout (seconds) for gateway reachability/readiness probes. Kept short so
    # an unreachable gateway degrades the status panel quickly rather than
    # blocking a page render. Must be > 0.
    gateway_timeout_seconds: float = Field(default=2.0, alias="GATEWAY_TIMEOUT_SECONDS", gt=0)

    # Optional server-side Bearer token for live gateway-backed simulation
    # (Phase 4). The gateway requires a verified Bearer token on /v1/evaluate and
    # derives subject identity from it. When set, the console sends this token as
    # the Authorization header on /v1/evaluate; when unset, live evaluation is
    # disabled and the simulator stays preview-only.
    #
    # Security: this value is for local/dev/operator-controlled environments. It
    # is never displayed in the UI, never written to logs, and never rendered in
    # any page. ``repr=False`` keeps it out of accidental object reprs. The
    # console is not an identity provider and does no OIDC login or token refresh.
    gateway_bearer_token: str | None = Field(default=None, alias="GATEWAY_BEARER_TOKEN", repr=False)

    @property
    def training_mode(self) -> bool:
        """True when the console is in educational/training presentation mode."""
        return self.basis_console_mode == "training"

    @property
    def operator_mode(self) -> bool:
        """True when the console is in the default operator presentation mode."""
        return self.basis_console_mode == "operator"

    @property
    def gateway_evaluation_enabled(self) -> bool:
        """True when live gateway evaluation can be attempted.

        Requires both a gateway base URL and a Bearer token, since the gateway
        rejects unauthenticated /v1/evaluate calls.
        """
        return bool(self.gateway_base_url) and bool(self.gateway_bearer_token)

    @field_validator("basis_console_mode", mode="before")
    @classmethod
    def validate_console_mode(cls, v: object) -> object:
        """Normalize and validate the presentation mode with a helpful error.

        Accepts any case/whitespace (e.g. ``Training``) and fails cleanly with a
        clear message listing the allowed values, rather than a generic enum
        error, so a typo'd ``BASIS_CONSOLE_MODE`` stops startup understandably.
        """
        if isinstance(v, str):
            candidate = v.strip().lower()
            if candidate not in _VALID_CONSOLE_MODES:
                raise ValueError(
                    f"Invalid BASIS_CONSOLE_MODE {v!r}. "
                    f"Must be one of: {', '.join(sorted(_VALID_CONSOLE_MODES))}"
                )
            return candidate
        return v

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
