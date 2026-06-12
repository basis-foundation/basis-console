"""HTTP client for probing basis-gateway connectivity.

The client is intentionally tiny. It probes ``/health`` and ``/ready`` and maps
the outcome to a :class:`GatewayStatusReport`. It never raises a network error
into its caller — every failure mode is represented as a status value so UI
routes and the readiness probe can render safely.

Phase 2 deliberately stops here. It does not call ``/v1/evaluate`` and does not
read policy or audit data; the gateway does not expose console-facing APIs for
those yet, and inventing them would violate the gateway-first boundary.
"""

from __future__ import annotations

import logging

import httpx

from basis_console.gateway.models import GatewayStatus, GatewayStatusReport

log = logging.getLogger(__name__)


class GatewayClient:
    """Probes basis-gateway operational endpoints and reports connection status.

    Parameters
    ──────────
    base_url   Gateway base URL, or None when not configured.
    timeout    Per-request timeout in seconds.
    transport  Optional httpx transport. Used by tests to inject mock responses;
               production code leaves it None to use the real network transport.
    """

    def __init__(
        self,
        base_url: str | None,
        timeout: float = 2.0,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") if base_url else None
        self._timeout = timeout
        self._transport = transport

    @property
    def base_url(self) -> str | None:
        return self._base_url

    @property
    def configured(self) -> bool:
        return self._base_url is not None

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
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, timeout, etc.
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
