"""HTTP client for basis-gateway.

The client maps gateway responses to typed result objects and never raises a
network error into its caller — every failure mode is represented as a status
value so UI routes and the readiness probe can render safely.

It does two things, both strictly through the gateway's HTTP surface:
  - ``check_status()`` probes ``/health`` and ``/ready`` for connectivity (Phase 2).
  - ``evaluate()`` submits an authorization request to ``POST /v1/evaluate`` and
    relays the gateway's decision verbatim (Phase 4). The console never evaluates
    locally, never imports ``basis-core``, and never reinterprets the decision.

Gateway-owned composition: the gateway is the action/resource composition
boundary. ``evaluate()`` submits a *normalized* request — a bare ``action`` verb
plus a ``resource_type`` and a *local* ``resource_id`` — and the gateway composes
the canonical kernel action (``{verb}:{resource_type}``) and the typed resource
id (``{resource_type}:{local_id}``). A fully-typed (direct) request omits
``resource_type``. The console never composes those canonical strings itself.

Identity boundary: the gateway derives subject identity exclusively from the
verified Bearer token and rejects caller-supplied subject fields. ``evaluate()``
therefore sends only ``action`` / ``resource_type`` / ``resource_id`` /
``context`` and never a subject. The configured Bearer token is sent only as the
``Authorization`` header; it is never logged, returned, or stored on any result
object.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from basis_console.gateway.models import (
    GatewayEvaluationResult,
    GatewayEvaluationStatus,
    GatewayProbeResult,
    GatewayStatus,
    GatewayStatusReport,
)
from basis_console.gateway.redaction import redact_headers, redact_json

log = logging.getLogger(__name__)


def _elapsed_ms(started: float) -> float:
    """Milliseconds elapsed since a ``time.perf_counter()`` mark, rounded to 1dp."""
    return round((time.perf_counter() - started) * 1000.0, 1)


class GatewayClient:
    """Talks to basis-gateway's HTTP surface and returns typed results.

    Parameters
    ──────────
    base_url       Gateway base URL, or None when not configured.
    timeout        Per-request timeout in seconds.
    bearer_token   Optional server-side Bearer token used only as the
                   ``Authorization`` header on ``evaluate()``. Never logged or
                   rendered. Absent → live evaluation is disabled.
    transport      Optional httpx transport. Used by tests to inject mock
                   responses; production leaves it None to use the real network.
    """

    def __init__(
        self,
        base_url: str | None,
        timeout: float = 2.0,
        *,
        bearer_token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._timeout = timeout
        # Stored privately and never exposed via a property, repr, or result.
        self._bearer_token = bearer_token or None
        self._transport = transport

    @property
    def base_url(self) -> str | None:
        return self._base_url

    @property
    def configured(self) -> bool:
        return self._base_url is not None

    @property
    def has_token(self) -> bool:
        """True when a Bearer token is configured. Never exposes the token itself."""
        return self._bearer_token is not None

    @property
    def evaluation_enabled(self) -> bool:
        """True when live evaluation can be attempted (base URL + token present)."""
        return self.configured and self.has_token

    def check_status(self) -> GatewayStatusReport:
        """Probe the gateway and return a typed status report. Never raises."""
        if self._base_url is None:
            return GatewayStatusReport(status=GatewayStatus.NOT_CONFIGURED)

        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                return self._probe(client)
        except httpx.TimeoutException as exc:
            # A timeout is a kind of unreachable, but say so specifically.
            log.warning("Gateway timed out at %s: %s", self._base_url, exc)
            return GatewayStatusReport(
                status=GatewayStatus.UNREACHABLE,
                base_url=self._base_url,
                configured=True,
                detail=f"gateway did not respond within {self._timeout:g}s (timeout)",
            )
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, etc.
            log.warning("Gateway unreachable at %s: %s", self._base_url, exc)
            return GatewayStatusReport(
                status=GatewayStatus.UNREACHABLE,
                base_url=self._base_url,
                configured=True,
                detail=f"could not contact gateway: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive catch-all
            log.error("Unexpected error probing gateway %s: %s", self._base_url, exc)
            return GatewayStatusReport(
                status=GatewayStatus.ERROR,
                base_url=self._base_url,
                configured=True,
                detail=f"unexpected error: {exc}",
            )

    def _probe(self, client: httpx.Client) -> GatewayStatusReport:
        # 1. Liveness: /health must answer 200.
        health = client.get("/health")
        if health.status_code != 200:
            return GatewayStatusReport(
                status=GatewayStatus.ERROR,
                base_url=self._base_url,
                configured=True,
                detail=f"/health returned HTTP {health.status_code}",
            )

        # 2. Readiness: /ready is informational. 200 → ready; anything else (incl.
        #    503 or a read error) means the gateway is up but not ready.
        try:
            ready = client.get("/ready")
        except httpx.HTTPError as exc:
            return GatewayStatusReport(
                status=GatewayStatus.REACHABLE,
                base_url=self._base_url,
                configured=True,
                reachable=True,
                detail=f"/health ok; /ready probe failed: {exc}",
            )

        if ready.status_code == 200:
            return GatewayStatusReport(
                status=GatewayStatus.READY,
                base_url=self._base_url,
                configured=True,
                reachable=True,
                ready=True,
            )

        return GatewayStatusReport(
            status=GatewayStatus.REACHABLE,
            base_url=self._base_url,
            configured=True,
            reachable=True,
            detail=f"/health ok; /ready returned HTTP {ready.status_code}",
        )

    # ------------------------------------------------------------------
    # Phase 9 — operational diagnostics probes
    # ------------------------------------------------------------------
    # These probe the SAME real gateway endpoints as check_status() (/health and
    # /ready) but capture the raw, redacted outcome of each call for the Gateway
    # Diagnostics view. They invent no endpoints and never raise into a route.

    def get_health(self) -> GatewayProbeResult:
        """Probe ``GET /health`` and capture the raw, redacted result. Never raises."""
        return self._diagnostic_probe("/health")

    def get_ready(self) -> GatewayProbeResult:
        """Probe ``GET /ready`` and capture the raw, redacted result. Never raises."""
        return self._diagnostic_probe("/ready")

    def _diagnostic_probe(self, endpoint: str) -> GatewayProbeResult:
        checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if self._base_url is None:
            return GatewayProbeResult(
                endpoint=endpoint,
                target_url=None,
                checked_at=checked_at,
                not_configured=True,
            )

        target_url = f"{self._base_url}{endpoint}"
        started = time.perf_counter()
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.get(endpoint)
        except httpx.TimeoutException as exc:
            log.warning("Gateway diagnostic probe of %s timed out: %s", target_url, exc)
            return GatewayProbeResult(
                endpoint=endpoint,
                target_url=target_url,
                checked_at=checked_at,
                reached=False,
                timed_out=True,
                latency_ms=_elapsed_ms(started),
                error=f"gateway did not respond within {self._timeout:g}s (timeout)",
            )
        except httpx.HTTPError as exc:
            log.warning("Gateway diagnostic probe of %s failed: %s", target_url, exc)
            return GatewayProbeResult(
                endpoint=endpoint,
                target_url=target_url,
                checked_at=checked_at,
                reached=False,
                latency_ms=_elapsed_ms(started),
                error=f"could not contact gateway: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive catch-all
            log.error("Unexpected error probing %s: %s", target_url, exc)
            return GatewayProbeResult(
                endpoint=endpoint,
                target_url=target_url,
                checked_at=checked_at,
                reached=False,
                error=f"unexpected error: {exc}",
            )

        return self._build_probe_result(
            endpoint, target_url, checked_at, response, _elapsed_ms(started)
        )

    @staticmethod
    def _build_probe_result(
        endpoint: str,
        target_url: str,
        checked_at: str,
        response: httpx.Response,
        latency_ms: float | None = None,
    ) -> GatewayProbeResult:
        """Map an HTTP response to a redacted ``GatewayProbeResult``. Never raises."""
        body: dict[str, Any] | None = None
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                # Redact defensively before the body is ever stored or rendered.
                body = redact_json(parsed)
        except Exception:
            body = None

        headers = redact_headers(response.headers)
        correlation_id = response.headers.get("X-Correlation-ID")

        return GatewayProbeResult(
            endpoint=endpoint,
            target_url=target_url,
            checked_at=checked_at,
            reached=True,
            http_status=response.status_code,
            ok=response.status_code == 200,
            response_json=body,
            headers=headers,
            correlation_id=correlation_id,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Phase 4 — live evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        *,
        action: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        context: dict[str, str] | None = None,
    ) -> GatewayEvaluationResult:
        """Submit an authorization request to ``POST /v1/evaluate``. Never raises.

        Only ``action`` / ``resource_type`` / ``resource_id`` / ``context`` are
        sent — never a subject, because the gateway derives identity from the
        Bearer token. In the normalized shape the gateway composes the canonical
        action and resource id from ``resource_type``; a direct (fully-typed)
        request omits ``resource_type``. The gateway's decision is relayed
        verbatim; this method does not reinterpret an ALLOW/DENY result, it only
        classifies the HTTP response for display.
        """
        if self._base_url is None:
            return GatewayEvaluationResult(status=GatewayEvaluationStatus.NOT_CONFIGURED)
        if self._bearer_token is None:
            return GatewayEvaluationResult(status=GatewayEvaluationStatus.TOKEN_MISSING)

        body: dict[str, Any] = {"action": action}
        if resource_type:
            body["resource_type"] = resource_type
        if resource_id:
            body["resource_id"] = resource_id
        if context:
            body["context"] = context

        headers = {"Authorization": f"Bearer {self._bearer_token}"}

        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.post("/v1/evaluate", json=body, headers=headers)
        except httpx.TimeoutException as exc:
            # A timeout is a kind of unavailable; say so specifically. Token must not leak.
            log.warning("Gateway evaluation timed out at %s: %s", self._base_url, exc)
            return GatewayEvaluationResult(
                status=GatewayEvaluationStatus.UNAVAILABLE,
                timed_out=True,
                detail=f"gateway did not respond within {self._timeout:g}s (timeout)",
            )
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, etc. Token must not leak.
            log.warning("Gateway evaluation could not contact %s: %s", self._base_url, exc)
            return GatewayEvaluationResult(
                status=GatewayEvaluationStatus.UNAVAILABLE,
                detail=f"could not contact gateway: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive catch-all
            log.error("Unexpected error during gateway evaluation: %s", exc)
            return GatewayEvaluationResult(
                status=GatewayEvaluationStatus.GATEWAY_ERROR,
                detail=f"unexpected error: {exc}",
            )

        return self._interpret_evaluation(response)

    @staticmethod
    def _interpret_evaluation(response: httpx.Response) -> GatewayEvaluationResult:
        """Map an /v1/evaluate HTTP response to a typed result. Never raises."""
        code = response.status_code

        body: dict[str, object] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except Exception:
            body = {}

        def _s(key: str) -> str | None:
            value = body.get(key)
            return value if isinstance(value, str) else None

        header_corr = response.headers.get("X-Correlation-ID")
        correlation_id = _s("correlation_id") or header_corr

        status_map = {
            200: GatewayEvaluationStatus.SUCCESS,
            403: GatewayEvaluationStatus.DENIED,
            401: GatewayEvaluationStatus.UNAUTHORIZED,
            400: GatewayEvaluationStatus.VALIDATION_ERROR,
            503: GatewayEvaluationStatus.UNAVAILABLE,
        }
        status = status_map.get(code, GatewayEvaluationStatus.GATEWAY_ERROR)

        return GatewayEvaluationResult(
            status=status,
            http_status=code,
            outcome=_s("outcome"),
            reason=_s("reason"),
            policy_version=_s("policy_version"),
            request_id=_s("request_id"),
            correlation_id=correlation_id,
            error_code=_s("error"),
            error_message=_s("message"),
            response_json=body or None,
        )
