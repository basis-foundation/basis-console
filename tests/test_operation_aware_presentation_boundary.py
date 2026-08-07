"""Architecture-boundary tests for the operation-aware presentation module (PR 3).

Narrow, AST-based checks mirroring ``tests/test_no_basis_core_boundary.py``'s
precedent (the general no-``basis_core``-anywhere-in-``src/`` sweep already
covers this file; these checks are file-scoped and specific to this module's
own invariants): the presentation module never imports the gateway HTTP
client to make calls, never imports console-mode configuration, and never
imports route/template/app modules. Deliberately not a general
dependency-linting framework — see that file's own docstring for the same
disclaimer.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from basis_console.operation_aware_presentation import build_operation_aware_presentation

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "src" / "basis_console" / "operation_aware_presentation.py"

# Module names (or dotted prefixes) this file must never import.
FORBIDDEN_IMPORT_MODULES = {
    "basis_core",
    "httpx",
    "basis_console.config",
    "basis_console.main",
    "basis_console.ui",
    "basis_console.api",
}

# Specific imported names this file must never bring in, even via the
# top-level ``basis_console.gateway`` re-export surface.
FORBIDDEN_IMPORTED_NAMES = {"GatewayClient", "ConsoleConfig", "load_config"}


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


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def test_module_file_exists():
    assert MODULE_PATH.is_file()


def test_no_forbidden_module_imports():
    imported = _imported_module_names(MODULE_PATH)
    forbidden_found = {
        name
        for name in imported
        if any(name == mod or name.startswith(mod + ".") for mod in FORBIDDEN_IMPORT_MODULES)
    }
    assert not forbidden_found, (
        f"operation_aware_presentation.py imports forbidden module(s): {sorted(forbidden_found)}"
    )


def test_no_forbidden_names_imported():
    imported_names = _imported_names(MODULE_PATH)
    forbidden_found = imported_names & FORBIDDEN_IMPORTED_NAMES
    assert not forbidden_found, (
        f"operation_aware_presentation.py imports forbidden name(s): {sorted(forbidden_found)}"
    )


def test_no_route_or_template_directories_imported():
    text = MODULE_PATH.read_text(encoding="utf-8")
    assert "jinja2" not in text
    assert "fastapi" not in text
    assert "APIRouter" not in text


def test_builder_signature_has_no_mode_or_config_parameter():
    params = list(inspect.signature(build_operation_aware_presentation).parameters)
    assert params == ["request", "result"]


def test_module_defines_no_mode_shaped_function_parameter():
    # No function anywhere in the module accepts a console-mode-shaped
    # parameter (by name), not just the public builder checked above. This is
    # an AST check (parameter names in `def` signatures), so a docstring that
    # merely *explains* the absence of a `console_mode` argument (as this
    # module's own docstring does) can never trip it — only a real parameter
    # declaration would.
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"), filename=str(MODULE_PATH))
    forbidden_param_names = {"console_mode", "is_training_mode", "mode"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            arg_names = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
            found = arg_names & forbidden_param_names
            assert not found, f"{node.name} declares forbidden mode-shaped parameter(s): {found}"
