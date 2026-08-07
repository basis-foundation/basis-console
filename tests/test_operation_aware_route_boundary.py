"""Narrow architecture-boundary tests for the PR 4 route/template integration.

Mirrors the discipline of ``test_no_basis_core_boundary.py`` and
``test_operation_aware_presentation_boundary.py``: small, mechanical,
AST/text-based checks for exactly the invariants PR 4 must not violate — not a
general dependency-linting framework.

The repository-wide ``test_no_basis_core_boundary.py`` sweep already covers
every file changed by this PR (``ui/views.py``, ``simulator.py``) for the
"never import basis_core" invariant, so it is not re-asserted here.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

from basis_console.ui.views import router as ui_router

REPO_ROOT = Path(__file__).resolve().parent.parent
VIEWS_PATH = REPO_ROOT / "src" / "basis_console" / "ui" / "views.py"
SIMULATE_TEMPLATE_PATH = REPO_ROOT / "src" / "basis_console" / "ui" / "templates" / "simulate.html"


def test_only_one_post_simulate_route_exists():
    """No separate Operator/Training operation-aware route was introduced."""
    post_simulate_routes = [
        route
        for route in ui_router.routes
        if isinstance(route, APIRoute)
        and route.path == "/simulate"
        and route.methods is not None
        and "POST" in route.methods
    ]
    assert len(post_simulate_routes) == 1


def test_route_module_does_not_call_response_json_for_operation_aware():
    """The route never parses raw gateway JSON itself for the OA path.

    ``GatewayClient.evaluate_operation_aware()`` already returns a fully
    parsed, typed ``OperationAwareEvaluationResult``; the route must consume
    it (and ``build_operation_aware_presentation()``) rather than calling
    ``.json()`` on a raw HTTP response or importing the private
    ``_parse_operation_aware_response`` parser.
    """
    text = VIEWS_PATH.read_text(encoding="utf-8")
    assert "_parse_operation_aware_response" not in text
    assert "_OperationAwareContractError" not in text
    assert ".json()" not in text


def test_route_module_does_not_import_httpx_response_types():
    """The route talks to GatewayClient only, never httpx directly."""
    tree = ast.parse(VIEWS_PATH.read_text(encoding="utf-8"), filename=str(VIEWS_PATH))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert "httpx" not in imported


def test_route_calls_evaluate_operation_aware_and_shared_presentation_builder():
    text = VIEWS_PATH.read_text(encoding="utf-8")
    assert "evaluate_operation_aware(" in text
    assert "build_operation_aware_presentation(" in text


def test_route_never_constructs_operation_aware_evaluation_response_directly():
    """The route never fabricates a governed response object itself."""
    text = VIEWS_PATH.read_text(encoding="utf-8")
    assert "OperationAwareEvaluationResponse(" not in text


def test_template_does_not_reconstruct_outcome_or_disposition_logic():
    """The template selects labels/layout only — it never recomputes semantics.

    Concretely: it must never compare a raw string literal against
    ``outcome``/``disposition``/``failure_reason`` to decide what to render —
    those decisions belong to ``operation_aware_presentation.py`` and are
    consumed here only via the already-built ``PresentationContentItem``
    fields (``.value``/``.present``/``.applicable``).
    """
    text = SIMULATE_TEMPLATE_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "outcome == 'allow'",
        'outcome == "allow"',
        "outcome == 'deny'",
        'outcome == "deny"',
        "outcome == 'not_applicable'",
        'outcome == "not_applicable"',
        "disposition == 'deny'",
        'disposition == "deny"',
    ):
        assert forbidden not in text


def test_template_never_imports_or_references_basis_core():
    text = SIMULATE_TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "basis_core" not in text
