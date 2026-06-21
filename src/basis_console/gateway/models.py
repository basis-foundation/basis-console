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


class GatewayEvaluationStatus(str, Enum):
    """Outcome category of a console-initiated call to ``POST /v1/evaluate``.

    These categories describe *what the gateway returned*; the console never
    decides anything itself and never reinterprets the gateway's decision. The
    mapping is a straight read of the gateway's documented HTTP contract.

    NOT_CONFIGURED   No GATEWAY_BASE_URL is set; no call was attempted.
    TOKEN_MISSING    A base URL is set but no GATEWAY_BEARER_TOKEN is configured;
                     the gateway requires a Bearer token, so no call was attempted.
    SUCCESS          HTTP 200 — the gateway returned an ALLOW decision.
    DENIED           HTTP 403 — the gateway returned a DENY / NOT_APPLICABLE
                     decision. This is a normal gateway answer, not an error, and
                     is surfaced verbatim (never hidden).
    UNAUTHORIZED     HTTP 401 — the gateway rejected the token (missing/invalid).
    VALIDATION_ERROR HTTP 400 — the gateway rejected the request body.
    UNAVAILABLE      HTTP 503, or the gateway could not be contacted (connection
                     refused, DNS failure, timeout).
    GATEWAY_ERROR    HTTP 500 or any other unexpected status / response.
    """

    NOT_CONFIGURED = "not_configured"
    TOKEN_MISSING = "token_missing"
    SUCCESS = "success"
    DENIED = "denied"
    UNAUTHORIZED = "unauthorized"
    VALIDATION_ERROR = "validation_error"
    UNAVAILABLE = "unavailable"
    GATEWAY_ERROR = "gateway_error"


@dataclass(frozen=True)
class GatewayEvaluationResult:
    """Typed result of a console-initiated ``/v1/evaluate`` call.

    Every field is derived solely from the gateway's response (or the lack of
    one). The configured Bearer token is NEVER stored here, so this object is
    always safe to render. The console does not compute ``outcome`` — it only
    relays what the gateway returned.

    Fields
    ──────
    status          Outcome category (see GatewayEvaluationStatus).
    http_status     The HTTP status code returned, or None when no call was made
                    or the gateway could not be contacted.
    outcome         Decision string from the response body ("allow" / "deny" /
                    "not_applicable"), when present.
    reason          Gateway-provided reason for the decision, when present.
    policy_version  Policy version reported by the gateway, when present.
    request_id      Request id echoed by the gateway, when present.
    correlation_id  Correlation id from the body or X-Correlation-ID header.
    error_code      Machine-readable error code from an ErrorResponse body.
    error_message   Human-readable error message from an ErrorResponse body.
    detail          Console-side note for transport failures (no gateway body).
    response_json   The parsed response body, for raw display. Contains no token.
    """

    status: GatewayEvaluationStatus
    http_status: int | None = None
    outcome: str | None = None
    reason: str | None = None
    policy_version: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    detail: str | None = None
    response_json: dict[str, object] | None = None

    @property
    def called_gateway(self) -> bool:
        """True when an HTTP call to the gateway was actually attempted."""
        return self.status not in (
            GatewayEvaluationStatus.NOT_CONFIGURED,
            GatewayEvaluationStatus.TOKEN_MISSING,
        )
