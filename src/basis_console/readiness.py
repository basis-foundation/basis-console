"""Readiness state for basis-console.

Tracks whether the console application is ready to serve its UI. In Phase 1 the
console renders read-only sample data and does not depend on the gateway, so the
only readiness component is ``configuration_loaded``.

This is intentionally separate from ``/health`` (liveness): ``/health`` answers
"is the process up?" while ``/ready`` answers "is the console initialized?".
Later phases may register additional components (e.g. "gateway_reachable") here
without changing the contract — but the console must always degrade gracefully
and must never substitute local authorization logic for a missing gateway.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class ReadinessState:
    """Thread-safe multi-component readiness tracker."""

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _components: dict[str, bool] = field(default_factory=dict)
    _reasons: dict[str, str] = field(default_factory=dict)

    def mark_ready(self, component: str = "app") -> None:
        with self._lock:
            self._components[component] = True
            self._reasons.pop(component, None)

    def mark_not_ready(
        self,
        reason: str = "application not initialized",
        component: str = "app",
    ) -> None:
        with self._lock:
            self._components[component] = False
            self._reasons[component] = reason

    @property
    def is_ready(self) -> bool:
        """True only when all registered components are ready."""
        with self._lock:
            if not self._components:
                return False
            return all(self._components.values())

    @property
    def reason(self) -> str:
        """Human-readable reason for the first not-ready component, else ''."""
        with self._lock:
            for component, ready in self._components.items():
                if not ready:
                    return self._reasons.get(component, f"{component} not ready")
            return ""

    @property
    def components(self) -> dict[str, bool]:
        """Snapshot of current component readiness states."""
        with self._lock:
            return dict(self._components)


# Module-level singleton shared by the FastAPI app and tests.
_state = ReadinessState()


def get_readiness_state() -> ReadinessState:
    return _state


def reset_readiness_state() -> None:
    """Reset to a clean not-ready state. For tests only."""
    with _state._lock:
        _state._components.clear()
        _state._reasons.clear()
