"""Architecture-boundary test: basis-console never imports or depends on basis-core.

This is the first runtime operation-aware code in basis-console (Phase 16 —
the new ``GatewayClient.evaluate_operation_aware()`` capability). Per
``docs/architecture.md``'s "Gateway-first integration rule" and the
operation-aware console integration plan's §3 ("the console must never import
``basis-core``, or any ``basis_core.*`` symbol, directly"), that invariant was
previously enforced only by ``pyproject.toml``'s dependency list and code
review (see that plan's §15). This adds a narrow, mechanical check alongside
the new gateway-client code, mirroring the AST-based boundary test precedent
in ``basis-identity`` (``tests/test_release_boundaries.py``).

Deliberately narrow: this checks exactly one thing (no ``basis_core`` import
anywhere in ``src/``, and no ``basis-core`` dependency in ``pyproject.toml``),
not a general dependency-linting framework. Built on ``ast.parse``/``ast.walk``
rather than text search so a docstring or comment that merely *mentions*
``basis_core`` (as this module's own docstring does) can never trip the check —
only a real ``import``/``from ... import`` statement can.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "basis_console"

FORBIDDEN_TOP_LEVEL_IMPORTS = {"basis_core"}


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _top_level_import_names(path: Path) -> set[str]:
    """Return the top-level package names of every import statement in ``path``.

    Only real ``import x`` / ``from x import y`` statements count — walking
    the AST (not grepping text) means a string or comment that merely mentions
    a package name can never be mistaken for an import.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        # node.level > 0 is a relative import (`from . import x`); it can never
        # resolve to an external package, so only level-0 imports are checked.
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            names.add(node.module.split(".")[0])
    return names


def test_src_files_present_for_boundary_check():
    """Guard against a silent false-pass if the source tree ever moves."""
    files = _python_files(SRC_ROOT)
    assert len(files) > 10, "expected basis_console source files under src/basis_console"


def _src_python_files() -> list[Path]:
    return _python_files(SRC_ROOT)


@pytest.mark.parametrize("path", _src_python_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_basis_core_import(path: Path):
    imported = _top_level_import_names(path)
    forbidden_found = imported & FORBIDDEN_TOP_LEVEL_IMPORTS
    assert not forbidden_found, (
        f"{path.relative_to(REPO_ROOT)} imports {sorted(forbidden_found)} — "
        "basis-console must never import basis-core (docs/architecture.md, "
        "'Gateway-first integration rule')"
    )


def test_no_basis_core_dependency_in_pyproject():
    """No dependency line anywhere in pyproject.toml names basis-core.

    Deliberately not a full TOML parse: the repository's minimum supported
    Python is 3.10 (``requires-python = ">=3.10"``), and ``tomllib`` is
    stdlib only from 3.11 — pulling in a third-party TOML parser solely for
    this one narrow check would be exactly the kind of unjustified new
    dependency this PR must avoid. A plain substring check is unambiguous
    here: ``basis-core``/``basis_core`` do not otherwise appear anywhere in
    this file (verified by direct inspection), so their presence at all would
    mean a dependency (or dependency-adjacent reference) was added.
    """
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "basis-core" not in text
    assert "basis_core" not in text
