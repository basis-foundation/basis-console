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
    # No hardcoded public URL — defaults to a local gateway address.
    assert config.gateway_base_url == "http://localhost:8000"


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
