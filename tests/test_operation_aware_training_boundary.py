"""Architecture-boundary tests for operation-aware Training-mode enrichment (PR 5).

Mirrors the discipline of ``test_no_basis_core_boundary.py``,
``test_operation_aware_presentation_boundary.py``, and
``test_operation_aware_route_boundary.py``: narrow, mechanical, AST/text
checks for exactly the invariants PR 5 must not violate — not a general
dependency-linting framework.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi.routing import APIRoute

from basis_console.ui.views import router as ui_router

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "src" / "basis_console" / "operation_aware_training.py"
PARTIAL_PATH = (
    REPO_ROOT
    / "src"
    / "basis_console"
    / "ui"
    / "templates"
    / "partials"
    / "operation_aware_training.html"
)
VIEWS_PATH = REPO_ROOT / "src" / "basis_console" / "ui" / "views.py"
SIMULATE_TEMPLATE_PATH = REPO_ROOT / "src" / "basis_console" / "ui" / "templates" / "simulate.html"

FORBIDDEN_IMPORT_MODULES = {
    "basis_core",
    "httpx",
    "fastapi",
    "jinja2",
    "basis_console.config",
    "basis_console.gateway.client",
    "basis_console.main",
    "basis_console.ui",
}


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
    return names


def test_module_and_partial_files_exist():
    assert MODULE_PATH.is_file()
    assert PARTIAL_PATH.is_file()


# ---------------------------------------------------------------------------
# Python module boundary
# ---------------------------------------------------------------------------


def test_training_module_has_no_forbidden_imports():
    imported = _imported_module_names(MODULE_PATH)
    forbidden_found = {
        name
        for name in imported
        if any(name == mod or name.startswith(mod + ".") for mod in FORBIDDEN_IMPORT_MODULES)
    }
    assert not forbidden_found, (
        f"operation_aware_training.py imports forbidden module(s): {sorted(forbidden_found)}"
    )


def test_training_module_declares_no_functions():
    """The module is pure static data — nothing computes content from an argument."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
    assert functions == [], f"unexpected function definitions: {[f.name for f in functions]}"


def test_training_module_performs_no_io_or_config_access():
    text = MODULE_PATH.read_text(encoding="utf-8")
    for forbidden_token in (
        "requests.",
        "httpx.",
        "os.environ",
        "getenv",
        "open(",
        "socket.",
        "GATEWAY_BEARER_TOKEN",
    ):
        assert forbidden_token not in text


# ---------------------------------------------------------------------------
# Template boundary
# ---------------------------------------------------------------------------


def test_partial_never_references_tokens_or_configuration():
    text = PARTIAL_PATH.read_text(encoding="utf-8")
    for forbidden in (
        "GATEWAY_BEARER_TOKEN",
        "bearer_token",
        "Authorization:",
        "Authorization header",
        "config.",
    ):
        assert forbidden not in text


def test_partial_never_references_basis_core():
    text = PARTIAL_PATH.read_text(encoding="utf-8")
    assert "basis_core" not in text


def test_partial_never_calls_the_gateway_or_a_second_client_method():
    text = PARTIAL_PATH.read_text(encoding="utf-8")
    assert "GatewayClient" not in text
    assert "evaluate_operation_aware(" not in text
    assert "evaluate(" not in text


def test_partial_does_not_reconstruct_outcome_disposition_or_failure_reason_logic():
    """The partial selects labels/layout by lookup only — it never recomputes
    kernel/gateway semantics via a literal comparison, matching the same
    discipline ``test_operation_aware_route_boundary.py`` enforces for
    ``simulate.html`` itself.
    """
    text = PARTIAL_PATH.read_text(encoding="utf-8")
    forbidden_fragments = (
        'outcome.value == "allow"',
        "outcome.value == 'allow'",
        'outcome.value == "deny"',
        "outcome.value == 'deny'",
        'outcome.value == "not_applicable"',
        "outcome.value == 'not_applicable'",
        'disposition.value == "allow"',
        "disposition.value == 'allow'",
        'disposition.value == "deny"',
        "disposition.value == 'deny'",
        'failure_reason.value == "',
        "failure_reason.value == '",
    )
    for forbidden in forbidden_fragments:
        assert forbidden not in text, f"found forbidden comparison: {forbidden}"


def test_partial_requires_no_javascript_to_render_content():
    text = PARTIAL_PATH.read_text(encoding="utf-8")
    assert "<script" not in text


def test_partial_uses_semantic_disclosure_and_table_headers():
    text = PARTIAL_PATH.read_text(encoding="utf-8")
    assert "<details" in text
    assert "<summary>" in text
    assert '<th scope="col">' in text


# ---------------------------------------------------------------------------
# Route/wiring boundary
# ---------------------------------------------------------------------------


def test_only_one_post_simulate_route_exists():
    """No separate Training-only route was introduced by PR 5."""
    post_simulate_routes = [
        route
        for route in ui_router.routes
        if isinstance(route, APIRoute)
        and route.path == "/simulate"
        and route.methods is not None
        and "POST" in route.methods
    ]
    assert len(post_simulate_routes) == 1


def test_views_module_calls_evaluate_operation_aware_exactly_once():
    """Exactly one real call site, ignoring docstring/comment mentions."""
    tree = ast.parse(VIEWS_PATH.read_text(encoding="utf-8"), filename=str(VIEWS_PATH))
    call_sites = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "evaluate_operation_aware"
    ]
    assert len(call_sites) == 1


def test_views_module_attaches_training_content_as_a_static_constant():
    """`oa_training` must be the same static object on every request — never
    built per-request from console mode, request content, or a response.
    """
    text = VIEWS_PATH.read_text(encoding="utf-8")
    assert 'ctx["oa_training"] = OA_TRAINING_CONTENT' in text


def test_views_module_does_not_construct_training_content_conditionally():
    """The context attachment must not be guarded by an is_training_mode/
    console_mode check in views.py — the template's own gate is the only
    place mode decides whether this content renders (matching PR3/PR4's
    established mode-independence discipline).
    """
    text = VIEWS_PATH.read_text(encoding="utf-8")
    assign_index = text.index('ctx["oa_training"] = OA_TRAINING_CONTENT')
    preceding_code_lines = [
        line
        for line in text[:assign_index].splitlines()[-6:]
        if line.strip() and not line.strip().startswith("#")
    ][-3:]
    for line in preceding_code_lines:
        assert "is_training_mode" not in line
        assert "console_mode" not in line


def test_simulate_template_includes_the_training_partial_only_inside_operation_aware_section():
    text = SIMULATE_TEMPLATE_PATH.read_text(encoding="utf-8")
    include_marker = '{% include "partials/operation_aware_training.html" %}'
    assert include_marker in text
    before_include = text[: text.index(include_marker)]
    # The nearest enclosing evaluation_type check before the include must be
    # the operation_aware branch, not the legacy one.
    last_if_oa = before_include.rfind('evaluation_type == "operation_aware"')
    last_if_legacy_section = before_include.rfind('evaluation_type == "legacy" and preview_json')
    assert last_if_oa > last_if_legacy_section
