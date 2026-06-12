"""basis-console — human-facing operational interface for the BASIS ecosystem.

Phase 1 is a read-only console skeleton. It renders policy, decision-simulation,
and audit views, and it does NOT evaluate authorization, authenticate users, or
talk directly to basis-core. See ``docs/architecture.md`` for the boundaries the
console must preserve.
"""

__version__ = "0.1.0"
