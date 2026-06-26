"""Typed status model for gateway connectivity checks.

These structures describe *connectivity* to ``basis-gateway`` — whether it is
configured, reachable, and ready. They deliberately model nothing about policy,
audit, or decision data; the console does not interpret authorization state.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from enum import Enum
from typing import Any

# Prefix the gateway uses for the composition evidence it records when it composes
# a canonical action / resource id from a normalized request. The console only
# *reads* these keys for display; it never sets them (the gateway rejects
# caller-supplied ``basis_gateway.*`` keys).
GATEWAY_EVIDENCE_PREFIX = "basis_gateway."


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


@dataclass(frozen=True)
class GatewayProbeResult:
    """Result of a single diagnostic probe of a gateway operational endpoint.

    Captured for the Gateway Diagnostics view (``/gateway``). Unlike
    :class:`GatewayStatusReport`, which summarizes overall connectivity, this
    records the *raw* outcome of one ``GET`` so an operator can inspect exactly
    what the gateway returned. Every field is derived solely from the gateway's
    response (or the lack of one); no secret is ever stored here — headers and
    body are redacted defensively before they reach this object.

    Fields
    ──────
    endpoint        The probed path (e.g. ``/health`` or ``/ready``).
    target_url      The full URL probed, or None when the gateway is unconfigured.
    checked_at      ISO-8601 UTC timestamp of when the probe ran.
    not_configured  True when no base URL is set; no request was attempted.
    reached         True when an HTTP response was received.
    http_status     The HTTP status code returned, or None when not reached.
    ok              True when ``http_status`` is 200.
    response_json   The parsed (and redacted) response body, when JSON.
    headers         Selected, redacted response headers (lowercased keys).
    correlation_id  The ``X-Correlation-ID`` response header, when present.
    latency_ms      Round-trip time of the probe in milliseconds, when measured
                    (on a completed request or a timed-out/failed attempt).
    timed_out       True when the probe failed specifically because the gateway
                    did not respond within the configured timeout.
    error           Transport error message when the gateway could not be reached.
    """

    endpoint: str
    target_url: str | None = None
    checked_at: str = ""
    not_configured: bool = False
    reached: bool = False
    http_status: int | None = None
    ok: bool = False
    response_json: dict[str, Any] | None = None
    headers: dict[str, str] = dataclass_field(default_factory=dict)
    correlation_id: str | None = None
    latency_ms: float | None = None
    timed_out: bool = False
    error: str | None = None


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


# Operator-facing, one-line explanation of each evaluation outcome category. These
# describe *what the gateway returned* (or why no call was made); the console never
# decides anything itself. Kept here next to the enum so the explanation and the
# status it describes cannot drift apart.
EVALUATION_STATE_EXPLANATIONS: dict[GatewayEvaluationStatus, str] = {
    GatewayEvaluationStatus.NOT_CONFIGURED: (
        "No gateway base URL is configured, so no evaluation was attempted. Set "
        "GATEWAY_BASE_URL to a running basis-gateway to enable live evaluation."
    ),
    GatewayEvaluationStatus.TOKEN_MISSING: (
        "No server-side bearer token is configured. The gateway requires a verified "
        "Bearer token on /v1/evaluate and derives the subject from it, so live "
        "evaluation is disabled until GATEWAY_BEARER_TOKEN is set."
    ),
    GatewayEvaluationStatus.SUCCESS: (
        "The gateway evaluated the request and returned an ALLOW decision (HTTP 200). "
        "The console relays this verbatim and never recomputes it."
    ),
    GatewayEvaluationStatus.DENIED: (
        "The gateway returned a DENY / NOT_APPLICABLE decision (HTTP 403). This is a "
        "normal gateway answer shown verbatim — not a console or transport error."
    ),
    GatewayEvaluationStatus.UNAUTHORIZED: (
        "The gateway rejected the bearer token (HTTP 401 — missing, expired, or "
        "invalid). Check GATEWAY_BEARER_TOKEN against the gateway's OIDC issuer; the "
        "console issues no tokens of its own."
    ),
    GatewayEvaluationStatus.VALIDATION_ERROR: (
        "The gateway rejected the request body (HTTP 400). The action or resource "
        "shape did not satisfy the gateway/kernel contract; the gateway composes the "
        "canonical action and resource id and validates them."
    ),
    GatewayEvaluationStatus.UNAVAILABLE: (
        "The gateway could not be reached or reported itself unavailable (HTTP 503, a "
        "connection error, or a timeout). The console surfaces no decision and never "
        "falls back to local authorization."
    ),
    GatewayEvaluationStatus.GATEWAY_ERROR: (
        "The gateway returned an unexpected status or response. The console relays "
        "this without reinterpreting it."
    ),
}


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
    timed_out       True when the call failed specifically because the gateway did
                    not respond within the configured timeout.
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
    timed_out: bool = False
    response_json: dict[str, object] | None = None

    @property
    def called_gateway(self) -> bool:
        """True when an HTTP call to the gateway was actually attempted."""
        return self.status not in (
            GatewayEvaluationStatus.NOT_CONFIGURED,
            GatewayEvaluationStatus.TOKEN_MISSING,
        )

    @property
    def explanation(self) -> str:
        """A plain, operator-facing explanation of this outcome category.

        Reads the gateway's outcome; it never reinterprets an ALLOW/DENY decision.
        Returns an empty string only for an unknown status (should not happen).
        """
        return EVALUATION_STATE_EXPLANATIONS.get(self.status, "")

    @property
    def composition_evidence(self) -> dict[str, object]:
        """Any ``basis_gateway.*`` composition evidence found in the response.

        When the gateway composes a canonical action / resource id from a
        normalized request it records evidence under keys prefixed with
        ``basis_gateway.`` (e.g. ``basis_gateway.composed_resource_id``). The
        gateway may surface these at the top level of the response body or nested
        under a ``context`` / ``evidence`` object; this scans both and returns the
        flattened mapping for display. Empty when no such evidence is present —
        the console never fabricates composition evidence.
        """
        if not self.response_json:
            return {}

        found: dict[str, object] = {}

        def _collect(obj: Any) -> None:
            if not isinstance(obj, dict):
                return
            for key, value in obj.items():
                if isinstance(key, str) and key.startswith(GATEWAY_EVIDENCE_PREFIX):
                    found[key] = value

        _collect(self.response_json)
        for nested_key in ("context", "evidence"):
            _collect(self.response_json.get(nested_key))
        return found
