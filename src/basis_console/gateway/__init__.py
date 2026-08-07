"""Gateway client abstraction for basis-console.

This package is the console's single point of contact with ``basis-gateway``:
  - Phase 2: probe ``/health`` and ``/ready`` and report a typed connection
    status.
  - Phase 4: submit an authorization request to ``POST /v1/evaluate`` and relay
    the gateway's decision verbatim, when a base URL and Bearer token are
    configured.
  - Phase 16: submit an operation-aware authorization request to
    ``POST /v1/evaluate/operation-aware`` and relay the kernel's governed
    result verbatim, via a request/response/result contract kept structurally
    separate from the legacy path above. Client capability only in this
    phase — no route, template, or navigation consumes it yet.

Invariants:
  - The console reaches the authorization system only through the gateway; this
    module never imports or calls ``basis-core`` and never evaluates locally.
  - The gateway derives subject identity from the verified Bearer token; the
    console never sends caller-supplied subject fields to ``/v1/evaluate`` or
    ``/v1/evaluate/operation-aware``.
  - Network failures are turned into status values, never raised into UI routes.
  - The console never falls back to local authorization behavior when the
    gateway is unreachable, and never reinterprets a gateway decision.
"""

from basis_console.gateway.client import GatewayClient
from basis_console.gateway.models import (
    GatewayEvaluationResult,
    GatewayEvaluationStatus,
    GatewayProbeResult,
    GatewayStatus,
    GatewayStatusReport,
)
from basis_console.gateway.operation_aware_models import (
    OperationAwareDisposition,
    OperationAwareEvaluationRequest,
    OperationAwareEvaluationResponse,
    OperationAwareEvaluationResult,
    OperationAwareEvaluationState,
    OperationAwareEvaluationStatus,
    OperationAwareFailureReason,
    OperationAwareOutcome,
)

__all__ = [
    "GatewayClient",
    "GatewayEvaluationResult",
    "GatewayEvaluationStatus",
    "GatewayProbeResult",
    "GatewayStatus",
    "GatewayStatusReport",
    "OperationAwareDisposition",
    "OperationAwareEvaluationRequest",
    "OperationAwareEvaluationResponse",
    "OperationAwareEvaluationResult",
    "OperationAwareEvaluationState",
    "OperationAwareEvaluationStatus",
    "OperationAwareFailureReason",
    "OperationAwareOutcome",
]
