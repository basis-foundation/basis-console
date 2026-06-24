"""Defensive redaction helpers for gateway diagnostics display.

The console renders raw gateway responses and selected headers for operational
debugging. Those payloads should never contain credentials, but the console
redacts known-sensitive keys **defensively** before anything is captured on a
result object or rendered, so a future gateway change (or a misconfigured proxy
echoing a header) can never leak a secret through the diagnostics view.

This is display hygiene, not security enforcement: the console holds no secrets
of its own beyond the operator-configured Bearer token, which it never sends to
``/health`` or ``/ready`` and never stores on a diagnostics result.
"""

from __future__ import annotations

from typing import Any

# Placeholder shown in place of any redacted value.
REDACTED = "[redacted]"

# Lowercased substrings that mark a header name or JSON key as sensitive. Matched
# as substrings (not exact keys) so variants like ``x-access-token`` or
# ``client_secret_id`` are still caught. Ordinary diagnostic fields
# (``correlation_id``, ``policy_version``, ``status``) contain none of these.
SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "authorization",
    "access_token",
    "refresh_token",
    "id_token",
    "client_secret",
    "password",
    "secret",
    "cookie",
    "bearer",
    "api_key",
    "apikey",
    "token",
)


def is_sensitive_key(key: str) -> bool:
    """True when ``key`` looks like it could carry a credential."""
    lowered = key.lower()
    return any(fragment in lowered for fragment in SENSITIVE_KEY_FRAGMENTS)


def redact_headers(headers: Any) -> dict[str, str]:
    """Return a lowercased header mapping with sensitive values redacted.

    Accepts anything iterable as ``(key, value)`` pairs (e.g. an ``httpx.Headers``
    object via ``.items()``). The Bearer token is a *request* header and is never
    sent to the probed endpoints, but ``authorization`` / ``set-cookie`` and
    friends are redacted regardless so the captured headers are always safe.
    """
    items = headers.items() if hasattr(headers, "items") else headers
    redacted: dict[str, str] = {}
    for key, value in items:
        name = str(key).lower()
        redacted[name] = REDACTED if is_sensitive_key(name) else str(value)
    return redacted


def redact_json(value: Any) -> Any:
    """Recursively redact sensitive keys in a parsed JSON structure.

    Dict keys matching :func:`is_sensitive_key` have their values replaced with
    :data:`REDACTED`; lists and nested dicts are walked. Non-container values are
    returned unchanged. Used before a response body is rendered or stored.
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if is_sensitive_key(str(key)) else redact_json(val))
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [redact_json(item) for item in value]
    return value
