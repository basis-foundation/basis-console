"""Typed status model for gateway connectivity checks.

These structures describe *connectivity* to ``basis-gateway`` — whether it is
configured, reachable, and ready. They deliberately model nothing about policy,
audit, or decision data; the console does not interpret authorization state.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GatewayStatus(str, Enum):
    """Connection state between the console and basis-gateway.

    NOT_CONFIGURED  No GATEWAY_BASE_URL is set. The console runs in sample-only
                    mode and makes no gateway calls.
    REACHABLE       The gateway answered /health, but is not (yet) ready — e.g.
                    /ready returned 503 or the readiness probe could not be read.
    READY           The gateway answered both /health and /ready successfully.
    UNREACHABLE     The gateway is configured but could not be contacted
                    (connection refused, DNS failure, timeout).
    ERROR           The gateway was contacted but responded unexpectedly
                    (e.g. /health returned a non-200 status).
    """

    NOT_CONFIGURED = "not_configured"
    REACHABLE = "reachable"
    READY = "ready"
    UNREACHABLE = "unreachable"
    ERROR = "error"


@dataclass(frozen=True)
class GatewayStatusReport:
    """Result of a gateway connectivity check.

    Fields
    ──────
    status      Overall connection state (see GatewayStatus).
    base_url    The configured gateway base URL, or None when not configured.
    configured  True when a base URL is set.
    reachable   True when the gateway answered /health with 200.
    ready       True when the gateway answered /ready with 200.
    detail      Optional human-readable context (error text, status codes).
    """

    status: GatewayStatus
    base_url: str | None = None
    configured: bool = False
    reachable: bool = False
    ready: bool = False
    detail: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize for JSON responses (e.g. /ready)."""
        return {
            "status": self.status.value,
            "base_url": self.base_url,
            "configured": self.configured,
            "reachable": self.reachable,
            "ready": self.ready,
            "detail": self.detail,
        }
