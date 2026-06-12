"""Gateway client abstraction for basis-console.

This package is the console's single point of contact with ``basis-gateway``.
In Phase 2 it does exactly one thing: probe the gateway's operational endpoints
(``/health`` and ``/ready``) and report a typed connection status. It does NOT
consume policy, audit, or evaluation APIs — those are future work and the
gateway does not yet expose console-facing variants of them.

Invariants:
  - The console reaches the authorization system only through the gateway; this
    module never imports or calls ``basis-core``.
  - Network failures are turned into status values, never raised into UI routes.
  - The console never falls back to local authorization behavior when the
    gateway is unreachable.
"""

from basis_console.gateway.client import GatewayClient
from basis_console.gateway.models import GatewayStatus, GatewayStatusReport

__all__ = ["GatewayClient", "GatewayStatus", "GatewayStatusReport"]
