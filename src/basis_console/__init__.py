"""basis-console — human-facing operational interface for the BASIS ecosystem.

The console is read-oriented and gateway-first: it observes, inspects, and
submits requests through `basis-gateway` for both the legacy and
operation-aware evaluation contracts, and explains the result. It does NOT
evaluate authorization, authenticate users, or talk directly to basis-core.
See ``docs/architecture.md`` for the boundaries the console must preserve.
"""

__version__ = "0.2.0"
