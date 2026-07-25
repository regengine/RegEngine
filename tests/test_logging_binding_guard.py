"""Guard: no structlog-style kwargs on stdlib logging.Logger bindings.

Context: modules in services/shared/request_workflow bound
``logging.getLogger(...)`` but every call site used structlog-style event
kwargs (``logger.warning("deadline_overdue", tenant_id=...)``). The stdlib
Logger rejects arbitrary kwargs, so each call raised ``TypeError`` at
runtime — on the FDA request deadline path, exactly when a case went
overdue. The same defect previously shipped in
services/ingestion/app/sandbox/router.py (see
services/ingestion/tests/test_sandbox_share_router.py), where the
TypeError masked an intended 503 as a 500. Two independent instances make
this a defect class, so this guard bans the pattern repo-wide: a module
must either bind ``structlog.get_logger`` or restrict itself to
stdlib-legal call signatures.

Static AST scan; no DB, no network, no imports of scanned modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = ("services", "regengine", "server", "cli", "scripts")
EXCLUDE_PARTS = {"venv", ".venv", "node_modules", "__pycache__", ".claude", "_archive"}
LOG_METHODS = {"debug", "info", "warning", "error", "critical", "exception", "log"}
# Keywords the stdlib Logger legitimately accepts.
STDLIB_LEGAL_KWARGS = {"exc_info", "stack_info", "stacklevel", "extra"}


def _stdlib_logger_names(tree: ast.Module) -> set[str]:
    """Names bound at module level via ``NAME = logging.getLogger(...)``."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)):
            continue
        func = call.func
        if (
            isinstance(func.value, ast.Name)
            and func.value.id == "logging"
            and func.attr == "getLogger"
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _violations_in(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    logger_names = _stdlib_logger_names(tree)
    if not logger_names:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        func = node.func
        if not (
            isinstance(func.value, ast.Name)
            and func.value.id in logger_names
            and func.attr in LOG_METHODS
        ):
            continue
        illegal = [
            kw.arg
            for kw in node.keywords
            if kw.arg is not None and kw.arg not in STDLIB_LEGAL_KWARGS
        ]
        if illegal:
            found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} kwargs={illegal}")
    return found


def test_no_structlog_kwargs_on_stdlib_loggers() -> None:
    violations: list[str] = []
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if EXCLUDE_PARTS.intersection(path.parts):
                continue
            violations.extend(_violations_in(path))
    assert not violations, (
        "stdlib logging.Logger called with structlog-style kwargs — these "
        "raise TypeError at runtime. Bind structlog.get_logger() instead "
        "(see services/shared/request_workflow):\n" + "\n".join(violations)
    )
