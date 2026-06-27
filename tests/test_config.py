"""Tests for configuration loading (config.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from basis_console.config import ConsoleConfig


def test_default_config_loads():
    config = ConsoleConfig()
    assert config.service_name == "basis-console"
    assert config.host == "127.0.0.1"
    assert config.port == 8080
    assert config.log_level == "INFO"
    assert config.environment == "local"
    # Gateway base URL is optional and unset by default (no public URL baked in).
    assert config.gateway_base_url is None
    # Timeout has a safe non-zero default.
    assert config.gateway_timeout_seconds == 2.0


def test_gateway_timeout_override(monkeypatch):
    monkeypatch.setenv("GATEWAY_TIMEOUT_SECONDS", "5.5")
    config = ConsoleConfig()
    assert config.gateway_timeout_seconds == 5.5


def test_gateway_timeout_must_be_positive(monkeypatch):
    monkeypatch.setenv("GATEWAY_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError):
        ConsoleConfig()


def test_env_override_host_and_port(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "9090")
    config = ConsoleConfig()
    assert config.host == "0.0.0.0"
    assert config.port == 9090


def test_env_override_gateway_base_url(monkeypatch):
    monkeypatch.setenv("GATEWAY_BASE_URL", "https://gw.internal.example:8443")
    config = ConsoleConfig()
    assert config.gateway_base_url == "https://gw.internal.example:8443"


def test_log_level_is_normalized(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")
    config = ConsoleConfig()
    assert config.log_level == "DEBUG"


def test_invalid_log_level_rejected(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError):
        ConsoleConfig()


def test_invalid_port_rejected(monkeypatch):
    monkeypatch.setenv("PORT", "70000")
    with pytest.raises(ValidationError):
        ConsoleConfig()


# ── Presentation mode (BASIS_CONSOLE_MODE) ──────────────────────────────────


def test_default_mode_is_operator():
    config = ConsoleConfig()
    assert config.basis_console_mode == "operator"
    assert config.operator_mode is True
    assert config.training_mode is False


def test_training_mode_config(monkeypatch):
    monkeypatch.setenv("BASIS_CONSOLE_MODE", "training")
    config = ConsoleConfig()
    assert config.basis_console_mode == "training"
    assert config.training_mode is True
    assert config.operator_mode is False


def test_mode_is_normalized(monkeypatch):
    monkeypatch.setenv("BASIS_CONSOLE_MODE", "  Training  ")
    config = ConsoleConfig()
    assert config.basis_console_mode == "training"


def test_invalid_mode_rejected(monkeypatch):
    monkeypatch.setenv("BASIS_CONSOLE_MODE", "bogus")
    with pytest.raises(ValidationError) as excinfo:
        ConsoleConfig()
    # The error is helpful: it names the variable and the allowed values.
    message = str(excinfo.value)
    assert "BASIS_CONSOLE_MODE" in message
    assert "operator" in message and "training" in message
