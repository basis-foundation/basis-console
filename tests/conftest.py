"""Shared pytest fixtures for basis-console tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from basis_console.main import create_app
from basis_console.readiness import reset_readiness_state


@pytest.fixture()
def app():
    reset_readiness_state()
    return create_app()


@pytest.fixture()
def client(app) -> Iterator[TestClient]:
    # The context manager runs the lifespan, which loads config and marks
    # the console ready.
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
