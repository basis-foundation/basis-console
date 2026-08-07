"""HTTP client for basis-gateway.

The client maps gateway responses to typed result objects and never raises a
network error into its caller — every failure mode is represented as a status
value so UI routes and the readiness probe can render safely.

It does three things, all strictly through the gateway's HTTP surface:
  - ``check_status()`` probes ``/health`` and ``/ready`` for connectivity (Phase 2).
  - ``evaluate()`` submits an authorization request to ``POST /v1/evaluate`` and
    relays the gateway's decision verbatim (Phase 4). The console never evaluates
    locally, never imports ``basis-core``, and never reinterprets the decision.
  - ``evaluate_operation_aware()`` submits an operation-aware authorization
    request to ``POST /v1/evaluate/operation-aware`` and relays the kernel's
    governed result verbatim (Phase 16). Structurally distinct from
    ``evaluate()`` end to end — separate request/response/result models
    (``basis_console.gateway.operation_aware_models``), separate endpoint,
    separate status enum — sharing only this client and the redaction
    helpers. This PR adds the client capability only; no route or template
    calls it yet.

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
from basis_console.gateway.operation_aware_models import (
    OperationAwareEvaluationRequest,
    OperationAwareEvaluationResult,
    OperationAwareEvaluationState,
    OperationAwareEvaluationStatus,
    _OperationAwareContractError,
    _parse_operation_aware_response,
    _reconcile_correlation_id,
    _serialize_operation_aware_request,
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

    # ------------------------------------------------------------------
    # Phase 16 — operation-aware evaluation (contract + client only; no UI)
    # ------------------------------------------------------------------

    # HTTP statuses this endpoint uses for a *generic* (ungoverned) pre-kernel
    # condition when the response body carries no ``evaluation_status`` key.
    # 403 is deliberately absent: per the endpoint contract this endpoint
    # always returns a governed body on 403 (deny / not_applicable), so a 403
    # without one is a contract violation, not a recognized generic status —
    # see ``_interpret_operation_aware`` below.
    _OPERATION_AWARE_GENERIC_STATUS_MAP: dict[int, OperationAwareEvaluationStatus] = {
        400: OperationAwareEvaluationStatus.REQUEST_REJECTED,
        401: OperationAwareEvaluationStatus.UNAUTHORIZED,
        404: OperationAwareEvaluationStatus.CAPABILITY_UNAVAILABLE,
        503: OperationAwareEvaluationStatus.EVALUATOR_UNAVAILABLE,
        500: OperationAwareEvaluationStatus.GATEWAY_ERROR,
    }

    def evaluate_operation_aware(
        self, request: OperationAwareEvaluationRequest
    ) -> OperationAwareEvaluationResult:
        """Submit a request to ``POST /v1/evaluate/operation-aware``. Never raises.

        Structurally separate from ``evaluate()``: a distinct request model
        (``OperationAwareEvaluationRequest``, with no field for a subject,
        arbitrary context, or any trusted-producer-only field — the type
        surface makes those impossible to set), a distinct endpoint, and a
        distinct result/status model
        (``OperationAwareEvaluationResult``/``OperationAwareEvaluationStatus``).
        The gateway's governed result — ``evaluation_status``, ``outcome``,
        ``failure_reason``, ``disposition``, ``bundle_id``/``bundle_version``,
        ``reason_code``, ``explanation`` — is relayed verbatim; this method
        never reinterprets it, and never fabricates evidence the gateway did
        not return. ``request`` is never mutated (it is a frozen dataclass).
        """
        if self._base_url is None:
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.NOT_CONFIGURED
            )
        if self._bearer_token is None:
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.TOKEN_MISSING
            )

        body = _serialize_operation_aware_request(request)
        headers = {"Authorization": f"Bearer {self._bearer_token}"}

        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.post("/v1/evaluate/operation-aware", json=body, headers=headers)
        except httpx.TimeoutException as exc:
            # A timeout is a kind of unavailable; say so specifically. Token must not leak.
            log.warning(
                "Gateway operation-aware evaluation timed out at %s: %s", self._base_url, exc
            )
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.UNAVAILABLE,
                timed_out=True,
                detail=f"gateway did not respond within {self._timeout:g}s (timeout)",
            )
        except httpx.HTTPError as exc:
            # Connection refused, DNS failure, etc. Token must not leak.
            log.warning(
                "Gateway operation-aware evaluation could not contact %s: %s", self._base_url, exc
            )
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.UNAVAILABLE,
                detail=f"could not contact gateway: {exc}",
            )
        except Exception as exc:  # pragma: no cover - defensive catch-all
            log.error("Unexpected error during operation-aware evaluation: %s", exc)
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.GATEWAY_ERROR,
                detail=f"unexpected error: {exc}",
            )

        return self._interpret_operation_aware(response)

    @classmethod
    def _interpret_operation_aware(cls, response: httpx.Response) -> OperationAwareEvaluationResult:
        """Map an operation-aware HTTP response to a typed result. Never raises.

        Distinguishes a governed ``OperationAwareEvaluateResponse`` body from a
        generic pre-kernel ``ErrorResponse``/framework body by inspecting the
        body for an ``evaluation_status`` key — never by HTTP status code
        alone, since this endpoint's ``400``/``403``/``500``/``503`` can each
        carry either shape (per the endpoint contract's "status code does not
        determine body shape" nuance).
        """
        code = response.status_code
        headers = redact_headers(response.headers)
        header_corr = response.headers.get("X-Correlation-ID")

        parsed: object = None
        try:
            parsed = response.json()
        except Exception:
            parsed = None

        body: dict[str, object] | None = parsed if isinstance(parsed, dict) else None
        redacted_body = redact_json(body) if body is not None else None

        if body is not None and "evaluation_status" in body:
            try:
                # Correlation-ID reconciliation (body vs. X-Correlation-ID
                # header) happens inside the strict parse, as one contract
                # invariant among the others it checks — a disagreement
                # raises the same _OperationAwareContractError and aborts
                # parsing before any OperationAwareEvaluationResponse is
                # constructed.
                governed = _parse_operation_aware_response(body, header_corr)
            except _OperationAwareContractError as exc:
                # Never select either correlation value as authoritative on a
                # contract violation (which may be exactly this mismatch, or
                # an unrelated one) — the redacted body/headers already
                # preserve both raw values as diagnostic material.
                return OperationAwareEvaluationResult(
                    status=OperationAwareEvaluationStatus.CONTRACT_INVALID,
                    http_status=code,
                    detail=f"gateway response failed contract validation: {exc}",
                    response_json=redacted_body,
                    headers=headers,
                )

            status = (
                OperationAwareEvaluationStatus.EVALUATION_COMPLETED
                if governed.evaluation_status is OperationAwareEvaluationState.COMPLETED
                else OperationAwareEvaluationStatus.EVALUATION_FAILED
            )
            return OperationAwareEvaluationResult(
                status=status,
                http_status=code,
                response=governed,
                # Already the single reconciled value — body and header agree
                # by construction, or exactly one of them was present.
                correlation_id=governed.correlation_id,
                response_json=redacted_body,
                headers=headers,
            )

        # No governed body. This endpoint always returns a governed body on
        # 403 (deny / not_applicable) — a 403 without one is a contract
        # violation, not a recognized generic-error status.
        if code == 403:
            try:
                corr = _reconcile_correlation_id(
                    body.get("correlation_id") if body is not None else None, header_corr
                )
            except _OperationAwareContractError:
                corr = None
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.CONTRACT_INVALID,
                http_status=code,
                detail="HTTP 403 response carried no governed evaluation body",
                correlation_id=corr,
                response_json=redacted_body,
                headers=headers,
            )

        error_code = body.get("error") if body is not None else None
        error_message = body.get("message") if body is not None else None
        body_correlation_raw = body.get("correlation_id") if body is not None else None

        try:
            correlation_id = _reconcile_correlation_id(body_correlation_raw, header_corr)
        except _OperationAwareContractError as exc:
            # Same evidence-integrity rule as the governed path: a mismatch
            # between the body and header correlation id is a contract
            # violation, not a generic error to relay with a guessed value.
            return OperationAwareEvaluationResult(
                status=OperationAwareEvaluationStatus.CONTRACT_INVALID,
                http_status=code,
                detail=f"gateway response failed contract validation: {exc}",
                response_json=redacted_body,
                headers=headers,
            )

        status = cls._OPERATION_AWARE_GENERIC_STATUS_MAP.get(
            code, OperationAwareEvaluationStatus.GATEWAY_ERROR
        )

        return OperationAwareEvaluationResult(
            status=status,
            http_status=code,
            correlation_id=correlation_id,
            error_code=error_code if isinstance(error_code, str) else None,
            error_message=error_message if isinstance(error_message, str) else None,
            response_json=redacted_body,
            headers=headers,
        )
